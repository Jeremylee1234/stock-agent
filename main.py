"""
Stock Agent 主入口
使用 iFinD HTTP API（Tushare 降级），基于 LangGraph Plan→Act Agent 进行 A 股分析
"""
import asyncio
import json
import sys
from agents.stock_agent_main import StockAnalysisGraph, run_stock_query


def _shorten(value, max_chars: int = 1200) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"...(截断，原始长度 {len(text)} 字符)"


async def _invoke_with_live_steps(graph: StockAnalysisGraph, query: str, thread_id: str) -> str:
    """流式执行并实时打印每一步。"""
    step = 1
    final_answer = ""

    async for event in graph.astream(query, thread_id=thread_id):
        event_type = event.get("event", "")
        name = event.get("name", "unknown")
        data = event.get("data", {}) or {}

        if event_type == "on_tool_start":
            tool_input = data.get("input", {})
            print(f"[步骤 {step}] 调用工具: {name}")
            print(f"  参数: {_shorten(tool_input, 800)}")
        elif event_type == "on_tool_end":
            tool_output = data.get("output", "")
            print(f"  返回: {_shorten(tool_output, 1200)}\n")
            try:
                parsed = json.loads(tool_output) if isinstance(tool_output, str) else {}
                validation = parsed.get("_validation", {}) if isinstance(parsed, dict) else {}
                warnings = validation.get("warnings", []) if isinstance(validation, dict) else []
                if warnings:
                    print("  校验警告:")
                    for w in warnings:
                        print(f"    - {w}")
                    print()
            except Exception:
                pass
            step += 1
        elif event_type == "on_chain_end":
            output = data.get("output")
            if isinstance(output, dict):
                messages = output.get("messages", [])
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", "")
                    if content:
                        final_answer = content

    if not final_answer:
        trace = graph.get_last_trace()
        final_answer = trace.get("final_answer_preview", "")

    return final_answer or "未获取到回答"


def interactive_mode():
    """交互模式"""
    print("初始化 Stock Agent（iFinD 优先 / Tushare 降级）...")
    graph = StockAnalysisGraph()
    print("初始化完成，进入交互模式（输入 quit 退出）")
    print("已开启实时步骤输出：会显示工具调用参数和返回值摘要\n")

    thread_id = "interactive"
    while True:
        try:
            query = input("请输入您的问题: ").strip()
            if not query:
                continue
            if query.lower() in ("quit", "exit", "退出"):
                print("再见！")
                break
            print("\n分析中（实时步骤）...\n")
            answer = asyncio.run(_invoke_with_live_steps(graph, query, thread_id))
            print("=== 最终回答 ===")
            print(answer)
            trace = graph.get_last_trace()
            tool_events = trace.get("tool_events", [])
            if tool_events:
                print("\n--- 调用统计 ---")
                for idx, event in enumerate(tool_events, start=1):
                    tool_name = event.get("tool_name", "unknown")
                    status = event.get("status", "unknown")
                    duration_ms = event.get("duration_ms", 0)
                    print(f"{idx}. {tool_name} | {status} | {duration_ms}ms")
            print()
        except KeyboardInterrupt:
            print("\n再见！")
            break
        except Exception as e:
            print(f"出错: {e}")
            import traceback
            traceback.print_exc()


async def demo():
    """演示模式"""
    graph = StockAnalysisGraph()
    examples = [
        "腾景科技近100个交易日 日换手率低于6%的情况下 未来1日、3日、5日的表现",]

    for q in examples:
        print(f"\n问题: {q}")
        result = await graph.ainvoke(q, thread_id="demo")
        messages = result.get("messages", [])
        if messages:
            print(f"回答: {getattr(messages[-1], 'content', '')[:500]}...")
        print("-" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        asyncio.run(demo())
    else:
        interactive_mode()
