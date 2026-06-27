"""
Tushare 扩展工具集 - 覆盖 tushare skill 全部 API 分类
包含：指数/ETF/公募基金/债券/期货/期权/港股/美股/外汇/现货/宏观/行业/资金流/打板/特色数据
"""
import json
from typing import Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool

# 复用共享模块（避免与 stock_agent_main 循环依赖）
from tools.tushare_client import pro, tushare_api_call_with_retry
from tools.stock_data_helpers import (
    to_ts_code as _to_ts_code,
    fmt_date as _fmt,
    clamp_today as _clamp_today,
    normalize_date as _normalize_date,
    fetch_daily_df_fallback as _fetch_daily_df_fallback,
    json_from_df as _json_from_df,
    TODAY_YMD,
)
from tools.data_sources.ifind_adapter import get_ifind_adapter
from tools.ifind.client import IFindAPIError
from tools.ifind_bridge import (
    wrap_ifind_payload,
    payload_to_json,
    df_to_payload,
    attach_tushare_units,
    try_ifind_moneyflow_history,
    try_ifind_data_pool,
    try_ifind_smart_picking,
)


def _wrap_df(df, limit: int = 50, sort_col: str = None, data_source: str = "tushare") -> str:
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
    if sort_col and sort_col in df.columns:
        df = df.sort_values(sort_col)
    pl = df_to_payload(df.head(limit), data_source=data_source)
    if data_source == "tushare":
        attach_tushare_units(pl)
    return payload_to_json(pl)


# ============================================================
# 股票基础数据
# ============================================================

@tool(description="""获取交易日历。
exchange: 交易所 SSE/SZSE/CFFEX/SHFE/DCE/CZCE（默认SSE）
start_date / end_date: 日期范围 YYYYMMDD
is_open: 1开市 0休市（可选）""")
def tool_get_trade_cal(exchange: str = "SSE", start_date: str = None,
                       end_date: str = None, is_open: str = None) -> str:
    try:
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        market = "212001" if exchange.upper() in ("SSE", "SH") else "212100"
        try:
            adapter = get_ifind_adapter()
            if adapter.is_available():
                payload = adapter.get_trade_dates(sd, ed, marketcode=market)
                if payload.get("success"):
                    return wrap_ifind_payload(payload, limit=100, sort_col="cal_date")
        except IFindAPIError:
            pass
        df = tushare_api_call_with_retry(
            pro.trade_cal, exchange=exchange, start_date=sd, end_date=ed, is_open=is_open
        )
        return _wrap_df(df, limit=100, sort_col="cal_date")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取股票曾用名历史记录。
stock_code: 股票代码""")
def tool_get_namechange(stock_code: str) -> str:
    try:
        df = tushare_api_call_with_retry(pro.namechange, ts_code=_to_ts_code(stock_code),
                            fields='ts_code,name,start_date,end_date,change_reason')
        return _wrap_df(df)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取IPO新股上市列表。
start_date / end_date: 上市日期范围 YYYYMMDD
字段单位说明：
  issue_price: 元（发行价）
  issue_amount: 万股（发行总量）
  market_amount: 万股（上网发行量）
  amount: 万元（募集资金）
  pe: 倍（市盈率）
  limit_amount: 万股（个人申购上限）
  funds: 亿元（超募资金）
  ballot: % 中签率）""")
def tool_get_new_share(start_date: str = None, end_date: str = None) -> str:
    try:
        df = tushare_api_call_with_retry(pro.new_share, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取沪深港通股票列表（北向/南向资金标的）。
hs_type: SH沪股通 SZ深股通
is_new: 1最新 0历史（默认1）""")
def tool_get_hs_const(hs_type: str = "SH", is_new: str = "1") -> str:
    try:
        df = tushare_api_call_with_retry(pro.hs_const, hs_type=hs_type, is_new=is_new)
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取ST/退市风险股票列表。
trade_date: 交易日期 YYYYMMDD（可选，默认最新）""")
def tool_get_stk_rewards(trade_date: str = None) -> str:
    try:
        df = tushare_api_call_with_retry(pro.stk_rewards, trade_date=_fmt(trade_date) or TODAY_YMD)
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 行情数据
# ============================================================

@tool(description="""获取股票复权行情（前复权/后复权）。
stock_code: 股票代码
start_date / end_date: 日期范围 YYYYMMDD
adj: qfq前复权 hfq后复权（默认qfq）
fields: 可选字段 ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount
字段单位说明：
  open/high/low/close/pre_close/change: 元（复权后价格）
  pct_chg: % 涨跌幅
  vol: 手（100股/手）
  amount: 千元""")
def tool_get_adj_factor(stock_code: str, start_date: str = None, end_date: str = None,
                        adj: str = "qfq", fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        sd = _normalize_date(start_date, (datetime.now() - timedelta(days=90)).strftime("%Y%m%d"))
        ed = _clamp_today(_normalize_date(end_date, TODAY_YMD))
        cps = "2" if adj.lower() in ("qfq", "2") else "3"
        df, src = _fetch_daily_df_fallback(tc, sd, ed, fields, cps=cps)
        if df is None or df.empty:
            df = tushare_api_call_with_retry(
                pro.daily, ts_code=tc, start_date=sd, end_date=ed, adj=adj, fields=fields
            )
            src = "tushare"
        if df is None or df.empty:
            return json.dumps({"error": "未查询到数据"}, ensure_ascii=False)
        return _json_from_df(df, tc, src, tail_limit=60, extra={"adj": adj})
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取股票周线/月线行情。
stock_code: 股票代码
freq: W周线 M月线
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount
字段单位说明：
  open/high/low/close/pre_close/change: 元（人民币）
  pct_chg: % 涨跌幅
  vol: 手（100股/手）
  amount: 千元""")
def tool_get_weekly_monthly(stock_code: str, freq: str = "W",
                            start_date: str = None, end_date: str = None,
                            fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=365 * 3)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        interval = "W" if freq.upper() == "W" else "M"
        try:
            adapter = get_ifind_adapter()
            if adapter.is_available():
                payload = adapter.get_daily_quotation(
                    tc, sd, ed, fields, cps="2", interval=interval
                )
                if payload.get("success"):
                    return wrap_ifind_payload(payload, limit=52, sort_col="trade_date")
        except IFindAPIError:
            pass
        api = pro.weekly if freq.upper() == "W" else pro.monthly
        df = tushare_api_call_with_retry(
            api, ts_code=tc, start_date=sd, end_date=ed, fields=fields
        )
        return _wrap_df(df, limit=52, sort_col="trade_date")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取每日停复牌信息。
trade_date: 交易日期 YYYYMMDD
stock_code: 股票代码（可选）""")
def tool_get_suspend_d(trade_date: str = None, stock_code: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.suspend_d(ts_code=tc, trade_date=_fmt(trade_date) or TODAY_YMD)
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取沪深股通十大成交股（北向资金）。
trade_date: 交易日期 YYYYMMDD
market_type: 1沪股通 3深股通（可选）
字段单位说明：
  close: 元（收盘价）
  change_rate: % 涨跌幅
  net_amount: 万元（净买入金额）
  buy_amount / sell_amount: 万元（买入/卖出金额）
  hold_ratio: % 持股占流通股比例""")
def tool_get_hsgt_top10(trade_date: str = None, market_type: str = None) -> str:
    try:
        df = pro.hsgt_top10(trade_date=_fmt(trade_date) or TODAY_YMD,
                            market_type=market_type)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 财务数据
# ============================================================

@tool(description="""获取业绩快报（正式财报前的快速披露）。
stock_code: 股票代码
start_date / end_date: 公告日期范围 YYYYMMDD
fields: 可选字段 ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,
        total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,growth_assets,yoy_equity
字段单位说明：
  revenue / operate_profit / total_profit / n_income: 元（人民币）
  total_assets / total_hldr_eqy_exc_min_int: 元
  diluted_eps: 元/股
  diluted_roe: % 摊薄净资产收益率
  yoy_net_profit / growth_assets / yoy_equity: % 同比增长率""")
def tool_get_express(stock_code: str = None, start_date: str = None,
                     end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.express(ts_code=tc, start_date=_fmt(start_date),
                         end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=10)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取主营业务构成（按产品/地区分类）。
stock_code: 股票代码
period: 报告期 YYYYMMDD（可选）
type: P按产品 D按地区（默认P）
字段单位说明：
  bz_sales: 元（主营业务收入）
  bz_profit: 元（主营业务利润）
  bz_cost: 元（主营业务成本）
  curr_type: 货币类型（CNY等）
  bz_sales_yoy: % 收入同比增长率""")
def tool_get_fina_mainbz(stock_code: str, period: str = None, bz_type: str = "P") -> str:
    try:
        tc = _to_ts_code(stock_code)
        df = pro.fina_mainbz(ts_code=tc, period=_fmt(period), type=bz_type)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取财务审计意见（标准/非标准）。
stock_code: 股票代码
start_date / end_date: 公告日期范围 YYYYMMDD""")
def tool_get_fina_audit(stock_code: str = None, start_date: str = None,
                        end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.fina_audit(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=10)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 参考数据
# ============================================================

@tool(description="""获取限售股解禁数据。
stock_code: 股票代码（可选）
start_date / end_date: 解禁日期范围 YYYYMMDD
字段单位说明：
  float_share: 万股（解禁股数）
  float_ratio: % 解禁股占总股本比例""")
def tool_get_share_float(stock_code: str = None, start_date: str = None,
                         end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.share_float(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股票回购数据。
stock_code: 股票代码（可选）
start_date / end_date: 公告日期范围 YYYYMMDD
字段单位说明：
  amount: 万元（回购金额）
  high / low: 元（回购价格区间）
  vol: 万股（回购数量）
  ratio: % 占总股本比例""")
def tool_get_repurchase(stock_code: str = None, start_date: str = None,
                        end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.repurchase(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股东增减持数据。
stock_code: 股票代码（可选）
start_date / end_date: 公告日期范围 YYYYMMDD
字段单位说明：
  change_vol: 万股（变动股数）
  change_ratio: % 占总股本变动比例
  after_share: 万股（变动后持股数）
  after_ratio: % 变动后持股比例
  avg_price: 元（均价）
  total_share: 万股（持股总数）""")
def tool_get_holder_trade(stock_code: str = None, start_date: str = None,
                          end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.holder_trade(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股东人数（户数）数据。
stock_code: 股票代码
start_date / end_date: 公告日期范围 YYYYMMDD
字段单位说明：
  holder_num: 户（股东人数）
  holder_num_rate: % 股东人数变动比例""")
def tool_get_stk_holdernumber(stock_code: str = None, start_date: str = None,
                               end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.stk_holdernumber(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=10)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取股权质押统计数据。
stock_code: 股票代码（可选）
end_date: 截止日期 YYYYMMDD
字段单位说明：
  total_share: 万股（总股本）
  pledge_count: 次（质押次数）
  unrest_pledge: 万股（无限售股质押数量）
  rest_pledge: 万股（限售股质押数量）
  total_pledge: 万股（总质押数量）
  pledge_ratio: % 质押比例（占总股本）""")
def tool_get_pledge_stat(stock_code: str = None, end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.pledge_stat(ts_code=tc, end_date=_fmt(end_date))
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取大宗交易数据（股票）。
stock_code: 股票代码（可选）
start_date / end_date: 交易日期范围 YYYYMMDD
字段单位说明：
  price: 元（成交价）
  vol: 万股（成交量）
  amount: 万元（成交金额）
  premium: % 溢价率（相对收盘价）""")
def tool_get_block_trade(stock_code: str = None, start_date: str = None,
                         end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.block_trade(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 资金流向
# ============================================================

@tool(description="""获取沪深港通资金流向（北向/南向资金）。
start_date / end_date: 日期范围 YYYYMMDD
trade_type: N北向 S南向（可选）
字段单位说明：
  buy_amount / sell_amount: 亿元（买入/卖出成交额）
  buy_amount_sse / sell_amount_sse: 亿元（沪市买入/卖出）
  buy_amount_szse / sell_amount_szse: 亿元（深市买入/卖出）
  net_amount: 亿元（净买入额）
  quota_daily / quota_daily_balance: 亿元（每日额度/余额）""")
def tool_get_moneyflow_hsgt(start_date: str = None, end_date: str = None,
                             trade_type: str = None) -> str:
    try:
        df = pro.moneyflow_hsgt(start_date=_fmt(start_date), end_date=_fmt(end_date),
                                trade_type=trade_type)
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取同花顺个股资金流向（THS）。
stock_code: 股票代码
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,close,pct_change,net_amount,net_d5_amount,buy_lg_amount,sell_lg_amount
字段单位说明：
  close: 元（收盘价）
  pct_change: % 涨跌幅
  net_amount / net_d5_amount: 万元（当日/5日净流入金额）
  buy_lg_amount / sell_lg_amount: 万元（大单买入/卖出金额）""")
def tool_get_moneyflow_ths(stock_code: str, start_date: str = None,
                            end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        sd = _fmt(start_date)
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        if sd and ed:
            payload = try_ifind_moneyflow_history(tc, sd, ed, fields or "net_amount,close,pct_change")
            if payload and payload.get("success"):
                payload["note"] = "同花顺口径资金流（iFinD date_sequence）"
                return wrap_ifind_payload(payload, limit=30, sort_col="trade_date")
        try:
            adapter = get_ifind_adapter()
            if adapter.is_available() and not start_date and not end_date:
                payload = adapter.get_realtime_quotation(
                    tc, "mainNetInflow,largeNetInflow,bigNetInflow,latest,changeRatio"
                )
                if payload.get("success"):
                    payload["note"] = "同花顺个股资金流（iFinD 实时）；历史区间请传 start_date/end_date"
                    return payload_to_json(payload)
        except IFindAPIError:
            pass
        df = tushare_api_call_with_retry(
            pro.moneyflow_ths,
            ts_code=tc,
            start_date=_fmt(start_date),
            end_date=_fmt(end_date),
            fields=fields,
        )
        return _wrap_df(df, limit=30, sort_col="trade_date")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取同花顺行业资金流向。
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  close: 点（板块指数收盘点位）
  pct_change: % 涨跌幅
  net_amount: 万元（净流入金额）
  buy_amount / sell_amount: 万元（买入/卖出金额）""")
def tool_get_moneyflow_ind_ths(trade_date: str = None, start_date: str = None,
                                end_date: str = None) -> str:
    try:
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or _fmt(trade_date) or TODAY_YMD)
        try:
            adapter = get_ifind_adapter()
            if adapter.is_available():
                payload = adapter.get_daily_quotation(
                    "883957.TI",
                    sd,
                    ed,
                    "close,changeRatio,volume,amount,turnoverRatio",
                    cps="1",
                )
                if payload.get("success"):
                    payload["note"] = "行业指数行情（iFinD）；完整行业资金流列表仍可能需 Tushare"
                    return wrap_ifind_payload(payload, limit=50)
        except IFindAPIError:
            pass
        df = pro.moneyflow_ind_ths(
            trade_date=_fmt(trade_date), start_date=sd, end_date=ed
        )
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(description="""获取东方财富大盘资金流向（DC）。
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  close: 点（上证指数收盘点位）
  net_amount: 亿元（净流入金额）
  buy_elg_amount / sell_elg_amount: 亿元（超大单买入/卖出）
  buy_lg_amount / sell_lg_amount: 亿元（大单买入/卖出）
  buy_md_amount / sell_md_amount: 亿元（中单买入/卖出）
  buy_sm_amount / sell_sm_amount: 亿元（小单买入/卖出）""")
def tool_get_moneyflow_mkt_dc(start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.moneyflow_mkt_dc(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 打板专题数据
# ============================================================

@tool(description="""获取涨跌停和炸板数据（2020年起）。
trade_date: 交易日期 YYYYMMDD
stock_code: 股票代码（可选）
fields: 可选字段 ts_code,trade_date,name,close,pct_chg,limit_times,fc_ratio,fl_ratio,fd_amount,first_time,last_time,open_times,strth,limit
字段单位说明：
  close: 元（收盘价）
  pct_chg: % 涨跌幅
  limit_times: 次（连板天数）
  fc_ratio: % 封单量占流通股比
  fl_ratio: % 封单额占成交额比
  fd_amount: 万元（封单金额）
  open_times: 次（炸板次数）
  strth: % 封板强度""")
def tool_get_limit_list_d(trade_date: str = None, stock_code: str = None,
                           fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        td = _fmt(trade_date) or TODAY_YMD
        payload = try_ifind_smart_picking("涨停", "stock")
        if payload and payload.get("success"):
            data = payload.get("data", [])
            if tc:
                data = [r for r in data if r.get("ts_code") == tc]
            payload["data"] = data
            payload["count"] = len(data)
            payload["trade_date"] = td
            payload["note"] = "iFinD smart_stock_picking（涨停）"
            return wrap_ifind_payload(payload, limit=50)
        df = pro.limit_list_d(trade_date=td, ts_code=tc, fields=fields)
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取涨停最强板块统计（每日涨停股最多的概念板块）。
trade_date: 交易日期 YYYYMMDD""")
def tool_get_limit_cpt_list(trade_date: str = None) -> str:
    try:
        df = pro.limit_cpt_list(trade_date=_fmt(trade_date) or TODAY_YMD)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取涨停股票连板天梯（每日连板晋级情况）。
trade_date: 交易日期 YYYYMMDD""")
def tool_get_limit_step_list(trade_date: str = None) -> str:
    try:
        df = pro.limit_step_list(trade_date=_fmt(trade_date) or TODAY_YMD)
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取龙虎榜机构交易明细。
trade_date: 交易日期 YYYYMMDD（可选）
stock_code: 股票代码（可选）
字段单位说明：
  buy / sell: 万元（机构买入/卖出金额）
  net_buy: 万元（净买入金额）""")
def tool_get_top_inst(trade_date: str = None, stock_code: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.top_inst(trade_date=_fmt(trade_date), ts_code=tc)
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取游资交易每日明细（2022年8月起）。
trade_date: 交易日期 YYYYMMDD（可选）
stock_code: 股票代码（可选）
字段单位说明：
  buy_amount / sell_amount: 万元（买入/卖出金额）
  net_amount: 万元（净买入金额）""")
def tool_get_hm_detail(trade_date: str = None, stock_code: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.hm_detail(trade_date=_fmt(trade_date) or TODAY_YMD, ts_code=tc)
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取同花顺行业概念板块列表及行情。
trade_date: 交易日期 YYYYMMDD（可选）
ts_code: 板块代码（可选）
字段单位说明：
  open/high/low/close: 点（板块指数点位）
  pct_change: % 涨跌幅
  vol: 手（成交量）
  turnover_rate: % 换手率
  total_mv: 亿元（总市值）""")
def tool_get_ths_index(trade_date: str = None, ts_code: str = None) -> str:
    try:
        code = ts_code or "883957.TI"
        sd = _fmt(trade_date) or (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(trade_date) or TODAY_YMD)
        df, src = _fetch_daily_df_fallback(
            code, sd, ed, "trade_date,open,high,low,close,pct_chg,vol,turnover_rate", cps="1"
        )
        if df is not None and not df.empty:
            return _json_from_df(df, code, src, tail_limit=50)
        df = pro.ths_daily(ts_code=code, trade_date=_fmt(trade_date) or TODAY_YMD)
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# 特色数据
# ============================================================

@tool(description="""获取沪深股通持股明细（北向资金持仓）。
stock_code: 股票代码（可选）
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  vol: 股（持股数量）
  ratio: % 持股占流通股比例
  close: 元（收盘价）""")
def tool_get_hk_hold(stock_code: str = None, trade_date: str = None,
                     start_date: str = None, end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.hk_hold(ts_code=tc, trade_date=_fmt(trade_date),
                         start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取机构调研数据。
stock_code: 股票代码（可选）
start_date / end_date: 调研日期范围 YYYYMMDD""")
def tool_get_stk_surv(stock_code: str = None, start_date: str = None,
                      end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.stk_surv(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取券商盈利预测数据（卖方研报）。
stock_code: 股票代码（可选）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,name,type,reporter,period,op_rt,op_pr,tp,np,eps,pe,rd,roe,ev_ebitda
字段单位说明：
  op_rt: 亿元（预测营业收入）
  op_pr: 亿元（预测营业利润）
  tp: 亿元（预测利润总额）
  np: 亿元（预测净利润）
  eps: 元/股（预测每股收益）
  pe: 倍（预测市盈率）
  rd: % 预测净利润增长率
  roe: % 预测净资产收益率
  ev_ebitda: 倍（EV/EBITDA）""")
def tool_get_report_rc(stock_code: str = None, start_date: str = None,
                       end_date: str = None, fields: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code) if stock_code else None
        df = pro.report_rc(ts_code=tc, start_date=_fmt(start_date),
                           end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取每日筹码及胜率（2018年起）。
stock_code: 股票代码
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  close: 元（收盘价）
  his_low / his_high: 元（历史最低/最高价）
  cost_5pct / cost_15pct / cost_50pct / cost_85pct / cost_95pct: 元（各分位筹码成本价）
  weight_avg: 元（加权平均成本）
  winner_rate: % 获利盘比例（胜率）""")
def tool_get_cyq_perf(stock_code: str, trade_date: str = None,
                      start_date: str = None, end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        df = pro.cyq_perf(ts_code=tc, trade_date=_fmt(trade_date),
                          start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取神奇九转指标（TD序列，2023年起）。
stock_code: 股票代码
start_date / end_date: 日期范围 YYYYMMDD""")
def tool_get_stk_nineturn(stock_code: str, start_date: str = None,
                           end_date: str = None) -> str:
    try:
        tc = _to_ts_code(stock_code)
        df = pro.stk_nineturn(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取AH股比价数据。
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  a_close: 元（A股收盘价，人民币）
  h_close: 港元（H股收盘价）
  ah_ratio: 倍（AH溢价率，A股/H股折算后比值）""")
def tool_get_ah_compare(trade_date: str = None, start_date: str = None,
                        end_date: str = None) -> str:
    try:
        df = pro.ah_compare(trade_date=_fmt(trade_date),
                            start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 指数专题
# ============================================================

@tool(description="""获取申万行业分类列表。
level: 一级/二级/三级（可选，默认全部）
src: SW2014 或 SW2021（默认SW2021）""")
def tool_get_sw_industry(level: str = None, src: str = "SW2021") -> str:
    try:
        df = pro.index_classify(level=level, src=src)
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取申万/中信行业成分股。
index_code: 行业指数代码（如 801010.SI）
is_new: 1最新 0历史（默认1）""")
def tool_get_index_member(index_code: str, is_new: str = "1") -> str:
    try:
        df = pro.index_member(index_code=index_code, is_new=is_new)
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取指数成分和权重（月度数据）。
index_code: 指数代码，如 000300.SH（沪深300）
start_date / end_date: 日期范围 YYYYMMDD（建议填当月首末日）
字段单位说明：
  weight: % 成分股权重""")
def tool_get_index_weight(index_code: str, start_date: str = None,
                          end_date: str = None) -> str:
    try:
        df = pro.index_weight(index_code=index_code,
                              start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取申万行业指数日行情。
ts_code: 申万行业指数代码（如 801010.SI）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,open,high,low,close,pct_change,vol,amount
字段单位说明：
  open/high/low/close: 点（指数点位）
  pct_change: % 涨跌幅
  vol: 手（成交量）
  amount: 万元（成交额）""")
def tool_get_sw_daily(ts_code: str, start_date: str = None,
                      end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.sw_daily(ts_code=ts_code, start_date=_fmt(start_date),
                          end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取国际主要指数日线行情（道琼斯/纳斯达克/标普500/恒生等）。
ts_code: 指数代码，如 DJI（道琼斯）IXIC（纳斯达克）HSI（恒生）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  open/high/low/close: 点（指数点位，各指数货币不同）
  pct_chg: % 涨跌幅
  vol: 手（成交量）
  amount: 百万（成交额，各指数货币不同）""")
def tool_get_index_global(ts_code: str, start_date: str = None,
                          end_date: str = None) -> str:
    try:
        df = pro.index_global(ts_code=ts_code, start_date=_fmt(start_date),
                              end_date=_fmt(end_date))
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# ETF 专题
# ============================================================

@tool(description="""获取ETF基本信息列表。
market: E场内 O场外（默认E）
status: L上市 D退市（默认L）
字段单位说明：
  issue_amount: 亿份（发行份额）
  m_fee: % 管理费率（年）
  c_fee: % 托管费率（年）""")
def tool_get_fund_basic(market: str = "E", status: str = "L") -> str:
    try:
        df = pro.fund_basic(market=market, status=status,
                            fields='ts_code,name,management,custodian,fund_type,found_date,due_date,list_date,issue_amount,m_fee,c_fee,benchmark,status,invest_type,type,trustee,purc_startdate,redm_startdate,market')
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取ETF日线行情。
ts_code: ETF代码，如 510300.SH（沪深300ETF）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,pre_close,open,high,low,close,change,pct_chg,vol,amount
字段单位说明：
  open/high/low/close/pre_close/change: 元（人民币）
  pct_chg: % 涨跌幅
  vol: 手（100份/手）
  amount: 千元""")
def tool_get_fund_daily(ts_code: str, start_date: str = None,
                        end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.fund_daily(ts_code=ts_code, start_date=_fmt(start_date),
                            end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取ETF份额规模数据（每日净值/收盘价/份额/规模）。
ts_code: ETF代码（可选）
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  fd_share: 亿份（基金份额）
  fd_nav: 元（单位净值）
  fd_nav_acc: 元（累计净值）
  fd_assets: 亿元（基金规模/净资产）""")
def tool_get_fund_share(ts_code: str = None, trade_date: str = None,
                        start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.fund_share(ts_code=ts_code, trade_date=_fmt(trade_date),
                            start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取公募基金净值数据。
ts_code: 基金代码
nav_date: 净值日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  unit_nav: 元（单位净值）
  accum_nav: 元（累计净值）
  accum_div: 元（累计分红）
  net_assets: 亿元（资产净值）
  adj_nav: 元（复权净值）""")
def tool_get_fund_nav(ts_code: str, nav_date: str = None,
                      start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.fund_nav(ts_code=ts_code, nav_date=_fmt(nav_date),
                          start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='nav_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取公募基金持仓数据（季度更新）。
ts_code: 基金代码（可选）
period: 报告期 YYYYMMDD（可选）
ann_date: 公告日期 YYYYMMDD（可选）
字段单位说明：
  mkv: 万元（持仓市值）
  amount: 万股（持仓数量）
  stk_mkv_ratio: % 占基金净值比例
  stk_float_ratio: % 占流通股比例""")
def tool_get_fund_portfolio(ts_code: str = None, period: str = None,
                             ann_date: str = None) -> str:
    try:
        df = pro.fund_portfolio(ts_code=ts_code, period=_fmt(period), ann_date=_fmt(ann_date))
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 债券专题
# ============================================================

@tool(description="""获取可转债基础信息。
ts_code: 可转债代码（可选）
list_status: L上市 D退市（默认L）
字段单位说明：
  par_value: 元（面值，通常为100元）
  issue_size: 亿元（发行规模）
  convert_price: 元（转股价格）
  convert_ratio: % 转股溢价率
  coupon_rate: % 票面利率
  maturity: 年（期限）""")
def tool_get_cb_basic(ts_code: str = None, list_status: str = "L") -> str:
    try:
        df = pro.cb_basic(ts_code=ts_code, list_status=list_status)
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取可转债日线行情。
ts_code: 可转债代码，如 113050.SH
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,pre_close,open,high,low,close,change,pct_chg,vol,amount,bond_value,bond_over_rate,cb_value,cb_over_rate
字段单位说明：
  open/high/low/close/pre_close/change: 元（可转债价格，面值100元）
  pct_chg: % 涨跌幅
  vol: 手（成交量）
  amount: 千元（成交额）
  bond_value: 元（纯债价值）
  bond_over_rate: % 纯债溢价率
  cb_value: 元（转股价值）
  cb_over_rate: % 转股溢价率""")
def tool_get_cb_daily(ts_code: str, start_date: str = None,
                      end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.cb_daily(ts_code=ts_code, start_date=_fmt(start_date),
                          end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取国债收益率曲线数据。
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 trade_date,ts_code,curve_term,yield_rate
字段单位说明：
  curve_term: 年（期限，如 0.25/0.5/1/2/3/5/7/10/20/30）
  yield_rate: % 收益率""")
def tool_get_yc_cb(start_date: str = None, end_date: str = None,
                   fields: str = None) -> str:
    try:
        df = pro.yc_cb(start_date=_fmt(start_date), end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=50, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取全球财经日历事件。
start_date / end_date: 日期范围 YYYYMMDD
country: 国家代码，如 CN US（可选）""")
def tool_get_eco_cal(start_date: str = None, end_date: str = None,
                     country: str = None) -> str:
    try:
        df = pro.eco_cal(start_date=_fmt(start_date), end_date=_fmt(end_date),
                         country=country)
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 期货数据
# ============================================================

@tool(description="""获取期货合约基础信息。
exchange: 交易所 CFFEX/DCE/CZCE/SHFE/INE/GFEX（可选）
fut_type: 1普通合约 2主力连续合约（默认1）
字段单位说明：
  multiplier: 合约乘数（每手对应标的数量）
  per_unit: 交易单位（如 吨/桶/克）
  quote_unit: 报价单位（如 元/吨）""")
def tool_get_fut_basic(exchange: str = None, fut_type: str = "1") -> str:
    try:
        df = pro.fut_basic(exchange=exchange, fut_type=fut_type,
                           fields='ts_code,symbol,exchange,name,fut_code,multiplier,trade_unit,per_unit,quote_unit,list_date,delist_date,d_mode_desc,io_price_type')
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取期货日线行情。
ts_code: 期货合约代码，如 CU2401.SHFE
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,pre_close,pre_settle,open,high,low,close,settle,change1,change2,vol,amount,oi,oi_chg
字段单位说明：
  open/high/low/close/pre_close/settle/pre_settle: 元（报价单位因品种而异，如 元/吨、元/克）
  change1: 元（收盘价-昨结算价）
  change2: 元（结算价-昨结算价）
  vol: 手（成交量）
  amount: 万元（成交额）
  oi: 手（持仓量）
  oi_chg: 手（持仓量变化）""")
def tool_get_fut_daily(ts_code: str, start_date: str = None,
                       end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.fut_daily(ts_code=ts_code, start_date=_fmt(start_date),
                           end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取期货每日持仓排名（多空主力席位）。
trade_date: 交易日期 YYYYMMDD
symbol: 品种代码，如 CU（铜）RB（螺纹钢）（可选）
字段单位说明：
  vol / vol_chg: 手（成交量/变化量）
  long_hld / long_chg: 手（多头持仓/变化）
  short_hld / short_chg: 手（空头持仓/变化）""")
def tool_get_fut_holding(trade_date: str = None, symbol: str = None) -> str:
    try:
        df = pro.fut_holding(trade_date=_fmt(trade_date) or TODAY_YMD, symbol=symbol)
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取期货主力与连续合约映射。
ts_code: 主力/连续合约代码，如 CU.SHFE
start_date / end_date: 日期范围 YYYYMMDD""")
def tool_get_fut_mapping(ts_code: str, start_date: str = None,
                         end_date: str = None) -> str:
    try:
        df = pro.fut_mapping(ts_code=ts_code, start_date=_fmt(start_date),
                             end_date=_fmt(end_date))
        return _wrap_df(df, limit=30)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 期权数据
# ============================================================

@tool(description="""获取期权合约基础信息。
exchange: 交易所 SSE/SZSE/CFFEX/DCE/CZCE/SHFE（可选）
call_put: C认购 P认沽（可选）
字段单位说明：
  per_unit: 合约单位（每张合约对应标的数量，如 10000份）
  exercise_price: 元（行权价格）
  list_price: 元（挂牌基准价）
  min_price_chg: 元（最小价格变动单位）""")
def tool_get_opt_basic(exchange: str = None, call_put: str = None) -> str:
    try:
        df = pro.opt_basic(exchange=exchange, call_put=call_put,
                           fields='ts_code,exchange,name,per_unit,opt_code,opt_type,call_put,exercise_type,exercise_price,s_month,maturity_date,list_price,list_date,delist_date,last_edate,quote_unit,min_price_chg')
        return _wrap_df(df, limit=50)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取期权日线行情。
ts_code: 期权合约代码
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,exchange,pre_settle,pre_close,open,high,low,close,settle,vol,amount,oi
字段单位说明：
  open/high/low/close/pre_close/settle/pre_settle: 元（期权价格）
  vol: 张（成交量）
  amount: 万元（成交额）
  oi: 张（持仓量）""")
def tool_get_opt_daily(ts_code: str, start_date: str = None,
                       end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.opt_daily(ts_code=ts_code, start_date=_fmt(start_date),
                           end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 港股数据
# ============================================================

@tool(description="""获取港股基础信息列表。
list_status: L上市 D退市（默认L）""")
def tool_get_hk_basic(list_status: str = "L") -> str:
    try:
        df = pro.hk_basic(list_status=list_status,
                          fields='ts_code,name,fullname,enname,cn_spell,market,list_status,list_date,delist_date,trade_unit,isin,curr_type')
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取港股日线行情。
ts_code: 港股代码，如 00700.HK（腾讯）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount
字段单位说明：
  open/high/low/close/pre_close/change: 港元（HKD）
  pct_chg: % 涨跌幅
  vol: 股（成交量）
  amount: 千港元（成交额）""")
def tool_get_hk_daily(ts_code: str, start_date: str = None,
                      end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.hk_daily(ts_code=ts_code, start_date=_fmt(start_date),
                          end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取港股财务指标数据。
ts_code: 港股代码
start_date / end_date: 公告日期范围 YYYYMMDD
fields: 可选字段 ts_code,ann_date,end_date,eps,bps,roe,roa,gross_profit_margin,net_profit_margin,debt_to_assets
字段单位说明：
  eps / bps: 港元/股（每股收益/净资产）
  roe / roa: % 净资产/总资产收益率
  gross_profit_margin / net_profit_margin: % 毛利率/净利率
  debt_to_assets: % 资产负债率""")
def tool_get_hk_fina(ts_code: str, start_date: str = None,
                     end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.hk_fina_indicator(ts_code=ts_code, start_date=_fmt(start_date),
                                   end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=10)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 美股数据
# ============================================================

@tool(description="""获取美股基础信息列表。
list_status: L上市 D退市（默认L）""")
def tool_get_us_basic(list_status: str = "L") -> str:
    try:
        df = pro.us_basic(list_status=list_status,
                          fields='ts_code,name,enname,classify,list_status,list_date,delist_date,exchange')
        return _wrap_df(df, limit=100)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取美股日线行情（未复权）。
ts_code: 美股代码，如 AAPL（苹果）TSLA（特斯拉）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount,vwap,turnover_rate,total_mv
字段单位说明：
  open/high/low/close/pre_close/change/vwap: 美元（USD）
  pct_chg: % 涨跌幅
  vol: 股（成交量）
  amount: 千美元（成交额）
  turnover_rate: % 换手率
  total_mv: 千美元（总市值）""")
def tool_get_us_daily(ts_code: str, start_date: str = None,
                      end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.us_daily(ts_code=ts_code, start_date=_fmt(start_date),
                          end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取美股财务指标数据（主要美股和中概股）。
ts_code: 美股代码
start_date / end_date: 公告日期范围 YYYYMMDD
fields: 可选字段 ts_code,ann_date,end_date,eps,bps,roe,roa,gross_profit_margin,net_profit_margin,debt_to_assets
字段单位说明：
  eps / bps: 美元/股（每股收益/净资产）
  roe / roa: % 净资产/总资产收益率
  gross_profit_margin / net_profit_margin: % 毛利率/净利率
  debt_to_assets: % 资产负债率""")
def tool_get_us_fina(ts_code: str, start_date: str = None,
                     end_date: str = None, fields: str = None) -> str:
    try:
        df = pro.us_fina_indicator(ts_code=ts_code, start_date=_fmt(start_date),
                                   end_date=_fmt(end_date), fields=fields)
        return _wrap_df(df, limit=10)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 宏观经济（扩展）
# ============================================================

@tool(description="""获取PMI采购经理指数。
start_date / end_date: 月度日期范围 YYYYMM（如 202301）
字段单位说明：
  pmi010000 / pmi010100 等: 指数值（50以上扩张，50以下收缩）
  所有PMI子指标均为无量纲指数，基准值为50""")
def tool_get_cn_pmi(start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.cn_pmi(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=24, sort_col='month')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取LPR贷款基础利率。
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  1y: % 1年期LPR利率
  5y: % 5年期以上LPR利率""")
def tool_get_lpr(start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.lpr(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=24, sort_col='date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取社会融资规模增量（月度）。
start_date / end_date: 月度日期范围 YYYYMM
字段单位说明：
  所有金额字段（rzye/rqye等）: 亿元（人民币）
  社融各分项增量均以亿元为单位""")
def tool_get_sf_month(start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.sf_month(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=24, sort_col='month')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取美国国债收益率曲线利率（每日）。
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  m1/m2/m3/m6: % 1/2/3/6个月期收益率
  y1/y2/y3/y5/y7/y10/y20/y30: % 1/2/3/5/7/10/20/30年期收益率""")
def tool_get_us_tycr(start_date: str = None, end_date: str = None) -> str:
    try:
        df = pro.us_tycr(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap_df(df, limit=30, sort_col='date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 融资融券
# ============================================================

@tool(description="""获取融资融券交易汇总数据。
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
exchange_id: SSE/SZSE（可选）
字段单位说明：
  rzye: 万元（融资余额）
  rzmre: 万元（融资买入额）
  rzche: 万元（融资偿还额）
  rqye: 万元（融券余额）
  rqmcl: 万股（融券卖出量）
  rzrqye: 万元（融资融券余额合计）""")
def tool_get_margin(trade_date: str = None, start_date: str = None,
                    end_date: str = None, exchange_id: str = None) -> str:
    try:
        df = pro.margin(trade_date=_fmt(trade_date), start_date=_fmt(start_date),
                        end_date=_fmt(end_date), exchange_id=exchange_id)
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取融资融券交易明细（个股）。
ts_code: 股票代码（可选）
trade_date: 交易日期 YYYYMMDD（可选）
start_date / end_date: 日期范围 YYYYMMDD
fields: 可选字段 ts_code,trade_date,name,rzye,rzmre,rzche,rqye,rqmcl,rzrqye,rqyl
字段单位说明：
  rzye: 万元（融资余额）
  rzmre: 万元（融资买入额）
  rzche: 万元（融资偿还额）
  rqye: 万元（融券余额）
  rqmcl: 万股（融券卖出量）
  rzrqye: 万元（融资融券余额合计）
  rqyl: 万股（融券余量）""")
def tool_get_margin_detail(ts_code: str = None, trade_date: str = None,
                            start_date: str = None, end_date: str = None,
                            fields: str = None) -> str:
    try:
        tc = _to_ts_code(ts_code) if ts_code else None
        df = pro.margin_detail(ts_code=tc, trade_date=_fmt(trade_date),
                               start_date=_fmt(start_date), end_date=_fmt(end_date),
                               fields=fields)
        return _wrap_df(df, limit=30, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 新闻/舆情数据
# ============================================================

def _fmt_news_dt(date_str: str) -> str:
    """将 YYYYMMDD 或 YYYY-MM-DD 转换为 news 接口要求的 'YYYY-MM-DD HH:MM:SS' 格式"""
    if not date_str:
        return None
    s = str(date_str).strip()
    # 已经是完整 datetime 格式，直接返回
    if len(s) >= 19 and '-' in s:
        return s[:19]
    # YYYYMMDD → YYYY-MM-DD 00:00:00
    digits = ''.join(c for c in s if c.isdigit())[:8]
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]} 00:00:00"
    return s


@tool(description="""获取财经新闻快讯（主流新闻网站，6年以上历史）。
start_date / end_date: 日期范围，输入 YYYYMMDD 即可，如 20240101
src: 新闻来源（可选，如 sina/wallstreetcn/eastmoney/yuncaijing/cls）""")
def tool_get_news(start_date: str = None, end_date: str = None,
                  src: str = None) -> str:
    try:
        df = pro.news(start_date=_fmt_news_dt(start_date),
                      end_date=_fmt_news_dt(end_date), src=src)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


@tool(description="""获取上市公司公告（提供PDF下载URL）。
ts_code: 股票代码（可选）
start_date / end_date: 公告日期范围 YYYYMMDD
ann_type: 公告类型（可选）""")
def tool_get_anns(ts_code: str = None, start_date: str = None,
                  end_date: str = None, ann_type: str = None) -> str:
    try:
        if not ts_code:
            return json.dumps({"error": "请指定股票代码 ts_code"}, ensure_ascii=False)
        tc = _to_ts_code(ts_code)
        sd = _fmt(start_date) or (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        ed = _clamp_today(_fmt(end_date) or TODAY_YMD)
        rtype = ann_type or "903"
        try:
            adapter = get_ifind_adapter()
            if adapter.is_available():
                payload = adapter.get_report_query(tc, sd, ed, report_type=rtype)
                if payload.get("success"):
                    return wrap_ifind_payload(payload, limit=20)
        except IFindAPIError:
            pass
        df = pro.anns(ts_code=tc, start_date=sd, end_date=ed, ann_type=ann_type)
        return _wrap_df(df, limit=20)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# iFinD 智能选股
# ============================================================

@tool(description="""iFinD 智能选股：按自然语言条件筛选 A 股列表。

【必填参数】
- searchstring (str): 选股条件，自然语言，如 "涨停"、"跌停"、"龙虎榜"、"高ROE"、"低市盈率"、"破净"

【可选参数】
- searchtype (str): 默认 "stock"（A股）

【常用 searchstring 示例】
- 涨停 / 跌停 / 龙虎榜 — 打板、异动
- 高ROE / 低市盈率 / 破净 — 价值选股
- 用户原话可直接作为 searchstring（如「ROE大于15%的白酒股」）

返回字段含 ts_code、name 及条件相关指标列；数据来自 iFinD smart_stock_picking。""")
def tool_smart_stock_picking(searchstring: str, searchtype: str = "stock") -> str:
    try:
        if not searchstring or not str(searchstring).strip():
            return json.dumps({"error": "请提供 searchstring 选股条件"}, ensure_ascii=False)
        payload = try_ifind_smart_picking(str(searchstring).strip(), searchtype or "stock")
        if payload and payload.get("success"):
            payload["searchstring"] = searchstring
            return wrap_ifind_payload(payload, limit=50)
        return json.dumps({"error": "未查询到数据", "searchstring": searchstring}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# 现货数据
# ============================================================

@tool(description="""获取上海黄金交易所现货日行情。
ts_code: 合约代码，如 AU99.99（黄金9999）
start_date / end_date: 日期范围 YYYYMMDD
字段单位说明：
  open/high/low/close: 元/克（人民币）
  vol: 千克（成交量）
  amount: 万元（成交额）""")
def tool_get_sge_daily(ts_code: str = None, start_date: str = None,
                       end_date: str = None) -> str:
    try:
        df = pro.sge_daily(ts_code=ts_code, start_date=_fmt(start_date),
                           end_date=_fmt(end_date))
        return _wrap_df(df, limit=60, sort_col='trade_date')
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)


# ============================================================
# 汇总：返回所有扩展工具列表
# ============================================================

def get_extra_tools():
    """返回所有扩展工具列表"""
    return [
        # 股票基础
        tool_get_trade_cal,
        tool_get_namechange,
        tool_get_new_share,
        tool_get_hs_const,
        tool_get_stk_rewards,
        # 行情
        tool_get_adj_factor,
        tool_get_weekly_monthly,
        tool_get_suspend_d,
        tool_get_hsgt_top10,
        # 财务
        tool_get_express,
        tool_get_fina_mainbz,
        tool_get_fina_audit,
        # 参考数据
        tool_get_share_float,
        tool_get_repurchase,
        tool_get_holder_trade,
        tool_get_stk_holdernumber,
        tool_get_pledge_stat,
        tool_get_block_trade,
        # 资金流向
        tool_get_moneyflow_hsgt,
        tool_get_moneyflow_ths,
        tool_get_moneyflow_ind_ths,
        tool_get_moneyflow_mkt_dc,
        # 打板专题
        tool_get_limit_list_d,
        tool_get_limit_cpt_list,
        tool_get_limit_step_list,
        tool_get_top_inst,
        tool_get_hm_detail,
        tool_get_ths_index,
        tool_smart_stock_picking,
        # 特色数据
        tool_get_hk_hold,
        tool_get_stk_surv,
        tool_get_report_rc,
        tool_get_cyq_perf,
        tool_get_stk_nineturn,
        tool_get_ah_compare,
        # 指数
        tool_get_sw_industry,
        tool_get_index_member,
        tool_get_index_weight,
        tool_get_sw_daily,
        tool_get_index_global,
        # ETF/基金
        tool_get_fund_basic,
        tool_get_fund_daily,
        tool_get_fund_share,
        tool_get_fund_nav,
        tool_get_fund_portfolio,
        # 债券
        tool_get_cb_basic,
        tool_get_cb_daily,
        tool_get_yc_cb,
        tool_get_eco_cal,
        # 期货
        tool_get_fut_basic,
        tool_get_fut_daily,
        tool_get_fut_holding,
        tool_get_fut_mapping,
        # 期权
        tool_get_opt_basic,
        tool_get_opt_daily,
        # 港股
        tool_get_hk_basic,
        tool_get_hk_daily,
        tool_get_hk_fina,
        # 美股
        tool_get_us_basic,
        tool_get_us_daily,
        tool_get_us_fina,
        # 宏观扩展
        tool_get_cn_pmi,
        tool_get_lpr,
        tool_get_sf_month,
        tool_get_us_tycr,
        # 融资融券
        tool_get_margin,
        tool_get_margin_detail,
        # 新闻/公告
        tool_get_news,
        tool_get_anns,
        # 现货
        tool_get_sge_daily,
    ]
