"""
Tushare Pro API 完整工具集
覆盖股票、指数、财务、市场、宏观等全量数据接口
"""
import tushare as ts
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta
import logging
import asyncio
from functools import wraps

from tools.tool_registry import get_global_registry

logger = logging.getLogger(__name__)

# ============================================================================
# Rate limit: 每次 Tushare API 调用前等待 3 秒，避免触发频率限制
# ============================================================================
TUSHARE_DELAY = 3.0  # 秒

def tushare_ratelimit(func):
    """装饰器：在每次 tushare API 调用前 sleep 3s，避免触发频率限制"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        await asyncio.sleep(TUSHARE_DELAY)
        return await func(*args, **kwargs)
    return wrapper

# ============================================================================
# Tushare Pro 初始化
# ============================================================================
token = '111f0e5add7466177e25b12754442fa1a15e2864e1127480dc19d484d4bc'
pro = ts.pro_api()
pro._DataApi__token = token
pro._DataApi__http_url = 'http://106.54.191.157:5000'

logger.info("Tushare Pro API initialized")


def _fmt(date_str: Optional[str]) -> Optional[str]:
    """格式化日期为 YYYYMMDD"""
    if not date_str:
        return None
    return ''.join(c for c in str(date_str) if c.isdigit())[:8] or None


def _code(stock_code: str) -> str:
    """股票代码转 Tushare 格式"""
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


def _wrap(df: pd.DataFrame, ts_code: str = None) -> dict:
    """统一返回格式"""
    if df is None or df.empty:
        return {'error': '未查询到数据'}
    result = {'success': True, 'data': df.to_dict('records'), 'count': len(df), 'data_source': 'tushare'}
    if ts_code:
        result['ts_code'] = ts_code
    return result


# ============================================================================
# 基础数据
# ============================================================================

async def get_stock_basic(exchange: str = None, list_status: str = "L") -> dict:
    """获取股票基础信息列表（代码、名称、上市日期、行业等）"""
    try:
        df = pro.stock_basic(exchange=exchange, list_status=list_status,
                             fields='ts_code,symbol,name,area,industry,market,list_date,delist_date')
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_trade_cal(exchange: str = "SSE", start_date: str = None, end_date: str = None, is_open: str = None) -> dict:
    """获取交易日历"""
    try:
        df = pro.trade_cal(exchange=exchange, start_date=_fmt(start_date), end_date=_fmt(end_date), is_open=is_open)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_stock_company(ts_code: str = None, exchange: str = None) -> dict:
    """获取上市公司基本信息（注册资本、法人、董秘等）"""
    try:
        df = pro.stock_company(ts_code=_code(ts_code) if ts_code else None, exchange=exchange)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_ipo_new(start_date: str = None, end_date: str = None) -> dict:
    """获取 IPO 新股上市列表"""
    try:
        df = pro.new_share(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 行情数据
# ============================================================================

async def get_daily(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取股票日线行情（开高低收量额）"""
    try:
        tc = _code(ts_code) if ts_code else None
        df = pro.daily(ts_code=tc, trade_date=_fmt(trade_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_weekly(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取股票周线行情"""
    try:
        tc = _code(ts_code) if ts_code else None
        df = pro.weekly(ts_code=tc, trade_date=_fmt(trade_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_monthly(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取股票月线行情"""
    try:
        tc = _code(ts_code) if ts_code else None
        df = pro.monthly(ts_code=tc, trade_date=_fmt(trade_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_daily_basic(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取每日指标（换手率、量比、PE、PB、总市值、流通市值等）"""
    try:
        tc = _code(ts_code) if ts_code else None
        df = pro.daily_basic(ts_code=tc, trade_date=_fmt(trade_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_adj_factor(ts_code: str, start_date: str = None, end_date: str = None) -> dict:
    """获取复权因子"""
    try:
        tc = _code(ts_code)
        df = pro.adj_factor(ts_code=tc, start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_suspend_d(ts_code: str = None, suspend_date: str = None, resume_date: str = None) -> dict:
    """获取停复牌信息"""
    try:
        df = pro.suspend_d(ts_code=_code(ts_code) if ts_code else None,
                           suspend_date=_fmt(suspend_date), resume_date=_fmt(resume_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_limit_list(trade_date: str, limit_type: str = "U") -> dict:
    """获取涨跌停列表（limit_type: U涨停 D跌停）"""
    try:
        df = pro.limit_list_d(trade_date=_fmt(trade_date), limit_type=limit_type)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_moneyflow(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取个股资金流向（大单/中单/小单买卖）"""
    try:
        tc = _code(ts_code) if ts_code else None
        df = pro.moneyflow(ts_code=tc, trade_date=_fmt(trade_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df, tc)
    except Exception as e:
        return {'error': str(e)}


async def get_hsgt_top10(trade_date: str = None, ts_code: str = None, market_type: str = "1") -> dict:
    """获取沪深股通十大成交股（market_type: 1沪股通 3深股通）"""
    try:
        df = pro.hsgt_top10(trade_date=_fmt(trade_date), ts_code=_code(ts_code) if ts_code else None, market_type=market_type)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_margin_detail(trade_date: str, ts_code: str = None) -> dict:
    """获取融资融券交易明细（融资余额、融券余额等）"""
    try:
        df = pro.margin_detail(trade_date=_fmt(trade_date), ts_code=_code(ts_code) if ts_code else None)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 财务数据
# ============================================================================

async def get_income(ts_code: str, start_date: str = None, end_date: str = None, period: str = None) -> dict:
    """获取利润表（营业收入、净利润等）"""
    try:
        df = pro.income(ts_code=_code(ts_code), start_date=_fmt(start_date), end_date=_fmt(end_date), period=_fmt(period))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_balancesheet(ts_code: str, start_date: str = None, end_date: str = None, period: str = None) -> dict:
    """获取资产负债表（总资产、总负债、股东权益等）"""
    try:
        df = pro.balancesheet(ts_code=_code(ts_code), start_date=_fmt(start_date), end_date=_fmt(end_date), period=_fmt(period))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_cashflow(ts_code: str, start_date: str = None, end_date: str = None, period: str = None) -> dict:
    """获取现金流量表（经营/投资/筹资活动现金流）"""
    try:
        df = pro.cashflow(ts_code=_code(ts_code), start_date=_fmt(start_date), end_date=_fmt(end_date), period=_fmt(period))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_fina_indicator(ts_code: str, start_date: str = None, end_date: str = None, period: str = None) -> dict:
    """获取财务指标（ROE、ROA、毛利率、净利率等）"""
    try:
        df = pro.fina_indicator(ts_code=_code(ts_code), start_date=_fmt(start_date), end_date=_fmt(end_date), period=_fmt(period))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_forecast(ts_code: str = None, ann_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取业绩预告（预增/预减/扭亏等）"""
    try:
        df = pro.forecast(ts_code=_code(ts_code) if ts_code else None,
                          ann_date=_fmt(ann_date), start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_express(ts_code: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取业绩快报"""
    try:
        df = pro.express(ts_code=_code(ts_code) if ts_code else None,
                         start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_dividend(ts_code: str, ann_date: str = None) -> dict:
    """获取分红送股数据"""
    try:
        df = pro.dividend(ts_code=_code(ts_code), ann_date=_fmt(ann_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 股东 & 持仓数据
# ============================================================================

async def get_top10_holders(ts_code: str, period: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取前十大股东（持股数量、比例）"""
    try:
        df = pro.top10_holders(ts_code=_code(ts_code), period=_fmt(period),
                               start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_top10_floatholders(ts_code: str, period: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取前十大流通股东"""
    try:
        df = pro.top10_floatholders(ts_code=_code(ts_code), period=_fmt(period),
                                    start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_pledge_stat(ts_code: str = None) -> dict:
    """获取股权质押统计数据"""
    try:
        df = pro.pledge_stat(ts_code=_code(ts_code) if ts_code else None)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_repurchase(ts_code: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取股票回购数据"""
    try:
        df = pro.repurchase(ts_code=_code(ts_code) if ts_code else None,
                            start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 龙虎榜
# ============================================================================

async def get_top_list(trade_date: str = None, ts_code: str = None) -> dict:
    """获取龙虎榜每日明细（上榜原因、买卖金额）"""
    try:
        df = pro.top_list(trade_date=_fmt(trade_date), ts_code=_code(ts_code) if ts_code else None)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_top_inst(trade_date: str = None, ts_code: str = None) -> dict:
    """获取龙虎榜机构交易明细"""
    try:
        df = pro.top_inst(trade_date=_fmt(trade_date), ts_code=_code(ts_code) if ts_code else None)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 指数数据
# ============================================================================

async def get_index_basic(market: str = None, publisher: str = None) -> dict:
    """获取指数基本信息"""
    try:
        df = pro.index_basic(market=market, publisher=publisher)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_index_daily(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取指数日线行情"""
    try:
        df = pro.index_daily(ts_code=ts_code, trade_date=_fmt(trade_date),
                             start_date=_fmt(start_date), end_date=_fmt(end_date))
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_index_weight(index_code: str, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取指数成份股及权重"""
    try:
        df = pro.index_weight(index_code=index_code, trade_date=_fmt(trade_date),
                              start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_index_dailybasic(ts_code: str = None, trade_date: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取大盘指数每日指标（PE/PB/股息率等）"""
    try:
        df = pro.index_dailybasic(ts_code=ts_code, trade_date=_fmt(trade_date),
                                  start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 概念板块
# ============================================================================

async def get_concept(src: str = "ts") -> dict:
    """获取概念板块分类列表"""
    try:
        df = pro.concept(src=src)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_concept_detail(id: str = None, ts_code: str = None) -> dict:
    """获取概念板块成份股"""
    try:
        df = pro.concept_detail(id=id, ts_code=_code(ts_code) if ts_code else None)
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 宏观经济
# ============================================================================

async def get_shibor(start_date: str = None, end_date: str = None) -> dict:
    """获取 Shibor 利率数据"""
    try:
        df = pro.shibor(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_cn_gdp(start_date: str = None, end_date: str = None) -> dict:
    """获取国内生产总值（GDP）数据"""
    try:
        df = pro.cn_gdp(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_cn_cpi(start_date: str = None, end_date: str = None) -> dict:
    """获取 CPI 居民消费价格指数"""
    try:
        df = pro.cn_cpi(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_cn_ppi(start_date: str = None, end_date: str = None) -> dict:
    """获取 PPI 工业生产者出厂价格指数"""
    try:
        df = pro.cn_ppi(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


async def get_cn_m(start_date: str = None, end_date: str = None) -> dict:
    """获取货币供应量（M0/M1/M2）月度数据"""
    try:
        df = pro.cn_m(start_date=_fmt(start_date), end_date=_fmt(end_date))
        return _wrap(df)
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 工具注册
# ============================================================================

def register_all_tushare_tools():
    """注册所有 Tushare 工具到全局注册中心"""
    registry = get_global_registry()
    tools = [
        # 基础数据
        ("get_stock_basic", get_stock_basic, "获取股票基础信息列表", ["basic", "stock_list"]),
        ("get_trade_cal", get_trade_cal, "获取交易日历", ["basic", "calendar"]),
        ("get_stock_company", get_stock_company, "获取上市公司基本信息", ["basic", "company"]),
        ("get_ipo_new", get_ipo_new, "获取 IPO 新股上市列表", ["basic", "ipo"]),
        # 行情数据
        ("get_daily", get_daily, "获取股票日线行情", ["market", "daily", "price"]),
        ("get_weekly", get_weekly, "获取股票周线行情", ["market", "weekly", "price"]),
        ("get_monthly", get_monthly, "获取股票月线行情", ["market", "monthly", "price"]),
        ("get_daily_basic", get_daily_basic, "获取每日指标（PE/PB/换手率/市值）", ["market", "indicator"]),
        ("get_adj_factor", get_adj_factor, "获取复权因子", ["market", "adjust"]),
        ("get_suspend_d", get_suspend_d, "获取停复牌信息", ["market", "suspend"]),
        ("get_limit_list", get_limit_list, "获取涨跌停列表", ["market", "limit"]),
        ("get_moneyflow", get_moneyflow, "获取个股资金流向", ["market", "moneyflow"]),
        ("get_hsgt_top10", get_hsgt_top10, "获取沪深股通十大成交股", ["market", "hsgt"]),
        ("get_margin_detail", get_margin_detail, "获取融资融券交易明细", ["market", "margin"]),
        # 财务数据
        ("get_income", get_income, "获取利润表", ["financial", "income"]),
        ("get_balancesheet", get_balancesheet, "获取资产负债表", ["financial", "balance"]),
        ("get_cashflow", get_cashflow, "获取现金流量表", ["financial", "cashflow"]),
        ("get_fina_indicator", get_fina_indicator, "获取财务指标（ROE/ROA/毛利率）", ["financial", "indicator"]),
        ("get_forecast", get_forecast, "获取业绩预告", ["financial", "forecast"]),
        ("get_express", get_express, "获取业绩快报", ["financial", "express"]),
        ("get_dividend", get_dividend, "获取分红送股数据", ["financial", "dividend"]),
        # 股东持仓
        ("get_top10_holders", get_top10_holders, "获取前十大股东", ["market", "holders"]),
        ("get_top10_floatholders", get_top10_floatholders, "获取前十大流通股东", ["market", "holders"]),
        ("get_pledge_stat", get_pledge_stat, "获取股权质押统计", ["market", "pledge"]),
        ("get_repurchase", get_repurchase, "获取股票回购数据", ["market", "repurchase"]),
        # 龙虎榜
        ("get_top_list", get_top_list, "获取龙虎榜每日明细", ["market", "top_list"]),
        ("get_top_inst", get_top_inst, "获取龙虎榜机构交易明细", ["market", "top_list"]),
        # 指数
        ("get_index_basic", get_index_basic, "获取指数基本信息", ["index", "basic"]),
        ("get_index_daily", get_index_daily, "获取指数日线行情", ["index", "daily"]),
        ("get_index_weight", get_index_weight, "获取指数成份股及权重", ["index", "weight"]),
        ("get_index_dailybasic", get_index_dailybasic, "获取大盘指数每日指标", ["index", "indicator"]),
        # 概念板块
        ("get_concept", get_concept, "获取概念板块分类", ["concept", "sector"]),
        ("get_concept_detail", get_concept_detail, "获取概念板块成份股", ["concept", "sector"]),
        # 宏观经济
        ("get_shibor", get_shibor, "获取 Shibor 利率", ["macro", "rate"]),
        ("get_cn_gdp", get_cn_gdp, "获取 GDP 数据", ["macro", "gdp"]),
        ("get_cn_cpi", get_cn_cpi, "获取 CPI 数据", ["macro", "cpi"]),
        ("get_cn_ppi", get_cn_ppi, "获取 PPI 数据", ["macro", "ppi"]),
        ("get_cn_m", get_cn_m, "获取货币供应量数据", ["macro", "money"]),
    ]
    for name, func, desc, tags in tools:
        registry.register(name=name, func=tushare_ratelimit(func), description=desc, category="tushare", data_source="tushare", tags=tags)
    logger.info(f"Registered {len(tools)} tushare tools")


try:
    register_all_tushare_tools()
except Exception as e:
    logger.warning(f"Failed to register tushare tools: {e}")
