"""解析 iFinD tables 响应并构建带 _field_units 的工具返回。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import re

from tools.ifind.client import IFindAPIError
from tools.ifind.field_maps import rename_record_keys_ifind_to_tushare
from tools.ifind.unit_registry import get_units_for_records


def _parse_time_series_block(
    block: Dict[str, Any],
    alias_to_tushare: bool,
    date_key: str,
) -> List[Dict[str, Any]]:
    """解析含 time 列的块（time 可在 block 顶层或 table 内）。"""
    thscode = block.get("thscode") or block.get("THSCODE") or block.get("code")
    table = block.get("table") or block.get("Table") or {}
    if not isinstance(table, dict):
        table = {}

    time_col = None
    times = None
    for tk in ("time", "date", "tradeDate", "trade_date", "datetime"):
        if tk in block and block[tk]:
            time_col = tk
            times = block[tk]
            break
    if times is None:
        for tk in ("time", "date", "tradeDate", "trade_date", "datetime"):
            if tk in table and table[tk]:
                time_col = tk
                times = table[tk]
                break

    records: List[Dict[str, Any]] = []
    if times is not None:
        if not isinstance(times, list):
            times = [times]
        n = len(times)
        for i in range(n):
            row: Dict[str, Any] = {}
            if thscode:
                row["ts_code"] = thscode
            tval = times[i]
            if tval is not None:
                ds = str(tval).replace("-", "").replace("/", "").replace(" ", "")[:8]
                row[date_key] = ds
            for col, vals in table.items():
                if col == time_col:
                    continue
                if isinstance(vals, list):
                    if len(vals) > i:
                        row[col] = vals[i]
                else:
                    row[col] = vals
            if alias_to_tushare:
                row = rename_record_keys_ifind_to_tushare(row)
            records.append(row)
        return records

    # 无 time 列：单行或多列标量/数组（取首元素）
    row = dict(table)
    if thscode:
        row["ts_code"] = thscode
    for col, vals in list(row.items()):
        if isinstance(vals, list) and len(vals) == 1:
            row[col] = vals[0]
    if alias_to_tushare:
        row = rename_record_keys_ifind_to_tushare(row)
    if row:
        records.append(row)
    return records


def normalize_ifind_tables(
    raw: Dict[str, Any],
    alias_to_tushare: bool = True,
    date_key: str = "trade_date",
) -> List[Dict[str, Any]]:
    """
    将 iFinD tables 转为 list[dict]。
    支持：
    - tables 为 list[{thscode, time, table:{...}}]
    - tables 为 dict{time:[...]}（交易日历）
    - tables 为 list[{thscode, table:{...}}]（基础数据）
    """
    errorcode = raw.get("errorcode", 0)
    try:
        if int(errorcode) != 0:
            raise IFindAPIError(raw.get("errmsg") or str(errorcode), errorcode=int(errorcode))
    except (TypeError, ValueError):
        pass

    tables_raw = raw.get("tables") or raw.get("Tables")
    if tables_raw is None or tables_raw == []:
        return []

    all_records: List[Dict[str, Any]] = []

    if isinstance(tables_raw, dict):
        # 扁平结构：get_trade_dates 返回 {"time": ["20250603", ...]}
        if "time" in tables_raw or "date" in tables_raw:
            all_records.extend(
                _parse_time_series_block({"table": tables_raw}, alias_to_tushare, date_key)
            )
        else:
            all_records.extend(
                _parse_time_series_block({"table": tables_raw}, alias_to_tushare, date_key)
            )
        return all_records

    if not isinstance(tables_raw, list):
        return []

    for block in tables_raw:
        if not isinstance(block, dict):
            continue
        all_records.extend(_parse_time_series_block(block, alias_to_tushare, date_key))

    return all_records


def normalize_smart_picking_tables(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    解析 smart_stock_picking 返回（中文列名 + 并行数组）。
    将 {'股票代码': [...], '股票简称': [...]} 展开为多条记录。
    """
    errorcode = raw.get("errorcode", 0)
    try:
        if int(errorcode) != 0:
            raise IFindAPIError(raw.get("errmsg") or str(errorcode), errorcode=int(errorcode))
    except (TypeError, ValueError):
        pass

    tables_raw = raw.get("tables") or []
    if not isinstance(tables_raw, list) or not tables_raw:
        return []

    block = tables_raw[0]
    table = block.get("table") or block.get("Table") or block
    if not isinstance(table, dict):
        return []

    code_col = next((k for k in table if "代码" in k or k in ("ts_code", "thscode")), None)
    name_col = next((k for k in table if "简称" in k or k in ("name", "secName")), None)
    if not code_col:
        return normalize_ifind_tables(raw, alias_to_tushare=False)

    codes = table.get(code_col) or []
    names = table.get(name_col) or [] if name_col else []
    if not isinstance(codes, list):
        codes = [codes]
    if not isinstance(names, list):
        names = [names] * len(codes)

    extra_cols = {k: v for k, v in table.items() if k not in (code_col, name_col)}
    records: List[Dict[str, Any]] = []
    for i, code in enumerate(codes):
        row: Dict[str, Any] = {"ts_code": str(code).strip(), "name": names[i] if i < len(names) else ""}
        for col, vals in extra_cols.items():
            # 简化列名：市盈率(pe)[20260605] -> 市盈率(pe)
            col_key = re.sub(r"\[\d{8}\]", "", col).strip()
            if isinstance(vals, list) and i < len(vals):
                row[col_key] = vals[i]
            elif not isinstance(vals, list):
                row[col_key] = vals
        records.append(row)
    return records


def build_ifind_tool_payload(
    records: List[Dict[str, Any]],
    *,
    ts_code: Optional[str] = None,
    data_source: str = "ifind",
    units_source: str = "ifind_native",
    extra: Optional[Dict[str, Any]] = None,
    alias_to_tushare: bool = True,
) -> Dict[str, Any]:
    """构建标准工具 JSON（含 _field_units）。"""
    if not records:
        return {
            "error": "未查询到数据",
            "data_source": data_source,
            "_units_source": units_source,
        }

    payload: Dict[str, Any] = {
        "success": True,
        "data": records,
        "count": len(records),
        "data_source": data_source,
        "_field_units": get_units_for_records(records, source=units_source),
        "_units_source": units_source,
    }
    if ts_code:
        payload["ts_code"] = ts_code
    if extra:
        payload.update(extra)
    return payload
