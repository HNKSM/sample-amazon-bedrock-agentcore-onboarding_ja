"""
AgentCore Gatewayでの細かいツールアクセス制御のためのCedarベースのポリシーをセットアップ

このスクリプトは以下を作成します:
1. Cognitoリソースサーバー上のロールスコープ（manager、developer）
2. ロール固有のスコープを持つ2つのM2Mアプリクライアント
3. managerスコープのみにメールツールを許可するCedarポリシーを持つPolicy Engine
4. ポリシーエンジンを既存のゲートウェイにアタッチ

前提条件:
- 06_identityのセットアップ完了（inbound_authorizer.jsonが存在）
- 07_gatewayのセットアップ完了（outbound_gateway.jsonが存在）

使用方法:
    uv run python 08_policy/setup_policy.py
    uv run python 08_policy/setup_policy.py --force
"""

import json
import logging
import argparse
from pathlib import Path
from typing import Optional

import boto3
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# ロギングを設定
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

IDENTITY_FILE = Path("../06_identity/inbound_authorizer.json")
GATEWAY_FILE = Path("../07_gateway/outbound_gateway.json")
CONFIG_FILE = Path("policy_config.json")

POLICY_ENGINE_NAME = "cost_estimator_policy_engine"
POLICY_NAME = "email_scope_policy"


def load_config() -> dict:
    """ファイルから設定を読み込み"""
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("r") as f:
            return json.load(f)
    return {}


def save_config(updates: Optional[dict] = None, delete_key: str = ""):
    """新しいデータで設定ファイルを更新"""
    config = load_config()
    if updates is not None:
        config.update(updates)
    elif delete_key:
        config.pop(delete_key, None)
    with CONFIG_FILE.open("w") as f:
        json.dump(config, f, indent=2)


def load_prerequisite_configs() -> tuple[dict, dict]:
    """ステップ06と07から設定を読み込み"""
    if not IDENTITY_FILE.exists():
        raise FileNotFoundError(
            f"Identity config not found: {IDENTITY_FILE}\n"
            "Please run 06_identity/setup_inbound_authorizer.py first."
        )
    if not GATEWAY_FILE.exists():
        raise FileNotFoundError(
            f"Gateway config not found: {GATEWAY_FILE}\n"
            "Please run 07_gateway/setup_outbound_gateway.py first."
        )
    with IDENTITY_FILE.open("r") as f:
        identity_config = json.load(f)
    with GATEWAY_FILE.open("r") as f:
        gateway_config = json.load(f)
    return identity_config, gateway_config


def setup_cognito_clients(
    identity_config: dict, gateway_config: dict, force: bool = False
) -> dict:
    """リソースサーバーにロールスコープを追加し、2つのM2Mアプリクライアントを作成

    各クライアントはinvokeスコープとロールスコープ（managerまたはdeveloper）を取得します。
    Cedarポリシーはスコープベースのマッチングを使用して、
    managerスコープを含むトークンのみにメールツールを許可します。
    """
    config = load_config()
    if "cognito_clients" in config and not force:
        logger.info("Cognito clients already configured (use --force to recreate)")
        return config["cognito_clients"]

    user_pool_id = identity_config["cognito"]["user_pool_id"]
    token_endpoint = identity_config["cognito"]["token_endpoint"]
    original_client_id = identity_config["cognito"]["client_id"]
    # ステップ06からの既存のスコープ（ゲートウェイ呼び出しに使用）
    existing_scope = identity_config["cognito"]["scope"]
    # スコープからリソースサーバー識別子を抽出（形式: "ResourceServer/scope"）
    resource_server_id = existing_scope.split("/")[0]

    cognito = boto3.client("cognito-idp")

    # forceの場合は既存のリソースをクリーンアップ
    if force and "cognito_clients" in config:
        logger.info("Cleaning up existing Cognito resources...")
        _cleanup_cognito_clients(cognito, config["cognito_clients"])

    # ステップ1: 既存のリソースサーバーにロールスコープを追加
    # リソースサーバーはステップ06で"invoke"スコープのみで作成されました。
    # ロールベースのアクセス制御のために"manager"と"developer"スコープを追加します。
    logger.info("Adding role scopes to resource server %s...", resource_server_id)
    cognito.update_resource_server(
        UserPoolId=user_pool_id,
        Identifier=resource_server_id,
        Name=resource_server_id,
        Scopes=[
            {"ScopeName": "invoke", "ScopeDescription": "Invoke the agent"},
            {"ScopeName": "manager", "ScopeDescription": "Manager role scope"},
            {"ScopeName": "developer", "ScopeDescription": "Developer role scope"},
        ],
    )
    logger.info("Resource server updated with role scopes")

    # Managerはinvoke + managerスコープを取得
    manager_scopes = [existing_scope, f"{resource_server_id}/manager"]
    # Developerはinvoke + developerスコープを取得
    developer_scopes = [existing_scope, f"{resource_server_id}/developer"]

    # ステップ2: Managerアプリクライアントを作成
    logger.info("Creating Manager app client...")
    manager_response = cognito.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName="CostEstimatorManager",
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=manager_scopes,
        AllowedOAuthFlowsUserPoolClient=True,
    )
    manager_client = manager_response["UserPoolClient"]
    logger.info("Manager client created: %s", manager_client["ClientId"])

    # ステップ3: Developerアプリクライアントを作成
    logger.info("Creating Developer app client...")
    developer_response = cognito.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName="CostEstimatorDeveloper",
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=developer_scopes,
        AllowedOAuthFlowsUserPoolClient=True,
    )
    developer_client = developer_response["UserPoolClient"]
    logger.info("Developer client created: %s", developer_client["ClientId"])

    cognito_config = {
        "user_pool_id": user_pool_id,
        "token_endpoint": token_endpoint,
        "original_client_id": original_client_id,
        "existing_scope": existing_scope,
        "resource_server_id": resource_server_id,
        "manager": {
            "client_id": manager_client["ClientId"],
            "client_secret": manager_client["ClientSecret"],
            "scopes": " ".join(manager_scopes),
        },
        "developer": {
            "client_id": developer_client["ClientId"],
            "client_secret": developer_client["ClientSecret"],
            "scopes": " ".join(developer_scopes),
        },
    }
    save_config({"cognito_clients": cognito_config})
    logger.info("Cognito clients configuration saved")
    return cognito_config


def update_gateway_allowed_clients(
    gateway_config: dict, cognito_config: dict
) -> str:
    """ゲートウェイのallowedClientsにManagerとDeveloperのクライアントIDを追加

    これがないと、新しいクライアントからのトークンはポリシー評価前に拒否されます。
    ゲートウェイARNを返します。
    """
    config = load_config()
    if "gateway_arn" in config:
        logger.info("Gateway already updated with new clients")
        return config["gateway_arn"]

    gateway_id = gateway_config["gateway"]["id"]
    region = boto3.Session().region_name
    control_client = boto3.client("bedrock-agentcore-control", region_name=region)

    # 既存の認証器設定を読み取るために現在のゲートウェイを取得
    gateway = control_client.get_gateway(gatewayIdentifier=gateway_id)
    gateway_arn = gateway["gatewayArn"]

    current_auth = gateway.get("authorizerConfiguration", {})
    jwt_config = current_auth.get("customJWTAuthorizer", {})
    current_clients = jwt_config.get("allowedClients", [])

    # 新しいクライアントIDを追加（既存の順序を保持し、欠落しているものを追加）
    new_clients = list(current_clients)
    for cid in [cognito_config["manager"]["client_id"], cognito_config["developer"]["client_id"]]:
        if cid not in new_clients:
            new_clients.append(cid)

    logger.info("Updating gateway allowedClients: %d -> %d clients",
                len(current_clients), len(new_clients))

    updated_auth = {
        "customJWTAuthorizer": {
            "discoveryUrl": jwt_config["discoveryUrl"],
            "allowedClients": new_clients,
        }
    }

    # 既存のフィールドを保持して更新リクエストを構築
    update_request = {
        "gatewayIdentifier": gateway_id,
        "name": gateway["name"],
        "roleArn": gateway["roleArn"],
        "protocolType": gateway["protocolType"],
        "authorizerType": gateway["authorizerType"],
        "authorizerConfiguration": updated_auth,
    }
    # オプションフィールドを保持
    for field in [
        "description", "policyEngineConfiguration", "protocolConfiguration",
        "kmsKeyArn", "customTransformConfiguration",
        "interceptorConfigurations", "exceptionLevel",
    ]:
        if field in gateway:
            update_request[field] = gateway[field]

    control_client.update_gateway(**update_request)
    logger.info("Gateway allowedClients updated")

    save_config({"gateway_arn": gateway_arn})
    return gateway_arn


def _fetch_existing_generation(
    policy_client: PolicyClient, engine_id: str, gen_name: str
) -> list:
    """名前で既存のNL2Cedar生成からアセットを取得"""
    try:
        generations = policy_client.list_policy_generations(
            policy_engine_id=engine_id
        )
        for gen in generations.get("policyGenerations", []):
            if gen.get("name", "").startswith(gen_name):
                gen_id = gen["policyGenerationId"]
                assets = policy_client.list_policy_generation_assets(
                    policy_engine_id=engine_id,
                    policy_generation_id=gen_id,
                )
                return assets.get("generatedPolicies", [])
    except Exception as e:
        logger.warning("Failed to fetch existing generation: %s", e)
    return []


def setup_policy_engine(console: Console) -> dict:
    """ポリシーエンジンを作成し、NL2Cedarをデモし、Cedarポリシーを作成"""
    config = load_config()
    if "policy_engine" in config and "policy" in config:
        logger.info("Policy engine and policy already configured")
        return config

    region = boto3.Session().region_name
    policy_client = PolicyClient(region_name=region)
    gateway_arn = config["gateway_arn"]

    # ステップ1: ポリシーエンジンを作成または取得
    if "policy_engine" not in config:
        logger.info("Creating policy engine...")
        engine = policy_client.create_or_get_policy_engine(
            name=POLICY_ENGINE_NAME,
            description="Policy engine for cost estimator gateway tool access control",
        )
        engine_id = engine["policyEngineId"]
        engine_arn = engine["policyEngineArn"]
        save_config({
            "policy_engine": {"id": engine_id, "arn": engine_arn},
        })
        logger.info("Policy engine created: %s", engine_id)
    else:
        engine_id = config["policy_engine"]["id"]
        engine_arn = config["policy_engine"]["arn"]

    # ステップ2: NL2Cedar経由でCedarポリシーを生成
    # NL2Cedarは自然言語の説明をCedarポリシーに変換します。
    # 有効に見える場合は生成されたポリシーを実際のポリシーとして使用し、
    # そうでない場合は手作りのポリシーにフォールバックします。
    nl2cedar_statement = None
    nl_description = (
        "Allow any user whose OAuth token scope contains 'manager' "
        "to use the markdown_to_email tool on the gateway. "
        "Deny all other users from using the markdown_to_email tool."
    )
    # エンジンIDから生成名を導出して決定論的な命名を実現:
    # 同じエンジン → 同じ名前（冪等）、新しいエンジン → 新しい名前（古い競合なし）
    engine_suffix = engine_id.rsplit("-", 1)[-1]
    gen_name = f"email_scope_nl2cedar_{engine_suffix}"
    logger.info("Generating Cedar policy via NL2Cedar...")
    try:
        generation = policy_client.generate_policy(
            policy_engine_id=engine_id,
            name=gen_name,
            resource={"arn": gateway_arn},
            content={"rawText": nl_description},
            fetch_assets=True,
        )
        generated_policies = generation.get("generatedPolicies", [])
    except Exception as e:
        # 生成が既に存在する場合（再実行時のConflictException）、
        # 失敗する代わりにその結果を取得
        generated_policies = []
        if "ConflictException" in str(e):
            logger.info("NL2Cedar generation already exists, fetching results...")
            generated_policies = _fetch_existing_generation(
                policy_client, engine_id, gen_name
            )
        else:
            logger.warning("NL2Cedar generation failed: %s", e)

    if generated_policies:
        console.print(Panel(
            f"[bold]Input:[/bold] {nl_description}",
            title="NL2Cedar: Natural Language Input",
        ))
        for i, asset in enumerate(generated_policies):
            cedar_def = asset.get("definition", {}).get("cedar", {})
            statement = cedar_def.get("statement", "")
            if statement:
                console.print(Panel(
                    Syntax(statement, "cedar", theme="monokai"),
                    title=f"NL2Cedar: Generated Policy {i + 1}",
                ))
                # permit文を含む最初の生成されたポリシーを使用
                if nl2cedar_statement is None and "permit" in statement:
                    nl2cedar_statement = statement
        if nl2cedar_statement:
            logger.info("NL2Cedar generated a usable policy")
        else:
            logger.warning("NL2Cedar output did not contain a usable permit statement")

    # ステップ3: 実際のCedarポリシーを作成
    if "policy" not in config:
        # ターゲット名は規約に従います: GatewayName + "Target"
        # アクション形式は: TargetName___ToolName（トリプルアンダースコア）
        target_name = "AWSCostEstimatorGatewayTarget"
        tool_name = "markdown_to_email"
        action_name = f"{target_name}___{tool_name}"

        # 手作りのフォールバックポリシー: like演算子を使用したスコープベースのマッチング
        handcrafted_statement = (
            "permit(\n"
            "  principal,\n"
            f'  action == AgentCore::Action::"{action_name}",\n'
            f'  resource == AgentCore::Gateway::"{gateway_arn}"\n'
            ") when {\n"
            '  principal.hasTag("scope") &&\n'
            '  principal.getTag("scope") like "*manager*"\n'
            "};"
        )

        if nl2cedar_statement:
            cedar_statement = nl2cedar_statement
            policy_source = "NL2Cedar"
        else:
            cedar_statement = handcrafted_statement
            policy_source = "hand-crafted"

        console.print(Panel(
            Syntax(cedar_statement, "cedar", theme="monokai"),
            title=f"Cedar Policy to Create ({policy_source})",
        ))

        logger.info("Creating Cedar policy (%s)...", policy_source)
        policy = policy_client.create_or_get_policy(
            policy_engine_id=engine_id,
            name=POLICY_NAME,
            definition={"cedar": {"statement": cedar_statement}},
            description=(
                "Permit markdown_to_email tool only for OAuth clients "
                "whose token contains the manager scope"
            ),
        )
        policy_id = policy["policyId"]
        policy_arn = policy["policyArn"]
        save_config({
            "policy": {
                "id": policy_id,
                "arn": policy_arn,
                "cedar_statement": cedar_statement,
                "source": policy_source,
            },
        })
        logger.info("Cedar policy created (%s): %s", policy_source, policy_id)

    return load_config()


def attach_policy_to_gateway() -> None:
    """ポリシーエンジンをENFORCEモードでゲートウェイにアタッチ"""
    config = load_config()
    if config.get("policy_attached"):
        logger.info("Policy engine already attached to gateway")
        return

    region = boto3.Session().region_name
    gateway_client = GatewayClient(region_name=region)
    gateway_id = None
    with GATEWAY_FILE.open("r") as f:
        gw_config = json.load(f)
        gateway_id = gw_config["gateway"]["id"]

    engine_arn = config["policy_engine"]["arn"]

    logger.info("Attaching policy engine to gateway (ENFORCE mode)...")
    gateway_client.update_gateway_policy_engine(
        gateway_identifier=gateway_id,
        policy_engine_arn=engine_arn,
        mode="ENFORCE",
    )
    save_config({"policy_attached": True})
    logger.info("Policy engine attached to gateway in ENFORCE mode")


def _cleanup_cognito_clients(cognito, cognito_config: dict) -> None:
    """このステップで作成されたCognitoアプリクライアントをクリーンアップ"""
    user_pool_id = cognito_config.get("user_pool_id")
    if not user_pool_id:
        return

    for role in ["manager", "developer"]:
        client_id = cognito_config.get(role, {}).get("client_id")
        if client_id:
            try:
                cognito.delete_user_pool_client(
                    UserPoolId=user_pool_id, ClientId=client_id
                )
                logger.info("Deleted %s client: %s", role, client_id)
            except Exception as e:
                logger.warning("Failed to delete %s client: %s", role, e)


def main():
    parser = argparse.ArgumentParser(
        description="Setup Cedar-based policy for AgentCore Gateway"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force recreation of resources"
    )
    args = parser.parse_args()
    console = Console()

    try:
        # 前提条件の設定を読み込み
        identity_config, gateway_config = load_prerequisite_configs()
        logger.info("Loaded prerequisite configs from step 06 and 07")

        # ステップ1: ロールスコープを追加 + M2Mクライアントを作成
        cognito_config = setup_cognito_clients(
            identity_config, gateway_config, force=args.force
        )
        logger.info("Step 1 complete: Cognito clients created")

        # ステップ2: ゲートウェイのallowedClientsを更新
        update_gateway_allowed_clients(gateway_config, cognito_config)
        logger.info("Step 2 complete: Gateway allowedClients updated")

        # ステップ3: ポリシーエンジン + Cedarポリシーを作成
        setup_policy_engine(console)
        logger.info("Step 3 complete: Policy engine and Cedar policy created")

        # ステップ4: ポリシーエンジンをゲートウェイにアタッチ
        attach_policy_to_gateway()
        logger.info("Step 4 complete: Policy engine attached to gateway")

        # 最終設定を表示
        console.print_json(json.dumps(load_config()))
        console.print(Panel(
            "uv run python 08_policy/test_policy.py --role manager --address you@example.com\n"
            "uv run python 08_policy/test_policy.py --role developer --address you@example.com",
            title="Next: Test role-based access control",
        ))

    except Exception as e:
        logger.error("Setup failed: %s", e)
        raise


if __name__ == "__main__":
    main()
