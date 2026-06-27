"""iFinD 与 Tushare 桥接：优先 iFinD，失败时降级 Tushare。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import get_settings
from tools.ifind.client import IFindAPIError
from tools.ifind.unit_registry import get_units_for_records, get_units_for_fields
from tools.data_sources.ifind_adapter import get_ifind_adapter


def _priority_has_ifind() -> bool:
    settings = get_settings()
    if not settings.has_ifind():
        return False
    return "ifind" in [s.lower() for s in settings.data_source.data_source_priority]


def attach_tushare_units(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("data") and isinstance(payload["data"], list):
        payload["_field_units"] = get_units_for_records(payload["data"], source="tushare")
        payload["_units_source"] = "tushare"
    return payload


def df_to_payload(df: pd.DataFrame, ts_code: str = None, data_source: str = "tushare") -> Dict[str, Any]:
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"error": "未查询到数据"}
    records = df.to_dict("records")
    payload = {
        "success": True,
        "data": records,
        "count": len(records),
        "data_source": data_source,
    }
    if ts_code:
        payload["ts_code"] = ts_code
    if data_source == "tushare":
        attach_tushare_units(payload)
    return payload


def payload_to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def fetch_daily_ifind(
    ts_code: str,
    start_date: str,
    end_date: str,
    fields: Optional[str] = None,
    cps: str = "2",
) -> Optional[Dict[str, Any]]:
    if not _priority_has_ifind():
        return None
    try:
        adapter = get_ifind_adapter()
        return adapter.get_daily_quotation(ts_code, start_date, end_date, fields, cps=cps)
    except IFindAPIError:
        return None


def fetch_daily_ifind_df(
    ts_code: str,
    start_date: str,
    end_date: str,
    fields: Optional[str] = None,
    cps: str = "2",
) -> Optional[pd.DataFrame]:
    payload = fetch_daily_ifind(ts_code, start_date, end_date, fields, cps)
    if not payload or not payload.get("success"):
        return None
    return pd.DataFrame(payload["data"])


def merge_local_and_ifind_payload(
    local_result: Dict[str, Any],
    ifind_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """合并本地 parquet 与 iFinD 增量。"""
    if local_result.get("success") and local_result.get("data"):
        local_df = pd.DataFrame(local_result["data"])
    else:
        local_df = None

    if ifind_df is not None and not ifind_df.empty:
        if local_df is not None and not local_df.empty:
            df = pd.concat([local_df, ifind_df], ignore_index=True)
            df = df.drop_duplicates(subset=["trade_date"], keep="last")
            data_source = "mixed"
        else:
            df = ifind_df
            data_source = "ifind"
    elif local_df is not None and not local_df.empty:
        df = local_df
        data_source = local_result.get("data_source", "local_parquet_ifind")
    else:
        return {"error": "未查询到数据"}

    df = df.sort_values("trade_date").reset_index(drop=True)
    records = df.to_dict("records")
    payload = {
        "success": True,
        "ts_code": local_result.get("ts_code") or (records[0].get("ts_code") if records else None),
        "data": records,
        "count": len(records),
        "data_source": data_source,
        "_field_units": get_units_for_records(records, source="local_parquet_ifind" if "local" in data_source else "ifind_native"),
        "_units_source": "mixed" if data_source == "mixed" else ("local_parquet_ifind" if "local" in data_source else "ifind_native"),
    }
    return payload


def wrap_ifind_payload(payload: Dict[str, Any], limit: int = 50, sort_col: str = None) -> str:
    """将 iFinD adapter 返回的 payload 截断后序列化为 JSON。"""
    if not payload.get("success"):
        return json.dumps(payload, ensure_ascii=False, default=str)
    data = list(payload.get("data") or [])
    if sort_col and data and sort_col in data[0]:
        data = sorted(data, key=lambda x: x.get(sort_col, ""))
    if limit and len(data) > limit:
        payload = dict(payload)
        payload["data"] = data[-limit:] if sort_col in ("trade_date", "cal_date", "end_date") else data[:limit]
        payload["returned_count"] = limit
        payload["count"] = len(data)
    return payload_to_json(payload)


def try_ifind_payload(callable_fn, *args, **kwargs) -> Optional[Dict[str, Any]]:
    """iFinD 可用时执行 adapter 方法，失败返回 None。"""
    if not _priority_has_ifind():
        return None
    try:
        adapter = get_ifind_adapter()
        if not adapter.is_available():
            return None
        payload = callable_fn(*args, **kwargs)
        if payload and payload.get("success"):
            return payload
    except IFindAPIError:
        pass
    return None


def try_ifind_financial(
    ts_code: str,
    fields: Optional[str],
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    adapter = get_ifind_adapter()
    return try_ifind_payload(
        adapter.get_fina_indicator,
        ts_code,
        period=period,
        fields=fields,
        start_date=start_date,
        end_date=end_date,
    )


def try_ifind_financial_series(
    ts_code: str,
    start_date: str,
    end_date: str,
    fields: Optional[str],
) -> Optional[Dict[str, Any]]:
    adapter = get_ifind_adapter()
    return try_ifind_payload(
        adapter.get_financial_series,
        ts_code,
        start_date,
        end_date,
        fields,
    )


def try_ifind_moneyflow_history(
    ts_code: str,
    start_date: str,
    end_date: str,
    fields: Optional[str],
) -> Optional[Dict[str, Any]]:
    adapter = get_ifind_adapter()
    return try_ifind_payload(
        adapter.get_moneyflow_history,
        ts_code,
        start_date,
        end_date,
        fields,
    )


def try_ifind_data_pool(report_key: str, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
    adapter = get_ifind_adapter()
    return try_ifind_payload(adapter.get_data_pool, report_key, start_date, end_date)


def try_ifind_smart_picking(searchstring: str, searchtype: str = "stock") -> Optional[Dict[str, Any]]:
    adapter = get_ifind_adapter()
    return try_ifind_payload(adapter.get_smart_stock_picking, searchstring, searchtype)
