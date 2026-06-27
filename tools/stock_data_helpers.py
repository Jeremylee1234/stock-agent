"""股票数据工具共享函数（iFinD 优先，Tushare 降级）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from tools.ifind.unit_registry import get_units_for_records
from tools.ifind_bridge import fetch_daily_ifind_df, attach_tushare_units, df_to_payload
from tools.tushare_client import pro, tushare_api_call_with_retry

logger = logging.getLogger(__name__)

TODAY_YMD = datetime.now().strftime("%Y%m%d")


def to_ts_code(stock_code: str) -> str:
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


def fmt_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    return "".join(c for c in str(date_str) if c.isdigit())[:8] or None


def clamp_today(end_date: str) -> str:
    if end_date and end_date > TODAY_YMD:
        return TODAY_YMD
    return end_date or TODAY_YMD


def normalize_date(date_str: str, fallback: str) -> str:
    if not date_str:
        return fallback
    cleaned = fmt_date(date_str)
    return cleaned or fallback


def fetch_daily_df_fallback(
    tc: str, sd: str, ed: str, fields: str, cps: str = "2"
) -> Tuple[Any, Optional[str]]:
    """优先 iFinD，失败降级 Tushare pro.daily。"""
    df = fetch_daily_ifind_df(tc, sd, ed, fields, cps=cps)
    if df is not None and not df.empty:
        return df, "ifind"
    try:
        df = tushare_api_call_with_retry(
            pro.daily, ts_code=tc, start_date=sd, end_date=ed, fields=fields
        )
        if df is not None and not df.empty:
            return df, "tushare"
    except Exception as exc:
        logger.warning("Tushare daily fallback failed: %s", exc)
    return None, None


def json_from_df(
    df,
    tc: str,
    data_source: str,
    sd: str = None,
    ed: str = None,
    tail_limit: int = None,
    extra: dict = None,
) -> str:
    if df is None or df.empty:
        return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)
    data_count = len(df)
    return_df = df.tail(tail_limit) if tail_limit and data_count > tail_limit else df
    payload: Dict[str, Any] = {
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
