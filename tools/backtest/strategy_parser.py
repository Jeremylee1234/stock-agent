"""
策略解析器 - 将自然语言策略描述解析为结构化执行计划

支持复杂策略，如：
- 连板回踩策略（20cm/10cm 不同规则）
- 技术指标组合（MACD金叉 + 均线突破 + 放量）
- 基本面筛选（ROE/PE/市值等）
- 时序逻辑（A发生后N天内B）
"""
import json
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_deepseek import ChatDeepSeek
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL


# ── 策略解析 Prompt ──────────────────────────────────────────────────────────

STRATEGY_PARSER_PROMPT = """你是一个专业的量化策略解析专家。
用户会描述一个选股+进场策略，你需要将其解析为结构化 JSON。

## 输出格式（严格 JSON，不要输出其他内容）

```json
{
  "strategy_name": "策略名称",
  "strategy_type": "momentum|value|technical|hybrid",
  "completeness": "complete|incomplete",
  "missing_info": ["缺少的信息1", "缺少的信息2"],
  "clarification_questions": ["追问问题1", "追问问题2"],

  "universe": {
    "market": ["SH", "SZ", "BJ"],
    "board": ["主板", "创业板", "科创板"],
    "exclude_st": true,
    "min_list_days": 180,
    "custom_filters": []
  },

  "stock_filter": {
    "fundamental": [
      {
        "metric": "roe",
        "op": ">",
        "value": 15,
        "period": "annual",
        "consecutive": 3,
        "description": "ROE连续3年>15%"
      }
    ],
    "technical": [
      {
        "type": "limit_up_streak",
        "board_type": "20cm",
        "min_count": 2,
        "description": "创业板/科创板连续2个涨停"
      }
    ],
    "market_cap": {"min": null, "max": null, "unit": "亿元"}
  },

  "entry_conditions": {
    "logic": "AND",
    "trigger_window_days": 30,
    "conditions": [
      {
        "id": "cond_1",
        "type": "price_vs_ma",
        "ma_period": 10,
        "op": "<=",
        "description": "收盘价 ≤ 10日均线",
        "after_event": null,
        "after_offset_days": null
      }
    ],
    "prerequisite_events": [
      {
        "id": "evt_break",
        "type": "limit_up_break",
        "description": "连板结束（断板日）：连板后第一个交易日未涨停且收盘价≥最后连板日收盘价"
      },
      {
        "id": "evt_confirm",
        "type": "new_high_confirm",
        "window_days": 5,
        "description": "强势确认：断板后5日内最高价>连板期间最高价"
      }
    ]
  },

  "exit_rules": {
    "stop_loss_pct": -8,
    "take_profit_pct": null,
    "max_hold_days": 30,
    "trailing_stop": null,
    "custom_exit": []
  },

  "data_requirements": {
    "adj_type": "qfq",
    "indicators": ["close", "high", "low", "open", "vol", "ma10", "ma20"],
    "lookback_days": 120
  },

  "backtest_config": {
    "start_date": "20200101",
    "end_date": "today",
    "initial_capital": 1000000,
    "position_size_pct": 100,
    "commission_rate": 0.0003,
    "slippage_pct": 0.001,
    "benchmark": "000300.SH"
  }
}
```

## 解析规则

1. **连板策略**：
   - 20cm股（创业板/科创板）：min_count=2
   - 10cm股（主板）：min_count=4
   - 断板条件：连板后第一天未涨停 + 收盘价≥最后连板日收盘价
   - 强势确认：断板后N日内创新高

2. **进场时序**：
   - prerequisite_events 按顺序发生
   - entry_conditions 在 trigger_window_days 内满足

3. **completeness 判断**：
   - complete：策略描述足够执行回测
   - incomplete：缺少关键参数，需要追问

4. **追问原则**：只追问影响回测结果的关键参数，不要追问可以用默认值的参数。

## 示例

用户输入："买入连板回踩的股票"
→ completeness: "incomplete"
→ clarification_questions: ["请问您关注的是主板（10cm）还是创业板/科创板（20cm）的连板股？", "连板要求几板以上？", "回踩的具体买入条件是什么？比如回踩到某条均线？"]

用户输入："创业板连续2个涨停后断板，断板后5日内创新高，然后在30个交易日内首次回踩10日均线时买入，止损8%，持有最多30天"
→ completeness: "complete"
→ 完整解析所有字段
"""


CLARIFICATION_PROMPT = """你是一个量化策略顾问。
用户描述了一个策略，但信息不完整。请根据缺失信息，用友好、专业的语气向用户提问。

要求：
1. 一次最多问3个问题，按重要性排序
2. 每个问题给出选项或示例，方便用户回答
3. 语气专业但不生硬
4. 不要重复用户已经说明的信息

缺失信息：{missing_info}
追问问题：{questions}

请生成一段自然的追问文字（不超过200字）。"""


class StrategyParser:
    """自然语言策略解析器"""

    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.1,  # 解析需要低温度保证稳定性
            extra_body={"reasoning": False}  # 禁用思考模式
        )

    async def parse(self, user_input: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        解析用户策略描述

        Returns:
            {
                "status": "complete" | "need_clarification",
                "strategy": {...},          # 结构化策略（complete时）
                "clarification": "...",     # 追问文字（need_clarification时）
                "questions": [...]          # 具体问题列表
            }
        """
        # 构建对话上下文
        messages = [SystemMessage(content=STRATEGY_PARSER_PROMPT)]

        if conversation_history:
            for turn in conversation_history[-4:]:  # 最近4轮
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                else:
                    from langchain_core.messages import AIMessage
                    messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=f"请解析以下策略：\n\n{user_input}"))

        try:
            resp = await self.model.ainvoke(messages)
            raw = getattr(resp, "content", "") or ""

            # 提取 JSON
            match = re.search(r'\{[\s\S]*\}', raw)
            if not match:
                return self._fallback_incomplete(user_input)

            strategy = json.loads(match.group())

            completeness = strategy.get("completeness", "incomplete")
            questions = strategy.get("clarification_questions", [])

            if completeness == "incomplete" and questions:
                clarification = await self._generate_clarification(
                    strategy.get("missing_info", []),
                    questions
                )
                return {
                    "status": "need_clarification",
                    "strategy": strategy,
                    "clarification": clarification,
                    "questions": questions,
                }

            return {
                "status": "complete",
                "strategy": strategy,
                "clarification": None,
                "questions": [],
            }

        except Exception as e:
            return self._fallback_incomplete(user_input, error=str(e))

    async def _generate_clarification(self, missing_info: List[str], questions: List[str]) -> str:
        """生成友好的追问文字"""
        try:
            prompt = CLARIFICATION_PROMPT.format(
                missing_info="\n".join(f"- {m}" for m in missing_info),
                questions="\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
            )
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            return getattr(resp, "content", "").strip()
        except Exception:
            return "您的策略描述还需要补充一些信息：\n" + "\n".join(
                f"{i+1}. {q}" for i, q in enumerate(questions[:3])
            )

    def _fallback_incomplete(self, user_input: str, error: str = None) -> Dict[str, Any]:
        return {
            "status": "need_clarification",
            "strategy": {"completeness": "incomplete"},
            "clarification": "您的策略描述需要更多细节，请补充：\n1. 选股范围（主板/创业板/科创板）\n2. 具体的进场条件\n3. 止损和持仓时间",
            "questions": ["选股范围？", "进场条件？", "止损设置？"],
            "parse_error": error,
        }
