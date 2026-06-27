"""
Tracing / debug utilities for LangChain + LangGraph runs.

What we capture (safe & useful for debugging):
- LLM start/end (model name, prompt snippet length, token usage when available)
- Tool start/end/error (tool name, input args, output summary)

Note:
We do NOT attempt to expose hidden chain-of-thought. Instead we surface
auditable artifacts: prompts, tool arguments, tool outputs, and step summaries.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler


def _safe_json(obj: Any, max_len: int = 6000) -> str:
    """Serialize to JSON (best-effort) and truncate to keep logs readable."""
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + "...(truncated)"
    return s


def summarize_tool_output(output: Any, max_len: int = 800) -> str:
    """Human-friendly summary for tool output without dumping huge payloads."""
    if output is None:
        return "null"
    # If tool returns JSON string, keep it short.
    if isinstance(output, str):
        s = output.strip()
        if len(s) > max_len:
            return s[:max_len] + "...(truncated)"
        return s
    # Common: dict/list
    if isinstance(output, dict):
        keys = list(output.keys())
        preview = {k: output.get(k) for k in keys[:10]}
        return f"dict(keys={keys[:10]}{'...' if len(keys) > 10 else ''}, preview={_safe_json(preview, max_len=max_len)})"
    if isinstance(output, list):
        return f"list(len={len(output)}, head={_safe_json(output[:2], max_len=max_len)})"
    return _safe_json(output, max_len=max_len)


@dataclass
class TraceEvent:
    ts: float
    kind: str  # llm_start/llm_end/tool_start/tool_end/tool_error
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)


class CallbackTracer(BaseCallbackHandler):
    """Collects trace events for LLM + Tool calls."""

    def __init__(self, *, print_live: bool = False):
        self.print_live = print_live
        self.events: List[TraceEvent] = []
        self._t0 = time.time()

    def _emit(self, kind: str, name: str, payload: Optional[Dict[str, Any]] = None):
        ev = TraceEvent(ts=time.time(), kind=kind, name=name, payload=payload or {})
        self.events.append(ev)
        if self.print_live:
            dt_ms = int((ev.ts - self._t0) * 1000)
            print(f"[trace +{dt_ms}ms] {kind} :: {name} :: {_safe_json(ev.payload, max_len=1200)}")

    # ---- LLM callbacks ----
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or (serialized or {}).get("id") or "llm"
        payload = {
            "prompts_count": len(prompts),
            "prompt_chars": [len(p) for p in prompts[:3]],
            "prompt_preview": [p[:400] for p in prompts[:1]],
        }
        self._emit("llm_start", str(name), payload)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = None
        try:
            # Some providers expose usage metadata in different places.
            usage = getattr(response, "llm_output", None) or getattr(response, "usage_metadata", None)
        except Exception:
            usage = None
        self._emit("llm_end", "llm", {"usage": usage})

    # ---- Tool callbacks ----
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or "tool"
        self._emit("tool_start", str(name), {"input": input_str[:2000]})

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self._emit("tool_end", "tool", {"output_summary": summarize_tool_output(output)})

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self._emit("tool_error", "tool", {"error": str(error)})

    def to_steps(self) -> List[Dict[str, Any]]:
        """Convert trace events to UI-friendly steps for streaming."""
        steps: List[Dict[str, Any]] = []
        for ev in self.events:
            steps.append(
                {
                    "stage": f"trace_{ev.kind}",
                    "title": f"[trace] {ev.kind}: {ev.name}",
                    "summary": summarize_tool_output(ev.payload, max_len=500),
                    "detail": ev.payload,
                }
            )
        return steps

