"""
股票分析工具集 - 基于 Tushare Pro API
替代原 iFinD 接口，提供完整的 A 股数据获取能力
"""
import tushare as ts
import pandas as pd
from mcp.server.fastmcp import FastMCP
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from tools.technical_indicators import TechnicalIndicators
from tools.tool_registry import get_global_registry

logger = logging.getLogger(__name__)

# 创建 MCP server
mcp = FastMCP("stock_mcp_server")

# ============================================================================
# Tushare Pro 初始化（使用指定 token 和私有服务器）
# ============================================================================
token = '111f0e5add7466177e25b12754442fa1a15e2864e1127480dc19d484d4bc'
pro = ts.pro_api()
pro._DataApi__token = token
pro._DataApi__http_url = 'http://106.54.191.157:5000'

logger.info("Tushare Pro API initialized with custom token and endpoint")


def to_ts_code(stock_code: str) -> str:
    """将股票代码转换为 Tushare 格式（带后缀）"""
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


def format_date(date_str: Optional[str]) -> Optional[str]:
    """格式化日期为 YYYYMMDD"""
    if not date_str:
        return None
    return ''.join(c for c in str(date_str) if c.isdigit())[:8] or None


# ============================================================================
# 行情数据工具
# ============================================================================

@mcp.tool(description='''获取股票历史日线行情数据及均线
使用 Tushare Pro 接口获取历史日级价格数据，并自动计算均线。

参数说明:
- stock_code: 股票代码，如 '600519' 或 '600519.SH'
- start_date: 开始日期，格式 YYYYMMDD
- end_date: 结束日期，格式 YYYYMMDD
''')
async def get_stock_history_price(
    stock_code: str,
    start_date: str,
    end_date: str,
) -> dict:
    """获取股票历史日线行情及均线"""
    try:
        ts_code = to_ts_code(stock_code)
        df = pro.daily(
            ts_code=ts_code,
            start_date=format_date(start_date),
            end_date=format_date(end_date)
        )
        if df is None or df.empty:
            return {'error': '未查询到数据', 'stock_code': stock_code}

        df = df.sort_values('trade_date').reset_index(drop=True)

        # 计算均线
        for period in [5, 10, 20, 30, 60]:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean().round(4)

        result = df.to_dict('records')
        return {
            'success': True,
            'stock_code': ts_code,
            'data': result,
            'count': len(result),
            'data_source': 'tushare'
        }
    except Exception as e:
        logger.error(f"get_stock_history_price error: {e}", exc_info=True)
        return {'error': str(e)}


@mcp.tool(description='''获取股票每日基本指标
包括换手率、量比、市盈率(PE)、市净率(PB)、总市值、流通市值等。

参数说明:
- stock_code: 股票代码，如 '600519'
- trade_date: 指定交易日 YYYYMMDD（与日期范围二选一）
- start_date: 开始日期 YYYYMMDD
- end_date: 结束日期 YYYYMMDD
''')
async def get_stock_daily_indicators(
    stock_code: str,
    trade_date: str = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """获取股票每日基本指标（PE/PB/换手率/市值等）"""
    try:
        ts_code = to_ts_code(stock_code)
        df = pro.daily_basic(
            ts_code=ts_code,
            trade_date=format_date(trade_date),
            start_date=format_date(start_date),
            end_date=format_date(end_date)
        )
        if df is None or df.empty:
            return {'error': '未查询到数据'}

        df = df.sort_values('trade_date').reset_index(drop=True)
        return {
            'success': True,
            'stock_code': ts_code,
            'data': df.to_dict('records'),
            'count': len(df),
            'data_source': 'tushare'
        }
    except Exception as e:
        logger.error(f"get_stock_daily_indicators error: {e}", exc_info=True)
        return {'error': str(e)}


@mcp.tool(description='''获取股票财务指标数据
包括 ROE、ROA、毛利率、净利率、EPS 等综合财务指标。

参数说明:
- stock_code: 股票代码，如 '600519'
- period: 报告期，如 '20231231'（年报）、'20230930'（三季报）
- start_date: 报告期开始日期 YYYYMMDD
- end_date: 报告期结束日期 YYYYMMDD
''')
async def get_stock_chip_indicators(
    stock_code: str,
    period: str = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """获取股票财务指标（ROE/ROA/毛利率等）"""
    try:
        ts_code = to_ts_code(stock_code)
        df = pro.fina_indicator(
            ts_code=ts_code,
            period=format_date(period),
            start_date=format_date(start_date),
            end_date=format_date(end_date)
        )
        if df is None or df.empty:
            return {'error': '未查询到数据'}

        return {
            'success': True,
            'stock_code': ts_code,
            'data': df.head(8).to_dict('records'),
            'count': len(df),
            'data_source': 'tushare'
        }
    except Exception as e:
        logger.error(f"get_stock_chip_indicators error: {e}", exc_info=True)
        return {'error': str(e)}


@mcp.tool(description='''获取股票新闻资讯及研报情绪数据
包括业绩预告、业绩快报、分红送股等公告信息。

参数说明:
- stock_code: 股票代码，如 '600519'
- start_date: 开始日期 YYYYMMDD
- end_date: 结束日期 YYYYMMDD
''')
async def get_stock_news_indicators(
    stock_code: str,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """获取股票公告、业绩预告、分红等情绪数据"""
    try:
        ts_code = to_ts_code(stock_code)
        result = {}

        # 业绩预告
        try:
            df_forecast = pro.forecast(ts_code=ts_code, start_date=format_date(start_date), end_date=format_date(end_date))
            result['forecast'] = df_forecast.head(5).to_dict('records') if df_forecast is not None and not df_forecast.empty else []
        except Exception:
            result['forecast'] = []

        # 业绩快报
        try:
            df_express = pro.express(ts_code=ts_code, start_date=format_date(start_date), end_date=format_date(end_date))
            result['express'] = df_express.head(5).to_dict('records') if df_express is not None and not df_express.empty else []
        except Exception:
            result['express'] = []

        # 分红送股
        try:
            df_div = pro.dividend(ts_code=ts_code)
            result['dividend'] = df_div.head(5).to_dict('records') if df_div is not None and not df_div.empty else []
        except Exception:
            result['dividend'] = []

        return {
            'success': True,
            'stock_code': ts_code,
            'data': result,
            'data_source': 'tushare'
        }
    except Exception as e:
        logger.error(f"get_stock_news_indicators error: {e}", exc_info=True)
        return {'error': str(e)}


@mcp.tool(description='''搜索历史相似走势
根据模式描述（如连续三次跌停、MACD金叉等）从历史 A 股中查找符合该模式的行情阶段，并统计后续走势。

参数说明:
- pattern_description: 模式描述，如"连续三次跌停"、"MACD金叉"
- stock_code: 可选，指定股票则只搜该股
- start_date: 搜索起始日期 YYYYMMDD
- end_date: 搜索结束日期 YYYYMMDD
- max_results: 最多返回匹配数，默认 20
- lookahead_days: 后续分析的天数，如 "5,10,20"
''')
async def search_similar_pattern(
    pattern_description: str,
    stock_code: str = None,
    start_date: str = None,
    end_date: str = None,
    max_results: int = 20,
    lookahead_days: str = "5,10,20",
) -> dict:
    """搜索历史相似走势"""
    import asyncio
    try:
        from tools.pattern_search import PatternSearchEngine

        lookahead_list = [int(d.strip()) for d in lookahead_days.split(",") if d.strip()]
        engine = PatternSearchEngine(enable_cache=True)
        pattern_lower = pattern_description.lower()

        indicator_keywords = {"macd": "MACD", "kdj": "KDJ", "rsi": "RSI", "均线": "MA", "ma": "MA"}
        indicator_type = next((v for k, v in indicator_keywords.items() if k in pattern_lower), None)

        loop = asyncio.get_event_loop()
        if indicator_type:
            result = await loop.run_in_executor(
                None,
                lambda: engine.search_indicator_pattern(
                    pattern_desc=pattern_description,
                    indicator_type=indicator_type,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results
                )
            )
        else:
            result = await loop.run_in_executor(
                None,
                lambda: engine.search_price_pattern(
                    pattern_desc=pattern_description,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results
                )
            )

        if result.get("success") and result.get("matches") and lookahead_list:
            perf_result = await loop.run_in_executor(
                None,
                lambda: engine.analyze_future_performance(
                    matches=result["matches"],
                    lookahead_days=lookahead_list
                )
            )
            if perf_result.get("success"):
                result["matches"] = perf_result.get("matches_with_performance", result["matches"])
                result["statistics"].update(perf_result.get("statistics", {}))

        return result
    except ImportError as e:
        return {"success": False, "error": f"模块导入失败: {e}", "matches": [], "statistics": {}}
    except Exception as e:
        return {"success": False, "error": str(e), "matches": [], "statistics": {}}


# ============================================================================
# 工具注册
# ============================================================================

def register_all_tools():
    """注册所有工具到全局注册中心"""
    registry = get_global_registry()
    tools_to_register = [
        ("get_stock_history_price", get_stock_history_price, "获取股票历史日线行情及均线", ["price", "history", "tushare"]),
        ("get_stock_daily_indicators", get_stock_daily_indicators, "获取股票每日基本指标（PE/PB/换手率/市值）", ["indicator", "fundamental", "tushare"]),
        ("get_stock_chip_indicators", get_stock_chip_indicators, "获取股票财务指标（ROE/ROA/毛利率）", ["financial", "tushare"]),
        ("get_stock_news_indicators", get_stock_news_indicators, "获取股票公告、业绩预告、分红等情绪数据", ["news", "announcement", "tushare"]),
        ("search_similar_pattern", search_similar_pattern, "搜索历史相似走势模式", ["pattern", "history", "tushare"]),
    ]
    for name, func, desc, tags in tools_to_register:
        registry.register(name=name, func=func, description=desc, category="data_source", data_source="tushare", tags=tags)
    logger.info(f"Registered {len(tools_to_register)} tools to global registry")


try:
    register_all_tools()
except Exception as e:
    logger.warning(f"Failed to register tools: {e}")


if __name__ == "__main__":
    mcp.run(transport='stdio')
