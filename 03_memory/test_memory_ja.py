"""
AgentCore Memoryを使用したAWSコスト見積もりエージェント

この実装はAgentCore Memoryの機能を実演します:
1. 短期メモリ（イベント）: セッション内で会話履歴を保存・取得
2. 長期メモリ（好み）: 時間経過とともにユーザーの好みを自動抽出
3. 比較: 短期メモリを使用して複数の見積もりを並べて比較
4. パーソナライゼーション: 長期メモリを使用してパーソナライズされた推奨を提供

01_code_interpreterの同じAWSCostEstimatorAgentをシンプルなアーキテクチャ説明と共に使用し、
実際のエンドツーエンドのメモリ統合を実演します。
"""

import sys
import os
import time
import logging
import traceback
import argparse
import json
import boto3
from datetime import datetime
from strands import Agent, tool
from bedrock_agentcore.memory.client import MemoryClient

# 01_code_interpreterからインポートするために親ディレクトリをパスに追加
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "01_code_interpreter"))
from cost_estimator_agent.cost_estimator_agent import AWSCostEstimatorAgent  # noqa: E402

# デバッグとモニタリング用のロギングを設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Prompt Templates
SYSTEM_PROMPT = """あなたはメモリ機能を持つAWSコスト見積もりエージェントです。

以下の機能でユーザーをサポートできます:
1. estimate: AWSアーキテクチャのコストを計算
2. compare: 複数のコスト見積もりを並べて比較
3. propose: ユーザーの好みと履歴に基づいて最適なアーキテクチャを推奨

常に詳細な説明を提供し、推奨を行う際にはユーザーの過去の好みを考慮してください。"""

COMPARISON_PROMPT_TEMPLATE = """以下のAWSコスト見積もりを比較し、インサイトを提供してください:

ユーザーリクエスト: {request}

見積もり:
{estimates}

以下を提供してください:
1. 各見積もりの概要
2. アーキテクチャ間の主な違い
3. コスト比較のインサイト
4. 比較に基づく推奨事項
"""

PROPOSAL_PROMPT_TEMPLATE = """以下に基づいてAWSアーキテクチャの提案を生成してください:

ユーザー要件: {requirements}

過去の好みとパターン:
{historical_data}

以下を提供してください:
1. 推奨アーキテクチャの概要
2. 主要なコンポーネントとサービス
3. 推定コスト（概算）
4. スケーラビリティの考慮事項
5. セキュリティのベストプラクティス
6. コスト最適化の推奨事項

利用可能な過去の好みに基づいて、提案をパーソナライズしてください。
"""


class AgentWithMemory:
    """
    AgentCore Memory機能で強化されたAWSコスト見積もりエージェント
    
    このクラスは、コスト見積もりと比較機能を通じて、
    短期メモリと長期メモリの実用的な違いを実演します:
    
    - 短期メモリ: セッション内で見積もりを保存し、即座に比較
    - 長期メモリ: 時間経過とともにユーザーの好みと意思決定パターンを学習
    """
    
    def __init__(self, actor_id: str, region: str = "", force_recreate: bool = False):
        """
        メモリ機能を持つエージェントを初期化
        
        Args:
            actor_id: ユーザー/アクターの一意識別子（メモリ名前空間に使用）
            region: AgentCoreサービス用のAWSリージョン
            force_recreate: Trueの場合、既存のメモリを削除して新規作成
        """
        self.actor_id = actor_id
        self.region = region
        if not self.region:
            # Use default region from boto3 session if not specified
            self.region = boto3.Session().region_name
        self.force_recreate = force_recreate
        self.memory_id = None
        self.memory = None
        self.memory_client = None
        self.agent = None
        self.bedrock_runtime = None
        self.session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        logger.info(f"Initializing AgentWithMemory for actor: {actor_id}")
        if force_recreate:
            logger.info("🔄 Force recreate mode enabled - will delete existing memory")
        
        # ユーザー好み戦略でAgentCore Memoryを初期化
        try:
            logger.info("Initializing AgentCore Memory...")
            self.memory_client = MemoryClient(region_name=self.region)
            
            # メモリが既に存在するか確認
            memory_name = "cost_estimator_memory"
            existing_memories = self.memory_client.list_memories()
            existing_memory = None
            for memory in existing_memories:
                if memory.get('memoryId').startswith(memory_name):
                    existing_memory = memory
                    break

            if existing_memory:
                if not force_recreate:
                    # 既存のメモリを再利用（デフォルト動作）
                    self.memory_id = existing_memory.get('id')
                    self.memory = existing_memory
                    logger.info(f"🔄 Reusing existing memory: {memory_name} (ID: {self.memory_id})")
                    logger.info("✅ Memory reuse successful - skipping creation time!")
                else:            
                    # force_recreateがTrueの場合は既存のメモリを削除
                    memory_id_to_delete = existing_memory.get('id')
                    logger.info(f"🗑️ Force deleting existing memory: {memory_name} (ID: {memory_id_to_delete})")
                    self.memory_client.delete_memory_and_wait(memory_id_to_delete, max_wait=300)
                    logger.info("✅ Existing memory deleted successfully")
                    existing_memory = None

            if existing_memory is None:
                # 新しいメモリを作成
                logger.info("Creating new AgentCore Memory...")
                self.memory = self.memory_client.create_memory_and_wait(
                    name=memory_name,
                    strategies=[{
                        "userPreferenceMemoryStrategy": {
                            "name": "UserPreferenceExtractor",
                            "description": "Extracts user preferences for AWS architecture decisions",
                            "namespaces": [f"/preferences/{self.actor_id}"]
                        }
                    }],
                    event_expiry_days=7,  # 許可される最小値
                )
                self.memory_id = self.memory.get('memoryId')
                logger.info(f"✅ AgentCore Memory created successfully with ID: {self.memory_id}")

            # AI駆動機能用のBedrock Runtimeクライアントを初期化
            self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
            logger.info("✅ Bedrock Runtime client initialized")
            
            # コスト見積もりツールとコールバックハンドラーでエージェントを作成
            self.agent = Agent(
                tools=[self.estimate, self.compare, self.propose],
                system_prompt=SYSTEM_PROMPT
            )
            
        except Exception as e:
            logger.exception(f"❌ Failed to initialize AgentWithMemory: {e}")

    def __enter__(self):
        """コンテキストマネージャーのエントリー"""
        return self.agent

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了 - デバッグのためデフォルトでメモリを保持"""
        # デバッグを高速化するため、デフォルトでメモリを保持
        # 必要に応じて--forceを使用してメモリを再作成
        try:
            if self.memory_client and self.memory_id:
                logger.info("🧹 Memory preserved for reuse (use --force to recreate)")
                logger.info("✅ Context manager exit completed")
        except Exception as e:
            logger.warning(f"⚠️ Error in context manager exit: {e}")

    def list_memory_events(self, max_results: int = 10):
        """デバッグ用にメモリイベントを検査するヘルパーメソッド"""
        try:
            if not self.memory_client or not self.memory_id:
                return "❌ Memory not available"
            
            events = self.memory_client.list_events(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                max_results=max_results
            )
            
            logger.info(f"📋 Found {len(events)} events in memory")
            for i, event in enumerate(events):
                logger.info(f"Event {i+1}: {json.dumps(event, indent=2, default=str)}")
            
            return events
        except Exception as e:
            logger.error(f"❌ Failed to list events: {e}")
            return []

    @tool
    def estimate(self, architecture_description: str) -> str:
        """
        Cost Estimator Agentを使用してAWSアーキテクチャのコストを見積もります。

        Args:
            architecture_description: 見積もり対象のAWSアーキテクチャの説明

        Returns:
            コスト見積もり結果
        """
        try:
            logger.info(f"🔍 Estimating costs for: {architecture_description}")

            # Cost Estimator Agent（Code Interpreter + MCP価格ツール）を使用
            cost_estimator = AWSCostEstimatorAgent(region=self.region)
            result = cost_estimator.estimate_costs(architecture_description)

            # 短期メモリにイベントを保存（create_event）
            # これにより、userPreferenceMemoryStrategyを介して
            # 非同期の長期メモリ抽出もトリガーされます
            logger.info("📝 Storing event to short-term memory...")
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                messages=[
                    (architecture_description, "USER"),
                    (result, "ASSISTANT")
                ]
            )

            logger.info("✅ Cost estimation completed and stored in memory")
            return result

        except Exception as e:
            logger.exception(f"❌ Cost estimation failed: {e}")
            return f"❌ Cost estimation failed: {e}"

    @tool
    def compare(self, request: str = "Compare my recent estimates") -> str:
        """
        メモリから複数のコスト見積もりを比較します
        
        Args:
            request: 比較内容の説明
            
        Returns:
            見積もりの詳細な比較
        """
        logger.info("📊 Retrieving estimates for comparison...")
        
        if not self.memory_client or not self.memory_id:
            return "❌ Memory not available for comparison"
        
        # メモリから最近の見積もりイベントを取得
        events = self.memory_client.list_events(
            memory_id=self.memory_id,
            actor_id=self.actor_id,
            session_id=self.session_id,
            max_results=4
        )
        
        # 見積もりツール呼び出しをフィルタリングして解析
        estimates = []
        for event in events:
            try:
                # ペイロードデータを抽出
                _input = ""
                _output = ""
                for payload in event.get('payload', []):
                    if 'conversational' in payload:
                        _message = payload['conversational']
                        _role = _message.get('role', 'unknown')
                        _content = _message.get('content')["text"]

                        if _role == 'USER':
                            _input = _content
                        elif _role == 'ASSISTANT':
                            _output = _content
                    
                    if _input and _output:
                        estimates.append(
                            "\n".join([
                                "## Estimate",
                                f"**Input:**:\n{_input}",
                                f"**Output:**:\n{_output}"
                            ])
                        )
                        _input = ""
                        _output = ""

            except Exception as parse_error:
                logger.warning(f"Failed to parse event: {parse_error}")
                continue
        
        if not estimates:
            raise Exception("ℹ️ No previous estimates found for comparison. Please run some estimates first.") 
        
        # Bedrockを使用して比較を生成
        logger.info(f"🔍 Comparing {len(estimates)} estimates... {estimates}")
        comparison_prompt = COMPARISON_PROMPT_TEMPLATE.format(
            request=request,
            estimates="\n\n".join(estimates)
        )
        
        comparison_result = self._generate_with_bedrock(comparison_prompt)
        
        logger.info(f"✅ Comparison completed for {len(estimates)} estimates")
        return comparison_result

    @tool
    def propose(self, requirements: str) -> str:
        """
        ユーザーの好みと履歴に基づいて最適なアーキテクチャを提案します

        Args:
            requirements: アーキテクチャのユーザー要件

        Returns:
            パーソナライズされたアーキテクチャの推奨事項
        """
        try:
            logger.info("💡 Generating architecture proposal based on user history...")

            if not self.memory_client or not self.memory_id:
                return "❌ Memory not available for personalized recommendations"

            # 長期メモリの抽出は非同期です。
            # 結果が表示されるまで（またはタイムアウトまで）retrieve_memories()をポーリングします。
            # https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-saving-and-retrieving-insights.html
            namespace = f"/preferences/{self.actor_id}"
            query = f"User preferences and decision patterns for: {requirements}"
            memories = []
            max_wait, poll_interval = 60, 5
            elapsed = 0
            while elapsed < max_wait:
                memories = self.memory_client.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=namespace,
                    query=query,
                    top_k=3
                )
                if memories:
                    break
                logger.info(f"⏳ Waiting for memory extraction... ({elapsed}s/{max_wait}s)")
                time.sleep(poll_interval)
                elapsed += poll_interval

            if not memories:
                logger.warning(
                    "⚠️ No long-term memories found after %ds — extraction may still be in progress",
                    max_wait,
                )

            contents = [memory.get('content', {}).get('text', '') for memory in memories]
            logger.info(f"📋 Retrieved {len(memories)} long-term memories after {elapsed}s")

            # Bedrockを使用して提案を生成
            logger.info(f"🔍 Generating proposal with requirements: {requirements}")
            proposal_prompt = PROPOSAL_PROMPT_TEMPLATE.format(
                requirements=requirements,
                historical_data="\n".join(contents) if memories else "No historical data available"
            )

            proposal = self._generate_with_bedrock(proposal_prompt)

            logger.info("✅ Architecture proposal generated")
            return proposal

        except Exception as e:
            logger.exception(f"❌ Proposal generation failed: {e}")
            return f"❌ Proposal generation failed: {e}"

    def _generate_with_bedrock(self, prompt: str) -> str:
        """
        Amazon Bedrock Converse APIを使用してコンテンツを生成
        
        Args:
            prompt: Bedrockに送信するプロンプト
            
        Returns:
            Bedrockから生成されたコンテンツ
        """
        try:
            # 高速でコスト効率の良い生成のためにClaude Sonnet 4を使用
            model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
            
            # メッセージを準備
            messages = [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ]
            
            # Converse APIを使用してモデルを呼び出し
            response = self.bedrock_runtime.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={
                    "maxTokens": 4000,
                    "temperature": 0.9
                }
            )
            
            # レスポンステキストを抽出
            output_message = response['output']['message']
            generated_text = output_message['content'][0]['text']
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Bedrock generation failed: {e}")
            # Bedrockが失敗した場合はシンプルなレスポンスにフォールバック
            return f"⚠️ AI generation failed. Error: {str(e)}"


def main():
    parser = argparse.ArgumentParser(
        description="AWS Cost Estimator Agent with AgentCore Memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_memory.py              # Reuse existing memory (fast debugging)
  python test_memory.py --force      # Force recreate memory (clean start)
        """
    )
    parser.add_argument(
        '--force', 
        action='store_true',
        help='Force delete and recreate memory (slower but clean start)'
    )
    
    args = parser.parse_args()
    
    print("🚀 AWS Cost Estimator Agent with AgentCore Memory")
    print("=" * 60)
    
    if args.force:
        print("🔄 Force mode: Will delete and recreate memory")
    else:
        print("⚡ Fast mode: Will reuse existing memory")
    
    try:
        # Create the memory-enhanced agent
        memory_agent = AgentWithMemory(actor_id="user123", force_recreate=args.force)

        with memory_agent as agent:
            # --- ステップ1: 短期メモリ（create_event） ---
            # コスト見積もりを短期メモリにイベントとして保存。
            # 各create_eventは非同期の長期抽出もトリガーします。
            print("\n📝 Step 1: Generating cost estimates (stored as short-term memory)...")

            architectures = [
                "1 EC2 t3.nano instance",
                "1 EC2 t3.micro instance with 20GB gp3 EBS",
            ]

            for i, architecture in enumerate(architectures, 1):
                print(f"\n--- Estimate #{i} ---")
                result = agent(f"Please estimate: {architecture}")
                result_text = result.message["content"] if result.message else ""
                print(f"Result: {result_text[:300]}..." if len(result_text) > 300 else f"Result: {result_text}")

            # --- ステップ2: 短期メモリ（list_events） ---
            # 保存されたイベントを取得し、見積もりを並べて比較。
            print("\n" + "=" * 60)
            print("📊 Step 2: Comparing estimates using short-term memory (list_events)...")
            comparison = agent("Compare the estimates I just generated")
            print(comparison)

            # --- ステップ3: 長期メモリ（retrieve_memories） ---
            # 抽出された好みを使用してパーソナライズされたアーキテクチャ提案を生成。
            print("\n" + "=" * 60)
            print("💡 Step 3: Generating proposal using long-term memory (retrieve_memories)...")
            proposal = agent("Propose the best architecture based on my preferences")
            print(proposal)

    except Exception as e:
        logger.exception(f"❌ Demo failed: {e}")
        print(f"\n❌ Demo failed: {e}")
        print(f"Stacktrace:\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
