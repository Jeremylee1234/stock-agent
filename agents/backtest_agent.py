"""
回测 Agent - 策略回测与收益评估

流程：
  1. 策略解析（LLM）：自然语言 → 结构化策略 JSON
     - 策略不完整时追问用户，直到信息足够
  2. 信号扫描：历史数据中找出所有满足条件的进场点
  3. 回测计算：模拟每笔交易，计算收益/回撤/胜率等
  4. 报告生成（LLM）：数据 → 自然语言评估报告（流式输出）

与现有架构集成：
  - 复用 StockAnalysisGraph 的 SSE 事件格式
  - 通过 astream_with_events 对外暴露，与 task_routes 无缝对接
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage

from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL
from tools.backtest.strategy_parser import StrategyParser
from tools.backtest.signal_scanner import scan_signals
from tools.backtest.backtest_engine import run_backtest
from tools.backtest.report_generator import ReportGenerator

TODAY_HYPHEN = datetime.now().strftime("%Y-%m-%d")
TODAY_YMD = datetime.now().strftime("%Y%m%d")


class BacktestAgent:
    """
    策略回测 Agent

    支持复杂策略描述，策略不完整时主动追问，
    完整后执行历史回测并流式输出分析报告。
    """

    def __init__(self):
        self.parser = StrategyParser()
        self.reporter = ReportGenerator()
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.3,
            extra_body={"reasoning": False}  # 禁用思考模式
        )
        # 多轮对话历史（按 thread_id 存储）
        self._conversations: Dict[str, List[Dict]] = {}

    def _get_history(self, thread_id: str) -> List[Dict]:
        return self._conversations.get(thread_id, [])

    def _append_history(self, thread_id: str, role: str, content: str):
        if thread_id not in self._conversations:
            self._conversations[thread_id] = []
        self._conversations[thread_id].append({"role": role, "content": content})
        # 只保留最近10轮
        self._conversations[thread_id] = self._conversations[thread_id][-20:]

    async def astream_with_events(
        self, query: str, config: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行回测，yield 标准化 SSE 事件（与 StockAnalysisGraph 格式一致）
        """
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "default")
        workflow_start = time.time()

        # ── workflow_start ────────────────────────────────────────────────
        yield _evt("workflow_start", {
            "session_id": thread_id,
            "query": query,
            "timestamp": _ts(),
        })

        self._append_history(thread_id, "user", query)
        history = self._get_history(thread_id)

        # ── Stage 1: 策略解析 ─────────────────────────────────────────────
        yield _evt("stage_start", {
            "stage": "analyze_question",
            "title": "策略解析",
            "description": "正在理解您的策略描述…",
            "timestamp": _ts(),
        })

        t0 = time.time()
        parse_result = await self.parser.parse(query, conversation_history=history[:-1])
        parse_ms = _ms(t0)

        # 策略不完整 → 追问
        if parse_result["status"] == "need_clarification":
            clarification = parse_result["clarification"]
            self._append_history(thread_id, "assistant", clarification)

            yield _evt("stage_complete", {
                "stage": "analyze_question",
                "summary": "策略信息不完整，需要补充",
                "duration_ms": parse_ms,
                "timestamp": _ts(),
            })

            # 流式输出追问内容
            yield _evt("stage_start", {
                "stage": "generate_answer",
                "title": "策略确认",
                "description": "需要您补充策略细节",
                "timestamp": _ts(),
            })

            for chunk in _split_chunks(clarification, 50):
                yield _evt("analysis_chunk", {
                    "stage": "generate_answer",
                    "content": chunk,
                    "is_final": False,
                    "timestamp": _ts(),
                })
                await asyncio.sleep(0)

            yield _evt("stage_complete", {
                "stage": "generate_answer",
                "summary": "等待用户补充策略信息",
                "duration_ms": 0,
                "timestamp": _ts(),
            })
            yield _evt("final_answer", {
                "content": clarification,
                "metadata": {
                    "type": "clarification",
                    "questions": parse_result.get("questions", []),
                    "total_duration_ms": _ms(workflow_start),
                },
                "timestamp": _ts(),
            })
            yield _evt("workflow_complete", {
                "session_id": thread_id,
                "status": "need_clarification",
                "timestamp": _ts(),
            })
            return

        # 策略完整
        strategy = parse_result["strategy"]
        strategy_name = strategy.get("strategy_name", "自定义策略")

        yield _evt("stage_complete", {
            "stage": "analyze_question",
            "summary": f"策略解析完成：{strategy_name}",
            "duration_ms": parse_ms,
            "timestamp": _ts(),
        })

        # 推送执行计划
        bt_cfg = strategy.get("backtest_config", {})
        yield _evt("execution_plan", {
            "question_type": "backtest",
            "stock_codes": [],
            "workflow_stages": [
                {"stage_id": 1, "title": "策略解析", "goal": "将自然语言策略转为结构化参数"},
                {"stage_id": 2, "title": "信号扫描", "goal": f"在 {bt_cfg.get('start_date','20200101')}~{bt_cfg.get('end_date','today')} 历史数据中扫描进场信号"},
                {"stage_id": 3, "title": "回测计算", "goal": "模拟每笔交易，计算收益和风险指标"},
                {"stage_id": 4, "title": "报告生成", "goal": "生成策略评估报告"},
            ],
            "key_points": [
                f"策略类型：{strategy.get('strategy_type', '')}",
                f"止损：{strategy.get('exit_rules', {}).get('stop_loss_pct', -8)}%",
                f"最大持仓：{strategy.get('exit_rules', {}).get('max_hold_days', 30)}天",
            ],
            "risk_points": [],
            "timestamp": _ts(),
        })

        # ── Stage 2: 信号扫描 ─────────────────────────────────────────────
        yield _evt("stage_start", {
            "stage": "collect_data",
            "title": "历史信号扫描",
            "description": "正在历史数据中扫描满足策略条件的进场点…",
            "timestamp": _ts(),
        })

        start_date = bt_cfg.get("start_date", "20200101")
        end_date = bt_cfg.get("end_date", TODAY_YMD)
        if end_date in ("today", None, ""):
            end_date = TODAY_YMD

        scanned_count = [0]
        total_stocks = [0]

        def progress_cb(current: int, total: int, ts_code: str):
            scanned_count[0] = current
            total_stocks[0] = total

        # 在线程池中运行同步扫描（避免阻塞事件循环）
        t0 = time.time()
        try:
            signals = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: scan_signals(
                    strategy=strategy,
                    start_date=start_date,
                    end_date=end_date,
                    max_stocks=300,
                    progress_callback=progress_cb,
                )
            )
        except Exception as e:
            yield _evt("error", {
                "error_code": "SCAN_ERROR",
                "error_message": f"信号扫描失败：{str(e)}",
                "error_detail": str(e),
                "recoverable": False,
                "timestamp": _ts(),
            })
            yield _evt("workflow_complete", {"session_id": thread_id, "status": "error", "timestamp": _ts()})
            return

        scan_ms = _ms(t0)

        yield _evt("tool_result", {
            "tool_name": "signal_scanner",
            "tool_id": "scan_1",
            "status": "success",
            "summary": f"扫描完成：共扫描 {total_stocks[0]} 只股票，找到 {len(signals)} 个进场信号",
            "timestamp": _ts(),
        })

        yield _evt("stage_complete", {
            "stage": "collect_data",
            "summary": f"找到 {len(signals)} 个历史进场信号（扫描 {total_stocks[0]} 只股票）",
            "duration_ms": scan_ms,
            "timestamp": _ts(),
        })

        if not signals:
            msg = "在指定时间范围内未找到满足策略条件的历史信号。\n\n可能原因：\n1. 策略条件过于严格\n2. 回测时间范围内市场环境不符合\n3. 建议放宽部分条件后重试"
            self._append_history(thread_id, "assistant", msg)
            yield _evt("final_answer", {
                "content": msg,
                "metadata": {"total_duration_ms": _ms(workflow_start), "signals_found": 0},
                "timestamp": _ts(),
            })
            yield _evt("workflow_complete", {"session_id": thread_id, "status": "success", "timestamp": _ts()})
            return

        # ── Stage 3: 回测计算 ─────────────────────────────────────────────
        yield _evt("stage_start", {
            "stage": "analyze_data",
            "title": "回测计算",
            "description": f"正在对 {len(signals)} 个信号进行回测模拟…",
            "timestamp": _ts(),
        })

        t0 = time.time()
        try:
            backtest_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_backtest(signals, strategy)
            )
        except Exception as e:
            yield _evt("error", {
                "error_code": "BACKTEST_ERROR",
                "error_message": f"回测计算失败：{str(e)}",
                "recoverable": False,
                "timestamp": _ts(),
            })
            yield _evt("workflow_complete", {"session_id": thread_id, "status": "error", "timestamp": _ts()})
            return

        bt_ms = _ms(t0)
        summary = backtest_result.get("summary", {})

        yield _evt("tool_result", {
            "tool_name": "backtest_engine",
            "tool_id": "bt_1",
            "status": "success",
            "summary": (
                f"回测完成：{summary.get('total_trades', 0)} 笔交易，"
                f"胜率 {summary.get('win_rate_pct', 0):.1f}%，"
                f"平均收益 {summary.get('avg_return_pct', 0):.2f}%"
            ),
            "timestamp": _ts(),
        })

        yield _evt("stage_complete", {
            "stage": "analyze_data",
            "summary": f"回测完成，共 {summary.get('total_trades', 0)} 笔交易",
            "duration_ms": bt_ms,
            "timestamp": _ts(),
        })

        # ── Stage 4: 报告生成（流式）─────────────────────────────────────
        yield _evt("stage_start", {
            "stage": "generate_answer",
            "title": "生成评估报告",
            "description": "正在生成策略分析报告…",
            "timestamp": _ts(),
        })

        t0 = time.time()
        report_chunks = []

        async def on_chunk(chunk: str):
            report_chunks.append(chunk)
            # 直接 yield 到外层（通过闭包）
            pass

        # 先推送结构化数据摘要
        structured_summary = _build_structured_summary(backtest_result, strategy)
        yield _evt("analysis_chunk", {
            "stage": "generate_answer",
            "content": structured_summary,
            "is_final": False,
            "timestamp": _ts(),
        })

        # 流式生成 LLM 报告
        report_text_chunks = []
        async for chunk in self._stream_report(strategy, backtest_result):
            report_text_chunks.append(chunk)
            yield _evt("analysis_chunk", {
                "stage": "generate_answer",
                "content": chunk,
                "is_final": False,
                "timestamp": _ts(),
            })

        report_text = "".join(report_text_chunks)
        gen_ms = _ms(t0)

        full_answer = structured_summary + "\n\n" + report_text
        self._append_history(thread_id, "assistant", full_answer[:500])  # 只存摘要

        yield _evt("stage_complete", {
            "stage": "generate_answer",
            "summary": f"报告生成完毕（{len(full_answer)} 字）",
            "duration_ms": gen_ms,
            "timestamp": _ts(),
        })

        yield _evt("final_answer", {
            "content": full_answer,
            "metadata": {
                "type": "backtest_report",
                "total_duration_ms": _ms(workflow_start),
                "signals_found": len(signals),
                "trades_count": summary.get("total_trades", 0),
                "win_rate_pct": summary.get("win_rate_pct", 0),
                "avg_return_pct": summary.get("avg_return_pct", 0),
                "tools_used": ["signal_scanner", "backtest_engine"],
            },
            "timestamp": _ts(),
        })

        yield _evt("workflow_complete", {
            "session_id": thread_id,
            "status": "success",
            "timestamp": _ts(),
        })

    async def _stream_report(
        self, strategy: Dict, backtest_result: Dict
    ) -> AsyncGenerator[str, None]:
        """流式生成 LLM 分析报告"""
        summary = backtest_result.get("summary", {})
        trades = backtest_result.get("trades", [])
        by_year = backtest_result.get("by_year", {})
        by_board = backtest_result.get("by_board", {})

        sorted_trades = sorted(trades, key=lambda x: x["net_return_pct"])
        sample = {
            "最佳3笔": [_fmt_trade(t) for t in sorted_trades[-3:][::-1]],
            "最差3笔": [_fmt_trade(t) for t in sorted_trades[:3]],
        }

        input_data = {
            "策略名称": strategy.get("strategy_name", "自定义策略"),
            "回测区间": f"{strategy.get('backtest_config', {}).get('start_date', '')} ~ {strategy.get('backtest_config', {}).get('end_date', 'today')}",
            "出场规则": strategy.get("exit_rules", {}),
            "汇总指标": summary,
            "分年度": by_year,
            "分板块": by_board,
            "典型案例": sample,
        }

        user_content = (
            f"回测数据：\n```json\n"
            f"{json.dumps(input_data, ensure_ascii=False, indent=2, default=str)}\n```\n\n"
            "请生成完整的策略评估报告。"
        )

        from tools.backtest.report_generator import REPORT_PROMPT
        messages = [
            SystemMessage(content=REPORT_PROMPT),
            HumanMessage(content=user_content),
        ]

        async for chunk in self.model.astream(messages):
            content = getattr(chunk, "content", "") or ""
            if content:
                yield content


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _evt(event_type: str, data: Dict) -> Dict:
    return {"event_type": event_type, "data": data}


def _ts() -> str:
    return datetime.now().isoformat()


def _ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def _split_chunks(text: str, size: int = 50) -> List[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def _fmt_trade(t: Dict) -> str:
    return (
        f"{t.get('ts_code','')} | {t.get('entry_date','')} 进场 "
        f"@{t.get('entry_price',0):.2f} → {t.get('exit_date','')} 出场 "
        f"@{t.get('exit_price',0):.2f} | "
        f"净收益 {t.get('net_return_pct',0):.2f}% | "
        f"出场原因：{t.get('exit_reason','')}"
    )


def _build_structured_summary(backtest_result: Dict, strategy: Dict) -> str:
    """构建结构化数据摘要（Markdown 表格）"""
    s = backtest_result.get("summary", {})
    by_year = backtest_result.get("by_year", {})
    trades = backtest_result.get("trades", [])

    lines = [
        f"## 📊 {strategy.get('strategy_name', '策略')} 回测结果",
        "",
        "### 核心指标",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总交易次数 | {s.get('total_trades', 0)} 笔 |",
        f"| 胜率 | {s.get('win_rate_pct', 0):.1f}% |",
        f"| 平均净收益 | {s.get('avg_return_pct', 0):.2f}% |",
        f"| 平均盈利 | {s.get('avg_win_pct', 0):.2f}% |",
        f"| 平均亏损 | {s.get('avg_loss_pct', 0):.2f}% |",
        f"| 盈亏比 | {s.get('profit_factor', 0)} |",
        f"| 夏普比率 | {s.get('sharpe_ratio', 0):.2f} |",
        f"| 最大单笔收益 | {s.get('max_return_pct', 0):.2f}% |",
        f"| 最大单笔亏损 | {s.get('min_return_pct', 0):.2f}% |",
        f"| 最大连续亏损次数 | {s.get('max_consecutive_losses', 0)} 次 |",
        f"| 平均持仓天数 | {s.get('avg_hold_days', 0):.1f} 天 |",
        f"| 累计收益（100万本金） | {s.get('total_return_pct', 0):.2f}% |",
        "",
    ]

    # 出场原因分布
    exit_dist = s.get("exit_reason_dist", {})
    if exit_dist:
        lines += [
            "### 出场原因分布",
            "| 原因 | 次数 |",
            "|------|------|",
        ]
        reason_map = {"stop_loss": "止损", "take_profit": "止盈", "max_hold": "到期出场", "data_end": "数据截止"}
        for reason, count in exit_dist.items():
            lines.append(f"| {reason_map.get(reason, reason)} | {count} |")
        lines.append("")

    # 分年度
    if by_year:
        lines += [
            "### 分年度表现",
            "| 年份 | 交易次数 | 胜率 | 平均收益 | 年度总收益 |",
            "|------|---------|------|---------|-----------|",
        ]
        for year, data in sorted(by_year.items()):
            lines.append(
                f"| {year} | {data['trades']} | {data['win_rate_pct']:.1f}% "
                f"| {data['avg_return_pct']:.2f}% | {data['total_return_pct']:.2f}% |"
            )
        lines.append("")

    # 典型案例（前5笔）
    if trades:
        sorted_trades = sorted(trades, key=lambda x: x["net_return_pct"])
        top5 = sorted_trades[-5:][::-1]
        lines += [
            "### 典型成功案例（收益最高5笔）",
            "| 股票 | 板块 | 连板数 | 进场日 | 出场日 | 净收益 | 出场原因 |",
            "|------|------|--------|--------|--------|--------|---------|",
        ]
        for t in top5:
            lines.append(
                f"| {t.get('ts_code','')} | {t.get('board','')} | {t.get('streak_count',0)}板 "
                f"| {t.get('entry_date','')} | {t.get('exit_date','')} "
                f"| {t.get('net_return_pct',0):.2f}% | {t.get('exit_reason','')} |"
            )
        lines.append("")

    return "\n".join(lines)
