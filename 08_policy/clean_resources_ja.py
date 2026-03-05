"""
08_policyで作成された全てのリソースを逆依存順序でクリーンアップ

クリーンアップ順序:
1. ゲートウェイからポリシーエンジンをデタッチ（ゲートウェイを更新してポリシー設定を削除）
2. ゲートウェイのallowedClientsを元に戻す（step-06クライアントのみ）
3. 全てのポリシーを削除してから、ポリシーエンジンを削除
4. Cognitoアプリクライアント（manager、developer）を削除
5. policy_config.jsonを削除

使用方法:
    uv run python 08_policy/clean_resources.py
"""

import json
import os
import time
from pathlib import Path

import boto3
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient

POLICY_CONFIG_FILE = Path("policy_config.json")
GATEWAY_CONFIG_FILE = Path("../07_gateway/outbound_gateway.json")


def clean_resources():
    """08_policy（Policy）で作成された全てのリソースをクリーンアップ"""
    if not POLICY_CONFIG_FILE.exists():
        print("No policy_config.json found, nothing to clean")
        return

    with POLICY_CONFIG_FILE.open("r", encoding="utf-8") as f:
        config = json.load(f)

    region = boto3.Session().region_name
    control_client = boto3.client("bedrock-agentcore-control", region_name=region)

    # ステップ1: ゲートウェイからポリシーエンジンをデタッチ
    if config.get("policy_attached") and GATEWAY_CONFIG_FILE.exists():
        with GATEWAY_CONFIG_FILE.open("r") as f:
            gw_config = json.load(f)
        gateway_id = gw_config["gateway"]["id"]
        print(f"Detaching policy engine from gateway {gateway_id}...")
        try:
            gateway = control_client.get_gateway(gatewayIdentifier=gateway_id)
            update_request = {
                "gatewayIdentifier": gateway_id,
                "name": gateway["name"],
                "roleArn": gateway["roleArn"],
                "protocolType": gateway["protocolType"],
                "authorizerType": gateway["authorizerType"],
            }
            # policyEngineConfiguration以外のフィールドを保持
            for field in [
                "description", "authorizerConfiguration", "protocolConfiguration",
                "kmsKeyArn", "customTransformConfiguration",
                "interceptorConfigurations", "exceptionLevel",
            ]:
                if field in gateway:
                    update_request[field] = gateway[field]
            # デタッチするためにpolicyEngineConfigurationを省略
            control_client.update_gateway(**update_request)
            print("Policy engine detached from gateway")
        except Exception as e:
            print(f"Warning: Failed to detach policy engine: {e}")

    # ステップ2: ゲートウェイのallowedClientsを元に戻す
    # デタッチ後のゲートウェイの更新完了を待機（ステップ1）
    cognito_clients = config.get("cognito_clients", {})
    original_client_id = cognito_clients.get("original_client_id")
    if original_client_id and GATEWAY_CONFIG_FILE.exists():
        with GATEWAY_CONFIG_FILE.open("r") as f:
            gw_config = json.load(f)
        gateway_id = gw_config["gateway"]["id"]
        print("Waiting for gateway to be ready...")
        for _ in range(12):
            gw_status = control_client.get_gateway(
                gatewayIdentifier=gateway_id
            ).get("status")
            if gw_status == "READY":
                break
            time.sleep(5)
        print("Restoring gateway allowedClients to original client only...")
        try:
            gateway = control_client.get_gateway(gatewayIdentifier=gateway_id)
            jwt_config = gateway.get("authorizerConfiguration", {}).get(
                "customJWTAuthorizer", {}
            )
            restored_auth = {
                "customJWTAuthorizer": {
                    "discoveryUrl": jwt_config["discoveryUrl"],
                    "allowedClients": [original_client_id],
                }
            }
            update_request = {
                "gatewayIdentifier": gateway_id,
                "name": gateway["name"],
                "roleArn": gateway["roleArn"],
                "protocolType": gateway["protocolType"],
                "authorizerType": gateway["authorizerType"],
                "authorizerConfiguration": restored_auth,
            }
            for field in [
                "description", "protocolConfiguration", "kmsKeyArn",
                "customTransformConfiguration", "interceptorConfigurations",
                "exceptionLevel",
            ]:
                if field in gateway:
                    update_request[field] = gateway[field]
            # policyEngineConfiguration を省略（ステップ1で既にデタッチ済み）
            control_client.update_gateway(**update_request)
            print("Gateway allowedClients restored")
        except Exception as e:
            print(f"Warning: Failed to restore allowedClients: {e}")

    # ステップ3: 全てのポリシーを削除してから、ポリシーエンジンを削除
    policy_engine = config.get("policy_engine", {})
    engine_id = policy_engine.get("id")
    if engine_id:
        print(f"Cleaning up policy engine {engine_id}...")
        try:
            policy_client = PolicyClient(region_name=region)
            policy_client.cleanup_policy_engine(engine_id)
            print("Policy engine cleaned up")
        except Exception as e:
            print(f"Warning: Failed to cleanup policy engine: {e}")

    # ステップ4: Cognitoアプリクライアントを削除
    user_pool_id = cognito_clients.get("user_pool_id")
    if user_pool_id:
        cognito = boto3.client("cognito-idp", region_name=region)
        for role in ["manager", "developer"]:
            client_id = cognito_clients.get(role, {}).get("client_id")
            if client_id:
                print(f"Deleting {role} app client: {client_id}")
                try:
                    cognito.delete_user_pool_client(
                        UserPoolId=user_pool_id, ClientId=client_id
                    )
                    print(f"{role.capitalize()} client deleted")
                except Exception as e:
                    print(f"Warning: Failed to delete {role} client: {e}")

        # ステップ4b: リソースサーバーを元のスコープに戻す（invokeのみ）
        resource_server_id = cognito_clients.get("resource_server_id")
        if resource_server_id:
            print(f"Restoring resource server {resource_server_id} to original scopes...")
            try:
                cognito.update_resource_server(
                    UserPoolId=user_pool_id,
                    Identifier=resource_server_id,
                    Name=resource_server_id,
                    Scopes=[
                        {"ScopeName": "invoke", "ScopeDescription": "Invoke the agent"},
                    ],
                )
                print("Resource server scopes restored")
            except Exception as e:
                print(f"Warning: Failed to restore resource server scopes: {e}")

    # ステップ5: 設定ファイルを削除
    print("Removing policy_config.json")
    os.remove(POLICY_CONFIG_FILE)
    print("Cleanup complete")


if __name__ == "__main__":
    clean_resources()
