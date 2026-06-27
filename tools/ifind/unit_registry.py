"""iFinD 字段单位注册表 — 供 agent 与工具返回 _field_units 使用。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# unit, cn_name, api
IFIND_FIELD_UNITS: Dict[str, Dict[str, str]] = {
    # cmd_history_quotation / 指数
    "preClose": {"unit": "元", "cn_name": "前收盘价", "api": "cmd_history_quotation"},
    "open": {"unit": "元", "cn_name": "开盘价", "api": "cmd_history_quotation"},
    "high": {"unit": "元", "cn_name": "最高价", "api": "cmd_history_quotation"},
    "low": {"unit": "元", "cn_name": "最低价", "api": "cmd_history_quotation"},
    "close": {"unit": "元", "cn_name": "收盘价", "api": "cmd_history_quotation"},
    "avgPrice": {"unit": "元", "cn_name": "均价", "api": "cmd_history_quotation"},
    "change": {"unit": "元", "cn_name": "涨跌额", "api": "cmd_history_quotation"},
    "changeRatio": {"unit": "%", "cn_name": "涨跌幅", "api": "cmd_history_quotation"},
    "volume": {"unit": "股", "cn_name": "成交量", "api": "cmd_history_quotation"},
    "amount": {"unit": "元", "cn_name": "成交额", "api": "cmd_history_quotation"},
    "turnoverRatio": {"unit": "%", "cn_name": "换手率", "api": "cmd_history_quotation"},
    "pe": {"unit": "倍", "cn_name": "市盈率", "api": "cmd_history_quotation"},
    "pe_ttm": {"unit": "倍", "cn_name": "市盈率TTM", "api": "cmd_history_quotation"},
    "pb": {"unit": "倍", "cn_name": "市净率", "api": "cmd_history_quotation"},
    "ps": {"unit": "倍", "cn_name": "市销率", "api": "cmd_history_quotation"},
    "pcf": {"unit": "倍", "cn_name": "市现率", "api": "cmd_history_quotation"},
    "totalCapital": {"unit": "元", "cn_name": "总市值", "api": "cmd_history_quotation"},
    "mv": {"unit": "元", "cn_name": "流通市值", "api": "cmd_history_quotation"},
    "vol_ratio": {"unit": "倍", "cn_name": "量比", "api": "cmd_history_quotation"},
    # Tushare 兼容别名（本地 parquet / 工具 fields 参数）
    "trade_date": {"unit": "YYYYMMDD", "cn_name": "交易日", "api": "common"},
    "ts_code": {"unit": "代码", "cn_name": "证券代码", "api": "common"},
    "pct_chg": {"unit": "%", "cn_name": "涨跌幅", "api": "tushare_alias"},
    "vol": {"unit": "手", "cn_name": "成交量(Tushare)", "api": "tushare_alias"},
    "pre_close": {"unit": "元", "cn_name": "前收盘价", "api": "tushare_alias"},
    "turnover_rate": {"unit": "%", "cn_name": "换手率", "api": "tushare_alias"},
    "total_mv": {"unit": "万元", "cn_name": "总市值(Tushare)", "api": "tushare_alias"},
    "circ_mv": {"unit": "万元", "cn_name": "流通市值(Tushare)", "api": "tushare_alias"},
    "ma5": {"unit": "元", "cn_name": "5日均线", "api": "computed"},
    "ma10": {"unit": "元", "cn_name": "10日均线", "api": "computed"},
    "ma20": {"unit": "元", "cn_name": "20日均线", "api": "computed"},
    "ma30": {"unit": "元", "cn_name": "30日均线", "api": "computed"},
    "ma60": {"unit": "元", "cn_name": "60日均线", "api": "computed"},
    # 实时 / 高频 资金流向
    "mainNetInflow": {"unit": "元", "cn_name": "主力净流入", "api": "real_time_quotation"},
    "ths_net_inflow_amt_stock": {"unit": "元", "cn_name": "净流入金额", "api": "date_sequence"},
    "net_mf_amount": {"unit": "元", "cn_name": "净流入金额(iFinD)", "api": "date_sequence"},
    "largeNetInflow": {"unit": "元", "cn_name": "超大单净流入", "api": "real_time_quotation"},
    "bigNetInflow": {"unit": "元", "cn_name": "大单净流入", "api": "real_time_quotation"},
    "large_amt_timeline": {"unit": "元", "cn_name": "主力净流入(时序)", "api": "high_frequency"},
    # basic_data_service 财务
    "ths_roe_stock": {"unit": "%", "cn_name": "ROE", "api": "basic_data_service"},
    "ths_eps_stock": {"unit": "元/股", "cn_name": "每股收益", "api": "basic_data_service"},
    "ths_roa_stock": {"unit": "%", "cn_name": "ROA", "api": "basic_data_service"},
    "ths_net_profit_yoy_stock": {"unit": "%", "cn_name": "净利润同比", "api": "basic_data_service"},
    "ths_total_revenue_stock": {"unit": "元", "cn_name": "营业总收入", "api": "basic_data_service"},
    "ths_np_stock": {"unit": "元", "cn_name": "净利润", "api": "basic_data_service"},
    "ths_total_assets_stock": {"unit": "元", "cn_name": "总资产", "api": "basic_data_service"},
    "ths_total_liab_stock": {"unit": "元", "cn_name": "总负债", "api": "basic_data_service"},
    "ths_cash_dividend_stock": {"unit": "元/股", "cn_name": "每股现金分红", "api": "basic_data_service"},
    "roe": {"unit": "%", "cn_name": "ROE", "api": "basic_data_service"},
    "eps": {"unit": "元/股", "cn_name": "每股收益", "api": "basic_data_service"},
    "end_date": {"unit": "YYYYMMDD", "cn_name": "报告期", "api": "financial"},
    "ann_date": {"unit": "YYYYMMDD", "cn_name": "公告日期", "api": "financial"},
    # 宏观 EDB
    "value": {"unit": "见指标说明", "cn_name": "指标值", "api": "edb_service"},
    # 指数点位
    "index_close": {"unit": "点", "cn_name": "指数收盘", "api": "cmd_history_quotation"},
}

TUSHARE_FIELD_UNITS: Dict[str, str] = {
    "close": "元",
    "pct_chg": "%",
    "vol": "手（100股/手）",
    "amount": "千元",
    "total_mv": "万元",
    "circ_mv": "万元",
    "turnover_rate": "%",
    "pe_ttm": "倍",
    "pb": "倍",
    "net_mf_amount": "万元",
    "trade_date": "YYYYMMDD",
}


def format_unit_label(field: str, meta: Optional[Dict[str, str]] = None) -> str:
    if meta:
        return f"{meta['unit']}（{meta['cn_name']}）"
    return field


def get_units_for_fields(fields: List[str], source: str = "ifind_native") -> Dict[str, str]:
    """按字段名列表生成 _field_units。"""
    registry = TUSHARE_FIELD_UNITS if source == "tushare" else IFIND_FIELD_UNITS
    out: Dict[str, str] = {}
    for f in fields:
        key = f.strip()
        if not key:
            continue
        if source == "tushare" and key in TUSHARE_FIELD_UNITS:
            out[key] = TUSHARE_FIELD_UNITS[key]
        elif key in IFIND_FIELD_UNITS:
            out[key] = format_unit_label(key, IFIND_FIELD_UNITS[key])
        else:
            out[key] = "未知（请对照 iFinD 超级命令）"
    return out


def get_units_for_records(
    records: List[Dict[str, Any]],
    source: str = "ifind_native",
    extra_fields: Optional[List[str]] = None,
) -> Dict[str, str]:
    """从 data 记录推断字段并生成单位表。"""
    keys: set = set(extra_fields or [])
    for row in records[:3]:
        if isinstance(row, dict):
            keys.update(row.keys())
    return get_units_for_fields(sorted(keys), source=source)


IFIND_UNITS_PROMPT = """
## iFinD 数据单位规范（CRITICAL）
1. 工具返回若含 _field_units，分析前必须先读取并对照单位，禁止假设 Tushare 旧单位
2. iFinD 与 Tushare 常见差异：
   - 成交量：iFinD volume=股，Tushare vol=手（1手=100股）
   - 成交额：iFinD amount=元，Tushare amount=千元
   - 市值：iFinD totalCapital/mv=元，Tushare total_mv/circ_mv=万元
   - 涨跌幅：iFinD changeRatio=%，Tushare pct_chg=%（含义相同）
3. 输出分析结论时，引用数值必须带单位（如「成交额 12.3 亿元」）
4. 若 _units_source 为 mixed，分别说明各段数据来源与单位
""".strip()
