"""iFinD 数据源适配器 — 供 stock agent 工具调用。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from tools.ifind.client import IFindAPIError, IFindClient, get_ifind_client
from tools.ifind.field_maps import (
    DAILY_BASIC_IFIND_INDICATORS,
    HISTORY_DEFAULT_IFIND,
    MONEYFLOW_IFIND_INDICATORS,
    TUSHARE_TO_IFIND_FINANCIAL,
    format_ifind_date,
    tushare_fields_to_ifind_indicators,
    tushare_fields_to_indipara,
    tushare_moneyflow_to_indipara,
)
from tools.ifind.response_parser import build_ifind_tool_payload, normalize_ifind_tables

_semaphore = threading.Semaphore(5)


class IFindAdapter:
    """iFinD HTTP API 封装。"""

    def __init__(self, client: Optional[IFindClient] = None):
        self.client = client or get_ifind_client()

    def is_available(self) -> bool:
        return self.client.is_configured()

    def _call(self, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_available():
            raise IFindAPIError("iFinD 未配置 IFIND_REFRESH_TOKEN")
        with _semaphore:
            return self.client.call(endpoint, body)

    def get_daily_quotation(
        self,
        codes: str,
        start_date: str,
        end_date: str,
        fields: Optional[str] = None,
        cps: str = "2",
        interval: str = "D",
    ) -> Dict[str, Any]:
        indicators = tushare_fields_to_ifind_indicators(fields, HISTORY_DEFAULT_IFIND)
        body = {
            "codes": codes,
            "indicators": indicators,
            "startdate": format_ifind_date(start_date),
            "enddate": format_ifind_date(end_date),
            "functionpara": {"Interval": interval, "CPS": cps, "Currency": "RMB", "Fill": "Previous"},
        }
        raw = self._call("cmd_history_quotation", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=True)
        return build_ifind_tool_payload(records, ts_code=codes.split(",")[0].strip(), data_source="ifind")

    def get_trade_dates(
        self,
        start_date: str,
        end_date: str,
        marketcode: str = "212001",
    ) -> Dict[str, Any]:
        body = {
            "marketcode": marketcode,
            "startdate": format_ifind_date(start_date),
            "enddate": format_ifind_date(end_date),
            "functionpara": {
                "mode": "1",
                "dateType": "0",
                "period": "D",
                "dateFormat": "2",
            },
        }
        raw = self._call("get_trade_dates", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=False, date_key="cal_date")
        # 统一为 cal_date / is_open 风格
        out = []
        for r in records:
            d = r.get("cal_date") or r.get("trade_date") or r.get("time")
            if d is not None:
                ds = str(d).replace("-", "")[:8]
                out.append({"cal_date": ds, "is_open": 1})
        if not out:
            # 兼容旧解析路径
            for r in records:
                d = list(r.values())[0] if r else None
                if d is not None:
                    ds = str(d).replace("-", "")[:8]
                    out.append({"cal_date": ds, "is_open": 1})
        return build_ifind_tool_payload(out, data_source="ifind")

    def get_thscode(self, seccode: str) -> Dict[str, Any]:
        body = {
            "seccode": seccode.replace(".SH", "").replace(".SZ", "").replace(".BJ", ""),
            "functionpara": {
                "mode": "seccode",
                "sectype": "",
                "market": "",
                "tradestatus": "0",
                "isexact": "0",
            },
        }
        raw = self._call("get_thscode", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=False)
        return build_ifind_tool_payload(records, data_source="ifind")

    def get_basic_data(
        self,
        codes: str,
        indicators: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        body = {"codes": codes, "indipara": indicators}
        raw = self._call("basic_data_service", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=True)
        return build_ifind_tool_payload(records, ts_code=codes.split(",")[0].strip(), data_source="ifind")

    def get_fina_indicator(
        self,
        codes: str,
        period: Optional[str] = None,
        fields: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        if start_date and end_date:
            indipara = tushare_fields_to_indipara(fields, report_period=period)
            if indipara:
                return self.get_date_sequence(codes, start_date, end_date, indipara)

        indipara = tushare_fields_to_indipara(fields, report_period=period)
        if not indipara:
            rd = period or datetime.now().strftime("%Y1231")
            rd = "".join(c for c in str(rd) if c.isdigit())[:8]
            indipara = [
                {"indicator": "ths_roe_stock", "indiparams": [rd]},
                {"indicator": "ths_eps_stock", "indiparams": [rd]},
            ]
        return self.get_basic_data(codes, indipara)

    def get_financial_series(
        self,
        codes: str,
        start_date: str,
        end_date: str,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """财务指标时间序列（date_sequence，报告期维度）。"""
        indipara = tushare_fields_to_indipara(fields)
        if not indipara:
            return {"error": "无有效财务字段"}
        return self.get_date_sequence(
            codes,
            start_date,
            end_date,
            indipara,
            interval="Q",
            days="Alldays",
        )

    def get_moneyflow_history(
        self,
        codes: str,
        start_date: str,
        end_date: str,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """历史资金流：优先 date_sequence（ths 指标），无数据则返回空。"""
        indipara = tushare_moneyflow_to_indipara(fields)
        if indipara:
            payload = self.get_date_sequence(codes, start_date, end_date, indipara)
            if payload.get("success"):
                return payload
        # cmd_history 对部分账号无资金流列，直接返回空由上层降级
        return {"error": "未查询到数据", "data_source": "ifind"}

    def get_date_sequence(
        self,
        codes: str,
        start_date: str,
        end_date: str,
        indicators: List[Dict[str, Any]],
        interval: str = "D",
        days: str = "Tradedays",
    ) -> Dict[str, Any]:
        body = {
            "codes": codes,
            "startdate": format_ifind_date(start_date),
            "enddate": format_ifind_date(end_date),
            "indipara": indicators,
            "functionpara": {"Days": days, "Fill": "Previous", "Interval": interval},
        }
        raw = self._call("date_sequence", body)
        date_key = "end_date" if interval in ("Q", "M", "Y", "S") else "trade_date"
        records = normalize_ifind_tables(raw, alias_to_tushare=True, date_key=date_key)
        return build_ifind_tool_payload(records, ts_code=codes.split(",")[0].strip(), data_source="ifind")

    def get_realtime_quotation(self, codes: str, indicators: str = MONEYFLOW_IFIND_INDICATORS) -> Dict[str, Any]:
        body = {"codes": codes, "indicators": indicators}
        raw = self._call("real_time_quotation", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=True)
        return build_ifind_tool_payload(records, ts_code=codes.split(",")[0].strip(), data_source="ifind")

    def get_edb(self, indicator_ids: str, start_date: str, end_date: str) -> Dict[str, Any]:
        body = {
            "indicators": indicator_ids,
            "startdate": format_ifind_date(start_date),
            "enddate": format_ifind_date(end_date),
        }
        raw = self._call("edb_service", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=False)
        return build_ifind_tool_payload(records, data_source="ifind")

    def get_smart_stock_picking(
        self,
        searchstring: str,
        searchtype: str = "stock",
    ) -> Dict[str, Any]:
        from tools.ifind.response_parser import normalize_smart_picking_tables

        body = {"searchstring": searchstring, "searchtype": searchtype}
        raw = self._call("smart_stock_picking", body)
        records = normalize_smart_picking_tables(raw)
        return build_ifind_tool_payload(records, data_source="ifind")

    def get_report_query(
        self,
        codes: str,
        begin_date: str,
        end_date: str,
        report_type: str = "903",
    ) -> Dict[str, Any]:
        body = {
            "codes": codes,
            "functionpara": {
                "reportType": report_type,
                "beginrDate": format_ifind_date(begin_date),
                "endrDate": format_ifind_date(end_date),
            },
            "outputpara": "reportDate:Y,thscode:Y,secName:Y,ctime:Y,reportTitle:Y,pdfURL:Y,seq:Y",
        }
        raw = self._call("report_query", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=False)
        return build_ifind_tool_payload(records, ts_code=codes.split(",")[0].strip(), data_source="ifind")

    def get_data_pool(
        self,
        report_key: str,
        start_date: str,
        end_date: str,
        outputpara: Optional[str] = None,
    ) -> Dict[str, Any]:
        from tools.ifind.report_codes import (
            DATA_POOL_FUNCTIONPARA,
            DATA_POOL_REPORTS,
            DEFAULT_OUTPUTPARA,
        )

        reportname = DATA_POOL_REPORTS.get(report_key, report_key)
        tpl = DATA_POOL_FUNCTIONPARA.get(report_key, DATA_POOL_FUNCTIONPARA.get("limit_up_pool", {}))
        sd = "".join(c for c in str(start_date) if c.isdigit())[:8]
        ed = "".join(c for c in str(end_date) if c.isdigit())[:8]
        functionpara = {k: v.format(start=sd, end=ed) if isinstance(v, str) else v for k, v in tpl.items()}
        body = {
            "reportname": reportname,
            "functionpara": functionpara,
            "outputpara": outputpara or DEFAULT_OUTPUTPARA,
        }
        raw = self._call("data_pool", body)
        records = normalize_ifind_tables(raw, alias_to_tushare=False)
        return build_ifind_tool_payload(records, data_source="ifind")

    def payload_to_json(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)


_adapter: Optional[IFindAdapter] = None


def get_ifind_adapter() -> IFindAdapter:
    global _adapter
    if _adapter is None:
        _adapter = IFindAdapter()
    return _adapter


def ifind_daily_basic(codes: str, start_date: str, end_date: str, fields: Optional[str] = None) -> Dict[str, Any]:
    ind = tushare_fields_to_ifind_indicators(fields, DAILY_BASIC_IFIND_INDICATORS)
    return get_ifind_adapter().get_daily_quotation(codes, start_date, end_date, ind, cps="1")
