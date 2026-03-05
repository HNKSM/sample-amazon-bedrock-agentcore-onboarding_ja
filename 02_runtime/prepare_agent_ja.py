#!/usr/bin/env python3
"""
AgentCore Runtime - エージェント登録・管理ツール

AIエージェントをAmazon Bedrock AgentCore Runtimeにデプロイするためのシンプルなツール
"""

import json
import os
import shutil
import logging
from pathlib import Path
import boto3
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from botocore.exceptions import ClientError

# ロギングを設定
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console()

# 定数
DEFAULT_REGION = (
    boto3.Session().region_name
    or os.environ.get('AWS_REGION')
    or os.environ.get('AWS_DEFAULT_REGION')
)
DEPLOYMENTS_DIR = Path('./deployment')


class AgentPreparer:
    """デプロイ用のエージェント準備を処理"""
    
    def __init__(self, source_dir: str, region: str = DEFAULT_REGION):
        self.source_dir = Path(source_dir)
        self.region = region
        self.iam_client = boto3.client('iam', region_name=region)
    
    @property
    def agent_name(self) -> str:
        """
        ソースディレクトリからエージェント名を抽出（最後のフォルダ名）
        
        Returns:
            str: エージェントの名前
        """
        return self.source_dir.name if self.source_dir.is_dir() else self.source_dir.stem

    def prepare(self) -> str:
        """
        デプロイメントディレクトリとIAMロールを作成してエージェントをデプロイ用に準備

        Returns:
            str: エージェント設定用のコマンド
        """
        if not self.region:
            raise click.ClickException(
                "AWSリージョンが設定されていません。以下を実行してください:\n"
                "  aws configure set region <your-region>  (例: us-west-2)\n"
                "その後、このスクリプトを再実行してください。"
            )

        # デプロイメントディレクトリを作成
        deployment_dir = self.create_source_directory()

        # IAMロールを作成
        role_info = self.create_agentcore_role()

        # agentcore configureコマンドを構築
        command = "\n".join([
            "",
            f"uv run agentcore configure --entrypoint {deployment_dir}/invoke_ja.py \\",
            f"--name {self.agent_name} \\",
            f"--execution-role {role_info['role_arn']} \\",
            f"--requirements-file {deployment_dir}/requirements.txt \\",
            "--non-interactive \\",
            "--deployment-type direct_code_deploy \\",
            "--disable-memory \\",
            f"--region {self.region} "
        ])

        return command

    def create_source_directory(self) -> str:
        """
        ソースディレクトリ全体をコピーしてデプロイメントディレクトリを作成
            
        Returns:
            デプロイメントディレクトリへのパス
        """
        logger.info(f"Creating deployment directory from {self.source_dir}")

        # ソースディレクトリの存在を検証
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {self.source_dir}")

        # デプロイメントディレクトリを作成
        target_dir = DEPLOYMENTS_DIR / self.agent_name
        target_dir.mkdir(parents=True, exist_ok=True)

        # ソースディレクトリからPythonファイルをコピー
        logger.info(f"Copying Python files from {self.source_dir} to {target_dir}")
        for file_path in self.source_dir.glob("*.py"):
            dest_path = target_dir / file_path.name
            shutil.copy2(file_path, dest_path)
            logger.info(f"Copied {file_path.name}")
            
        logger.info(f"Source directory is copied to deployment directory: {DEPLOYMENTS_DIR}")
        return str(DEPLOYMENTS_DIR)

    def create_agentcore_role(self) -> dict:
        """
        AgentCore権限を持つIAMロールを作成
        参考: https://github.com/awslabs/amazon-bedrock-agentcore-samples
                    
        Returns:
            ARNを含むロール情報
        """
        role_name = f"AgentCoreRole-{self.agent_name}"
        logger.info(f"Creating IAM role: {role_name}")
        
        # アカウントIDを取得
        sts_client = boto3.client('sts', region_name=self.region)
        account_id = sts_client.get_caller_identity()['Account']
        
        # 信頼ポリシーを作成
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "bedrock-agentcore.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {
                            "aws:SourceAccount": account_id
                        },
                        "ArnLike": {
                            "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:*"
                        }
                    }
                }
            ]
        }
        
        # 実行ポリシーを作成
        execution_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "BedrockPermissions",
                    "Effect": "Allow",
                    "Action": [
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    "Resource": "*"
                },
                {
                    "Sid": "ECRImageAccess",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer"
                    ],
                    "Resource": [
                        f"arn:aws:ecr:{self.region}:{account_id}:repository/*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:DescribeLogStreams",
                        "logs:CreateLogGroup"
                    ],
                    "Resource": [
                        f"arn:aws:logs:{self.region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:DescribeLogGroups"
                    ],
                    "Resource": [
                        f"arn:aws:logs:{self.region}:{account_id}:log-group:*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": [
                        f"arn:aws:logs:{self.region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                    ]
                },
                {
                    "Sid": "ECRTokenAccess",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken"
                    ],
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "xray:PutTraceSegments",
                        "xray:PutTelemetryRecords",
                        "xray:GetSamplingRules",
                        "xray:GetSamplingTargets"
                        ],
                    "Resource": [ "*" ]
                },
                {
                    "Effect": "Allow",
                    "Resource": "*",
                    "Action": "cloudwatch:PutMetricData",
                    "Condition": {
                        "StringEquals": {
                            "cloudwatch:namespace": "bedrock-agentcore"
                        }
                    }
                },
                {
                    "Sid": "GetAgentAccessToken",
                    "Effect": "Allow",
                    "Action": [
                        "bedrock-agentcore:GetWorkloadAccessToken",
                        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                        "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                    ],
                    "Resource": [
                        f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default*",
                        f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default/workload-identity/{self.agent_name}-*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "bedrock-agentcore:CreateCodeInterpreter",
                        "bedrock-agentcore:StartCodeInterpreterSession",
                        "bedrock-agentcore:InvokeCodeInterpreter",
                        "bedrock-agentcore:StopCodeInterpreterSession",
                        "bedrock-agentcore:DeleteCodeInterpreter",
                        "bedrock-agentcore:ListCodeInterpreters",
                        "bedrock-agentcore:GetCodeInterpreter",
                        "bedrock-agentcore:GetCodeInterpreterSession",
                        "bedrock-agentcore:ListCodeInterpreterSessions"
                    ],
                    "Resource": "arn:aws:bedrock-agentcore:*:*:*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "pricing:*"
                    ],
                    "Resource": "*"
                },
                {
                    "Sid": "MarketplaceAccess",
                    "Effect": "Allow",
                    "Action": [
                        "aws-marketplace:Subscribe",
                        "aws-marketplace:ViewSubscriptions"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        role_exists = False
        response = None

        try:
            response = self.iam_client.get_role(RoleName=role_name)
            logger.info(f"Role {role_name} already exists")
            role_exists = True
        except ClientError:
            pass

        if not role_exists:
            try:
                response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f'AgentCore execution role for {self.agent_name}'
                )
                logger.info(f"IAM role created successfully: {role_name}")
            except ClientError as e:
                logger.error(f"Failed to create IAM role: {e}")
                return {}

        # 実行ポリシーが常にアタッチされていることを確認（新規・既存ロール両方）
        try:
            self.iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=f'{role_name}-ExecutionPolicy',
                PolicyDocument=json.dumps(execution_policy)
            )
            logger.info(f"Execution policy attached to role: {role_name}")
        except ClientError as e:
            logger.error(f"Failed to attach execution policy: {e}")
            return {}

        return {
            'agent_name': self.agent_name,
            'role_name': role_name,
            'role_arn': response['Role']['Arn']
        }


@click.command()
@click.option('--source-dir', default="../01_code_interpreter/cost_estimator_agent", required=True, help='コピー元のソースディレクトリ')
@click.option('--region', default=DEFAULT_REGION, help='AWSリージョン')
def prepare(source_dir: str, region: str):
    """ソースディレクトリをコピーしてエージェントをデプロイ用に準備"""
    console.print(f"[bold blue]エージェントを準備中: {source_dir}[/bold blue]")
    
    preparer = AgentPreparer(source_dir, region)
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            _ = progress.add_task("[cyan]エージェントを準備中...", total=None)
            configure_command = preparer.prepare()
            progress.stop()
        
        # 明確な視覚的階層を持つ成功出力
        console.print("\n[bold green]✓ エージェントの準備が正常に完了しました！[/bold green]")
        console.print(f"\n[bold]エージェント名:[/bold] {preparer.agent_name}")
        console.print(f"[bold]デプロイメントディレクトリ:[/bold] {DEPLOYMENTS_DIR}")
        console.print(f"[bold]リージョン:[/bold] {region}")
        
        # 明確な視覚的分離を持つ次のステップ
        console.print("\n[bold yellow]📋 次のステップ:[/bold yellow]")
        console.print("\n[bold]1. エージェントランタイムを設定:[/bold]")
        console.print(f"   [cyan]{configure_command}[/cyan]")
        
        console.print("\n[bold]2. エージェントをデプロイ:[/bold]")
        console.print("   [cyan]uv run agentcore deploy[/cyan]")
        
        console.print("\n[bold]3. エージェントをテスト:[/bold]")
        console.print("   [cyan]uv run agentcore invoke '{\"prompt\": \"I would like to connect t3.micro from my PC. How much does it cost?\"}'[/cyan]")
        
        # プロのヒント
        console.print("\n[dim]💡 ヒント: 上記のコマンドをターミナルに直接コピー＆ペーストできます。[/dim]")
        
    except Exception as e:
        console.print(f"\n[bold red]❌ エラー: {e}[/bold red]")
        raise click.Abort()


if __name__ == '__main__':
    prepare()
