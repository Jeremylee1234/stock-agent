"""
股票分析 LangGraph Agent - 基于 iFinD HTTP API（Tushare 降级）
根据用户输入智能分析并调用 iFinD / Tushare 接口获取数据，给出完整分析结果。

架构：Plan → Act
  1. Planner LLM：先将用户问题拆解为有序步骤（每步含目标、工具、字段）
  2. ReAct Agent：按步骤执行，每步思考过程和工具调用实时打印到终端并通过 SSE 推送
"""
import asyncio
import json
import time
import os
import threading
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import re

TODAY_YMD = datetime.now().strftime("%Y%m%d")
TODAY_HYPHEN = datetime.now().strftime("%Y-%m-%d")

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.prebuilt import create_react_agent

from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL, get_settings
from tools.ifind.unit_registry import IFIND_UNITS_PROMPT, get_units_for_records
from tools.tool_param_guide import (
    get_tool_param_prompt,
    get_tool_spec_summary,
    get_tool_param_hint,
    enrich_plan_with_inferred_args,
    build_act_user_message,
)
from tools.ifind_bridge import (
    fetch_daily_ifind_df,
    merge_local_and_ifind_payload,
    payload_to_json,
    df_to_payload,
    attach_tushare_units,
    try_ifind_financial,
    try_ifind_financial_series,
    try_ifind_moneyflow_history,
    try_ifind_data_pool,
    try_ifind_smart_picking,
    wrap_ifind_payload,
)
from tools.data_sources.ifind_adapter import get_ifind_adapter
from tools.ifind.client import IFindAPIError
from agents.state import AgentState
from utils.logger import get_logger

logger = get_logger(name="stock_analysis", log_level="INFO", console_output=True, file_output=True)

MAX_QUERY_CHARS = int(os.getenv("STOCK_AGENT_MAX_QUERY_CHARS", "1200000"))
MAX_RETRY_QUERY_CHARS = int(os.getenv("STOCK_AGENT_MAX_RETRY_QUERY_CHARS", "25000"))
MAX_TOOL_JSON_CHARS = int(os.getenv("STOCK_AGENT_MAX_TOOL_JSON_CHARS", "1200000"))
MAX_TOOL_LIST_ITEMS = int(os.getenv("STOCK_AGENT_MAX_TOOL_LIST_ITEMS", "2000"))
MAX_TOOL_STR_CHARS = int(os.getenv("STOCK_AGENT_MAX_TOOL_STR_CHARS", "600"))

TOKEN_LIMIT_ERROR_PATTERNS = (
    "maximum context length",
    "max token",
    "context_length_exceeded",
    "token limit",
    "prompt is too long",
)

# ============================================================================
# Tushare Pro（降级数据源）
# ============================================================================
from tools.tushare_client import pro

# ============================================================================
# Tushare API 并发控制（解决并发限制问题）
# ============================================================================
# Tushare Pro 并发上限为2个，使用信号量控制并发
_tushare_semaphore = threading.Semaphore(2)
_tushare_lock = threading.Lock()
_tushare_retry_config = {
    'max_retries': 10,  # 增加重试次数
    'base_delay': 3,  # 基础等待时间（秒）
    'max_delay': 120,  # 最大等待时间（秒）- 允许等待2分钟
    'retry_on_errors': [
        '并发请求过多',
        'too many concurrent',
        'rate limit',
        '请求过于频繁',
        '您的并发',
        'waiting',
        '上限',
    ]
}


def _tushare_api_call_with_retry(func, *args, **kwargs):
    """
    带重试机制的Tushare API调用
    解决并发限制问题（并发上限2个）
    """
    last_error = None
    
    for attempt in range(_tushare_retry_config['max_retries']):
        # 获取信号量（最多2个并发）
        acquired = _tushare_semaphore.acquire(timeout=120)
        if not acquired:
            logger.warning(f"Tushare API信号量获取超时，等待重试...")
            time.sleep(5)
            continue
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_msg = str(e).lower()
            last_error = e
            
            # 检查是否是并发限制错误
            is_rate_limit = any(err in error_msg for err in _tushare_retry_config['retry_on_errors'])
            
            if is_rate_limit:
                # 计算等待时间（指数退避）
                delay = min(
                    _tushare_retry_config['base_delay'] * (2 ** attempt),
                    _tushare_retry_config['max_delay']
                )
                logger.warning(f"Tushare API并发限制，等待 {delay}秒后重试 (尝试 {attempt + 1}/{_tushare_retry_config['max_retries']}): {e}")
                time.sleep(delay)
            else:
                # 非并发限制错误，直接抛出
                raise e
        finally:
            _tushare_semaphore.release()
    
    # 所有重试都失败
    raise last_error


def _tushare_api_call(func):
    """
    装饰器：为Tushare API调用添加并发控制和重试机制
    """
    def wrapper(*args, **kwargs):
        return _tushare_api_call_with_retry(func, *args, **kwargs)
    return wrapper


def _validate_fields_param(fields: str, tool_name: str, available_fields: str) -> Optional[str]:
    """
    验证fields参数是否为空，如果为空则返回错误信息。
    这是强制性的安全检查，确保agent必须为每个工具调用指定fields参数。
    """
    if not fields or fields.strip() == '':
        spec_hint = get_tool_param_hint(tool_name) or {}
        field_examples = spec_hint.get("fields_examples") or {
            '价格趋势分析': 'trade_date,close,pct_chg,vol',
            '估值分析': 'trade_date,pe_ttm,pb,total_mv,circ_mv',
            '盈利能力分析': 'end_date,roe,roa,netprofit_margin,grossprofit_margin',
            '财务健康分析': 'end_date,debt_to_assets,current_ratio,quick_ratio',
            '资金流向分析': 'trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount',
        }
        return json.dumps({
            'error': '必须指定 fields 参数！请根据用户问题和分析目的选择最小必要字段集。',
            'error_code': 'FIELDS_REQUIRED',
            'tool_name': tool_name,
            'required_params': spec_hint.get('required', []),
            'suggestion': spec_hint.get('infer') or '先阅读执行计划中的 args_hint/fields_hint，或参考 available_fields 与 examples 后重试。',
            'available_fields': available_fields,
            'examples': field_examples,
        }, ensure_ascii=False)
    return None


def _to_ts_code(stock_code: str) -> str:
    if not stock_code:
        return ""
    code = str(stock_code).strip()
    if "." in code:
        return code
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith("0") or code.startswith("3"):
        return f"{code}.SZ"
    if code.startswith("4") or code.startswith("8") or code.startswith("9"):
        return f"{code}.BJ"
    return f"{code}.SH"


def _fmt(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    return ''.join(c for c in str(date_str) if c.isdigit())[:8] or None


def _wrap(df, ts_code: str = None, data_source: str = "tushare") -> dict:
    import pandas as pd
    if df is None or (hasattr(df, 'empty') and df.empty):
        return {'error': '未查询到数据'}
    payload = df_to_payload(df, ts_code=ts_code, data_source=data_source)
    if data_source == "ifind" and payload.get("success"):
        payload["_field_units"] = get_units_for_records(payload["data"], source="ifind_native")
        payload["_units_source"] = "ifind_native"
    return payload


def _fetch_daily_df_fallback(tc: str, sd: str, ed: str, fields: str, cps: str = "2"):
    """优先 iFinD，失败降级 Tushare pro.daily。"""
    df = fetch_daily_ifind_df(tc, sd, ed, fields, cps=cps)
    if df is not None and not df.empty:
        return df, "ifind"
    try:
        df = _tushare_api_call_with_retry(
            pro.daily, ts_code=tc, start_date=sd, end_date=ed, fields=fields
        )
        if df is not None and not df.empty:
            return df, "tushare"
    except Exception as exc:
        logger.warning(f"Tushare daily fallback failed: {exc}")
    return None, None


def _json_from_df(
    df,
    tc: str,
    data_source: str,
    sd: str = None,
    ed: str = None,
    tail_limit: int = None,
    extra: dict = None,
) -> str:
    import pandas as pd
    if df is None or df.empty:
        return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
    df = df.sort_values("trade_date").reset_index(drop=True) if "trade_date" in df.columns else df
    data_count = len(df)
    return_df = df.tail(tail_limit) if tail_limit and data_count > tail_limit else df
    payload = {
        "success": True,
        "ts_code": tc,
        "data": return_df.to_dict("records"),
        "count": data_count,
        "data_source": data_source,
    }
    if tail_limit and data_count > tail_limit:
        payload["returned_count"] = tail_limit
        payload["note"] = f"数据量较大({data_count}条)，已返回最近{tail_limit}条。"
    if sd and ed:
        payload["date_range"] = f"{sd} 至 {ed}"
    if extra:
        payload.update(extra)
    if data_source == "ifind":
        payload["_field_units"] = get_units_for_records(payload["data"], source="ifind_native")
        payload["_units_source"] = "ifind_native"
    elif data_source == "tushare":
        attach_tushare_units(payload)
    elif data_source in ("mixed", "local_parquet", "local_parquet_ifind"):
        payload["_field_units"] = get_units_for_records(
            payload["data"],
            source="local_parquet_ifind" if "local" in data_source else "mixed",
        )
        payload["_units_source"] = data_source
    return json.dumps(payload, ensure_ascii=False, default=str)


def _try_ifind_fina(
    tc: str,
    period: str = None,
    fields: str = None,
    start_date: str = None,
    end_date: str = None,
) -> Optional[dict]:
    return try_ifind_financial(
        tc,
        fields=fields,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )


def _try_ifind_statement(
    tc: str,
    start_date: str,
    end_date: str,
    fields: str,
    default_fields: str,
    tail: int = 8,
) -> Optional[str]:
    sd = _fmt(start_date) or (datetime.now() - timedelta(days=365 * 3)).strftime("%Y%m%d")
    ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
    payload = try_ifind_financial_series(tc, sd, ed, fields or default_fields)
    if not payload or not payload.get("success"):
        return None
    data = list(payload.get("data") or [])
    if data:
        sort_key = "end_date" if any("end_date" in r for r in data) else "trade_date"
        data = sorted(data, key=lambda x: x.get(sort_key, ""), reverse=True)[:tail]
        payload["data"] = data
        payload["returned_count"] = len(data)
        payload["ts_code"] = tc
    return payload_to_json(payload)


def _clamp_today(end_date: str) -> str:
    if end_date and end_date > TODAY_YMD:
        return TODAY_YMD
    return end_date or TODAY_YMD


def _normalize_date(date_str: str, fallback: str) -> str:
    if not date_str:
        return fallback
    s = str(date_str).strip().replace("-", "").replace(".", "").replace("/", "")
    return s if len(s) == 8 and s.isdigit() else fallback


def _clip_text(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...(已截断，原始长度 {len(text)} 字符)"


def _compact_for_model(value: Any, depth: int = 0) -> Any:
    """压缩工具返回，防止过长 observation 触发 token 超限。"""
    if depth > 4:
        return str(value)[:MAX_TOOL_STR_CHARS]

    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            compacted[key] = _compact_for_model(item, depth + 1)
        return compacted

    if isinstance(value, list):
        sliced = value[:MAX_TOOL_LIST_ITEMS]
        compacted = [_compact_for_model(item, depth + 1) for item in sliced]
        if len(value) > MAX_TOOL_LIST_ITEMS:
            compacted.append(
                {
                    "_truncated": True,
                    "original_count": len(value),
                    "kept_count": MAX_TOOL_LIST_ITEMS,
                }
            )
        return compacted

    if isinstance(value, str):
        return _clip_text(value, MAX_TOOL_STR_CHARS)

    return value


def _summarize_text(text: Any, max_chars: int = 240) -> str:
    s = str(text)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "..."


def _safe_tool_output(raw_result: Any) -> str:
    """把工具返回压缩成安全字符串（优先保持 JSON 结构）。"""
    if raw_result is None:
        return json.dumps({"success": False, "error": "工具返回为空"}, ensure_ascii=False)

    if not isinstance(raw_result, str):
        raw_result = str(raw_result)

    if len(raw_result) <= MAX_TOOL_JSON_CHARS:
        return raw_result

    try:
        payload = json.loads(raw_result)
    except Exception:
        return _clip_text(raw_result, MAX_TOOL_JSON_CHARS)

    compacted = _compact_for_model(payload)
    output = json.dumps(compacted, ensure_ascii=False, default=str)
    if len(output) <= MAX_TOOL_JSON_CHARS:
        return output

    # 兜底：继续截断（保持整体可读）
    return _clip_text(output, MAX_TOOL_JSON_CHARS)


def _validate_tool_payload(tool_name: str, safe_result: str) -> Dict[str, Any]:
    """
    对工具返回进行基础校验，降低后续模型误读概率。
    返回结构:
    {
      "payload": dict,
      "normalized_result": str,
      "status": "success" | "error",
      "error": Optional[str],
      "warnings": List[str]
    }
    """
    warnings: List[str] = []
    try:
        payload = json.loads(safe_result)
    except Exception as exc:
        payload = {
            "success": False,
            "error": f"{tool_name} 返回非 JSON 格式，已判定为不可用结果",
            "raw_preview": _summarize_text(safe_result, 300),
        }
        warnings.append(f"JSON 解析失败: {exc}")
        payload["_validation"] = {
            "passed": False,
            "warnings": warnings,
            "checked_at": datetime.now().isoformat(),
        }
        return {
            "payload": payload,
            "normalized_result": json.dumps(payload, ensure_ascii=False, default=str),
            "status": "error",
            "error": payload["error"],
            "warnings": warnings,
        }

    if not isinstance(payload, dict):
        payload = {"success": True, "data": payload}
        warnings.append("工具返回 JSON 根节点不是对象，已自动包装为 {success,data}")

    has_error = bool(payload.get("error"))
    has_data = "data" in payload
    declared_count = payload.get("count")
    data_obj = payload.get("data")

    if has_error and has_data:
        warnings.append("返回同时包含 error 与 data，已按 error 优先处理")

    if has_data and isinstance(data_obj, list):
        actual_count = len(data_obj)
        if isinstance(declared_count, int) and declared_count != actual_count:
            warnings.append(f"count({declared_count}) 与 data长度({actual_count}) 不一致，已修正 count")
            payload["count"] = actual_count
        elif declared_count is None:
            payload["count"] = actual_count
    elif has_data and not isinstance(data_obj, (dict, list)):
        warnings.append("data 字段不是 list/dict，模型解释时需谨慎")
    elif not has_error and not has_data:
        warnings.append("返回既无 data 也无 error，信息不足")

    if payload.get("success") is True and has_error:
        payload["success"] = False
        warnings.append("success 与 error 冲突，已将 success 修正为 false")
    elif payload.get("success") is None:
        payload["success"] = not has_error

    payload["_validation"] = {
        "passed": (not has_error) and (len(warnings) == 0),
        "warnings": warnings,
        "checked_at": datetime.now().isoformat(),
    }

    normalized = json.dumps(payload, ensure_ascii=False, default=str)
    if len(normalized) > MAX_TOOL_JSON_CHARS:
        normalized = _safe_tool_output(normalized)

    return {
        "payload": payload,
        "normalized_result": normalized,
        "status": "error" if has_error else "success",
        "error": str(payload.get("error")) if has_error else None,
        "warnings": warnings,
    }


def _is_token_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(pattern in msg for pattern in TOKEN_LIMIT_ERROR_PATTERNS)


def _prepare_query(query: str, max_chars: int = MAX_QUERY_CHARS) -> str:
    return _clip_text(query.strip(), max_chars)


# ============================================================================
# LangChain 工具定义（同步包装 Tushare Pro 调用）
# ============================================================================

def _run_sync(coro):
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool(description="""获取股票历史日线行情及均线（MA5/10/20/30/60）。

【调用前必填参数】
- stock_code (str): 股票代码，如 "600519" 或 "600519.SH"；从用户问题中提取
- fields (str): 逗号分隔字段，**必填**；例 "trade_date,close,pct_chg,vol"

【可选参数】
- start_date (str): 开始日期 YYYYMMDD；用户未说明时默认约30个交易日前
- end_date (str): 结束日期 YYYYMMDD；默认今天

【用户意图 → fields 示例】
- 走势/涨跌 → trade_date,close,pct_chg,vol
- 技术分析 → trade_date,open,high,low,close,vol
- 量价 → trade_date,close,pct_chg,vol,amount

字段单位见返回 JSON 的 _field_units（iFinD: vol=股, amount=元；Tushare降级: vol=手, amount=千元）""")
def tool_get_stock_history(stock_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        import pandas as pd
        from tools.local_stock_data import get_stock_history_from_local, check_date_in_local_range, LOCAL_DATA_END
        
        tc = _to_ts_code(stock_code)
        
        # 智能默认时间窗口：如果没有指定start_date，根据是否指定end_date决定
        if start_date is None:
            if end_date is None:
                # 既没有start_date也没有end_date：默认获取最近30天（短期分析）
                sd = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            else:
                # 只有end_date：默认获取end_date前30天
                ed_date = datetime.strptime(_normalize_date(end_date, TODAY_YMD), "%Y%m%d")
                sd = (ed_date - timedelta(days=30)).strftime("%Y%m%d")
        else:
            sd = _normalize_date(start_date, (datetime.now() - timedelta(days=30)).strftime("%Y%m%d"))
        
        ed = _clamp_today(_normalize_date(end_date, TODAY_YMD))
        
        # 检查fields参数是否为空 - 这是强制性的安全检查
        fields_error = _validate_fields_param(fields, 'tool_get_stock_history', 
                                             'ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount')
        if fields_error:
            return fields_error
        
        # 确保 close 字段存在（用于计算均线）
        field_list = [f.strip() for f in fields.split(',')]
        if 'close' not in field_list:
            field_list.append('close')
        if 'trade_date' not in field_list:
            field_list.append('trade_date')
        fetch_fields = ','.join(field_list)
        
        # 优先从本地Parquet读取，如果日期范围超出本地数据则分段处理
        data_source = "mixed"
        df = None
        
        # 检查日期范围是否在本地数据范围内
        if check_date_in_local_range(sd, ed):
            # 日期完全在本地范围内，尝试从本地读取
            local_result = get_stock_history_from_local(tc, sd, ed, fetch_fields)
            if local_result.get('success') and local_result.get('data'):
                df = pd.DataFrame(local_result['data'])
                data_source = "local_parquet"
                logger.info(f"从本地Parquet读取 {tc} {sd}-{ed}，共{len(df)}条数据")
            else:
                logger.warning(f"本地读取失败，fallback到 iFinD: {local_result.get('error')}")
                data_source = "ifind"
        else:
            # 日期部分或完全超出本地范围，需要分段处理
            # 获取本地数据的最新日期
            local_end_dt = datetime.strptime(LOCAL_DATA_END, "%Y-%m-%d")
            query_start_dt = datetime.strptime(sd, "%Y%m%d")
            query_end_dt = datetime.strptime(ed, "%Y%m%d")
            
            # 如果查询开始日期在本地数据范围内
            if query_start_dt <= local_end_dt:
                # 分段：本地 + iFinD 增量
                local_end_str = local_end_dt.strftime("%Y%m%d")
                local_result = get_stock_history_from_local(tc, sd, local_end_str, fetch_fields)
                ifind_df = None
                if query_end_dt > local_end_dt:
                    ifind_start = (local_end_dt + timedelta(days=1)).strftime("%Y%m%d")
                    ifind_df, _ = _fetch_daily_df_fallback(tc, ifind_start, ed, fetch_fields, cps="2")
                    if ifind_df is not None and not ifind_df.empty:
                        logger.info(f"从 iFinD 读取 {tc} {ifind_start}-{ed}，共{len(ifind_df)}条")
                if local_result.get("success"):
                    merged = merge_local_and_ifind_payload(local_result, ifind_df)
                    if merged.get("success"):
                        df = pd.DataFrame(merged["data"])
                        data_source = merged.get("data_source", "mixed")
                    else:
                        df = ifind_df
                        data_source = "ifind"
                elif ifind_df is not None and not ifind_df.empty:
                    df = ifind_df
                    data_source = "ifind"
                else:
                    df = None
            else:
                logger.info(f"查询日期 {sd}-{ed} 超出本地范围 {LOCAL_DATA_END}，使用 iFinD")
                data_source = "ifind"

        if data_source in ("ifind", "tushare") or df is None:
            df, src = _fetch_daily_df_fallback(tc, sd, ed, fetch_fields, cps="2")
            if df is not None and not df.empty:
                data_source = src

        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)

        if "close" in df.columns:
            for p in [5, 10, 20, 30, 60]:
                df[f"ma{p}"] = df["close"].rolling(p).mean().round(4)

        return _json_from_df(df, tc, data_source, sd=sd, ed=ed, tail_limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股票每日基本指标：PE、PB、换手率、总市值、流通市值、量比等。

【调用前必填参数】
- stock_code (str): 股票代码，如 "600519"
- fields (str): 逗号分隔，**必填**；估值例 "trade_date,pe_ttm,pb,total_mv,circ_mv"

【可选参数】
- trade_date (str): 指定单日 YYYYMMDD
- start_date / end_date (str): 日期范围；未说明时默认近30日

【用户意图 → fields 示例】
- 估值/PE/PB → trade_date,pe_ttm,pb,total_mv,circ_mv
- 流动性/换手 → trade_date,turnover_rate,turnover_rate_f,volume_ratio

可选全部字段：ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,
        pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv
分析类型提示（供agent参考）：
- 估值分析：建议获取最近20-30个交易日，字段：trade_date,pe_ttm,pb,total_mv,circ_mv
- 流动性分析：建议获取最近30个交易日，字段：trade_date,turnover_rate,turnover_rate_f,volume_ratio
- 综合指标分析：根据具体需求选择字段，避免获取不必要字段
字段单位说明：
  close: 元（人民币）
  turnover_rate / turnover_rate_f: % 换手率（全部/自由流通）
  volume_ratio: 倍（量比）
  pe / pe_ttm / pb / ps / ps_ttm: 倍（估值倍数）
  dv_ratio / dv_ttm: % 股息率
  total_share / float_share / free_share: 万股
  total_mv / circ_mv: 万元""")
def tool_get_daily_basic(stock_code: str, trade_date: str = None, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        
        # 检查fields参数是否为空 - 这是强制性的安全检查
        fields_error = _validate_fields_param(fields, 'tool_get_daily_basic',
                                             'ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv')
        if fields_error:
            return fields_error
        
        if trade_date:
            sd = ed = _fmt(trade_date) or TODAY_YMD
        elif start_date is None and end_date is None:
            sd = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            ed = TODAY_YMD
        else:
            sd = _fmt(start_date) or (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            ed = _clamp_today(_fmt(end_date) or TODAY_YMD)

        df, src = _fetch_daily_df_fallback(tc, sd, ed, fields, cps="1")
        if df is None or df.empty:
            if trade_date:
                df = _tushare_api_call_with_retry(
                    pro.daily_basic, ts_code=tc, trade_date=_fmt(trade_date), fields=fields
                )
            else:
                df = _tushare_api_call_with_retry(
                    pro.daily_basic, ts_code=tc, start_date=sd, end_date=ed, fields=fields
                )
            src = "tushare"
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        return _json_from_df(df, tc, src, tail_limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股票财务指标：ROE、ROA、毛利率、净利率、EPS 等。
stock_code: 股票代码
period: 报告期，如 '20231231'（可选）
start_date / end_date: 报告期范围（可选，默认获取最近4个报告期）
fields: 可选字段（逗号分隔），常用字段：ts_code,ann_date,end_date,eps,dt_eps,
        roe,roe_waa,roe_dt,roa,netprofit_margin,grossprofit_margin,
        debt_to_assets,current_ratio,quick_ratio,
        netprofit_yoy,tr_yoy,or_yoy,basic_eps_yoy,
        ebit,ebitda,fcff,bps,ocfps
        不填返回全部字段（字段多，强烈建议按需选择！）
分析类型提示（供agent参考）：
- 盈利能力分析：建议字段：end_date,roe,roa,netprofit_margin,grossprofit_margin,netprofit_yoy
- 财务健康分析：建议字段：end_date,debt_to_assets,current_ratio,quick_ratio,fcff
- EPS分析：建议字段：end_date,eps,dt_eps,basic_eps_yoy
- 综合财务分析：根据具体需求选择核心字段，避免获取不必要字段
字段单位说明：
  eps / dt_eps / bps / ocfps: 元/股
  roe / roe_waa / roe_dt / roa: % 收益率
  netprofit_margin / grossprofit_margin: % 利润率
  debt_to_assets: % 资产负债率
  current_ratio / quick_ratio: 倍（流动/速动比率）
  netprofit_yoy / tr_yoy / or_yoy / basic_eps_yoy: % 同比增长率
  ebit / ebitda / fcff: 元（人民币）""")
def tool_get_fina_indicator(stock_code: str, period: str = None, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        payload = _try_ifind_fina(
            tc,
            period=_fmt(period),
            fields=fields,
            start_date=_fmt(start_date),
            end_date=_fmt(end_date),
        )
        if payload and payload.get("success"):
            data = payload.get("data", [])
            if period is None and start_date is None and end_date is None and len(data) > 6:
                data = sorted(data, key=lambda x: x.get("end_date", ""), reverse=True)[:6]
                payload["returned_count"] = 6
                payload["note"] = "已返回最近6个报告期"
            payload["data"] = data
            payload["count"] = len(data)
            return payload_to_json(payload)

        if period is None and start_date is None and end_date is None:
            df = _tushare_api_call_with_retry(pro.fina_indicator, ts_code=tc, fields=fields)
            if df is not None and not df.empty:
                df = df.sort_values("end_date", ascending=False).head(4)
        else:
            df = _tushare_api_call_with_retry(
                pro.fina_indicator,
                ts_code=tc,
                period=_fmt(period),
                start_date=_fmt(start_date),
                end_date=_fmt(end_date),
                fields=fields,
            )
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        pl = df_to_payload(df.head(6), ts_code=tc, data_source="tushare")
        return payload_to_json(pl)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取利润表数据：营业收入、营业成本、净利润等。
stock_code: 股票代码
start_date / end_date: 报告期范围（可选）
fields: 可选字段（逗号分隔），常用字段：ts_code,ann_date,end_date,report_type,
        basic_eps,diluted_eps,total_revenue,revenue,total_cogs,oper_cost,
        sell_exp,admin_exp,fin_exp,assets_impair_loss,
        operate_profit,total_profit,income_tax,n_income,n_income_attr_p,
        ebit,ebitda,rd_exp
        不填返回全部字段（字段极多，强烈建议按需选择）
字段单位说明：
  basic_eps / diluted_eps: 元/股
  total_revenue / revenue / total_cogs / oper_cost: 元（人民币）
  sell_exp / admin_exp / fin_exp / assets_impair_loss: 元
  operate_profit / total_profit / income_tax / n_income / n_income_attr_p: 元
  ebit / ebitda / rd_exp: 元""")
def tool_get_income(stock_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        ifind_json = _try_ifind_statement(
            tc, start_date, end_date, fields,
            "total_revenue,n_income,operate_profit,basic_eps,total_profit",
        )
        if ifind_json:
            return ifind_json
        df = _tushare_api_call_with_retry(pro.income, ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date), fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        return json.dumps({'success': True, 'ts_code': tc, 'data': df.head(8).to_dict('records'), 'count': len(df)}, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取资产负债表：总资产、总负债、股东权益等。
stock_code: 股票代码
start_date / end_date: 报告期范围（可选）
fields: 可选字段（逗号分隔），常用字段：ts_code,ann_date,end_date,report_type,
        total_assets,total_liab,total_hldr_eqy_exc_min_int,total_hldr_eqy_inc_min_int,
        money_cap,accounts_receiv,inventories,fix_assets,
        st_borr,lt_borr,bond_payable,total_cur_assets,total_cur_liab
        不填返回全部字段（字段极多，强烈建议按需选择）
字段单位说明：
  total_assets / total_liab: 元（人民币）
  total_hldr_eqy_exc_min_int / total_hldr_eqy_inc_min_int: 元
  money_cap / accounts_receiv / inventories / fix_assets: 元
  st_borr / lt_borr / bond_payable: 元（短期/长期借款、应付债券）
  total_cur_assets / total_cur_liab: 元（流动资产/负债合计）""")
def tool_get_balancesheet(stock_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        ifind_json = _try_ifind_statement(
            tc, start_date, end_date, fields,
            "total_assets,total_liab,total_hldr_eqy_exc_min_int",
        )
        if ifind_json:
            return ifind_json
        df = _tushare_api_call_with_retry(pro.balancesheet, ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date), fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        return json.dumps({'success': True, 'ts_code': tc, 'data': df.head(8).to_dict('records'), 'count': len(df)}, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取现金流量表：经营/投资/筹资活动现金流。
stock_code: 股票代码
start_date / end_date: 报告期范围（可选）
fields: 可选字段（逗号分隔），常用字段：ts_code,ann_date,end_date,report_type,
        n_cashflow_act,n_cash_flows_inv_act,n_cash_flows_fnc_act,
        c_pay_acq_const_fiolta,stot_cash_in_oper,stot_cash_out_oper,
        free_cashflow
        不填返回全部字段（字段极多，强烈建议按需选择）
字段单位说明：
  n_cashflow_act: 元（经营活动现金流净额）
  n_cash_flows_inv_act: 元（投资活动现金流净额）
  n_cash_flows_fnc_act: 元（筹资活动现金流净额）
  stot_cash_in_oper / stot_cash_out_oper: 元（经营活动现金流入/流出合计）
  c_pay_acq_const_fiolta / free_cashflow: 元""")
def tool_get_cashflow(stock_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        ifind_json = _try_ifind_statement(
            tc, start_date, end_date, fields,
            "n_cashflow_act,n_cash_flows_inv_act,n_cash_flows_fnc_act",
        )
        if ifind_json:
            return ifind_json
        df = _tushare_api_call_with_retry(pro.cashflow, ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date), fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        return json.dumps({'success': True, 'ts_code': tc, 'data': df.head(8).to_dict('records'), 'count': len(df)}, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取业绩预告（预增/预减/扭亏/首亏等）。
stock_code: 股票代码（可选）
start_date / end_date: 公告日期范围（可选）
fields: 可选字段（逗号分隔），可选：ts_code,ann_date,end_date,type,p_change_min,p_change_max,
        net_profit_min,net_profit_max,last_parent_net,change_reason
        例如只看业绩变动幅度可填 'ann_date,type,p_change_min,p_change_max'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  p_change_min / p_change_max: % 预计净利润变动幅度（最小/最大）
  net_profit_min / net_profit_max: 万元（预计净利润最小/最大值）
  last_parent_net: 万元（上年同期归母净利润）""")
def tool_get_forecast(stock_code: str = None, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = _tushare_api_call_with_retry(pro.forecast, ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date), fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        if data_count > 10:
            return_data = df.head(10)
            return json.dumps({
                'success': True, 
                'data': return_data.to_dict('records'), 
                'count': data_count,
                'returned_count': 10,
                'note': f'数据量较大({data_count}条)，已返回前10条。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'data': df.to_dict('records'), 
                'count': data_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取分红送股数据。
stock_code: 股票代码
fields: 可选字段（逗号分隔），可选：ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,
        stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date
        例如只看分红方案可填 'end_date,div_proc,stk_div,cash_div'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  div_proc: 分红方案进度状态
  stk_div: 股（每股送转股数）
  stk_bo_rate: 股（每股送股比例）
  stk_co_rate: 股（每股转增比例）
  cash_div: 元/股（每股现金分红，税前）
  cash_div_tax: 元/股（每股现金分红，税后）
  record_date / ex_date / pay_date: 日期""")
def tool_get_dividend(stock_code: str, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        payload = try_ifind_financial(
            tc,
            fields=fields or "cash_div,stk_div",
            period=None,
        )
        if payload and payload.get("success"):
            return payload_to_json(payload)
        df = _tushare_api_call_with_retry(pro.dividend, ts_code=tc, fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        # if data_count > 10:
        #     return_data = df.head(10)
        #     return json.dumps({
        #         'success': True, 
        #         'ts_code': tc, 
        #         'data': return_data.to_dict('records'), 
        #         'count': data_count,
        #         'returned_count': 10,
        #         'note': f'数据量较大({data_count}条)，已返回前10条。'
        #     }, ensure_ascii=False, default=str)
        # else:
        return json.dumps({
            'success': True, 
            'ts_code': tc, 
            'data': df.to_dict('records'), 
            'count': data_count
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取前十大股东及前十大流通股东数据。
stock_code: 股票代码
period: 报告期，如 '20230930'（可选）
fields: 可选字段（逗号分隔），可选：ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,
        holder_type,inst_type,inst_province
        例如只看持股比例可填 'end_date,holder_name,hold_amount,hold_ratio'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  hold_amount: 股（持股数量）
  hold_ratio: % 持股比例""")
def tool_get_holders(stock_code: str, period: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        result = {}
        
        # 解析fields参数，如果没有指定则使用默认字段
        if fields:
            field_list = [f.strip() for f in fields.split(',')]
        else:
            field_list = ['ts_code', 'ann_date', 'end_date', 'holder_name', 'hold_amount', 'hold_ratio']
        
        fetch_fields = ','.join(field_list) if fields else None
        
        df1 = pro.top10_holders(ts_code=tc, period=_fmt(period), fields=fetch_fields)
        result['top10_holders'] = df1.to_dict('records') if df1 is not None and not df1.empty else []
        df2 = pro.top10_floatholders(ts_code=tc, period=_fmt(period), fields=fetch_fields)
        result['top10_float_holders'] = df2.to_dict('records') if df2 is not None and not df2.empty else []
        
        total_count = len(result.get('top10_holders', [])) + len(result.get('top10_float_holders', []))
        
        if total_count > 20:
            # 数据太多，限制返回数量
            for key in ['top10_holders', 'top10_float_holders']:
                if key in result and len(result[key]) > 10:
                    result[key] = result[key][:10]
            
            return json.dumps({
                'success': True, 
                'ts_code': tc, 
                'data': result, 
                'total_count': total_count,
                'returned_count': min(20, total_count),
                'note': f'数据量较大({total_count}条)，已返回前20条。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'ts_code': tc, 
                'data': result,
                'total_count': total_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取个股资金流向（大单/中单/小单买卖净额）。
stock_code: 股票代码
start_date / end_date: 日期范围（可选）
fields: 可选字段（逗号分隔），可选：ts_code,trade_date,
        buy_sm_vol,buy_sm_amount,sell_sm_vol,sell_sm_amount,
        buy_md_vol,buy_md_amount,sell_md_vol,sell_md_amount,
        buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,
        buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount,
        net_mf_vol,net_mf_amount
        例如只看净流入可填 'trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount'
字段单位说明：
  buy_*/sell_*_vol / net_mf_vol: 手（成交量）
  buy_*/sell_*_amount / net_mf_amount: 万元（成交金额）""")
def tool_get_moneyflow(stock_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        sd = _fmt(start_date)
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        if sd and ed:
            payload = try_ifind_moneyflow_history(tc, sd, ed, fields)
            if payload and payload.get("success"):
                data = payload.get("data", [])
                if len(data) > 30:
                    payload["data"] = sorted(data, key=lambda x: x.get("trade_date", ""))[-30:]
                    payload["returned_count"] = 30
                return payload_to_json(payload)
        if not start_date and not end_date:
            try:
                adapter = get_ifind_adapter()
                if adapter.is_available():
                    payload = adapter.get_realtime_quotation(
                        tc, "mainNetInflow,largeNetInflow,bigNetInflow,latest,changeRatio"
                    )
                    if payload.get("success"):
                        return payload_to_json(payload)
            except IFindAPIError:
                pass
        df = _tushare_api_call_with_retry(
            pro.moneyflow, ts_code=tc, start_date=sd, end_date=ed, fields=fields
        )
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        df = df.sort_values("trade_date")
        pl = df_to_payload(df.tail(30), ts_code=tc, data_source="tushare")
        return payload_to_json(pl)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取龙虎榜数据（上榜原因、买卖金额）。
trade_date: 交易日期 YYYYMMDD（可选）
stock_code: 股票代码（可选）
fields: 可选字段（逗号分隔），可选：ts_code,trade_date,name,close,pct_chg,turnover_rate,
        buy_value,sell_value,net_value,amount,reason
        例如只看买卖金额可填 'trade_date,name,buy_value,sell_value,net_value'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  close: 元（收盘价）
  pct_chg: % 涨跌幅
  turnover_rate: % 换手率
  buy_value / sell_value: 万元（买入/卖出金额）
  net_value: 万元（净买入金额）
  amount: 万元（当日总成交额）""")
def tool_get_top_list(trade_date: str = None, stock_code: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        payload = try_ifind_smart_picking("龙虎榜", "stock")
        if payload and payload.get("success"):
            data = payload.get("data", [])
            if tc:
                data = [r for r in data if r.get("ts_code") == tc]
                payload["data"] = data
                payload["count"] = len(data)
            payload["note"] = "iFinD smart_stock_picking（龙虎榜）"
            return wrap_ifind_payload(payload, limit=20)
        df = _tushare_api_call_with_retry(pro.top_list, trade_date=_fmt(trade_date), ts_code=tc, fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        if data_count > 20:
            return_data = df.head(20)
            return json.dumps({
                'success': True, 
                'data': return_data.to_dict('records'), 
                'count': data_count,
                'returned_count': 20,
                'note': f'数据量较大({data_count}条)，已返回前20条。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'data': df.to_dict('records'), 
                'count': data_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取涨跌停列表。
trade_date: 交易日期 YYYYMMDD
limit_type: U 涨停 / D 跌停，默认 U
fields: 可选字段（逗号分隔），可选：ts_code,trade_date,name,close,pct_chg,fd_amount,
        first_time,last_time,open_times,strth,limit
        例如只看涨停强度可填 'trade_date,name,close,pct_chg,strth'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  close: 元（收盘价）
  pct_chg: % 涨跌幅
  fd_amount: 万元（封单金额）
  first_time / last_time: 时间（首次/最后封板时间）
  open_times: 次（炸板次数）
  strth: % 封板强度""")
def tool_get_limit_list(trade_date: str, limit_type: str = "U", fields: str = None) -> str:
    try:
        td = _fmt(trade_date) or TODAY_YMD
        keyword = "跌停" if str(limit_type).upper() == "D" else "涨停"
        payload = try_ifind_smart_picking(keyword, "stock")
        if payload and payload.get("success"):
            payload["trade_date"] = td
            payload["limit_type"] = limit_type
            payload["note"] = f"iFinD smart_stock_picking（{keyword}）"
            return wrap_ifind_payload(payload, limit=30)
        df = _tushare_api_call_with_retry(pro.limit_list_d, trade_date=td, limit_type=limit_type, fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        if data_count > 30:
            return_data = df.head(30)
            return json.dumps({
                'success': True, 
                'data': return_data.to_dict('records'), 
                'count': data_count,
                'returned_count': 30,
                'note': f'数据量较大({data_count}条)，已返回前30条。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'data': df.to_dict('records'), 
                'count': data_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取指数日线行情（上证指数、深证成指、创业板指等）。
ts_code: 指数代码，如 '000001.SH'（上证综指）、'399001.SZ'（深证成指）、'399006.SZ'（创业板指）
start_date / end_date: 日期范围（可选）
fields: 可选字段（逗号分隔），可选：ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount
        例如只看涨跌幅可填 'trade_date,close,pct_chg,vol'
字段单位说明：
  open/high/low/close/pre_close/change: 点（指数点位）
  pct_chg: % 涨跌幅
  vol: 手
  amount: 万元""")
def tool_get_index_daily(ts_code: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        df, src = _fetch_daily_df_fallback(ts_code, sd, ed, fields or "trade_date,open,high,low,close,pct_chg,vol", cps="1")
        if df is None or df.empty:
            df = _tushare_api_call_with_retry(
                pro.index_daily, ts_code=ts_code, start_date=sd, end_date=ed, fields=fields
            )
            src = "tushare"
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        return _json_from_df(df, ts_code, src, tail_limit=60)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取大盘指数每日指标（PE/PB/股息率等）。
ts_code: 指数代码，如 '000001.SH'
trade_date: 指定日期 YYYYMMDD（可选）
start_date / end_date: 日期范围（可选）
fields: 可选字段（逗号分隔），可选：ts_code,trade_date,total_mv,float_mv,total_share,
        float_share,free_share,turnover_rate,turnover_rate_f,pe,pe_ttm,pb,dv_ratio,dv_ttm
        例如只看估值指标可填 'trade_date,pe_ttm,pb,dv_ratio'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明：
  total_mv / float_mv: 万元（总市值/流通市值）
  total_share / float_share: 万股（总股本/流通股本）
  free_share: 万股（自由流通股本）
  turnover_rate / turnover_rate_f: % 换手率
  pe / pe_ttm / pb: 倍（估值倍数）
  dv_ratio / dv_ttm: % 股息率""")
def tool_get_index_dailybasic(ts_code: str, trade_date: str = None, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or _fmt(trade_date) or TODAY_YMD)
        fld = fields or "trade_date,pe_ttm,pb,turnover_rate,total_mv"
        df, src = _fetch_daily_df_fallback(ts_code, sd, ed, fld, cps="1")
        if df is None or df.empty:
            df = _tushare_api_call_with_retry(
                pro.index_dailybasic,
                ts_code=ts_code,
                trade_date=_fmt(trade_date),
                start_date=sd,
                end_date=ed,
                fields=fields,
            )
            src = "tushare"
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        return _json_from_df(df, ts_code, src, tail_limit=30)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取股票基础信息（代码、名称、行业、上市日期等）。
exchange: 交易所 SSE/SZSE/BSE（可选）
list_status: 上市状态 L上市 D退市，默认 L
fields: 可选字段（逗号分隔），可选：ts_code,symbol,name,area,industry,market,list_date,
        fullname,enname,cnspell,exchange,curr_type,list_status,is_hs
        例如只看基本信息可填 'ts_code,symbol,name,industry,list_date'
        强烈建议根据分析目的选择最小必要字段集！""")
def tool_get_stock_basic(exchange: str = None, list_status: str = "L", fields: str = None) -> str:
    try:
        # 如果没有指定fields，使用最小必要字段集
        if not fields:
            fields = 'ts_code,symbol,name,area,industry,market,list_date'
        
        df = _tushare_api_call_with_retry(pro.stock_basic, exchange=exchange, list_status=list_status, fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        if data_count > 50:
            return_data = df.head(50)
            return json.dumps({
                'success': True, 
                'data': return_data.to_dict('records'), 
                'count': data_count,
                'returned_count': 50,
                'note': f'数据量较大({data_count}条)，已返回前50条。如需更多数据请指定更具体的筛选条件。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'data': df.to_dict('records'), 
                'count': data_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取上市公司基本信息（注册资本、法人代表、主营业务等）。
stock_code: 股票代码
fields: 可选字段（逗号分隔），可选：ts_code,chairman,manager,secretary,reg_capital,
        setup_date,province,city,introduction,website,email,office,employees,
        main_business,business_scope
        例如只看公司概况可填 'ts_code,chairman,reg_capital,province,main_business'
        强烈建议根据分析目的选择最小必要字段集！""")
def tool_get_stock_company(stock_code: str, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        df = _tushare_api_call_with_retry(pro.stock_company, ts_code=tc, fields=fields)
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 通常只有一条记录，但确保格式一致
        data_count = len(df)
        return json.dumps({
            'success': True, 
            'ts_code': tc, 
            'data': df.to_dict('records'),
            'count': data_count
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# iFinD EDB 宏观指标 ID（可按账号在超级命令中扩展）
IFIND_EDB_BY_TYPE = {
    "gdp": "M001620326",
    "cpi": "M002822183",
    "ppi": "M002845824",
    "m": "M0001385M0001",
}


@tool(description="""获取宏观经济数据：GDP、CPI、PPI、货币供应量（M0/M1/M2）、Shibor 利率。
data_type: 数据类型，可选 'gdp' / 'cpi' / 'ppi' / 'm' / 'shibor'
start_date / end_date: 日期范围（可选）
fields: 可选字段（逗号分隔），根据data_type不同可选字段不同：
  - gdp: period,gdp,gdp_yoy,pi,pi_yoy,si,si_yoy,ti,ti_yoy
  - cpi: month,nt_val,nt_yoy,town_val,town_yoy,cnt_val,cnt_yoy
  - ppi: month,ppi_yoy,ppi_mp_yoy,ppi_mp_mom,ppi_cg_yoy,ppi_cg_mom
  - m: month,m0,m0_yoy,m1,m1_yoy,m2,m2_yoy
  - shibor: date,on,1w,2w,1m,3m,6m,9m,1y
        例如只看GDP增长率可填 'period,gdp_yoy'
        强烈建议根据分析目的选择最小必要字段集！
字段单位说明（按 data_type）：
  gdp: gdp/gdp_yoy（亿元/% 同比）; pi/pi_yoy（亿元/% 第一产业）; si/si_yoy（亿元/% 第二产业）; ti/ti_yoy（亿元/% 第三产业）
  cpi: nt_val/nt_yoy（全国当月值/% 同比）; town_val/town_yoy（城市）; cnt_val/cnt_yoy（农村）
  ppi: ppi_yoy/ppi_mp_yoy 等（% 同比）
  m: m0/m1/m2（亿元）; m0_yoy/m1_yoy/m2_yoy（% 同比）
  shibor: on/1w/2w/1m/3m/6m/9m/1y（% 各期限利率）""")
def tool_get_macro_data(data_type: str, start_date: str = None, end_date: str = None, fields: str = None) -> str:
    try:
        dt = data_type.lower().strip()
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)

        if dt != "shibor":
            edb_id = IFIND_EDB_BY_TYPE.get(dt)
            if edb_id:
                try:
                    adapter = get_ifind_adapter()
                    if adapter.is_available():
                        payload = adapter.get_edb(edb_id, sd, ed)
                        if payload.get("success"):
                            payload["data_type"] = dt
                            data = payload.get("data", [])
                            if len(data) > 24:
                                payload["data"] = data[-24:]
                                payload["returned_count"] = 24
                                payload["note"] = f"已返回最近24条"
                            return payload_to_json(payload)
                except IFindAPIError as e:
                    logger.warning(f"iFinD EDB {dt}: {e}")

        # 根据data_type调用不同的API
        if dt == 'gdp':
            df = _tushare_api_call_with_retry(pro.cn_gdp, start_date=sd, end_date=ed, fields=fields)
        elif dt == 'cpi':
            df = _tushare_api_call_with_retry(pro.cn_cpi, start_date=sd, end_date=ed, fields=fields)
        elif dt == 'ppi':
            df = _tushare_api_call_with_retry(pro.cn_ppi, start_date=sd, end_date=ed, fields=fields)
        elif dt == 'm':
            df = _tushare_api_call_with_retry(pro.cn_m, start_date=sd, end_date=ed, fields=fields)
        elif dt == 'shibor':
            df = _tushare_api_call_with_retry(pro.shibor, start_date=sd, end_date=ed, fields=fields)
        else:
            return json.dumps({'error': f'不支持的数据类型: {data_type}，可选: gdp/cpi/ppi/m/shibor'}, ensure_ascii=False)
        
        if df is None or df.empty:
            return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
        
        # 智能返回数据量
        data_count = len(df)
        if data_count > 24:
            return_data = df.tail(24)
            return json.dumps({
                'success': True, 
                'data_type': dt, 
                'data': return_data.to_dict('records'), 
                'count': data_count,
                'returned_count': 24,
                'note': f'数据量较大({data_count}条)，已返回最近24条。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({
                'success': True, 
                'data_type': dt, 
                'data': df.to_dict('records'), 
                'count': data_count
            }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取概念板块分类及成份股。
action: 'list' 获取板块列表 / 'detail' 获取成份股
concept_id: 概念板块 ID（action='detail' 时必填）
stock_code: 股票代码（可选，查询该股所属概念）
fields: 可选字段（逗号分隔），可选：id,concept_name,src,ts_code,name,in_date,out_date
        例如只看概念名称和股票可填 'concept_name,ts_code,name'
        强烈建议根据分析目的选择最小必要字段集！
字段说明：
  id: 概念板块ID
  concept_name: 概念名称
  src: 数据来源
  ts_code: 股票代码
  name: 股票名称
  in_date / out_date: 纳入/移出日期""")
def tool_get_concept(action: str = "list", concept_id: str = None, stock_code: str = None, fields: str = None) -> str:
    try:
        if action == "list":
            df = _tushare_api_call_with_retry(pro.concept, src="ts", fields=fields)
            if df is None or df.empty:
                return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
            
            # 智能返回数据量
            data_count = len(df)
            if data_count > 30:
                return_data = df.head(30)
                return json.dumps({
                    'success': True, 
                    'data': return_data.to_dict('records'), 
                    'count': data_count,
                    'returned_count': 30,
                    'note': f'数据量较大({data_count}条)，已返回前30条。'
                }, ensure_ascii=False, default=str)
            else:
                return json.dumps({
                    'success': True, 
                    'data': df.to_dict('records'), 
                    'count': data_count
                }, ensure_ascii=False, default=str)
        else:
            tc = _to_ts_code(stock_code) if stock_code else None
            df = _tushare_api_call_with_retry(pro.concept_detail, id=concept_id, ts_code=tc, fields=fields)
            if df is None or df.empty:
                return json.dumps({'error': '未查询到数据'}, ensure_ascii=False)
            
            # 智能返回数据量
            data_count = len(df)
            if data_count > 50:
                return_data = df.head(50)
                return json.dumps({
                    'success': True, 
                    'data': return_data.to_dict('records'), 
                    'count': data_count,
                    'returned_count': 50,
                    'note': f'数据量较大({data_count}条)，已返回前50条。'
                }, ensure_ascii=False, default=str)
            else:
                return json.dumps({
                    'success': True, 
                    'data': df.to_dict('records'), 
                    'count': data_count
                }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""搜索历史相似走势（如连续跌停、MACD金叉等模式）并统计后续表现。
pattern_description: 模式描述，如"连续三次跌停"、"MACD金叉"
stock_code: 可选，指定股票
start_date / end_date: 搜索日期范围（可选）
max_results: 最多返回匹配数，默认 20
lookahead_days: 后续分析天数，如 "5,10,20"（可选）
fields: 可选字段（逗号分隔），用于获取匹配股票的详细数据，可选：ts_code,trade_date,open,high,low,close,pct_chg,vol,amount
        例如只看价格和成交量可填 'trade_date,close,pct_chg,vol'
        强烈建议根据分析目的选择最小必要字段集！
字段说明：
  ts_code: 股票代码
  trade_date: 交易日期
  open/high/low/close: 开盘/最高/最低/收盘价（元）
  pct_chg: % 涨跌幅
  vol: 手（成交量）
  amount: 千元（成交金额）""")
def tool_search_similar_pattern(
    pattern_description: str,
    stock_code: str = None,
    start_date: str = None,
    end_date: str = None,
    max_results: int = 20,
    lookahead_days: str = "5,10,20",
    fields: str = None,
) -> str:
    try:
        from tools.stock_analysis_tool import search_similar_pattern
        result = _run_sync(search_similar_pattern(
            pattern_description=pattern_description,
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results,
            lookahead_days=lookahead_days,
            fields=fields,
        ))
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""分段获取股票历史数据，适用于需要大量历史数据的分析场景。
当需要分析多年趋势但一次性获取数据量太大时，使用此工具分段获取。
stock_code: 股票代码
total_years: 需要分析的总年数（如：3表示3年）
segment_years: 每段获取的年数（默认1，表示每次获取1年数据）
fields: 需要获取的字段（逗号分隔），强烈建议只选择必要字段！
analysis_goal: 分析目标描述，用于指导分段策略
使用示例：先获取第1段（最近1年）数据进行分析，如果不够再获取第2段（前1年）数据，依此类推。
注意：此工具返回的是当前段的数据，agent需要记录已获取的数据段，并在需要时继续获取下一段。""")
def tool_get_segmented_history(
    stock_code: str,
    total_years: int = 3,
    segment_years: int = 1,
    fields: str = "trade_date,close,pct_chg,vol",
    analysis_goal: str = "长期趋势分析"
) -> str:
    """
    分段获取股票历史数据
    """
    try:
        import pandas as pd
        tc = _to_ts_code(stock_code)
        
        # 计算日期范围
        end_date = TODAY_YMD
        start_date = (datetime.now() - timedelta(days=total_years*365)).strftime("%Y%m%d")
        
        # 计算当前段的范围（从最近开始）
        # 这里简化实现：直接获取全部数据，但标注分段信息
        # 实际应用中，agent应该记录当前段索引
        
        df, src = _fetch_daily_df_fallback(tc, start_date, end_date, fields, cps="2")
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        
        df = df.sort_values('trade_date').reset_index(drop=True)
        total_count = len(df)
        
        # 计算分段信息
        segments = []
        current_date = datetime.strptime(end_date, "%Y%m%d")
        for i in range(total_years // segment_years + 1):
            segment_end = current_date
            segment_start = current_date - timedelta(days=segment_years*365)
            
            # 过滤出该时间段的数据
            segment_df = df[
                (df['trade_date'] >= segment_start.strftime("%Y%m%d")) & 
                (df['trade_date'] <= segment_end.strftime("%Y%m%d"))
            ]
            
            if len(segment_df) > 0:
                segments.append({
                    'segment_id': i + 1,
                    'start_date': segment_start.strftime("%Y%m%d"),
                    'end_date': segment_end.strftime("%Y%m%d"),
                    'count': len(segment_df),
                    'years': segment_years
                })
            
            current_date = segment_start - timedelta(days=1)
        
        # 返回第一段数据（最近的一段）
        if segments:
            current_segment = segments[0]
            segment_df = df[
                (df['trade_date'] >= current_segment['start_date']) & 
                (df['trade_date'] <= current_segment['end_date'])
            ]
            
            return json.dumps({
                'success': True,
                'ts_code': tc,
                'data': segment_df.to_dict('records'),
                'current_segment': current_segment,
                'total_segments': len(segments),
                'total_data_count': total_count,
                'segments': segments,
                'note': f'数据已分段，共{len(segments)}段。当前返回第1段（最近{segment_years}年）。如需更多数据，请继续获取下一段。',
                'analysis_goal': analysis_goal,
                'recommendation': '建议先分析当前段数据，如果结论不够充分再获取下一段。'
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({'error': '无法分段数据'}, ensure_ascii=False)
            
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


def get_all_tools():
    """返回所有可用工具列表（核心 + 扩展）"""
    from tools.tushare_extra_tools import get_extra_tools
    from tools.data_filter_tools import get_data_filter_tools
    core = [
        tool_get_stock_history,
        tool_get_daily_basic,
        tool_get_fina_indicator,
        tool_get_income,
        tool_get_balancesheet,
        tool_get_cashflow,
        tool_get_forecast,
        tool_get_dividend,
        tool_get_holders,
        tool_get_moneyflow,
        tool_get_top_list,
        tool_get_limit_list,
        tool_get_index_daily,
        tool_get_index_dailybasic,
        tool_get_stock_basic,
        tool_get_stock_company,
        tool_get_macro_data,
        tool_get_concept,
        tool_search_similar_pattern,
        tool_get_segmented_history,  # 新增：分段获取工具
    ]
    return core + get_extra_tools() + get_data_filter_tools()


# ============================================================================
# 终端彩色打印工具
# ============================================================================

_COLORS = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[36m",
    "yellow": "\033[33m",
    "green":  "\033[32m",
    "red":    "\033[31m",
    "blue":   "\033[34m",
    "magenta":"\033[35m",
    "gray":   "\033[90m",
}

def _c(color: str, text: str) -> str:
    return f"{_COLORS.get(color,'')}{text}{_COLORS['reset']}"

def _print_stage(label: str, content: str = "", color: str = "cyan"):
    """打印带分隔线的阶段标题"""
    width = 70
    print(f"\n{_c(color, '─' * width)}")
    print(f"{_c('bold', _c(color, f'  {label}'))}")
    if content:
        print(f"  {content}")
    print(_c(color, '─' * width))

def _print_step(idx: int, total: int, title: str, detail: str = ""):
    print(f"\n{_c('bold', _c('yellow', f'[步骤 {idx}/{total}]'))} {_c('bold', title)}")
    if detail:
        print(f"  {_c('gray', detail)}")

def _print_tool_call(tool_name: str, args: dict):
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items() if v is not None)
    print(f"  {_c('blue', '⚙ 调用工具:')} {_c('bold', tool_name)}({_c('gray', args_str)})")

def _print_tool_result(tool_name: str, status: str, preview: str, duration_ms: int):
    icon = _c('green', '✓') if status == 'success' else _c('red', '✗')
    print(f"  {icon} {_c('gray', tool_name)} 返回 [{duration_ms}ms]: {_c('gray', preview[:200])}")

def _print_thinking(text: str):
    """打印 agent 的思考片段（流式）"""
    print(_c('magenta', text), end='', flush=True)

def _print_final_answer_start():
    _print_stage("最终分析结果", color="green")

def _print_final_answer_end():
    print(f"\n{_c('green', '─' * 70)}\n")


# ============================================================================
# Planner：将用户问题拆解为有序执行步骤
# ============================================================================

PLANNER_PROMPT = f"""你是一个 A 股分析规划师。用户提出了一个分析问题，你需要将其拆解为 2~6 个有序执行步骤。

{get_tool_param_prompt()}

{get_tool_spec_summary()}

每个步骤包含：
- step_id: 步骤序号（从1开始）
- title: 步骤标题（简短，10字以内）
- goal: 本步骤要达成的目标（1~2句话）
- tools: 需要调用的工具列表（从可用工具中选择，可为空列表）
- args_hint: **每个工具的具体调用参数**（JSON 对象，键为 tool 名，值为参数字典）
  示例: {{"tool_get_stock_history": {{"stock_code": "600519", "start_date": "20250501", "end_date": "20250604", "fields": "trade_date,close,pct_chg,vol"}}}}
  规则: stock_code/ts_code/data_type 必填项不能缺；有 fields 的工具必须写 fields
- fields_hint: 每个工具建议获取的字段（与 args_hint 中 fields 保持一致）
- analysis_hint: 拿到数据后如何分析、关注什么指标

同时在计划根级别输出：
- stock_codes: 从用户问题识别出的股票代码列表，如 ["600519"]
- date_hints: 推断的日期范围 {{"start_date": "YYYYMMDD", "end_date": "YYYYMMDD", "note": "推断依据"}}

可用工具（按分类）：
【A股核心】tool_get_stock_history, tool_get_daily_basic, tool_get_fina_indicator,
  tool_get_income, tool_get_balancesheet, tool_get_cashflow, tool_get_forecast,
  tool_get_dividend, tool_get_holders, tool_get_moneyflow, tool_get_top_list,
  tool_get_limit_list, tool_get_index_daily, tool_get_index_dailybasic,
  tool_get_stock_basic, tool_get_stock_company, tool_get_macro_data,
  tool_get_concept, tool_search_similar_pattern, tool_smart_stock_picking
【基础/行情】tool_get_trade_cal, tool_get_new_share, tool_get_hs_const,
  tool_get_adj_factor, tool_get_weekly_monthly, tool_get_suspend_d, tool_get_hsgt_top10
【财务/参考】tool_get_express, tool_get_fina_mainbz, tool_get_share_float,
  tool_get_repurchase, tool_get_holder_trade, tool_get_stk_holdernumber,
  tool_get_pledge_stat, tool_get_block_trade
【资金/打板】tool_get_moneyflow_hsgt, tool_get_moneyflow_ths, tool_get_moneyflow_ind_ths,
  tool_get_moneyflow_mkt_dc, tool_get_limit_list_d, tool_get_limit_cpt_list,
  tool_get_limit_step_list, tool_get_top_inst, tool_get_hm_detail, tool_get_ths_index
【特色数据】tool_get_hk_hold, tool_get_stk_surv, tool_get_report_rc,
  tool_get_cyq_perf, tool_get_stk_nineturn, tool_get_ah_compare
【指数/ETF/基金】tool_get_sw_industry, tool_get_index_member, tool_get_index_weight,
  tool_get_sw_daily, tool_get_index_global, tool_get_fund_basic, tool_get_fund_daily,
  tool_get_fund_share, tool_get_fund_nav, tool_get_fund_portfolio
【债券/期货/期权】tool_get_cb_basic, tool_get_cb_daily, tool_get_yc_cb, tool_get_eco_cal,
  tool_get_fut_basic, tool_get_fut_daily, tool_get_fut_holding, tool_get_fut_mapping,
  tool_get_opt_basic, tool_get_opt_daily
【港股/美股】tool_get_hk_basic, tool_get_hk_daily, tool_get_hk_fina,
  tool_get_us_basic, tool_get_us_daily, tool_get_us_fina
【宏观/融资/新闻】tool_get_cn_pmi, tool_get_lpr, tool_get_sf_month, tool_get_us_tycr,
  tool_get_margin, tool_get_margin_detail, tool_get_news, tool_get_anns, tool_get_sge_daily

只输出 JSON，格式如下（不要有任何额外文字）：
{{
  "analysis_type": "简短描述分析类型，如：个股综合分析/走势分析/财务分析/选股/宏观分析",
  "stock_codes": ["600519"],
  "date_hints": {{"start_date": "20250501", "end_date": "20250604", "note": "用户问最近走势，默认30日"}},
  "steps": [
    {{
      "step_id": 1,
      "title": "步骤标题",
      "goal": "本步骤目标",
      "tools": ["tool_get_stock_history"],
      "args_hint": {{
        "tool_get_stock_history": {{
          "stock_code": "600519",
          "start_date": "20250501",
          "end_date": "20250604",
          "fields": "trade_date,close,pct_chg,vol"
        }}
      }},
      "fields_hint": "tool_get_stock_history: trade_date,close,pct_chg,vol",
      "analysis_hint": "关注哪些指标，如何判断"
    }}
  ]
}}"""


async def _run_planner(query: str, model: Any) -> Dict[str, Any]:
    """调用 LLM 生成执行计划，返回结构化步骤列表"""
    from langchain_core.messages import SystemMessage, HumanMessage as HM
    try:
        resp = await model.ainvoke([
            SystemMessage(content=PLANNER_PROMPT),
            HM(content=f"用户问题：{query}")
        ])
        raw = getattr(resp, "content", "") or ""
        # 提取 JSON（兼容 markdown 代码块）
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            plan = json.loads(match.group())
            return enrich_plan_with_inferred_args(plan, query)
    except Exception as e:
        logger.warning(f"Planner failed: {e}")
    # 降级：返回单步计划并规则推断参数
    fallback = {
        "analysis_type": "综合分析",
        "steps": [{"step_id": 1, "title": "数据获取与分析", "goal": query,
                   "tools": [], "fields_hint": "", "analysis_hint": "综合分析"}]
    }
    return enrich_plan_with_inferred_args(fallback, query)


_INTENT_CLASSIFY_PROMPT = """判断用户问题是否与金融/股票/投资/经济/市场相关。
只输出 JSON，格式：{"is_finance": true} 或 {"is_finance": false}
不要输出任何其他内容。"""

async def _is_finance_query(query: str, model: Any) -> bool:
    """快速判断问题是否属于金融/股票领域，非金融问题跳过 plan 和工具调用。"""
    from langchain_core.messages import SystemMessage, HumanMessage as HM
    try:
        resp = await model.ainvoke([
            SystemMessage(content=_INTENT_CLASSIFY_PROMPT),
            HM(content=query)
        ])
        raw = getattr(resp, "content", "") or ""
        match = re.search(r'\{[\s\S]*?\}', raw)
        if match:
            result = json.loads(match.group())
            return bool(result.get("is_finance", True))
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}, defaulting to finance=True")
    return True  # 分类失败时保守处理，走正常流程


_FINAL_REPORT_SYSTEM_PROMPT = f"""你是专业的 A 股分析师，今天日期是 {TODAY_HYPHEN}。

你将收到用户问题和已收集的数据摘要。请直接撰写最终分析报告。

## 输出要求（必须严格遵守）
1. **只输出分析报告正文**，不要描述任何数据收集过程
2. **禁止**出现以下类型的语句：
   - 「我来分析…」「首先…」「让我查询…」「我需要先了解…」
   - 「token验证」「换个方式查询」「API 错误」「重试」
   - 工具名称、接口名称、查询步骤、执行计划
3. 报告应结构清晰，建议包含：事件/背景、数据要点、影响分析、风险提示、结论
4. 必须基于已提供的数据摘要，不得编造未提供的数据
5. 文末注明：以上分析仅供参考，不构成投资建议

使用 Markdown 格式输出。"""


# ============================================================================
# StockAnalysisGraph - LangGraph 工作流
# ============================================================================

def _build_system_prompt(plan: Dict[str, Any] = None) -> str:
    """构建 system prompt，可选注入执行计划"""
    base = f"""你是一个专业的 A 股分析助手，今天日期是 {TODAY_HYPHEN}。

数据源：优先同花顺 iFinD HTTP API（返回含 _field_units 的单位说明）。
当 iFinD 不可用、无权限或接口无数据时，自动降级 Tushare Pro（单位见 _units_source: tushare）。

已迁移至 iFinD 优先的核心能力：历史行情、每日指标、指数行情、交易日历、复权/周月线、
财务指标/三表、分红、个股资金流、宏观 EDB、公告、同花顺资金流、打板池（data_pool，需账号报表权限）。
其余工具仍以 Tushare 为主，iFinD 能力持续扩展中。

{IFIND_UNITS_PROMPT}

{get_tool_param_prompt()}

你拥有以下数据工具（iFinD 优先）：

【核心工具 - A股】
- tool_get_stock_history: 历史日线行情及均线（智能时间窗口和字段选择）
- tool_get_daily_basic: 每日基本指标（PE/PB/换手率/市值）（智能时间窗口和字段选择）
- tool_get_fina_indicator: 财务指标（ROE/ROA/毛利率/净利率）（智能字段选择）
- tool_get_income: 利润表
- tool_get_balancesheet: 资产负债表
- tool_get_cashflow: 现金流量表
- tool_get_forecast: 业绩预告
- tool_get_dividend: 分红送股
- tool_get_holders: 前十大股东/流通股东
- tool_get_moneyflow: 个股资金流向
- tool_get_top_list: 龙虎榜
- tool_get_limit_list: 涨跌停列表
- tool_get_index_daily: 指数日线行情
- tool_get_index_dailybasic: 大盘指数每日指标
- tool_get_stock_basic: 股票基础信息列表
- tool_get_stock_company: 上市公司基本信息
- tool_get_macro_data: 宏观经济（GDP/CPI/PPI/M/Shibor）
- tool_get_concept: 概念板块
- tool_search_similar_pattern: 历史相似走势
- tool_smart_stock_picking: iFinD 智能选股（涨停/龙虎榜/高ROE/低PE 等自然语言条件）
- tool_get_segmented_history: 分段获取历史数据（适用于大量历史数据分析）

【基础数据】
- tool_get_trade_cal: 交易日历
- tool_get_namechange: 股票曾用名
- tool_get_new_share: IPO新股上市
- tool_get_hs_const: 沪深港通标的列表
- tool_get_stk_rewards: ST/退市风险股票

【行情扩展】
- tool_get_adj_factor: 复权行情（前复权/后复权）
- tool_get_weekly_monthly: 周线/月线行情
- tool_get_suspend_d: 每日停复牌信息
- tool_get_hsgt_top10: 沪深股通十大成交股（北向资金）

【财务扩展】
- tool_get_express: 业绩快报
- tool_get_fina_mainbz: 主营业务构成
- tool_get_fina_audit: 财务审计意见

【参考数据】
- tool_get_share_float: 限售股解禁
- tool_get_repurchase: 股票回购
- tool_get_holder_trade: 股东增减持
- tool_get_stk_holdernumber: 股东人数
- tool_get_pledge_stat: 股权质押统计
- tool_get_block_trade: 大宗交易

【资金流向】
- tool_get_moneyflow_hsgt: 沪深港通资金流向（北向/南向）
- tool_get_moneyflow_ths: 同花顺个股资金流向
- tool_get_moneyflow_ind_ths: 同花顺行业资金流向
- tool_get_moneyflow_mkt_dc: 东方财富大盘资金流向

【打板专题】
- tool_get_limit_list_d: 涨跌停和炸板数据
- tool_get_limit_cpt_list: 涨停最强板块统计
- tool_get_limit_step_list: 涨停连板天梯
- tool_get_top_inst: 龙虎榜机构交易明细
- tool_get_hm_detail: 游资交易每日明细
- tool_get_ths_index: 同花顺行业概念板块行情

【特色数据】
- tool_get_hk_hold: 沪深股通持股明细（北向持仓）
- tool_get_stk_surv: 机构调研数据
- tool_get_report_rc: 券商盈利预测
- tool_get_cyq_perf: 每日筹码及胜率
- tool_get_stk_nineturn: 神奇九转指标
- tool_get_ah_compare: AH股比价

【指数专题】
- tool_get_sw_industry: 申万行业分类列表
- tool_get_index_member: 申万/中信行业成分股
- tool_get_index_weight: 指数成分和权重（沪深300/中证500等）
- tool_get_sw_daily: 申万行业指数日行情
- tool_get_index_global: 国际主要指数（道琼斯/纳斯达克/恒生等）

【ETF/公募基金】
- tool_get_fund_basic: ETF/基金基本信息
- tool_get_fund_daily: ETF日线行情
- tool_get_fund_share: ETF份额规模
- tool_get_fund_nav: 公募基金净值
- tool_get_fund_portfolio: 公募基金持仓

【债券/可转债】
- tool_get_cb_basic: 可转债基础信息
- tool_get_cb_daily: 可转债日线行情
- tool_get_yc_cb: 国债收益率曲线
- tool_get_eco_cal: 全球财经日历事件

【期货】
- tool_get_fut_basic: 期货合约基础信息
- tool_get_fut_daily: 期货日线行情
- tool_get_fut_holding: 期货每日持仓排名
- tool_get_fut_mapping: 期货主力合约映射

【期权】
- tool_get_opt_basic: 期权合约信息
- tool_get_opt_daily: 期权日线行情

【港股】
- tool_get_hk_basic: 港股基础信息
- tool_get_hk_daily: 港股日线行情
- tool_get_hk_fina: 港股财务指标

【美股】
- tool_get_us_basic: 美股基础信息
- tool_get_us_daily: 美股日线行情
- tool_get_us_fina: 美股财务指标

【宏观扩展】
- tool_get_cn_pmi: PMI采购经理指数
- tool_get_lpr: LPR贷款基础利率
- tool_get_sf_month: 社会融资规模增量
- tool_get_us_tycr: 美国国债收益率曲线

【融资融券】
- tool_get_margin: 融资融券交易汇总
- tool_get_margin_detail: 融资融券交易明细

【新闻/公告】
- tool_get_news: 财经新闻快讯
- tool_get_anns: 上市公司公告

【现货】
- tool_get_sge_daily: 上海黄金交易所现货行情

## 字段选择和时间窗口原则（CRITICAL，必须严格遵守）
所有工具都支持fields参数，agent在调用任何工具前必须分析思考需要哪些字段来解决问题，通过fields参数只请求必要字段。绝对不能一次性获取全部字段！

### 调用工具前必须执行以下思考：
1. 分析用户问题的核心需求是什么？
2. 解决这个问题需要哪些具体数据字段？
3. 哪些字段是必需的，哪些是可选的？
4. 选择最小必要字段集，通过fields参数传递

### 重要规则：
- 如果fields参数为空或不指定，工具将返回全部字段，这会导致token超限和性能问题
- 因此，agent必须为每个工具调用指定fields参数！
- 优先获取最小必要数据集，如果不够再逐步扩大
- 如果所需数据量太大无法一次性处理，明确告知用户并建议缩小分析范围或分段获取

### 字段选择参考：
- 走势/技术分析 → trade_date,close,pct_chg,vol（日线）；trade_date,pe_ttm,pb,turnover_rate（每日指标）
- 估值分析 → trade_date,pe_ttm,pb,ps_ttm,total_mv,circ_mv
- 盈利能力分析 → end_date,roe,roa,netprofit_margin,grossprofit_margin,netprofit_yoy,tr_yoy
- 财务健康分析 → end_date,debt_to_assets,current_ratio,quick_ratio,fcff,netdebt
- 利润表核心 → end_date,total_revenue,revenue,operate_profit,n_income_attr_p,basic_eps
- 资金流向分析 → trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount
- 大盘走势 → trade_date,close,pct_chg,vol

### 时间窗口选择原则：
1. **短期分析**（最近走势）：默认获取最近20-30个交易日数据
2. **中期分析**（季度/半年）：默认获取最近60-120个交易日数据
3. **长期分析**（年度/多年）：根据具体需求确定，但优先获取最近数据
4. **特殊需求**：如果用户明确指定时间范围，按用户要求获取

### 数据分段处理原则：
如果分析需要大量历史数据（如多年趋势分析），请按以下步骤处理：
1. 先获取最近一段时间的核心数据进行分析
2. 如果发现需要更长时间数据才能得出结论，再分段获取更早的数据
3. 每段数据获取后立即进行初步分析
4. 最后综合所有分段数据给出完整结论
5. 如果数据量太大无法一次性处理，明确告知用户并建议缩小分析范围

### 工作原则（必须严格遵守）：
0. **数据收集阶段禁止输出面向用户的文字** — 需要数据时直接调用工具，不要先说「我来查询…」等过程描述
1. **CRITICAL：调用任何工具前必须先分析需要哪些fields字段** - 这是最重要的规则！必须为每个工具调用指定fields参数，选择最小必要字段集
2. 调用工具前先分析问题，确定需要哪些字段和时间范围
3. 优先获取最小必要数据集，如果不够再逐步扩大
4. 股票代码格式：600519（贵州茅台）、000001（平安银行）等，工具会自动补全后缀
5. 日期格式统一使用 YYYYMMDD，如 20240101
6. 数据获取后，结合专业知识进行深度分析，给出有价值的结论
7. 分析结果要包含：数据摘要、趋势判断、风险提示、投资建议（仅供参考）
8. 如果用户问的是选股、板块、宏观等问题，也要主动调用相关工具
9. 对于历史相似走势问题，使用 tool_search_similar_pattern
10. 一定要基于真实数据进行回答，不能编造数据和胡乱编造答案
11. **绝对不能一次性获取全部字段** - 这会导致token超限和系统崩溃
12. **如果忘记指定fields参数，系统将返回错误** - 这是强制性的安全检查
10. 将获取到的数据取样展示到最后的分析结果中
11. 每个工具返回中若包含 _validation.warnings，必须先解释这些数据质量风险，再给结论
12. 一定要注意获取的数据所对应单位，否则会产生错误结论
13. **如果所需数据量太大，明确告知用户并分段处理，不要使用不完整数据给出错误结论**

注意：所有分析仅供参考，不构成投资建议。"""

    # 注入执行计划
    if plan and plan.get("steps"):
        steps = plan["steps"]
        plan_text = "\n\n## 本次分析执行计划\n"
        plan_text += f"分析类型：{plan.get('analysis_type', '综合分析')}\n"
        if plan.get("stock_codes"):
            plan_text += f"识别股票：{', '.join(plan['stock_codes'])}\n"
        if plan.get("date_hints"):
            plan_text += f"日期范围：{plan['date_hints']}\n"
        plan_text += "\n"
        for s in steps:
            plan_text += f"**步骤{s['step_id']}：{s['title']}**\n"
            plan_text += f"  目标：{s['goal']}\n"
            if s.get('tools'):
                plan_text += f"  工具：{', '.join(s['tools'])}\n"
            if s.get('args_hint'):
                plan_text += f"  参数：{json.dumps(s['args_hint'], ensure_ascii=False)}\n"
            if s.get('fields_hint'):
                plan_text += f"  字段：{s['fields_hint']}\n"
            if s.get('analysis_hint'):
                plan_text += f"  分析要点：{s['analysis_hint']}\n"
            plan_text += "\n"
        plan_text += "请严格按照以上步骤顺序执行；调用工具时必须填入 args_hint 中的参数，必填项不可省略。"
        base += plan_text

    return base


# 默认 prompt（无 plan 时使用）
SYSTEM_PROMPT = _build_system_prompt()


class StockAnalysisGraph:
    """股票分析 LangGraph 工作流（Plan → Act）"""

    def __init__(
        self,
        trace: bool = False,
        print_live_trace: bool = False,
        enable_data_compression: bool = True,
    ):
        self._last_trace: Dict[str, Any] = {}
        self._current_tool_events: List[Dict[str, Any]] = []
        self._current_plan: Dict[str, Any] = {}
        self._trace = trace
        self._print_live_trace = print_live_trace
        self._enable_data_compression = enable_data_compression
        self._enable_langsmith_if_configured()
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.7,
            extra_body={"thinking": {"type": "disabled"}}  # 禁用思考模式
        )
        self.tools = get_all_tools()
        self._instrument_tools(self.tools)
        self.memory = MemorySaver()
        logger.info(f"StockAnalysisGraph initialized with {len(self.tools)} tools")

    def _make_agent(self, plan: Dict[str, Any] = None):
        """根据 plan 动态构建 ReAct agent"""
        prompt = _build_system_prompt(plan)
        return create_react_agent(self.model, self.tools, prompt=prompt)

    async def _stream_final_report(
        self, query: str, tool_summaries: List[str]
    ) -> AsyncGenerator[str, None]:
        """基于已收集数据单独生成分析报告，避免过程性文字混入。"""
        from langchain_core.messages import SystemMessage, HumanMessage as HM

        if tool_summaries:
            data_section = "\n\n".join(
                f"【数据 {i + 1}】\n{s}" for i, s in enumerate(tool_summaries)
            )
        else:
            data_section = "（未获取到有效工具数据，请基于问题给出有限分析并说明数据不足）"

        messages = [
            SystemMessage(content=_FINAL_REPORT_SYSTEM_PROMPT),
            HM(content=f"用户问题：{query}\n\n已收集数据摘要：\n{data_section}"),
        ]
        async for chunk in self.model.astream(messages):
            content = getattr(chunk, "content", "") or ""
            if content:
                yield content

    def _enable_langsmith_if_configured(self):
        """可选启用 LangSmith（未配置时自动跳过）。"""
        if not os.getenv("LANGSMITH_API_KEY"):
            return
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", "stock-agent")
        logger.info("LangSmith tracing enabled (LANGSMITH_API_KEY detected)")

    def _instrument_tools(self, tools: List[Any]):
        """为工具统一加日志与输出压缩，避免每个工具函数重复改造。"""
        for tool_obj in tools:
            original_func = getattr(tool_obj, "func", None)
            if not callable(original_func):
                continue

            tool_name = getattr(tool_obj, "name", "unknown_tool")

            def wrapped_func(*args, __orig=original_func, __tool_name=tool_name, **kwargs):
                started_at = time.time()
                logger.log_tool_call(__tool_name, kwargs, status="started")
                try:
                    raw_result = __orig(*args, **kwargs)
                    safe_result = _safe_tool_output(raw_result)
                    checked = _validate_tool_payload(__tool_name, safe_result)
                    checked_result = checked["normalized_result"]
                    duration_ms = int((time.time() - started_at) * 1000)
                    status = checked["status"]
                    error_msg = checked["error"]
                    warnings = checked["warnings"]

                    logger.log_tool_call(
                        __tool_name,
                        kwargs,
                        status=status,
                        duration_ms=duration_ms,
                        result_summary=_summarize_text(checked_result, 320),
                        error=error_msg,
                    )
                    self._current_tool_events.append(
                        {
                            "tool_name": __tool_name,
                            "args": kwargs,
                            "status": status,
                            "duration_ms": duration_ms,
                            "result_preview": _summarize_text(checked_result, 400),
                            "validation_warnings": warnings,
                            "error": error_msg,
                        }
                    )
                    return checked_result
                except Exception as exc:
                    duration_ms = int((time.time() - started_at) * 1000)
                    logger.log_tool_call(
                        __tool_name,
                        kwargs,
                        status="error",
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    self._current_tool_events.append(
                        {
                            "tool_name": __tool_name,
                            "args": kwargs,
                            "status": "error",
                            "duration_ms": duration_ms,
                            "error": str(exc),
                        }
                    )
                    raise

            tool_obj.func = wrapped_func

    def _build_trace_summary(self, result: dict, thread_id: str, query: str) -> Dict[str, Any]:
        messages = result.get("messages", []) if isinstance(result, dict) else []
        steps: List[Dict[str, Any]] = []
        final_answer = ""

        for msg in messages:
            if isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    for call in tool_calls:
                        steps.append(
                            {
                                "type": "plan_tool_call",
                                "tool_name": call.get("name", "unknown"),
                                "args": call.get("args", {}),
                            }
                        )
                else:
                    final_answer = getattr(msg, "content", "") or final_answer
            elif isinstance(msg, ToolMessage):
                steps.append(
                    {
                        "type": "tool_result",
                        "tool_name": getattr(msg, "name", "unknown"),
                        "tool_call_id": getattr(msg, "tool_call_id", ""),
                        "content_preview": _summarize_text(getattr(msg, "content", ""), 240),
                    }
                )

        return {
            "thread_id": thread_id,
            "query_preview": _summarize_text(query, 180),
            "tool_events": list(self._current_tool_events),
            "message_steps": steps,
            "final_answer_preview": _summarize_text(final_answer, 360),
            "created_at": datetime.now().isoformat(),
        }

    def invoke(self, query: str, thread_id: str = "default") -> dict:
        """同步调用（Plan → Act）"""
        self._current_tool_events = []
        self._current_plan = {}
        prepared_query = _prepare_query(query, MAX_QUERY_CHARS)
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100  # 增加递归限制，允许更多步骤
        }
        logger.log_user_query(prepared_query, session_id=thread_id, status="started")

        # Plan 阶段（同步运行异步 planner）
        try:
            plan = asyncio.get_event_loop().run_until_complete(
                _run_planner(prepared_query, self.model)
            )
        except Exception:
            plan = None

        self._current_plan = plan or {}
        self._print_plan_to_terminal(plan, prepared_query)

        act_message = build_act_user_message(prepared_query, plan)
        agent = self._make_agent(plan)
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=act_message)]},
                config=config
            )
        except Exception as exc:
            if _is_token_limit_error(exc):
                retry_query = _prepare_query(query, MAX_RETRY_QUERY_CHARS)
                retry_message = build_act_user_message(retry_query, plan)
                result = agent.invoke(
                    {"messages": [HumanMessage(content=retry_message)]},
                    config=config
                )
            else:
                logger.log_user_query(prepared_query, session_id=thread_id, status="error")
                raise

        self._last_trace = self._build_trace_summary(result, thread_id=thread_id, query=prepared_query)
        logger.log_user_query(prepared_query, session_id=thread_id, status="completed")
        return result

    async def ainvoke(self, query: str, thread_id: str = "default") -> dict:
        """异步调用（Plan → Act）"""
        self._current_tool_events = []
        self._current_plan = {}
        prepared_query = _prepare_query(query, MAX_QUERY_CHARS)
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100  # 增加递归限制，允许更多步骤
        }
        logger.log_user_query(prepared_query, session_id=thread_id, status="started")

        # Plan 阶段
        plan = await _run_planner(prepared_query, self.model)
        self._current_plan = plan
        self._print_plan_to_terminal(plan, prepared_query)

        act_message = build_act_user_message(prepared_query, plan)
        agent = self._make_agent(plan)
        try:
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=act_message)]},
                config=config
            )
        except Exception as exc:
            if _is_token_limit_error(exc):
                retry_query = _prepare_query(query, MAX_RETRY_QUERY_CHARS)
                retry_message = build_act_user_message(retry_query, plan)
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=retry_message)]},
                    config=config
                )
            else:
                logger.log_user_query(prepared_query, session_id=thread_id, status="error")
                raise

        self._last_trace = self._build_trace_summary(result, thread_id=thread_id, query=prepared_query)
        logger.log_user_query(prepared_query, session_id=thread_id, status="completed")
        return result

    async def astream(self, query: str, thread_id: str = "default"):
        """流式异步调用，逐步 yield 原始 LangGraph 事件（兼容旧接口）"""
        self._current_tool_events = []
        prepared_query = _prepare_query(query, MAX_QUERY_CHARS)
        config = {"configurable": {"thread_id": thread_id}}
        plan = await _run_planner(prepared_query, self.model)
    async def astream_with_events(
        self, query: str, config: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Plan → Act 流式执行，yield 标准化 SSE 事件（对齐 api/event_types.py）。

        事件类型（标准）：
          workflow_start   - 工作流开始
          execution_plan   - 执行计划就绪
          stage_start      - 阶段开始（collect_data / generate_answer）
          analysis_chunk   - 分析内容增量（流式文本）
          tool_call        - 工具调用开始
          tool_result      - 工具调用结束
          stage_complete   - 阶段完成
          final_answer     - 最终答案（完整内容）
          workflow_complete - 全部完成
        """
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "default")
        prepared_query = _prepare_query(query, MAX_QUERY_CHARS)
        lc_config = config or {"configurable": {"thread_id": thread_id}}
        # 确保config包含recursion_limit
        if "recursion_limit" not in lc_config:
            lc_config["recursion_limit"] = 100  # 增加递归限制，允许更多步骤
        workflow_start_time = time.time()

        # ── workflow_start ────────────────────────────────────────────────
        yield {
            "event_type": "workflow_start",
            "data": {
                "session_id": thread_id,
                "query": prepared_query,
                "timestamp": datetime.now().isoformat(),
            }
        }

        # ── 意图分类：非金融问题直接用 LLM 回答，跳过 plan + 工具 ──────────
        is_finance = await _is_finance_query(prepared_query, self.model)
        if not is_finance:
            _print_stage("通用问答（非金融问题）", color="magenta")
            answer_chunks: List[str] = []
            stage_start_time = time.time()
            yield {
                "event_type": "stage_start",
                "data": {
                    "stage": "generate_answer",
                    "title": "直接回答",
                    "description": "非金融问题，直接使用模型知识回答",
                    "timestamp": datetime.now().isoformat(),
                }
            }
            from langchain_core.messages import SystemMessage
            general_messages = [
                SystemMessage(content=f"你是一个智能助手，今天日期是 {TODAY_HYPHEN}。请直接回答用户问题。"),
                HumanMessage(content=prepared_query),
            ]
            async for chunk in self.model.astream(general_messages):
                content = getattr(chunk, "content", "") or ""
                if content:
                    _print_thinking(content)
                    answer_chunks.append(content)
                    yield {
                        "event_type": "analysis_chunk",
                        "data": {
                            "stage": "generate_answer",
                            "content": content,
                            "is_final": False,
                            "timestamp": datetime.now().isoformat(),
                        }
                    }
            _print_final_answer_end()
            final_answer = "".join(answer_chunks)
            gen_duration_ms = int((time.time() - stage_start_time) * 1000)
            yield {
                "event_type": "stage_complete",
                "data": {
                    "stage": "generate_answer",
                    "summary": f"回答生成完毕（{len(final_answer)} 字）",
                    "duration_ms": gen_duration_ms,
                    "timestamp": datetime.now().isoformat(),
                }
            }
            yield {
                "event_type": "final_answer",
                "data": {
                    "content": final_answer,
                    "metadata": {
                        "total_duration_ms": int((time.time() - workflow_start_time) * 1000),
                        "tools_used": [],
                        "data_sources": [],
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            }
            yield {
                "event_type": "workflow_complete",
                "data": {
                    "session_id": thread_id,
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                }
            }
            return

        # ── 1. Plan 阶段 ──────────────────────────────────────────────────
        _print_stage(f"分析规划  [{prepared_query[:40]}...]", color="cyan")
        print(f"  {_c('gray', '正在生成执行计划...')}")

        # 推送"分析中"状态，前端可展示 loading
        yield {
            "event_type": "analyzing",
            "data": {
                "message": "正在分析问题，制定执行计划…",
                "timestamp": datetime.now().isoformat(),
            }
        }

        plan = await _run_planner(prepared_query, self.model)
        self._current_plan = plan
        self._print_plan_to_terminal(plan, prepared_query)

        steps = plan.get("steps", [])
        # 将 plan steps 映射为标准 workflow_stages 格式
        workflow_stages = [
            {
                "stage_id": s.get("step_id", i + 1),
                "title": s.get("title", f"步骤 {i + 1}"),
                "goal": s.get("goal", ""),
                "tools": s.get("tools", []),
            }
            for i, s in enumerate(steps)
        ]

        yield {
            "event_type": "execution_plan",
            "data": {
                "question_type": plan.get("analysis_type", "综合分析"),
                "stock_codes": plan.get("stock_codes", []),
                "workflow_stages": workflow_stages,
                "key_points": plan.get("key_points", []),
                "risk_points": plan.get("risk_points", []),
                "timestamp": datetime.now().isoformat(),
            }
        }

        # ── 2. Act 阶段：流式执行 ─────────────────────────────────────────
        agent = self._make_agent(plan)
        total_steps = len(steps)
        current_step_idx = 0
        tool_call_buffer: Dict[str, Dict] = {}  # run_id -> {name, args, start_time}
        final_answer_chunks: List[str] = []
        tools_used: List[str] = []
        tool_data_summaries: List[str] = []

        # 阶段追踪
        stage_start_time = time.time()
        collect_data_started = False
        generate_answer_started = False

        _print_stage("开始执行", color="yellow")

        act_message = build_act_user_message(prepared_query, plan)
        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=act_message)]},
            config=lc_config,
            version="v2"
        ):
            etype = event.get("event", "")
            edata = event.get("data", {})
            name  = event.get("name", "")

            # ── 工具调用开始 ──────────────────────────────────────────────
            if etype == "on_tool_start":
                tool_name = name
                tool_input = edata.get("input", {})
                run_id = event.get("run_id", "")
                tool_call_buffer[run_id] = {
                    "name": tool_name,
                    "args": tool_input,
                    "start_time": time.time(),
                }

                # 第一个工具调用时开启 collect_data 阶段
                if not collect_data_started:
                    collect_data_started = True
                    stage_start_time = time.time()
                    # 推进步骤标题
                    step_title = steps[0]["title"] if steps else "收集数据"
                    _print_step(1, total_steps, step_title, "")
                    yield {
                        "event_type": "stage_start",
                        "data": {
                            "stage": "collect_data",
                            "title": step_title,
                            "description": steps[0].get("goal", "") if steps else "",
                            "timestamp": datetime.now().isoformat(),
                        }
                    }

                # 推进步骤指示器（后续步骤）
                if current_step_idx < total_steps:
                    step = steps[current_step_idx]
                    if tool_name in step.get("tools", []) or current_step_idx == 0:
                        if current_step_idx > 0:
                            _print_step(
                                current_step_idx + 1, total_steps,
                                step["title"], step.get("goal", "")
                            )
                        current_step_idx += 1

                _print_tool_call(tool_name, tool_input if isinstance(tool_input, dict) else {})
                # 只传参数键名和简短值，不传原始数据
                safe_args = {
                    k: (str(v)[:80] if isinstance(v, str) and len(str(v)) > 80 else v)
                    for k, v in (tool_input.items() if isinstance(tool_input, dict) else {})
                }
                yield {
                    "event_type": "tool_call",
                    "data": {
                        "tool_name": tool_name,
                        "tool_id": run_id,
                        "args": safe_args,
                        "timestamp": datetime.now().isoformat(),
                    }
                }

            # ── 工具调用结束 ──────────────────────────────────────────────
            elif etype == "on_tool_end":
                run_id = event.get("run_id", "")
                buf = tool_call_buffer.pop(run_id, {})
                tool_name = buf.get("name", name)
                duration_ms = int((time.time() - buf.get("start_time", time.time())) * 1000)
                output = edata.get("output", "")
                output_str = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)

                # 判断状态
                try:
                    parsed = json.loads(output_str)
                    has_error = parsed.get("error") if isinstance(parsed, dict) else False
                    status = "error" if has_error else "success"
                    error_msg = str(parsed.get("error", "")) if has_error else None
                except Exception:
                    status = "success"
                    error_msg = None

                summary = _summarize_text(output_str, 200)
                if tool_name not in tools_used:
                    tools_used.append(tool_name)
                if status == "success" and summary:
                    tool_data_summaries.append(f"{tool_name}: {summary}")

                _print_tool_result(tool_name, status, summary, duration_ms)
                # tool_result 只传状态和耗时，不传数据内容
                result_data: Dict[str, Any] = {
                    "tool_name": tool_name,
                    "tool_id": run_id,
                    "status": status,
                    "summary": f"{tool_name} 执行{'成功' if status == 'success' else '失败'}，耗时 {duration_ms}ms",
                    "timestamp": datetime.now().isoformat(),
                }
                if error_msg:
                    result_data["error"] = error_msg
                yield {"event_type": "tool_result", "data": result_data}

            # ── LLM 流式输出（数据收集阶段仅打日志，不推送给前端）──────────
            elif etype == "on_chat_model_stream":
                chunk = edata.get("chunk", {})
                content = ""
                if hasattr(chunk, "content"):
                    content = chunk.content or ""
                elif isinstance(chunk, dict):
                    content = chunk.get("content", "")

                if not content:
                    continue

                tool_calls = []
                if hasattr(chunk, "tool_calls"):
                    tool_calls = chunk.tool_calls or []
                elif isinstance(chunk, dict):
                    tool_calls = chunk.get("tool_calls", [])
                if tool_calls:
                    continue

                # ReAct 阶段的思考/过程文字只写终端，不进入最终报告
                _print_thinking(content)

        # ── 3. 单独生成最终分析报告 ─────────────────────────────────────
        if collect_data_started:
            collect_data_duration = int((time.time() - stage_start_time) * 1000)
            yield {
                "event_type": "stage_complete",
                "data": {
                    "stage": "collect_data",
                    "summary": f"共调用 {len(tools_used)} 个工具",
                    "duration_ms": collect_data_duration,
                    "timestamp": datetime.now().isoformat(),
                }
            }

        generate_answer_started = True
        stage_start_time = time.time()
        _print_final_answer_start()
        yield {
            "event_type": "stage_start",
            "data": {
                "stage": "generate_answer",
                "title": "生成分析报告",
                "description": "基于收集的数据生成最终分析结论",
                "timestamp": datetime.now().isoformat(),
            }
        }

        async for content in self._stream_final_report(prepared_query, tool_data_summaries):
            final_answer_chunks.append(content)
            yield {
                "event_type": "analysis_chunk",
                "data": {
                    "stage": "generate_answer",
                    "content": content,
                    "is_final": False,
                    "timestamp": datetime.now().isoformat(),
                }
            }

        _print_final_answer_end()

        # ── 4. 完成 ───────────────────────────────────────────────────────
        final_answer = "".join(final_answer_chunks)
        total_duration_ms = int((time.time() - workflow_start_time) * 1000)

        # 关闭 generate_answer 阶段
        if generate_answer_started:
            gen_duration_ms = int((time.time() - stage_start_time) * 1000)
            yield {
                "event_type": "stage_complete",
                "data": {
                    "stage": "generate_answer",
                    "summary": f"分析报告生成完毕（{len(final_answer)} 字）",
                    "duration_ms": gen_duration_ms,
                    "timestamp": datetime.now().isoformat(),
                }
            }

        # final_answer 事件
        yield {
            "event_type": "final_answer",
            "data": {
                "content": final_answer,
                "metadata": {
                    "total_duration_ms": total_duration_ms,
                    "tools_used": tools_used,
                    "data_sources": list({t.replace("tool_", "") for t in tools_used}),
                },
                "timestamp": datetime.now().isoformat(),
            }
        }

        yield {
            "event_type": "workflow_complete",
            "data": {
                "session_id": thread_id,
                "status": "success",
                "timestamp": datetime.now().isoformat(),
            }
        }

    def _print_plan_to_terminal(self, plan: Dict[str, Any], query: str):
        """将执行计划打印到终端"""
        if not plan:
            return
        steps = plan.get("steps", [])
        analysis_type = plan.get("analysis_type", "综合分析")
        _print_stage(f"执行计划  [{analysis_type}]", color="cyan")
        print(f"  {_c('gray', f'问题: {query[:60]}')}")
        print()
        for s in steps:
            tools_str = ", ".join(s.get("tools", [])) or "无"
            print(f"  {_c('bold', _c('yellow', 'Step ' + str(s['step_id'])))} {_c('bold', s['title'])}")
            print(f"    目标: {_c('gray', s.get('goal', ''))}")
            print(f"    工具: {_c('blue', tools_str)}")
            if s.get("analysis_hint"):
                print(f"    分析: {_c('gray', s['analysis_hint'][:80])}")
            print()

    def get_last_trace(self) -> Dict[str, Any]:
        """获取最近一次调用的可观测追踪数据。"""
        return self._last_trace


# ============================================================================
# 便捷入口
# ============================================================================

_graph_instance: Optional[StockAnalysisGraph] = None


def get_stock_graph() -> StockAnalysisGraph:
    """获取全局 StockAnalysisGraph 单例"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = StockAnalysisGraph()
    return _graph_instance


def run_stock_query(query: str, thread_id: str = "default") -> str:
    """同步运行股票查询，返回最终回答文本"""
    graph = get_stock_graph()
    result = graph.invoke(query, thread_id=thread_id)
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return getattr(last, "content", str(last))
    return "未获取到回答"


if __name__ == "__main__":
    import sys

    async def _main():
        query = sys.argv[1] if len(sys.argv) > 1 else "分析一下贵州茅台600519最近的走势"
        graph = StockAnalysisGraph()
        config = {"configurable": {"thread_id": "cli"}}
        async for event in graph.astream_with_events(query, config):
            if event["event_type"] == "workflow_complete":
                break  # 终端输出已在 astream_with_events 内实时打印

    asyncio.run(_main())
