"""エージェントが必要なツールを呼び出したかどうかをチェックする評価器

成功要因: エージェントは、トレーニングデータから価格をハルシネーションするのではなく、
価格APIツールを使用して実際のデータを取得する必要があります。
"""

import logging

from opentelemetry.sdk.trace import ReadableSpan
from strands_evals.evaluators.evaluator import Evaluator
from strands_evals.types.evaluation import EvaluationData, EvaluationOutput

logger = logging.getLogger(__name__)


class ToolCallEvaluator(Evaluator[str, str]):
    """エージェントが実行中に全ての必要なツールを呼び出したかをチェック

    インメモリエクスポーターによってキャプチャされた生のOTelスパンを検査します。
    ツール実行スパンは ``gen_ai.operation.name == "execute_tool"`` を持ち、
    ツール名は ``span.name`` に保存されています。

    Args:
        required_tools: トラジェクトリに現れる必要があるツール名
        min_tool_calls: *任意の*必要なツールが呼び出される必要がある最小回数
    """

    def __init__(
        self,
        required_tools: list[str] | None = None,
        min_tool_calls: int = 1,
    ):
        super().__init__()
        self.required_tools = required_tools or ["get_pricing"]
        self.min_tool_calls = min_tool_calls

    def evaluate(self, evaluation_case: EvaluationData[str, str]) -> list[EvaluationOutput]:
        """全ての必要なツールが呼び出されたかを評価"""
        trajectory = evaluation_case.actual_trajectory
        if not trajectory:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason="No trajectory data available",
                )
            ]

        # OTelスパンからツール名を抽出
        called_tools: dict[str, int] = {}
        for item in trajectory:
            if not isinstance(item, ReadableSpan):
                continue
            attrs = item.attributes or {}
            operation = attrs.get("gen_ai.operation.name", "")
            if operation == "execute_tool":
                tool_name = attrs.get("gen_ai.tool.name", item.name or "")
                called_tools[tool_name] = called_tools.get(tool_name, 0) + 1

        # 各必要なツールをチェック
        missing_tools = []
        for tool in self.required_tools:
            count = called_tools.get(tool, 0)
            if count < self.min_tool_calls:
                missing_tools.append(f"{tool} (called {count}x, need {self.min_tool_calls}x)")

        if missing_tools:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason=f"Missing required tools: {', '.join(missing_tools)}. "
                    f"Tools called: {list(called_tools.keys())}",
                )
            ]

        return [
            EvaluationOutput(
                score=1.0,
                test_pass=True,
                reason=f"All required tools called: {list(called_tools.keys())}",
            )
        ]
