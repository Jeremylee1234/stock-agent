#!/usr/bin/env python3
"""非交互式 Agent 单次问答测试。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "分析贵州茅台最近一周走势，给出简要结论"
    from agents.stock_agent_main import StockAnalysisGraph

    print(f"Query: {query}\n")
    graph = StockAnalysisGraph(print_live_trace=False)
    result = await graph.ainvoke(query, thread_id="smoke-agent")
    messages = result.get("messages", [])
    answer = getattr(messages[-1], "content", "") if messages else ""
    print("=== Answer ===")
    print(answer[:3000])
    if len(answer) > 3000:
        print("...(truncated)")

    trace = graph.get_last_trace()
    events = trace.get("tool_events", [])
    print("\n=== Tools ===")
    for e in events:
        args = json.dumps(e.get("args", {}), ensure_ascii=False)[:120]
        src = ""
        preview = e.get("result_preview", "")
        if "ifind" in preview:
            src = " [ifind]"
        elif "tushare" in preview:
            src = " [tushare]"
        print(f"- {e.get('tool_name')} | {e.get('status')} | {e.get('duration_ms')}ms{src}")
    return 0 if answer else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
