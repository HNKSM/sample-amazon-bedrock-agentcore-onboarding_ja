import boto3
from botocore.exceptions import ClientError

EVALUATOR_NAME = "cost_estimator_tool_usage"
ONLINE_CONFIG_NAME = "cost_estimator_online_eval"


def clean_resources():
    """評価リソースをクリーンアップ"""
    control = boto3.client("bedrock-agentcore-control")

    # ---- ステップ1: オンライン評価設定を削除（評価器の前に実行する必要がある） ----
    # オンライン設定はカスタム評価器をロックします — 設定を先に削除してロックを解除します。
    try:
        resp = control.list_online_evaluation_configs()
        for cfg in resp.get("onlineEvaluationConfigs", []):
            if cfg.get("onlineEvaluationConfigName") == ONLINE_CONFIG_NAME:
                config_id = cfg["onlineEvaluationConfigId"]
                print(f"Found online eval config: {ONLINE_CONFIG_NAME} ({config_id})")
                try:
                    control.delete_online_evaluation_config(
                        onlineEvaluationConfigId=config_id
                    )
                    print("Online eval config deletion initiated (async).")
                except ClientError as e:
                    print(f"Failed to delete online eval config: {e}")
                break
        else:
            print(f"No online eval config named '{ONLINE_CONFIG_NAME}' found.")
    except ClientError as e:
        print(f"Failed to list online eval configs: {e}")

    # ---- ステップ2: カスタム評価器を削除 ----
    try:
        resp = control.list_evaluators()
    except ClientError as e:
        print(f"Failed to list evaluators: {e}")
        return

    for ev in resp.get("evaluators", []):
        if ev["evaluatorName"] == EVALUATOR_NAME:
            evaluator_id = ev["evaluatorId"]
            print(f"Delete evaluator {EVALUATOR_NAME} ({evaluator_id}).")
            try:
                control.delete_evaluator(evaluatorId=evaluator_id)
                print("Deletion initiated (async).")
            except ClientError as e:
                print(f"Failed to delete evaluator: {e}")
            return

    print(f"No evaluator named '{EVALUATOR_NAME}' found. Nothing to clean.")


if __name__ == "__main__":
    clean_resources()
