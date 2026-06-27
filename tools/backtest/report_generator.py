"""
回测报告生成器 - 将回测结果转化为自然语言分析报告

使用 LLM 对回测数据进行解读，给出策略评估和改进建议
"""
import json
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_deepseek import ChatDeepSeek
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL


REPORT_PROMPT = """你是一个专业的量化策略分析师。
请根据以下回测结果，生成一份专业、客观的策略评估报告。

## 报告结构（必须包含以下部分）

### 一、策略概述
简述策略逻辑和回测参数

### 二、核心指标解读
- 胜率、盈亏比、夏普比率的含义和评价
- 与市场基准的对比（如有）

### 三、历史案例展示
列举3-5个典型的成功和失败案例，说明进场时机和结果

### 四、分年度表现
分析策略在不同市场环境下的表现差异

### 五、策略优势与风险
- 优势：策略的核心alpha来源
- 风险：潜在的失效场景和注意事项

### 六、改进建议
基于数据给出1-3条具体的优化方向

## 写作要求
- 数据驱动，引用具体数字
- 客观中立，不夸大也不贬低
- 专业但易懂，避免过度术语
- 末尾必须注明：以上分析仅供参考，不构成投资建议
"""


class ReportGenerator:
    """回测报告生成器"""

    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.5,
            extra_body={"reasoning": False}  # 禁用思考模式
        )

    async def generate(
        self,
        strategy: Dict[str, Any],
        backtest_result: Dict[str, Any],
        stream_callback=None,
    ) -> str:
        """
        生成回测分析报告

        Args:
            strategy: 解析后的策略结构
            backtest_result: 回测引擎输出
            stream_callback: 流式回调 async fn(chunk: str)

        Returns:
            完整报告文本
        """
        summary = backtest_result.get("summary", {})
        trades = backtest_result.get("trades", [])
        by_year = backtest_result.get("by_year", {})
        by_board = backtest_result.get("by_board", {})

        # 构建典型案例（取收益最高/最低各3笔）
        sorted_trades = sorted(trades, key=lambda x: x["net_return_pct"])
        worst_cases = sorted_trades[:3]
        best_cases = sorted_trades[-3:][::-1]

        sample_cases = {
            "best_cases": [_format_trade(t) for t in best_cases],
            "worst_cases": [_format_trade(t) for t in worst_cases],
        }

        # 构建输入数据（控制 token 量）
        input_data = {
            "strategy_name": strategy.get("strategy_name", "自定义策略"),
            "strategy_type": strategy.get("strategy_type", ""),
            "backtest_period": strategy.get("backtest_config", {}).get("start_date", "") + " ~ " +
                               strategy.get("backtest_config", {}).get("end_date", "today"),
            "exit_rules": strategy.get("exit_rules", {}),
            "summary": summary,
            "by_year": by_year,
            "by_board": by_board,
            "sample_cases": sample_cases,
            "total_trades_shown": len(trades),
        }

        user_content = f"回测数据：\n```json\n{json.dumps(input_data, ensure_ascii=False, indent=2, default=str)}\n```\n\n请生成完整的策略评估报告。"

        messages = [
            SystemMessage(content=REPORT_PROMPT),
            HumanMessage(content=user_content),
        ]

        chunks = []
        if stream_callback:
            async for chunk in self.model.astream(messages):
                content = getattr(chunk, "content", "") or ""
                if content:
                    chunks.append(content)
                    await stream_callback(content)
        else:
            resp = await self.model.ainvoke(messages)
            chunks.append(getattr(resp, "content", "") or "")

        return "".join(chunks)


def _format_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "股票": t.get("ts_code", ""),
        "板块": t.get("board", ""),
        "连板数": t.get("streak_count", 0),
        "断板日": t.get("break_date", ""),
        "进场日": t.get("entry_date", ""),
        "进场价": t.get("entry_price", 0),
        "出场日": t.get("exit_date", ""),
        "出场价": t.get("exit_price", 0),
        "出场原因": t.get("exit_reason", ""),
        "持仓天数": t.get("hold_days", 0),
        "净收益率": f"{t.get('net_return_pct', 0):.2f}%",
        "最大回撤": f"{t.get('max_drawdown_pct', 0):.2f}%",
    }
