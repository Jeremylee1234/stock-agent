#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare数据源适配器

基于tushare skill的完整实现，提供股票、基金、期货、债券等金融数据接口
"""

import os
import time
import logging
import pandas as pd
import tushare as ts
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DataSourceAdapter(ABC):
    """数据源适配器基类"""
    
    @abstractmethod
    def get_stock_basic(self, stock_code: str) -> dict:
        """获取股票基本信息"""
        pass
    
    @abstractmethod
    def get_daily_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取日线数据"""
        pass
    
    @abstractmethod
    def get_financial_data(self, stock_code: str) -> dict:
        """获取财务数据"""
        pass
    
    def handle_error(self, error: Exception) -> dict:
        """统一错误处理"""
        return {
            "error": True,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "data_source": self.__class__.__name__
        }


class TushareAdapter(DataSourceAdapter):
    """Tushare数据源适配器
    
    基于tushare skill实现，提供全面的金融数据接口
    """
    
    def __init__(self, token: str = None, timeout: int = 30, retry_count: int = 3):
        """初始化Tushare适配器
        
        Args:
            token: Tushare Pro token
            timeout: 请求超时时间（秒）
            retry_count: 重试次数
        """
        self.token = token or os.getenv('DATA_SOURCE__TUSHARE_TOKEN') or ts.get_token()
        self.timeout = timeout
        self.retry_count = retry_count
        
        if not self.token:
            raise ValueError("Tushare token is required. Please set DATA_SOURCE__TUSHARE_TOKEN environment variable or register at https://tushare.pro/register")
        
        # 初始化pro接口
        self.pro = ts.pro_api(self.token)
        logger.info("TushareAdapter initialized successfully")
    
    def _retry_request(self, func, *args, **kwargs):
        """带重试的请求执行"""
        last_error = None
        
        for attempt in range(self.retry_count):
            try:
                result = func(*args, **kwargs)
                if result is not None and not result.empty:
                    return result
                else:
                    logger.warning(f"Empty result on attempt {attempt + 1}")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed on attempt {attempt + 1}: {e}")
                
                if attempt < self.retry_count - 1:
                    # 指数退避
                    wait_time = (2 ** attempt) * 1
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        # 所有重试都失败了
        if last_error:
            raise last_error
        else:
            raise Exception("All retry attempts returned empty results")
    
    def get_stock_basic(self, stock_code: str = None) -> dict:
        """获取股票基本信息
        
        Args:
            stock_code: 股票代码（可选，如果不提供则返回所有股票列表）
            
        Returns:
            dict: 包含股票基本信息的字典
        """
        try:
            if stock_code:
                # 获取单只股票信息
                df = self._retry_request(
                    self.pro.stock_basic,
                    ts_code=stock_code,
                    fields='ts_code,symbol,name,area,industry,market,list_date,delist_date'
                )
                
                if df.empty:
                    return {
                        "error": True,
                        "error_message": f"Stock {stock_code} not found",
                        "data_source": "TushareAdapter"
                    }
                
                stock_info = df.iloc[0].to_dict()
                return {
                    "ts_code": stock_info.get("ts_code"),
                    "symbol": stock_info.get("symbol"),
                    "name": stock_info.get("name"),
                    "area": stock_info.get("area"),
                    "industry": stock_info.get("industry"),
                    "market": stock_info.get("market"),
                    "list_date": stock_info.get("list_date"),
                    "delist_date": stock_info.get("delist_date"),
                    "data_source": "tushare"
                }
            else:
                # 获取所有上市股票列表
                df = self._retry_request(
                    self.pro.stock_basic,
                    exchange='',
                    list_status='L',
                    fields='ts_code,symbol,name,area,industry,list_date'
                )
                
                return {
                    "total_count": len(df),
                    "stocks": df.to_dict('records'),
                    "data_source": "tushare"
                }
                
        except Exception as e:
            logger.error(f"Failed to get stock basic info: {e}")
            return self.handle_error(e)
    
    def get_daily_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取股票日线数据
        
        Args:
            stock_code: 股票代码（ts_code格式，如 000001.SZ）
            start_date: 开始日期（YYYYMMDD格式）
            end_date: 结束日期（YYYYMMDD格式）
            
        Returns:
            pd.DataFrame: 日线数据
        """
        try:
            df = self._retry_request(
                self.pro.daily,
                ts_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                logger.warning(f"No daily data found for {stock_code} from {start_date} to {end_date}")
                return pd.DataFrame()
            
            # 按日期排序
            df = df.sort_values('trade_date')
            df['data_source'] = 'tushare'
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to get daily data for {stock_code}: {e}")
            raise e
    
    def get_financial_data(self, stock_code: str, year: int = None, quarter: int = None) -> dict:
        """获取财务数据
        
        Args:
            stock_code: 股票代码
            year: 年份（可选）
            quarter: 季度（可选）
            
        Returns:
            dict: 财务数据
        """
        try:
            # 获取财务指标数据
            fina_df = self._retry_request(
                self.pro.fina_indicator,
                ts_code=stock_code,
                year=year,
                quarter=quarter
            )
            
            # 获取利润表数据
            income_df = self._retry_request(
                self.pro.income,
                ts_code=stock_code,
                year=year,
                quarter=quarter
            )
            
            # 获取资产负债表数据
            balancesheet_df = self._retry_request(
                self.pro.balancesheet,
                ts_code=stock_code,
                year=year,
                quarter=quarter
            )
            
            # 获取现金流量表数据
            cashflow_df = self._retry_request(
                self.pro.cashflow,
                ts_code=stock_code,
                year=year,
                quarter=quarter
            )
            
            return {
                "financial_indicators": fina_df.to_dict('records') if not fina_df.empty else [],
                "income_statement": income_df.to_dict('records') if not income_df.empty else [],
                "balance_sheet": balancesheet_df.to_dict('records') if not balancesheet_df.empty else [],
                "cash_flow": cashflow_df.to_dict('records') if not cashflow_df.empty else [],
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get financial data for {stock_code}: {e}")
            return self.handle_error(e)
    
    def get_realtime_data(self, stock_codes: Union[str, List[str]]) -> dict:
        """获取实时行情数据
        
        Args:
            stock_codes: 股票代码或代码列表
            
        Returns:
            dict: 实时行情数据
        """
        try:
            if isinstance(stock_codes, str):
                stock_codes = [stock_codes]
            
            # 使用实时日线接口
            results = []
            for code in stock_codes:
                df = self._retry_request(
                    self.pro.stk_factor,
                    ts_code=code,
                    trade_date=datetime.now().strftime('%Y%m%d')
                )
                
                if not df.empty:
                    results.extend(df.to_dict('records'))
            
            return {
                "realtime_data": results,
                "data_source": "tushare",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get realtime data: {e}")
            return self.handle_error(e)
    
    def get_technical_indicators(self, stock_code: str, start_date: str, end_date: str) -> dict:
        """获取技术指标数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: 技术指标数据
        """
        try:
            # 获取股票技术面因子（专业版）
            df = self._retry_request(
                self.pro.stk_factor,
                ts_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": f"No technical indicators found for {stock_code}",
                    "data_source": "tushare"
                }
            
            return {
                "technical_indicators": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get technical indicators for {stock_code}: {e}")
            return self.handle_error(e)
    
    def get_fund_flow_data(self, stock_code: str, start_date: str, end_date: str) -> dict:
        """获取资金流向数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: 资金流向数据
        """
        try:
            # 获取个股资金流向数据
            df = self._retry_request(
                self.pro.moneyflow,
                ts_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": f"No fund flow data found for {stock_code}",
                    "data_source": "tushare"
                }
            
            return {
                "fund_flow": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get fund flow data for {stock_code}: {e}")
            return self.handle_error(e)
    
    def get_chip_distribution(self, stock_code: str, trade_date: str = None) -> dict:
        """获取筹码分布数据
        
        Args:
            stock_code: 股票代码
            trade_date: 交易日期（可选，默认最新）
            
        Returns:
            dict: 筹码分布数据
        """
        try:
            if not trade_date:
                trade_date = datetime.now().strftime('%Y%m%d')
            
            # 获取每日筹码分布数据
            df = self._retry_request(
                self.pro.cyq_perf,
                ts_code=stock_code,
                trade_date=trade_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": f"No chip distribution data found for {stock_code}",
                    "data_source": "tushare"
                }
            
            return {
                "chip_distribution": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get chip distribution for {stock_code}: {e}")
            return self.handle_error(e)
    
    def get_news_data(self, stock_code: str = None, start_date: str = None, end_date: str = None) -> dict:
        """获取新闻数据
        
        Args:
            stock_code: 股票代码（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            
        Returns:
            dict: 新闻数据
        """
        try:
            # 获取新闻快讯数据
            df = self._retry_request(
                self.pro.news,
                src='sina',
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": "No news data found",
                    "data_source": "tushare"
                }
            
            # 如果指定了股票代码，过滤相关新闻
            if stock_code:
                # 获取股票名称
                stock_info = self.get_stock_basic(stock_code)
                if not stock_info.get("error"):
                    stock_name = stock_info.get("name", "")
                    # 简单的关键词过滤
                    df = df[df['title'].str.contains(stock_name, na=False)]
            
            return {
                "news": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get news data: {e}")
            return self.handle_error(e)
    
    def get_research_reports(self, stock_code: str = None, start_date: str = None, end_date: str = None) -> dict:
        """获取券商研究报告
        
        Args:
            stock_code: 股票代码（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            
        Returns:
            dict: 研究报告数据
        """
        try:
            # 获取券商研究报告数据
            df = self._retry_request(
                self.pro.broker_recommend,
                ts_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": f"No research reports found for {stock_code}",
                    "data_source": "tushare"
                }
            
            return {
                "research_reports": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get research reports for {stock_code}: {e}")
            return self.handle_error(e)
    
    def get_index_data(self, index_code: str, start_date: str, end_date: str) -> dict:
        """获取指数数据
        
        Args:
            index_code: 指数代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: 指数数据
        """
        try:
            # 获取指数日线行情
            df = self._retry_request(
                self.pro.index_daily,
                ts_code=index_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": f"No index data found for {index_code}",
                    "data_source": "tushare"
                }
            
            return {
                "index_data": df.to_dict('records'),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to get index data for {index_code}: {e}")
            return self.handle_error(e)
    
    def search_stocks(self, keyword: str, limit: int = 20) -> dict:
        """搜索股票
        
        Args:
            keyword: 搜索关键词（股票名称或代码）
            limit: 返回结果数量限制
            
        Returns:
            dict: 搜索结果
        """
        try:
            # 获取所有股票列表
            df = self._retry_request(
                self.pro.stock_basic,
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,list_date'
            )
            
            if df.empty:
                return {
                    "error": True,
                    "error_message": "No stock data available",
                    "data_source": "tushare"
                }
            
            # 搜索匹配的股票
            mask = (
                df['name'].str.contains(keyword, case=False, na=False) |
                df['ts_code'].str.contains(keyword, case=False, na=False) |
                df['symbol'].str.contains(keyword, case=False, na=False)
            )
            
            results = df[mask].head(limit)
            
            return {
                "search_results": results.to_dict('records'),
                "total_found": len(results),
                "data_source": "tushare"
            }
            
        except Exception as e:
            logger.error(f"Failed to search stocks with keyword '{keyword}': {e}")
            return self.handle_error(e)


# 工厂函数
def create_tushare_adapter(token: str = None, **kwargs) -> TushareAdapter:
    """创建Tushare适配器实例
    
    Args:
        token: Tushare Pro token
        **kwargs: 其他配置参数
        
    Returns:
        TushareAdapter: Tushare适配器实例
    """
    return TushareAdapter(token=token, **kwargs)


if __name__ == "__main__":
    # 测试代码
    adapter = TushareAdapter()
    
    # 测试获取股票基本信息
    print("=== 测试获取股票基本信息 ===")
    result = adapter.get_stock_basic("000001.SZ")
    print(result)
    
    # 测试获取日线数据
    print("\n=== 测试获取日线数据 ===")
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    df = adapter.get_daily_data("000001.SZ", start_date, end_date)
    print(f"获取到 {len(df)} 条日线数据")
    if not df.empty:
        print(df.head())
    
    # 测试搜索股票
    print("\n=== 测试搜索股票 ===")
    search_result = adapter.search_stocks("平安", limit=5)
    print(search_result)