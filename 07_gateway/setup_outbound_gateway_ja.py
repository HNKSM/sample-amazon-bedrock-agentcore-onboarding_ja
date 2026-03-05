"""
AgentCore SDKを使用してLambdaターゲットを持つAgentCore Gatewayを作成
"""

import json
import logging
import argparse
import boto3
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# ロギングを設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

PROVIDER_NAME = "outbound-identity-for-cost-estimator-agent"
IDENTITY_FILE = Path("../06_identity/inbound_authorizer.json")
CONFIG_FILE = Path("outbound_gateway.json")


def setup_gateway(provider_name: str = PROVIDER_NAME, force: bool = False) -> dict:
    """
    GitHub OAuth2認証情報プロバイダーでGatewayをセットアップ
    
    この関数は:
    1. 06_identityからのInbound AuthorizerでGatewayを作成
    2. AWS LambdaをOutboundターゲットとしてGatewayにアタッチ
    3. 設定をoutbound_gateway.jsonに保存

    Args:
        provider_name: 認証情報プロバイダーの名前
        force: リソースの強制再作成を行うかどうか

    Returns:
        dict: 設定
    """

    config = load_config()
    region = boto3.Session().region_name

    has_provider = config and 'provider' in config
    has_gateway = config and 'gateway' in config

    control_client = boto3.client('bedrock-agentcore-control', region_name=region)
    gateway_client = GatewayClient(region_name=region)
    
    # ゲートウェイは存在するがターゲット作成が不完全かチェック
    has_target = has_gateway and 'target_id' in config.get('gateway', {})

    # 全てが完了していて強制でない場合は、サマリーを表示して終了
    if config and has_provider and has_target and not force:
        logger.info("All components already configured (use --force to recreate)")
        return config
    elif config:
        if has_gateway and force:
            logger.info("Delete existing Gateway...")
            delete_gateway(gateway_client, config['gateway'])
            has_gateway = False
            has_target = False
    
    if not has_gateway:
        logger.info("Creating Gateway with credential provider...")

        logger.info("Loading identity configuration from file...")
        if IDENTITY_FILE.exists():
            with open(IDENTITY_FILE) as f:
                identity_config = json.load(f)
        else:
            raise FileNotFoundError("Identity configuration file not found")

        gateway_name = "AWSCostEstimatorGateway"
        authorizer_config = {
            "customJWTAuthorizer": {
                "discoveryUrl": identity_config["cognito"]["discovery_url"],
                "allowedClients": [identity_config["cognito"]["client_id"]]
            }
        }
        gateway = gateway_client.create_mcp_gateway(
            name=gateway_name,
            role_arn=None,
            authorizer_config=authorizer_config,
            enable_semantic_search=False
        )
            
        gateway_id = gateway["gatewayId"]
        gateway_url = gateway["gatewayUrl"]

        logger.info("Gateway is created!")

        # IAMロールの伝播を待機 — SDKはrole_arn=Noneの場合に
        # AgentCoreGatewayExecutionRoleを自動作成し、IAMロールは
        # 結果整合性があります（AWS全体に伝播するのに約10-15秒）。
        import time
        logger.info("Waiting 15s for IAM role propagation...")
        time.sleep(15)

        logger.info("Adding Lambda target to Gateway...")
        tool_schema = [
            {
                "name": "markdown_to_email",
                "description": "Convert Markdown content to email format",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "markdown_text": {
                            "type": "string",
                            "description": "Markdown content to convertre to email format"
                        },
                        "email_address": {
                            "type": "string",
                            "description": "Recipient email address"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Title of email"
                        }
                    },
                    "required": ["markdown_text", "email_address"]
                }
            }
        ]

        # 必要なcredentialProviderConfigurationsでLambdaターゲットを作成
        # 注意: toolkitのcreate_mcp_gateway_targetはカスタムtarget_payload + credentialsを処理しません
        # 参考: https://github.com/aws/bedrock-agentcore-starter-toolkit/pull/57 
        target_name = gateway_name + "Target"
            
        create_request = {
            "gatewayIdentifier": gateway_id,
            "name": target_name,
            "targetConfiguration": {
                "mcp": {
                    "lambda": {
                        "lambdaArn": config["lambda_arn"],
                        "toolSchema": {
                            "inlinePayload": tool_schema
                        }
                    }
                }
            },
            "credentialProviderConfigurations": [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        }

        # ターゲット作成前にゲートウェイ設定を保存（部分的な失敗時の再開を可能にする）
        save_config({
            "gateway": {
                "id": gateway_id,
                "url": gateway_url,
            }
        })

        target_response = control_client.create_gateway_target(**create_request)
        target_id = target_response["targetId"]
        # ターゲット情報で設定を更新
        save_config({
            "gateway": {
                "id": gateway_id,
                "url": gateway_url,
                "target_id": target_id
            }
        })
        logger.info("✅ Gateway configuration saved")            
        logger.info("✅ Gateway setup complete!")
        logger.info("Next step: Run 'uv run python test_gateway_ja.py' to test the Gateway")
    
    config = load_config()
    return config


def delete_gateway(client, config):
    """既存のGatewayリソースをクリーンアップ"""
    # 最初にターゲットを削除
    if 'target_id' in config and 'id' in config:
        client.delete_mcp_gateway_target(config['id'], config['target_id'])
        logger.info("Deleted Gateway target")
    
    # Gatewayを削除
    if 'id' in config:
        client.delete_mcp_gateway(config['id'])
        logger.info("Deleted Gateway")


def load_config():
    """ファイルから設定を読み込み"""
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open('r') as f:
        config = json.load(f)
    return config


def save_config(updates: Optional[dict]=None, delete_key: str=""):
    """新しいデータで設定ファイルを更新"""
    config = load_config()
    
    if updates is not None:
        config.update(updates)
    elif delete_key:
        del config[delete_key]
    
    with CONFIG_FILE.open('w') as f:
        json.dump(config, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Create AgentCore Gateway')
    parser.add_argument('--force', action='store_true', help='Force recreation of resources')
    args = parser.parse_args()
    console = Console()
    
    try:
        config = setup_gateway(force=args.force)
    except Exception as e:
        logger.warning("❌ Setup Gateway failed:")
        logger.exception(e)
        return

    console.print_json(json.dumps(config))
    console.print(Panel("uv run python test_gateway_ja.py", title="Gatewayを使ったエージェントをテストしましょう！"))


if __name__ == "__main__":
    main()
