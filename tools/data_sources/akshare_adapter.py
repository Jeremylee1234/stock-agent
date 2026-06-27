"""Akshare数据源适配器

提供Akshare数据接口的统一封装，包括股票基本信息、日线数据、财务数据、
资金流向、筹码分布等。
"""

from typing import Dict, Any, Optional
import pandas as pd
from datetime import datetime, timedelta

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

from .base_adapter import DataSourceAdapter
from utils.logger import get_logger

logger = get_logger(__name__)


class AkshareAdapter(DataSourceAdapter):
    """Akshare数据源适配器
    
    提供Akshare API的统一接口，包括：
    - 股票基本信息查询
    - 日线行情数据
    - 财务数据
    - 资金流向
    - 筹码分布
    - 新闻研报
    """
    
    def __init__(self):
        """初始化Akshare适配器
        
        Raises:
            ImportError: 如果akshare包未安装
        """
        super().__init__(name="akshare")
        
        if not AKSHARE_AVAILABLE:
            raise ImportError(
                "akshare包未安装，请运行: pip install akshare"
            )
        
        self.logger.info("Akshare适配器初始化成功")
    
    def format_stock_code(self, stock_code: str) -> str:
        """格式化股票代码为Akshare格式
        
        Akshare格式: 纯数字代码（如：600519）
        
        Args:
            stock_code: 原始股票代码
            
        Returns:
            Akshare格式的股票代码
        """
        stock_code = stock_code.strip().upper()
        
        # 移除交易所后缀
        if '.' in stock_code:
            stock_code = stock_code.split('.')[0]
        
        return stock_code
    
    def _get_exchange_prefix(self, stock_code: str) -> str:
        """获取交易所前缀（用于某些Akshare接口）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            交易所前缀（sh/sz/bj）
        """
        code = self.format_stock_code(stock_code)
        
        if code.startswith('6'):
            return 'sh'
        elif code.startswith(('0', '3')):
            return 'sz'
        elif code.startswith(('4', '8')):
            return 'bj'
        else:
            return 'sh'  # 默认上海
    
    def get_stock_basic(self, stock_code: str) -> Dict[str, Any]:
        """获取股票基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票基本信息字典
        """
        try:
            # 验证股票代码
            if not self.validate_stock_code(stock_code):
                raise ValueError(f"无效的股票代码: {stock_code}")
            
            # 格式化股票代码
            code = self.format_stock_code(stock_code)
            
            # 获取A股实时行情数据（包含基本信息）
            df = ak.stock_zh_a_spot_em()
            
            # 查找对应股票
            stock_data = df[df['代码'] == code]
            
            if stock_data.empty:
                raise ValueError(f"未找到股票信息: {stock_code}")
            
            # 转换为字典
            row = stock_data.iloc[0]
            result = {
                "stock_code": code,
                "stock_name": row['名称'],
                "latest_price": float(row['最新价']) if pd.notna(row['最新价']) else None,
                "change_percent": float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else None,
                "change_amount": float(row['涨跌额']) if pd.notna(row['涨跌额']) else None,
                "volume": float(row['成交量']) if pd.notna(row['成交量']) else None,
                "amount": float(row['成交额']) if pd.notna(row['成交额']) else None,
                "turnover_rate": float(row['换手率']) if pd.notna(row['换手率']) else None,
                "pe_ratio": float(row['市盈率-动态']) if pd.notna(row['市盈率-动态']) else None,
                "pb_ratio": float(row['市净率']) if pd.notna(row['市净率']) else None,
                "market_cap": float(row['总市值']) if pd.notna(row['总市值']) else None,
                "data_source": self.name,
                "timestamp": datetime.now().isoformat()
            }
            
            self.logger.info(f"成功获取股票基本信息: {stock_code}")
            return result
            
        except Exception as e:
            return self.handle_error(e, f"get_stock_basic({stock_code})")
    
    def get_daily_data(
        self,
        stock_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """获取日线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期（格式：YYYYMMDD）
            end_date: 结束日期（格式：YYYYMMDD）
            
        Returns:
            日线数据DataFrame
        """
        try:
            # 验证参数
            if not self.validate_stock_code(stock_code):
                raise ValueError(f"无效的股票代码: {stock_code}")
            
            if not self.validate_date_format(start_date):
                raise ValueError(f"无效的开始日期格式: {start_date}")
            
            if not self.validate_date_format(end_date):
                raise ValueError(f"无效的结束日期格式: {end_date}")
            
            # 格式化股票代码
            code = self.format_stock_code(stock_code)
            
            # 转换日期格式（Akshare使用YYYY-MM-DD格式）
            start_date_formatted = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            end_date_formatted = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
            
            # 调用Akshare API获取历史行情数据
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date_formatted,
                end_date=end_date_formatted,
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                self.logger.warning(
                    f"未获取到日线数据: {stock_code}, "
                    f"{start_date} - {end_date}"
                )
                return pd.DataFrame()
            
            # 重命名列以符合统一格式
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'change_percent',
                '涨跌额': 'change_amount',
                '换手率': 'turnover_rate'
            })
            
            # 转换日期格式为YYYYMMDD
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d')
            
            # 选择需要的列
            columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
            df = df[columns]
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            # 按日期排序
            df = df.sort_values('date').reset_index(drop=True)
            
            self.logger.info(
                f"成功获取日线数据: {stock_code}, "
                f"{start_date} - {end_date}, 共 {len(df)} 条"
            )
            
            return df
            
        except Exception as e:
            error_info = self.handle_error(
                e,
                f"get_daily_data({stock_code}, {start_date}, {end_date})"
            )
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
    
    def get_financial_data(self, stock_code: str) -> Dict[str, Any]:
        """获取财务数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            财务数据字典
        """
        try:
            # 验证股票代码
            if not self.validate_stock_code(stock_code):
                raise ValueError(f"无效的股票代码: {stock_code}")
            
            # 格式化股票代码
            code = self.format_stock_code(stock_code)
            
            # 获取财务摘要数据
            try:
                # 获取利润表数据
                income_df = ak.stock_financial_benefit_ths(
                    symbol=code,
                    indicator="按报告期"
                )
                
                # 获取资产负债表数据
                balance_df = ak.stock_financial_debt_ths(
                    symbol=code,
                    indicator="按年度"
                )
                
                result = {
                    "stock_code": code,
                    "data_source": self.name,
                    "timestamp": datetime.now().isoformat()
                }
                
                # 处理利润表数据
                if not income_df.empty:
                    latest_income = income_df.iloc[0]
                    result.update({
                        "report_date": str(latest_income.get('报告期', '')),
                        "revenue": float(latest_income.get('营业总收入', 0)) if pd.notna(latest_income.get('营业总收入')) else None,
                        "net_profit": float(latest_income.get('净利润', 0)) if pd.notna(latest_income.get('净利润')) else None,
                        "operate_profit": float(latest_income.get('营业利润', 0)) if pd.notna(latest_income.get('营业利润')) else None,
                    })
                
                # 处理资产负债表数据
                if not balance_df.empty:
                    latest_balance = balance_df.iloc[0]
                    result.update({
                        "total_assets": float(latest_balance.get('总资产', 0)) if pd.notna(latest_balance.get('总资产')) else None,
                        "total_liabilities": float(latest_balance.get('总负债', 0)) if pd.notna(latest_balance.get('总负债')) else None,
                        "total_equity": float(latest_balance.get('股东权益合计', 0)) if pd.notna(latest_balance.get('股东权益合计')) else None,
                    })
                
                if not income_df.empty or not balance_df.empty:
                    self.logger.info(f"成功获取财务数据: {stock_code}")
                    return result
                else:
                    raise ValueError(f"未找到财务数据: {stock_code}")
                    
            except Exception as inner_e:
                self.logger.warning(f"获取详细财务数据失败，尝试获取摘要数据: {inner_e}")
                
                # 尝试获取财务摘要
                abstract_df = ak.stock_financial_abstract_ths(
                    symbol=code,
                    indicator="按报告期"
                )
                
                if abstract_df.empty:
                    raise ValueError(f"未找到财务数据: {stock_code}")
                
                latest = abstract_df.iloc[0]
                result = {
                    "stock_code": code,
                    "report_date": str(latest.get('报告期', '')),
                    "revenue": float(latest.get('营业总收入', 0)) if pd.notna(latest.get('营业总收入')) else None,
                    "net_profit": float(latest.get('净利润', 0)) if pd.notna(latest.get('净利润')) else None,
                    "data_source": self.name,
                    "timestamp": datetime.now().isoformat()
                }
                
                self.logger.info(f"成功获取财务摘要数据: {stock_code}")
                return result
            
        except Exception as e:
            return self.handle_error(e, f"get_financial_data({stock_code})")
    
    def get_fund_flow(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        """获取个股资金流向数据
        
        Args:
            stock_code: 股票代码
            days: 获取最近N天的数据
            
        Returns:
            资金流向DataFrame
        """
        try:
            code = self.format_stock_code(stock_code)
            exchange = self._get_exchange_prefix(stock_code)
            
            # 获取个股资金流向
            df = ak.stock_individual_fund_flow(
                stock=code,
                market=exchange
            )
            
            if df.empty:
                self.logger.warning(f"未获取到资金流向数据: {stock_code}")
                return pd.DataFrame()
            
            # 获取最近N天的数据
            df = df.tail(days)
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            self.logger.info(f"成功获取资金流向数据: {stock_code}, 共 {len(df)} 条")
            return df
            
        except Exception as e:
            error_info = self.handle_error(e, f"get_fund_flow({stock_code})")
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
    
    def get_chip_distribution(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        """获取筹码分布数据
        
        Args:
            stock_code: 股票代码
            days: 获取最近N天的数据
            
        Returns:
            筹码分布DataFrame
        """
        try:
            code = self.format_stock_code(stock_code)
            
            # 获取筹码分布
            df = ak.stock_cyq_em(symbol=code, adjust="")
            
            if df.empty:
                self.logger.warning(f"未获取到筹码分布数据: {stock_code}")
                return pd.DataFrame()
            
            # 获取最近N天的数据
            df = df.tail(days)
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            self.logger.info(f"成功获取筹码分布数据: {stock_code}, 共 {len(df)} 条")
            return df
            
        except Exception as e:
            error_info = self.handle_error(e, f"get_chip_distribution({stock_code})")
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
    
    def get_top_10_holders(self, stock_code: str, date: Optional[str] = None) -> pd.DataFrame:
        """获取十大流通股东
        
        Args:
            stock_code: 股票代码
            date: 报告期日期（格式：YYYYMMDD），默认最新
            
        Returns:
            十大流通股东DataFrame
        """
        try:
            code = self.format_stock_code(stock_code)
            exchange = self._get_exchange_prefix(stock_code)
            
            # 如果没有指定日期，使用最近的季度末
            if not date:
                today = datetime.now()
                # 获取最近的季度末（3/31, 6/30, 9/30, 12/31）
                quarter_ends = [
                    f"{today.year}0331",
                    f"{today.year}0630",
                    f"{today.year}0930",
                    f"{today.year}1231"
                ]
                # 找到最近的过去的季度末
                for qe in reversed(quarter_ends):
                    if qe <= today.strftime('%Y%m%d'):
                        date = qe
                        break
                if not date:
                    # 如果今年没有，使用去年最后一个季度
                    date = f"{today.year - 1}1231"
            
            # 获取十大流通股东
            df = ak.stock_gdfx_free_top_10_em(
                symbol=f"{exchange}{code}",
                date=date
            )
            
            if df.empty:
                self.logger.warning(f"未获取到十大流通股东数据: {stock_code}, 日期: {date}")
                return pd.DataFrame()
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            self.logger.info(f"成功获取十大流通股东数据: {stock_code}")
            return df
            
        except Exception as e:
            error_info = self.handle_error(e, f"get_top_10_holders({stock_code}, {date})")
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
    
    def get_news(self, stock_code: str, limit: int = 10) -> pd.DataFrame:
        """获取个股新闻
        
        Args:
            stock_code: 股票代码
            limit: 获取新闻数量
            
        Returns:
            新闻DataFrame
        """
        try:
            code = self.format_stock_code(stock_code)
            
            # 获取个股新闻
            df = ak.stock_news_em(symbol=code)
            
            if df.empty:
                self.logger.warning(f"未获取到新闻数据: {stock_code}")
                return pd.DataFrame()
            
            # 限制数量
            df = df.head(limit)
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            self.logger.info(f"成功获取新闻数据: {stock_code}, 共 {len(df)} 条")
            return df
            
        except Exception as e:
            error_info = self.handle_error(e, f"get_news({stock_code})")
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
    
    def get_research_reports(self, stock_code: str, limit: int = 5) -> pd.DataFrame:
        """获取研报数据
        
        Args:
            stock_code: 股票代码
            limit: 获取研报数量
            
        Returns:
            研报DataFrame
        """
        try:
            code = self.format_stock_code(stock_code)
            
            # 获取研报
            df = ak.stock_research_report_em(symbol=code)
            
            if df.empty:
                self.logger.warning(f"未获取到研报数据: {stock_code}")
                return pd.DataFrame()
            
            # 限制数量
            df = df.head(limit)
            
            # 添加数据源标识
            df['data_source'] = self.name
            
            self.logger.info(f"成功获取研报数据: {stock_code}, 共 {len(df)} 条")
            return df
            
        except Exception as e:
            error_info = self.handle_error(e, f"get_research_reports({stock_code})")
            df = pd.DataFrame()
            df.attrs['error'] = error_info
            return df
