"""
AgentCore GatewayでCedarベースのポリシー適用をテスト

スコープベースのアクセス制御を実演:
- Manager: トークンにmanagerスコープが含まれる → Cedarのpermitが一致 → メール送信可能
- Developer: トークンにmanagerスコープがない → 一致するpermitなし → メールツールが非表示

使用方法:
    uv run python 08_policy/test_policy.py --role manager --address you@example.com
    uv run python 08_policy/test_policy.py --role developer --address you@example.com
    uv run python 08_policy/test_policy.py --role both --address you@example.com
"""

import json
import os
import sys
import logging
import argparse
import boto3
import requests
from strands import Agent
from strands import tool
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console
from rich.panel import Panel
from pathlib import Path

# ロギングを設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 01_code_interpreterからインポートするために親ディレクトリをパスに追加
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "01_code_interpreter"))
from cost_estimator_agent.cost_estimator_agent import AWSCostEstimatorAgent  # noqa: E402

POLICY_CONFIG_FILE = Path("policy_config.json")
GATEWAY_CONFIG_FILE = Path("../07_gateway/outbound_gateway.json")


@tool(name="cost_estimator_tool", description="アーキテクチャの説明からAWSのコストを見積もります")
def cost_estimator_tool(architecture_description: str) -> str:
    """ローカルツール: アーキテクチャの説明からAWSコストを見積もります。"""
    region = boto3.Session().region_name
    cost_estimator = AWSCostEstimatorAgent(region=region)
    logger.info("Estimating costs for: %s", architecture_description)
    return cost_estimator.estimate_costs(architecture_description)


def get_token_via_client_credentials(
    token_endpoint: str, client_id: str, client_secret: str, scopes: str
) -> str:
    """Cognito client_credentialsフローを使用してOAuth2アクセストークンを取得"""
    logger.info("Requesting token from %s", token_endpoint)
    response = requests.post(
        token_endpoint,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scopes,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data["access_token"]
    logger.info("Token obtained (scopes: %s)", scopes)
    return access_token


def run_agent_with_role(role: str, architecture: str, address: str, console: Console):
    """特定のロールの認証情報でエージェントを実行"""
    # 設定を読み込み
    with POLICY_CONFIG_FILE.open("r") as f:
        policy_config = json.load(f)
    with GATEWAY_CONFIG_FILE.open("r") as f:
        gateway_config = json.load(f)

    cognito = policy_config["cognito_clients"]
    role_config = cognito[role]
    gateway_url = gateway_config["gateway"]["url"]

    console.print(Panel(
        f"[bold]Role:[/bold] {role.upper()}\n"
        f"[bold]Client ID:[/bold] {role_config['client_id']}\n"
        f"[bold]Scopes:[/bold] {role_config['scopes']}",
        title=f"Testing as {role.upper()}",
    ))

    # このロールのアクセストークンを取得
    access_token = get_token_via_client_credentials(
        token_endpoint=cognito["token_endpoint"],
        client_id=role_config["client_id"],
        client_secret=role_config["client_secret"],
        scopes=role_config["scopes"],
    )

    # ベアラートークンでMCPクライアントを作成
    def create_transport():
        return streamablehttp_client(
            gateway_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    mcp_client = MCPClient(create_transport)

    # ローカル + ゲートウェイツールでエージェントを構築
    tools = [cost_estimator_tool]
    with mcp_client:
        # 全てのゲートウェイツールをページネーション
        more_tools = True
        pagination_token = None
        while more_tools:
            tmp_tools = mcp_client.list_tools_sync(pagination_token=pagination_token)
            tools.extend(tmp_tools)
            if tmp_tools.pagination_token is None:
                more_tools = False
            else:
                pagination_token = tmp_tools.pagination_token

        tool_names = [t.tool_name for t in tools]
        logger.info("Available tools: %s", tool_names)

        # ポリシー効果を表示: このロールにはどのツールが表示されるか？
        # ENFORCEモードでは、未承認のツールはリストから非表示になります
        has_email = any("markdown_to_email" in name for name in tool_names)
        local_tools = [n for n in tool_names if "___" not in n]
        gateway_tools = [n for n in tool_names if "___" in n]

        tool_list = "\n".join(f"  [green]✓[/green] {n}" for n in local_tools)
        if gateway_tools:
            tool_list += "\n" + "\n".join(
                f"  [green]✓[/green] {n}" for n in gateway_tools
            )
        else:
            tool_list += (
                "\n  [yellow]✗ markdown_to_email — hidden by Cedar policy[/yellow]"
            )

        if has_email:
            verdict = "[green bold]PERMITTED[/green bold] — token scope matches Cedar policy"
        else:
            verdict = "[yellow bold]DEFAULT-DENY[/yellow bold] — token scope does not match any permit"

        console.print(Panel(
            f"[bold]Tools visible to {role.upper()}:[/bold]\n"
            f"{tool_list}\n\n"
            f"[bold]Policy decision:[/bold] {verdict}",
            title=f"Policy Effect: {role.upper()}",
        ))

        agent = Agent(
            system_prompt=(
                "あなたはプロフェッショナルなソリューションアーキテクトです。AWSプラットフォームのコストを見積もってください。"
                "1. 顧客の要件を10〜50語で`architecture_description`にまとめてください。"
                "2. `architecture_description`を'cost_estimator_tool'に渡してください。"
                "3. 見積もりを`markdown_to_email`で送信してください。"
            ),
            tools=tools,
        )

        prompt = f"requirements: {architecture}, address: {address}"
        logger.info("Sending prompt to agent...")

        result = agent(prompt)
        console.print(Panel(
            f"[green]Agent completed successfully for {role.upper()}[/green]",
            title="Result",
        ))
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Test Cedar policy enforcement on AgentCore Gateway"
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["manager", "developer", "both"],
        default="both",
        help="Role to test (default: both)",
    )
    parser.add_argument(
        "--architecture",
        type=str,
        default=(
            "A simple web application with an Application Load Balancer, "
            "2 EC2 t3.medium instances, and an RDS MySQL database in us-east-1."
        ),
        help="Architecture description for cost estimation",
    )
    parser.add_argument(
        "--address",
        type=str,
        required=True,
        help="Email address to send estimation",
    )
    args = parser.parse_args()
    console = Console()

    roles = ["manager", "developer"] if args.role == "both" else [args.role]

    for role in roles:
        console.print()
        console.rule(f"Testing {role.upper()} role")
        run_agent_with_role(role, args.architecture, args.address, console)
        console.print()


if __name__ == "__main__":
    main()
