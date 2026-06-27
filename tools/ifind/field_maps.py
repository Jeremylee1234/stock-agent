"""Tushare 工具 fields 参数 ↔ iFinD indicators 映射。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

# Tushare field -> iFinD indicator (cmd_history_quotation)
TUSHARE_TO_IFIND_QUOTE: Dict[str, str] = {
    "trade_date": "time",
    "ts_code": "thscode",
    "pre_close": "preClose",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "change": "change",
    "pct_chg": "changeRatio",
    "vol": "volume",
    "amount": "amount",
    "turnover_rate": "turnoverRatio",
    "turnover_rate_f": "turnoverRatio",
    "volume_ratio": "vol_ratio",
    "pe": "pe",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "ps": "ps",
    "ps_ttm": "ps",
    "total_mv": "totalCapital",
    "circ_mv": "mv",
    "total_share": "totalCapital",
    "float_share": "mv",
}

# iFinD indicator -> Tushare field（输出兼容）
IFIND_TO_TUSHARE_QUOTE: Dict[str, str] = {v: k for k, v in TUSHARE_TO_IFIND_QUOTE.items() if k not in ("turnover_rate_f", "ps_ttm", "total_share", "float_share")}
IFIND_TO_TUSHARE_QUOTE.update({
    "changeRatio": "pct_chg",
    "volume": "vol",
    "preClose": "pre_close",
    "turnoverRatio": "turnover_rate",
    "totalCapital": "total_mv",
    "mv": "circ_mv",
    "time": "trade_date",
})

DAILY_BASIC_IFIND_INDICATORS = "close,turnoverRatio,pe_ttm,pb,ps,totalCapital,mv,vol_ratio"

HISTORY_DEFAULT_IFIND = "open,high,low,close,preClose,change,changeRatio,volume,amount"

# 财务：Tushare field -> ths 指标名（可按账号权限扩展）
TUSHARE_TO_IFIND_FINANCIAL: Dict[str, str] = {
    "roe": "ths_roe_stock",
    "roa": "ths_roa_stock",
    "eps": "ths_eps_stock",
    "dt_eps": "ths_eps_deducted_stock",
    "bps": "ths_bps_stock",
    "netprofit_yoy": "ths_np_yoy_stock",
    "netprofit_margin": "ths_np_margin_stock",
    "grossprofit_margin": "ths_gross_profit_margin_stock",
    "debt_to_assets": "ths_asset_liab_ratio_stock",
    "current_ratio": "ths_current_ratio_stock",
    "quick_ratio": "ths_quick_ratio_stock",
    "total_revenue": "ths_operating_total_revenue_stock",
    "revenue": "ths_operating_revenue_stock",
    "n_income": "ths_np_stock",
    "n_income_attr_p": "ths_np_atoopc_stock",
    "total_assets": "ths_total_assets_stock",
    "total_liab": "ths_total_liab_stock",
    "total_hldr_eqy_exc_min_int": "ths_total_equity_atoopc_stock",
    "n_cashflow_act": "ths_ncf_from_oa_stock",
    "n_cash_flows_inv_act": "ths_ncf_from_ia_stock",
    "n_cash_flows_fnc_act": "ths_ncf_from_fa_stock",
    "operate_profit": "ths_op_stock",
    "total_profit": "ths_total_profit_stock",
    "basic_eps": "ths_basic_eps_stock",
    "cash_div": "ths_cash_dividend_ps_stock",
    "stk_div": "ths_stock_dividend_ps_stock",
}

# 资金流历史（date_sequence）— ths_net_inflow_amt_stock 已联调可用
TUSHARE_TO_IFIND_MONEYFLOW: Dict[str, str] = {
    "net_mf_amount": "ths_net_inflow_amt_stock",
    "net_amount": "ths_net_inflow_amt_stock",
    "buy_elg_amount": "ths_super_large_net_inflow_stock",
    "sell_elg_amount": "ths_super_large_net_outflow_stock",
    "buy_lg_amount": "ths_large_net_inflow_stock",
    "sell_lg_amount": "ths_large_net_outflow_stock",
    "pct_change": "ths_chg_ratio_stock",
    "close": "ths_close_price_stock",
}

IFIND_TO_TUSHARE_MONEYFLOW: Dict[str, str] = {
    "ths_net_inflow_amt_stock": "net_mf_amount",
    "mainNetInflow": "net_mf_amount",
    "largeNetInflow": "buy_elg_amount",
    "bigNetInflow": "buy_lg_amount",
}

DEFAULT_FINANCIAL_FIELDS = "roe,roa,eps,netprofit_margin,grossprofit_margin,debt_to_assets"
DEFAULT_MONEYFLOW_FIELDS = "net_mf_amount,buy_elg_amount,sell_elg_amount,close"

MONEYFLOW_IFIND_INDICATORS = "mainNetInflow,largeNetInflow,bigNetInflow"


def tushare_fields_to_ifind_indicators(fields: Optional[str], default: str = HISTORY_DEFAULT_IFIND) -> str:
    """将逗号分隔的 Tushare fields 转为 iFinD indicators 列表。"""
    if not fields or not str(fields).strip():
        return default
    parts = [p.strip() for p in str(fields).split(",") if p.strip()]
    mapped: List[str] = []
    for p in parts:
        if p in TUSHARE_TO_IFIND_QUOTE:
            ind = TUSHARE_TO_IFIND_QUOTE[p]
            if ind not in mapped and ind != "time":
                mapped.append(ind)
        elif p in IFIND_TO_TUSHARE_QUOTE or p in TUSHARE_TO_IFIND_QUOTE.values():
            if p not in mapped:
                mapped.append(p)
        else:
            mapped.append(p)
    if "time" not in mapped and "trade_date" in parts:
        pass  # 日期由 parser 从 time 列生成
    return ",".join(mapped) if mapped else default


def tushare_fields_to_indipara(
    fields: Optional[str],
    default_fields: str = DEFAULT_FINANCIAL_FIELDS,
    report_period: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """将 Tushare fields 转为 basic_data / date_sequence 的 indipara 数组。"""
    field_list = [f.strip() for f in (fields or default_fields).split(",") if f.strip()]
    rd = report_period or datetime.now().strftime("%Y1231")
    rd = "".join(c for c in str(rd) if c.isdigit())[:8]
    indipara: List[Dict[str, Any]] = []
    for f in field_list:
        if f in ("ts_code", "ann_date", "end_date", "trade_date", "report_type"):
            continue
        ths = TUSHARE_TO_IFIND_FINANCIAL.get(f)
        if not ths:
            ths = f if f.startswith("ths_") else f"ths_{f}_stock"
        indipara.append({"indicator": ths, "indiparams": ["", "100"] if not report_period else [rd]})
    return indipara


def tushare_moneyflow_to_indipara(fields: Optional[str]) -> List[Dict[str, Any]]:
    field_list = [f.strip() for f in (fields or DEFAULT_MONEYFLOW_FIELDS).split(",") if f.strip()]
    indipara: List[Dict[str, Any]] = []
    for f in field_list:
        if f in ("ts_code", "trade_date"):
            continue
        ths = TUSHARE_TO_IFIND_MONEYFLOW.get(f, f"ths_{f}_stock")
        indipara.append({"indicator": ths, "indiparams": [""]})
    return indipara


def rename_record_keys_ifind_to_tushare(record: Dict, alias: bool = True) -> Dict:
    """单条记录：iFinD 字段名转为 Tushare 兼容名（保持 agent 现有 fields 认知）。"""
    if not alias:
        return record
    out = {}
    for k, v in record.items():
        nk = IFIND_TO_TUSHARE_MONEYFLOW.get(k) or IFIND_TO_TUSHARE_QUOTE.get(k, k)
        if nk == "time":
            nk = "trade_date"
            if v and isinstance(v, str):
                v = v.replace("-", "").replace("/", "")[:8]
        out[nk] = v
    return out


def format_ifind_date(ymd: Optional[str]) -> str:
    """YYYYMMDD -> YYYY-MM-DD"""
    if not ymd:
        return ""
    s = "".join(c for c in str(ymd) if c.isdigit())[:8]
    if len(s) != 8:
        return str(ymd)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
