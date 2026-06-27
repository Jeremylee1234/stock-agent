"""
历史模式搜索引擎

提供基于Tushare的历史相似走势搜索功能，支持价格形态、技术指标和筹码分布模式匹配。
满足需求 11.1-11.10
"""
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np

from utils.logger import get_logger
from config.settings import get_settings

# 尝试导入tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None

# 导入技术指标计算模块
from tools.technical_indicators import TechnicalIndicators


class PatternSearchEngine:
    """历史模式搜索引擎
    
    基于Tushare Pro API实现历史相似走势搜索，支持：
    - 价格形态模式（连续涨停/跌停、V型反转、W底、头肩顶等）
    - 技术指标模式（MACD金叉/死叉/背离、KDJ超买/超卖、均线排列等）
    - 筹码分布模式（筹码集中度、主力资金流向等）
    - 组合模式搜索（多条件AND/OR组合）
    """
    
    def __init__(self, tushare_token: Optional[str] = None, enable_cache: bool = True):
        """初始化模式搜索引擎
        
        Args:
            tushare_token: Tushare Pro API Token，如果不提供则从配置读取
            enable_cache: 是否启用缓存
        """
        self.logger = get_logger("pattern_search")
        self.settings = get_settings()
        
        # 获取Tushare token
        self.tushare_token = tushare_token or self.settings.get_tushare_token()
        if not self.tushare_token:
            self.logger.warning("Tushare token未配置，模式搜索功能将不可用")
        
        # 检查tushare是否可用
        if not TUSHARE_AVAILABLE:
            self.logger.error("Tushare未安装，请运行: pip install tushare")
            self.pro = None
        else:
            try:
                self.pro = ts.pro_api(self.tushare_token)
                # 设置自定义服务器（如果需要）
                if hasattr(self.pro, '_DataApi__http_url'):
                    self.pro._DataApi__http_url = 'http://106.54.191.157:5000'
                self.logger.info("Tushare Pro API初始化成功")
            except Exception as e:
                self.logger.error(f"Tushare Pro API初始化失败: {e}")
                self.pro = None
        
        # 缓存配置
        self.enable_cache = enable_cache
        self.cache: Dict[str, Any] = {}
        self.cache_ttl = self.settings.cache.cache_ttl if hasattr(self.settings, 'cache') else 3600
        
        self.logger.info(f"PatternSearchEngine初始化完成，缓存{'启用' if enable_cache else '禁用'}")
    
    def _check_availability(self) -> bool:
        """检查搜索引擎是否可用"""
        if not TUSHARE_AVAILABLE:
            return False
        if not self.pro:
            return False
        if not self.tushare_token:
            return False
        return True
    
    def _to_ts_code(self, stock_code: str) -> str:
        """将股票代码转换为Tushare格式
        
        Args:
            stock_code: 股票代码，如 "600519" 或 "600519.SH"
            
        Returns:
            Tushare格式的股票代码，如 "600519.SH"
        """
        if not stock_code:
            return ""
        
        code = str(stock_code).strip()
        
        # 如果已经包含后缀，直接返回
        if "." in code:
            return code
        
        # 根据代码前缀判断市场
        if code.startswith("6"):
            return f"{code}.SH"  # 上海主板
        elif code.startswith("0") or code.startswith("3"):
            return f"{code}.SZ"  # 深圳主板/创业板
        elif code.startswith("4") or code.startswith("8"):
            return f"{code}.BJ"  # 北京交易所
        else:
            return f"{code}.SH"  # 默认上海
    
    def _get_stock_list(self, stock_code: Optional[str] = None) -> List[str]:
        """获取股票列表
        
        Args:
            stock_code: 如果指定，则只返回该股票；否则返回所有A股
            
        Returns:
            股票代码列表（Tushare格式）
        """
        if stock_code:
            return [self._to_ts_code(stock_code)]
        
        # 从缓存获取
        cache_key = "stock_list_all"
        if self.enable_cache and cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                self.logger.debug(f"从缓存获取股票列表，共{len(cached_data)}只")
                return cached_data
        
        try:
            # 获取所有上市股票
            df = self.pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,name,market"
            )
            
            if df is None or df.empty:
                self.logger.warning("获取股票列表失败，返回空列表")
                return []
            
            stock_list = df["ts_code"].tolist()
            
            # 缓存结果
            if self.enable_cache:
                self.cache[cache_key] = (stock_list, datetime.now())
            
            self.logger.info(f"获取股票列表成功，共{len(stock_list)}只")
            return stock_list
            
        except Exception as e:
            self.logger.error(f"获取股票列表失败: {e}", exc_info=True)
            return []
    
    def _get_stock_names(self, ts_codes: List[str]) -> Dict[str, str]:
        """批量获取股票名称
        
        Args:
            ts_codes: Tushare格式的股票代码列表
            
        Returns:
            股票代码到名称的映射字典
        """
        name_map = {}
        
        try:
            df = self.pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,name"
            )
            
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    name_map[row["ts_code"]] = row["name"]
        except Exception as e:
            self.logger.warning(f"获取股票名称失败: {e}")
        
        # 对于未找到名称的股票，使用代码作为名称
        for code in ts_codes:
            if code not in name_map:
                name_map[code] = code
        
        return name_map
    
    def _get_daily_data(
        self,
        ts_code: str,
        start_date: str,
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """获取股票日线数据
        
        Args:
            ts_code: Tushare格式的股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            
        Returns:
            日线数据DataFrame，失败返回None
        """
        cache_key = f"daily_{ts_code}_{start_date}_{end_date}"
        
        # 从缓存获取
        if self.enable_cache and cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_data.copy()
        
        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                return None
            
            # 按日期排序
            df = df.sort_values("trade_date").reset_index(drop=True)
            
            # 缓存结果
            if self.enable_cache:
                self.cache[cache_key] = (df, datetime.now())
            
            return df
            
        except Exception as e:
            self.logger.error(f"获取{ts_code}日线数据失败: {e}")
            return None

    
    def search_price_pattern(
        self,
        pattern_desc: str,
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 20
    ) -> Dict[str, Any]:
        """搜索价格形态模式
        
        支持的模式:
        - "连续N天涨停"
        - "连续N天跌停"
        - "V型反转"
        - "W底"
        - "头肩顶"
        等
        
        Args:
            pattern_desc: 模式描述
            stock_code: 指定股票代码（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            max_results: 最大返回结果数
            
        Returns:
            {
                "success": bool,
                "pattern_description": str,
                "matches": List[Dict],
                "statistics": Dict,
                "search_params": Dict
            }
        """
        self.logger.info(f"开始搜索价格形态模式: {pattern_desc}")
        
        # 检查可用性
        if not self._check_availability():
            return {
                "success": False,
                "error": "Tushare未配置或不可用",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 设置默认日期范围
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=365 * 2)
            start_date = start_dt.strftime("%Y%m%d")
        
        
        # 解析模式类型
        pattern_type, params = self._parse_price_pattern(pattern_desc)
        # 执行搜索
        matches = []
        if pattern_type =='limit_up' or pattern_type =='limit_down':
            if pattern_type == "limit_up":
                matches = self._search_consecutive_limit(
                    start_date, end_date, params["count"], "up", max_results
                )
            elif pattern_type == "limit_down":
                matches = self._search_consecutive_limit(
                    start_date, end_date, params["count"], "down", max_results
                )
            # 获取股票列表
        else:
            stock_list = self._get_stock_list(stock_code)
            if not stock_list:
                return {
                    "success": False,
                    "error": "无法获取股票列表",
                    "matches": [],
                    "statistics": {
                        "total_matches": 0
                    }
                }
            elif pattern_type == "v_reversal":
                matches = self._search_v_reversal(
                    stock_list, start_date, end_date, max_results
                )
            elif pattern_type == "w_bottom":
                matches = self._search_w_bottom(
                    stock_list, start_date, end_date, max_results
                )
            elif pattern_type == "head_shoulders":
                matches = self._search_head_shoulders(
                    stock_list, start_date, end_date, max_results
                )
            else:
                self.logger.warning(f"未识别的价格形态模式: {pattern_desc}")
                return {
                    "success": False,
                    "error": f"未识别的模式: {pattern_desc}",
                    "matches": [],
                    "statistics": {
                        "total_matches": 0
                    }
                }
        
        # 获取股票名称
        if matches:
            ts_codes = [m["stock_code"] for m in matches]
            name_map = self._get_stock_names(ts_codes)
            for m in matches:
                m["stock_name"] = name_map.get(m["stock_code"], m["stock_code"])
        
        # 计算统计信息
        statistics = {
            "total_matches": len(matches),
            "search_date_range": f"{start_date} ~ {end_date}",
            "pattern_type": pattern_type
        }
        
        self.logger.info(f"价格形态搜索完成，找到{len(matches)}个匹配案例")
        
        return {
            "success": True,
            "pattern_description": pattern_desc,
            "matches": matches,
            "statistics": statistics,
            "search_params": {
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "max_results": max_results
            }
        }
    
    def _parse_price_pattern(self, pattern_desc: str) -> tuple:
        """解析价格形态模式描述
        
        使用更智能的模式匹配，支持多种中文表达方式
        
        Returns:
            (pattern_type, params)
        """
        import re
        
        desc = pattern_desc.strip().lower()
        
        # 数字映射（支持中文数字）
        chinese_num_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5,
            '6': 6, '7': 7, '8': 8, '9': 9, '0': 0
        }
        
        def extract_number(text: str) -> Optional[int]:
            """从文本中提取数字（支持中文和阿拉伯数字）"""
            # 尝试匹配阿拉伯数字
            m = re.search(r'(\d+)', text)
            if m:
                return int(m.group(1))
            
            # 尝试匹配中文数字
            for cn, num in chinese_num_map.items():
                if cn in text:
                    return num
            
            return None
        
        # 1. 连续涨停模式
        # 支持: "连续3天涨停", "三连板", "3连板", "连续三个涨停", "3个涨停板"
        涨停_keywords = ['涨停', '涨停板', '连板', '涨板']
        if any(kw in desc for kw in 涨停_keywords):
            # 检查是否包含"跌"字，避免误判
            if '跌' not in desc:
                count = extract_number(desc)
                if count is None:
                    count = 1  # 默认1天
                return ("limit_up", {"count": count})
        
        # 2. 连续跌停模式
        # 支持: "连续3天跌停", "三连跌", "3连跌", "连续三个跌停"
        跌停_keywords = ['跌停', '跌停板', '连跌', '跌板']
        if any(kw in desc for kw in 跌停_keywords):
            count = extract_number(desc)
            if count is None:
                count = 1  # 默认1天
            return ("limit_down", {"count": count})
        
        # 3. V型反转模式
        # 支持: "V型反转", "V型", "v型", "V反转", "v反", "尖底反转"
        v型_keywords = ['v型反转', 'v型', 'v反转', 'v反', '尖底反转', '尖底']
        if any(kw in desc for kw in v型_keywords):
            return ("v_reversal", {})
        
        # 4. W底模式
        # 支持: "W底", "w底", "双底", "双重底", "W形态", "w形态"
        w底_keywords = ['w底', 'w形', '双底', '双重底', '二次底']
        if any(kw in desc for kw in w底_keywords):
            return ("w_bottom", {})
        
        # 5. 头肩顶模式
        # 支持: "头肩顶", "头肩形态", "头肩型"
        头肩顶_keywords = ['头肩顶', '头肩形', '头肩型']
        if any(kw in desc for kw in 头肩顶_keywords):
            return ("head_shoulders", {})
        
        # 6. 其他可能的模式（可扩展）
        # 圆弧底
        if '圆弧底' in desc or '圆底' in desc:
            self.logger.warning(f"暂不支持圆弧底模式: {pattern_desc}")
            return ("unknown", {})
        
        # 三角形整理
        if '三角' in desc and ('整理' in desc or '形态' in desc):
            self.logger.warning(f"暂不支持三角形整理模式: {pattern_desc}")
            return ("unknown", {})
        
        # 如果都不匹配，记录日志
        self.logger.warning(f"未识别的价格形态模式: {pattern_desc}")
        return ("unknown", {})
    
    def _search_consecutive_limit(
        self,
        start_date: str,
        end_date: str,
        count: int,
        direction: str,  # "up" or "down"
        max_results: int
    ) -> List[Dict]:
        """搜索连续涨停/跌停
        
        Returns:
            匹配案例列表
        """
        matches = []
        
        if direction =='up':
            limit_type = 'D'
        else:
            limit_type = 'U'
        
        results_df = self.pro.limit_list_d(start_date=start_date,
            end_date = end_date,
            limit_type= 'D')

        results_df = results_df[results_df['limit_times']==count].head(max_results)
        
        if len(results_df)>0:
            for i,row in results_df.iterrows():
                    matches.append({
                        "stock_code": row['ts_code'],
                        "match_date": row['trade_date'],
                        "match_score": 1.0,
                        "pattern_data": {
                            "consecutive_days": count,
                            "direction": direction,
                            "close_at_match": row['close']
                        }
                    })
        else:
            self.logger.debug(f"没有匹配的股票")
        return matches
    
    def _search_v_reversal(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索V型反转形态
        
        V型反转特征：
        - 连续下跌后快速反转上涨
        - 下跌和上涨的幅度相近
        """
        matches = []
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 10:
                    continue
                
                # 寻找V型反转点
                for i in range(5, len(df) - 5):
                    # 前5天下跌
                    down_days = sum(1 for j in range(i-5, i) if df.iloc[j]["pct_chg"] < 0)
                    # 后5天上涨
                    up_days = sum(1 for j in range(i, i+5) if df.iloc[j]["pct_chg"] > 0)
                    
                    if down_days >= 4 and up_days >= 4:
                        # 计算下跌和上涨幅度
                        down_pct = (df.iloc[i]["close"] / df.iloc[i-5]["close"] - 1) * 100
                        up_pct = (df.iloc[i+5]["close"] / df.iloc[i]["close"] - 1) * 100
                        
                        # V型反转：下跌幅度和上涨幅度相近
                        if abs(down_pct) > 10 and up_pct > 10:
                            if 0.5 < abs(up_pct / down_pct) < 2.0:
                                match_score = 1.0 - abs(1.0 - abs(up_pct / down_pct))
                                
                                matches.append({
                                    "stock_code": ts_code,
                                    "match_date": df.iloc[i]["trade_date"],
                                    "match_score": round(match_score, 2),
                                    "pattern_data": {
                                        "down_pct": round(down_pct, 2),
                                        "up_pct": round(up_pct, 2),
                                        "reversal_point": round(float(df.iloc[i]["close"]), 2)
                                    }
                                })
                                
                                if len(matches) >= max_results:
                                    return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_w_bottom(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索W底（双底）形态
        
        W底特征：
        - 两个相近的低点
        - 中间有一个高点
        """
        matches = []
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 20:
                    continue
                
                # 寻找局部极值点
                for i in range(10, len(df) - 10):
                    # 寻找第一个低点
                    if df.iloc[i]["low"] < df.iloc[i-5:i]["low"].min() and \
                       df.iloc[i]["low"] < df.iloc[i+1:i+6]["low"].min():
                        
                        first_low = df.iloc[i]["low"]
                        first_low_idx = i
                        
                        # 寻找中间高点
                        for j in range(i+5, min(i+15, len(df)-5)):
                            if df.iloc[j]["high"] > df.iloc[j-3:j]["high"].max() and \
                               df.iloc[j]["high"] > df.iloc[j+1:j+4]["high"].max():
                                
                                middle_high = df.iloc[j]["high"]
                                
                                # 寻找第二个低点
                                for k in range(j+5, min(j+15, len(df))):
                                    if df.iloc[k]["low"] < df.iloc[k-3:k]["low"].min():
                                        second_low = df.iloc[k]["low"]
                                        
                                        # 判断是否形成W底
                                        if abs(second_low - first_low) / first_low < 0.05:  # 两个低点相近
                                            if (middle_high - first_low) / first_low > 0.05:  # 中间有明显反弹
                                                match_score = 1.0 - abs(second_low - first_low) / first_low
                                                
                                                matches.append({
                                                    "stock_code": ts_code,
                                                    "match_date": df.iloc[k]["trade_date"],
                                                    "match_score": round(match_score, 2),
                                                    "pattern_data": {
                                                        "first_low": round(float(first_low), 2),
                                                        "second_low": round(float(second_low), 2),
                                                        "middle_high": round(float(middle_high), 2),
                                                        "pattern_days": k - first_low_idx
                                                    }
                                                })
                                                
                                                if len(matches) >= max_results:
                                                    return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_head_shoulders(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索头肩顶形态
        
        头肩顶特征：
        - 三个高点，中间最高
        - 左右两个肩部高度相近
        """
        matches = []
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 30:
                    continue
                
                # 寻找三个高点
                for i in range(10, len(df) - 20):
                    # 左肩
                    if df.iloc[i]["high"] > df.iloc[i-5:i]["high"].max() and \
                       df.iloc[i]["high"] > df.iloc[i+1:i+6]["high"].max():
                        
                        left_shoulder = df.iloc[i]["high"]
                        
                        # 头部
                        for j in range(i+5, min(i+15, len(df)-10)):
                            if df.iloc[j]["high"] > df.iloc[j-5:j]["high"].max() and \
                               df.iloc[j]["high"] > df.iloc[j+1:j+6]["high"].max():
                                
                                head = df.iloc[j]["high"]
                                
                                # 头部应该高于左肩
                                if head > left_shoulder * 1.05:
                                    # 右肩
                                    for k in range(j+5, min(j+15, len(df))):
                                        if df.iloc[k]["high"] > df.iloc[k-5:k]["high"].max():
                                            right_shoulder = df.iloc[k]["high"]
                                            
                                            # 判断是否形成头肩顶
                                            if abs(right_shoulder - left_shoulder) / left_shoulder < 0.05:
                                                if right_shoulder < head * 0.95:
                                                    match_score = 1.0 - abs(right_shoulder - left_shoulder) / left_shoulder
                                                    
                                                    matches.append({
                                                        "stock_code": ts_code,
                                                        "match_date": df.iloc[k]["trade_date"],
                                                        "match_score": round(match_score, 2),
                                                        "pattern_data": {
                                                            "left_shoulder": round(float(left_shoulder), 2),
                                                            "head": round(float(head), 2),
                                                            "right_shoulder": round(float(right_shoulder), 2)
                                                        }
                                                    })
                                                    
                                                    if len(matches) >= max_results:
                                                        return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches

    
    def search_indicator_pattern(
        self,
        pattern_desc: str,
        indicator_type: str,
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """搜索技术指标模式
        
        支持的指标:
        - MACD: "金叉", "死叉", "底背离", "顶背离"
        - KDJ: "超买", "超卖", "金叉", "死叉"
        - RSI: "超买", "超卖", "背离"
        - 均线: "多头排列", "空头排列", "金叉", "死叉"
        
        Args:
            pattern_desc: 模式描述
            indicator_type: 指标类型 (MACD, KDJ, RSI, MA)
            stock_code: 指定股票代码（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            max_results: 最大返回结果数
            **kwargs: 其他参数
            
        Returns:
            {
                "success": bool,
                "pattern_description": str,
                "indicator_type": str,
                "matches": List[Dict],
                "statistics": Dict,
                "search_params": Dict
            }
        """
        self.logger.info(f"开始搜索技术指标模式: {indicator_type} - {pattern_desc}")
        
        # 检查可用性
        if not self._check_availability():
            return {
                "success": False,
                "error": "Tushare未配置或不可用",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 设置默认日期范围
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=365 * 2)
            start_date = start_dt.strftime("%Y%m%d")
        
        # 获取股票列表
        stock_list = self._get_stock_list(stock_code)
        if not stock_list:
            return {
                "success": False,
                "error": "无法获取股票列表",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 根据指标类型执行搜索
        matches = []
        indicator_type_upper = indicator_type.upper()
        
        if indicator_type_upper == "MACD":
            matches = self._search_macd_pattern(
                stock_list, pattern_desc, start_date, end_date, max_results
            )
        elif indicator_type_upper == "KDJ":
            matches = self._search_kdj_pattern(
                stock_list, pattern_desc, start_date, end_date, max_results
            )
        elif indicator_type_upper == "RSI":
            matches = self._search_rsi_pattern(
                stock_list, pattern_desc, start_date, end_date, max_results
            )
        elif indicator_type_upper == "MA":
            matches = self._search_ma_pattern(
                stock_list, pattern_desc, start_date, end_date, max_results
            )
        else:
            self.logger.warning(f"未识别的指标类型: {indicator_type}")
            return {
                "success": False,
                "error": f"未识别的指标类型: {indicator_type}",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 获取股票名称
        if matches:
            ts_codes = [m["stock_code"] for m in matches]
            name_map = self._get_stock_names(ts_codes)
            for m in matches:
                m["stock_name"] = name_map.get(m["stock_code"], m["stock_code"])
        
        # 计算统计信息
        statistics = {
            "total_matches": len(matches),
            "search_date_range": f"{start_date} ~ {end_date}",
            "indicator_type": indicator_type_upper
        }
        
        self.logger.info(f"技术指标搜索完成，找到{len(matches)}个匹配案例")
        
        return {
            "success": True,
            "pattern_description": pattern_desc,
            "indicator_type": indicator_type_upper,
            "matches": matches,
            "statistics": statistics,
            "search_params": {
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "max_results": max_results
            }
        }
    
    def _search_macd_pattern(
        self,
        stock_list: List[str],
        pattern_desc: str,
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索MACD模式"""
        matches = []
        
        # 解析模式类型
        is_golden_cross = "金叉" in pattern_desc
        is_dead_cross = "死叉" in pattern_desc
        is_bottom_divergence = "底背离" in pattern_desc
        is_top_divergence = "顶背离" in pattern_desc
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 35:  # MACD需要至少35个数据点
                    continue
                
                # 计算MACD
                macd_result = TechnicalIndicators.calculate_macd(df["close"])
                if not macd_result.get("success"):
                    continue
                
                dif = macd_result["dif"]
                dea = macd_result["dea"]
                
                # 搜索金叉/死叉
                if is_golden_cross or is_dead_cross:
                    for i in range(1, len(df)):
                        if pd.isna(dif.iloc[i]) or pd.isna(dea.iloc[i]):
                            continue
                        if pd.isna(dif.iloc[i-1]) or pd.isna(dea.iloc[i-1]):
                            continue
                        
                        prev_dif, prev_dea = dif.iloc[i-1], dea.iloc[i-1]
                        cur_dif, cur_dea = dif.iloc[i], dea.iloc[i]
                        
                        if is_golden_cross and prev_dif < prev_dea and cur_dif > cur_dea:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "MACD金叉",
                                    "dif": round(float(cur_dif), 4),
                                    "dea": round(float(cur_dea), 4),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                        
                        elif is_dead_cross and prev_dif > prev_dea and cur_dif < cur_dea:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "MACD死叉",
                                    "dif": round(float(cur_dif), 4),
                                    "dea": round(float(cur_dea), 4),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                
                # 搜索背离（简化版）
                elif is_bottom_divergence or is_top_divergence:
                    # 背离检测需要更复杂的逻辑，这里实现简化版
                    for i in range(20, len(df)):
                        if pd.isna(dif.iloc[i]):
                            continue
                        
                        # 寻找价格和MACD的背离
                        price_window = df["close"].iloc[i-20:i]
                        dif_window = dif.iloc[i-20:i]
                        
                        if is_bottom_divergence:
                            # 价格创新低，但MACD不创新低
                            if df.iloc[i]["close"] == price_window.min():
                                if dif.iloc[i] > dif_window.min():
                                    matches.append({
                                        "stock_code": ts_code,
                                        "match_date": df.iloc[i]["trade_date"],
                                        "match_score": 0.8,
                                        "pattern_data": {
                                            "pattern": "MACD底背离",
                                            "close": round(float(df.iloc[i]["close"]), 2),
                                            "dif": round(float(dif.iloc[i]), 4)
                                        }
                                    })
                                    if len(matches) >= max_results:
                                        return matches
                        
                        elif is_top_divergence:
                            # 价格创新高，但MACD不创新高
                            if df.iloc[i]["close"] == price_window.max():
                                if dif.iloc[i] < dif_window.max():
                                    matches.append({
                                        "stock_code": ts_code,
                                        "match_date": df.iloc[i]["trade_date"],
                                        "match_score": 0.8,
                                        "pattern_data": {
                                            "pattern": "MACD顶背离",
                                            "close": round(float(df.iloc[i]["close"]), 2),
                                            "dif": round(float(dif.iloc[i]), 4)
                                        }
                                    })
                                    if len(matches) >= max_results:
                                        return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_kdj_pattern(
        self,
        stock_list: List[str],
        pattern_desc: str,
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索KDJ模式"""
        matches = []
        
        # 解析模式类型
        is_overbought = "超买" in pattern_desc
        is_oversold = "超卖" in pattern_desc
        is_golden_cross = "金叉" in pattern_desc
        is_dead_cross = "死叉" in pattern_desc
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 9:  # KDJ需要至少9个数据点
                    continue
                
                # 计算KDJ
                kdj_result = TechnicalIndicators.calculate_kdj(
                    df["high"], df["low"], df["close"]
                )
                if not kdj_result.get("success"):
                    continue
                
                k = kdj_result["k"]
                d = kdj_result["d"]
                j = kdj_result["j"]
                
                # 搜索超买/超卖
                if is_overbought or is_oversold:
                    for i in range(len(df)):
                        if pd.isna(k.iloc[i]) or pd.isna(d.iloc[i]):
                            continue
                        
                        k_val = k.iloc[i]
                        d_val = d.iloc[i]
                        
                        if is_overbought and k_val > 80 and d_val > 80:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "KDJ超买",
                                    "k": round(float(k_val), 2),
                                    "d": round(float(d_val), 2),
                                    "j": round(float(j.iloc[i]), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                        
                        elif is_oversold and k_val < 20 and d_val < 20:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "KDJ超卖",
                                    "k": round(float(k_val), 2),
                                    "d": round(float(d_val), 2),
                                    "j": round(float(j.iloc[i]), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                
                # 搜索金叉/死叉
                elif is_golden_cross or is_dead_cross:
                    for i in range(1, len(df)):
                        if pd.isna(k.iloc[i]) or pd.isna(d.iloc[i]):
                            continue
                        if pd.isna(k.iloc[i-1]) or pd.isna(d.iloc[i-1]):
                            continue
                        
                        prev_k, prev_d = k.iloc[i-1], d.iloc[i-1]
                        cur_k, cur_d = k.iloc[i], d.iloc[i]
                        
                        if is_golden_cross and prev_k < prev_d and cur_k > cur_d:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "KDJ金叉",
                                    "k": round(float(cur_k), 2),
                                    "d": round(float(cur_d), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                        
                        elif is_dead_cross and prev_k > prev_d and cur_k < cur_d:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "KDJ死叉",
                                    "k": round(float(cur_k), 2),
                                    "d": round(float(cur_d), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_rsi_pattern(
        self,
        stock_list: List[str],
        pattern_desc: str,
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索RSI模式"""
        matches = []
        
        # 解析模式类型
        is_overbought = "超买" in pattern_desc
        is_oversold = "超卖" in pattern_desc
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 15:  # RSI需要至少15个数据点
                    continue
                
                # 计算RSI
                rsi_result = TechnicalIndicators.calculate_rsi(df["close"])
                if not rsi_result.get("success"):
                    continue
                
                rsi = rsi_result["rsi"]
                
                # 搜索超买/超卖
                for i in range(len(df)):
                    if pd.isna(rsi.iloc[i]):
                        continue
                    
                    rsi_val = rsi.iloc[i]
                    
                    if is_overbought and rsi_val > 70:
                        matches.append({
                            "stock_code": ts_code,
                            "match_date": df.iloc[i]["trade_date"],
                            "match_score": 1.0,
                            "pattern_data": {
                                "pattern": "RSI超买",
                                "rsi": round(float(rsi_val), 2),
                                "close": round(float(df.iloc[i]["close"]), 2)
                            }
                        })
                        if len(matches) >= max_results:
                            return matches
                    
                    elif is_oversold and rsi_val < 30:
                        matches.append({
                            "stock_code": ts_code,
                            "match_date": df.iloc[i]["trade_date"],
                            "match_score": 1.0,
                            "pattern_data": {
                                "pattern": "RSI超卖",
                                "rsi": round(float(rsi_val), 2),
                                "close": round(float(df.iloc[i]["close"]), 2)
                            }
                        })
                        if len(matches) >= max_results:
                            return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_ma_pattern(
        self,
        stock_list: List[str],
        pattern_desc: str,
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索均线模式"""
        matches = []
        
        # 解析模式类型
        is_bullish = "多头排列" in pattern_desc or "多头" in pattern_desc
        is_bearish = "空头排列" in pattern_desc or "空头" in pattern_desc
        is_golden_cross = "金叉" in pattern_desc
        is_dead_cross = "死叉" in pattern_desc
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 60:  # 均线需要足够的数据点
                    continue
                
                # 计算均线
                ma_result = TechnicalIndicators.calculate_ma(df["close"], [5, 10, 20, 60])
                if not ma_result.get("success"):
                    continue
                
                ma_values = ma_result["ma_values"]
                
                # 搜索多头/空头排列
                if is_bullish or is_bearish:
                    for i in range(len(df)):
                        # 获取各均线的当前值
                        ma5 = ma_values[5].iloc[i] if not pd.isna(ma_values[5].iloc[i]) else None
                        ma10 = ma_values[10].iloc[i] if not pd.isna(ma_values[10].iloc[i]) else None
                        ma20 = ma_values[20].iloc[i] if not pd.isna(ma_values[20].iloc[i]) else None
                        
                        if ma5 is None or ma10 is None or ma20 is None:
                            continue
                        
                        if is_bullish and ma5 > ma10 > ma20:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "均线多头排列",
                                    "ma5": round(float(ma5), 2),
                                    "ma10": round(float(ma10), 2),
                                    "ma20": round(float(ma20), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                        
                        elif is_bearish and ma5 < ma10 < ma20:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "均线空头排列",
                                    "ma5": round(float(ma5), 2),
                                    "ma10": round(float(ma10), 2),
                                    "ma20": round(float(ma20), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                
                # 搜索金叉/死叉（短期均线与长期均线）
                elif is_golden_cross or is_dead_cross:
                    for i in range(1, len(df)):
                        ma5_prev = ma_values[5].iloc[i-1] if not pd.isna(ma_values[5].iloc[i-1]) else None
                        ma20_prev = ma_values[20].iloc[i-1] if not pd.isna(ma_values[20].iloc[i-1]) else None
                        ma5_cur = ma_values[5].iloc[i] if not pd.isna(ma_values[5].iloc[i]) else None
                        ma20_cur = ma_values[20].iloc[i] if not pd.isna(ma_values[20].iloc[i]) else None
                        
                        if ma5_prev is None or ma20_prev is None or ma5_cur is None or ma20_cur is None:
                            continue
                        
                        if is_golden_cross and ma5_prev < ma20_prev and ma5_cur > ma20_cur:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "均线金叉",
                                    "ma5": round(float(ma5_cur), 2),
                                    "ma20": round(float(ma20_cur), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                        
                        elif is_dead_cross and ma5_prev > ma20_prev and ma5_cur < ma20_cur:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": df.iloc[i]["trade_date"],
                                "match_score": 1.0,
                                "pattern_data": {
                                    "pattern": "均线死叉",
                                    "ma5": round(float(ma5_cur), 2),
                                    "ma20": round(float(ma20_cur), 2),
                                    "close": round(float(df.iloc[i]["close"]), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches

    
    def search_chip_pattern(
        self,
        pattern_desc: str,
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """搜索筹码分布模式
        
        支持的模式:
        - "筹码集中度上升"
        - "主力资金流入"
        - "散户离场"
        等
        
        Args:
            pattern_desc: 模式描述
            stock_code: 指定股票代码（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            max_results: 最大返回结果数
            **kwargs: 其他参数
            
        Returns:
            {
                "success": bool,
                "pattern_description": str,
                "matches": List[Dict],
                "statistics": Dict,
                "search_params": Dict
            }
        """
        self.logger.info(f"开始搜索筹码分布模式: {pattern_desc}")
        
        # 检查可用性
        if not self._check_availability():
            return {
                "success": False,
                "error": "Tushare未配置或不可用",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 设置默认日期范围
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=365)
            start_date = start_dt.strftime("%Y%m%d")
        
        # 获取股票列表
        stock_list = self._get_stock_list(stock_code)
        if not stock_list:
            return {
                "success": False,
                "error": "无法获取股票列表",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 解析模式类型
        is_concentration = "筹码集中" in pattern_desc or "集中度上升" in pattern_desc
        is_main_inflow = "主力" in pattern_desc and "流入" in pattern_desc
        is_retail_outflow = "散户" in pattern_desc and "离场" in pattern_desc
        
        matches = []
        
        # 筹码集中度分析
        if is_concentration:
            matches = self._search_chip_concentration(
                stock_list, start_date, end_date, max_results
            )
        
        # 主力资金流向分析
        elif is_main_inflow:
            matches = self._search_main_fund_flow(
                stock_list, start_date, end_date, "inflow", max_results
            )
        
        # 散户离场分析
        elif is_retail_outflow:
            matches = self._search_main_fund_flow(
                stock_list, start_date, end_date, "outflow", max_results
            )
        
        else:
            self.logger.warning(f"未识别的筹码分布模式: {pattern_desc}")
            return {
                "success": False,
                "error": f"未识别的模式: {pattern_desc}",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 获取股票名称
        if matches:
            ts_codes = [m["stock_code"] for m in matches]
            name_map = self._get_stock_names(ts_codes)
            for m in matches:
                m["stock_name"] = name_map.get(m["stock_code"], m["stock_code"])
        
        # 计算统计信息
        statistics = {
            "total_matches": len(matches),
            "search_date_range": f"{start_date} ~ {end_date}"
        }
        
        self.logger.info(f"筹码分布搜索完成，找到{len(matches)}个匹配案例")
        
        return {
            "success": True,
            "pattern_description": pattern_desc,
            "matches": matches,
            "statistics": statistics,
            "search_params": {
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "max_results": max_results
            }
        }
    
    def _search_chip_concentration(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        max_results: int
    ) -> List[Dict]:
        """搜索筹码集中度上升的股票
        
        使用换手率和成交量变化来判断筹码集中度
        """
        matches = []
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                df = self._get_daily_data(ts_code, start_date, end_date)
                if df is None or len(df) < 30:
                    continue
                
                # 计算换手率的移动平均
                if "turnover_rate" not in df.columns:
                    continue
                
                df["turnover_ma10"] = df["turnover_rate"].rolling(window=10).mean()
                df["turnover_ma30"] = df["turnover_rate"].rolling(window=30).mean()
                
                # 筹码集中：换手率下降（交易不活跃，筹码锁定）
                for i in range(30, len(df)):
                    if pd.isna(df.iloc[i]["turnover_ma10"]) or pd.isna(df.iloc[i]["turnover_ma30"]):
                        continue
                    
                    turnover_ma10 = df.iloc[i]["turnover_ma10"]
                    turnover_ma30 = df.iloc[i]["turnover_ma30"]
                    
                    # 短期换手率低于长期换手率，且都在低位
                    if turnover_ma10 < turnover_ma30 * 0.7 and turnover_ma10 < 3.0:
                        # 计算集中度评分
                        concentration_score = 1.0 - (turnover_ma10 / turnover_ma30)
                        
                        matches.append({
                            "stock_code": ts_code,
                            "match_date": df.iloc[i]["trade_date"],
                            "match_score": round(concentration_score, 2),
                            "pattern_data": {
                                "pattern": "筹码集中度上升",
                                "turnover_rate": round(float(df.iloc[i]["turnover_rate"]), 2),
                                "turnover_ma10": round(float(turnover_ma10), 2),
                                "turnover_ma30": round(float(turnover_ma30), 2),
                                "close": round(float(df.iloc[i]["close"]), 2)
                            }
                        })
                        
                        if len(matches) >= max_results:
                            return matches
                        break  # 每只股票只取一个匹配点
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches
    
    def _search_main_fund_flow(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        flow_type: str,  # "inflow" or "outflow"
        max_results: int
    ) -> List[Dict]:
        """搜索主力资金流向
        
        使用大单成交量来判断主力资金流向
        """
        matches = []
        
        for ts_code in stock_list:
            if len(matches) >= max_results:
                break
            
            try:
                # 获取资金流向数据（如果可用）
                try:
                    df_moneyflow = self.pro.moneyflow(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date
                    )
                except:
                    # 如果没有资金流向数据，使用成交量和价格变化估算
                    df = self._get_daily_data(ts_code, start_date, end_date)
                    if df is None or len(df) < 10:
                        continue
                    
                    # 简化版：使用成交量和涨跌幅估算资金流向
                    for i in range(5, len(df)):
                        if df.iloc[i]["pct_chg"] > 3 and df.iloc[i]["vol"] > df.iloc[i-5:i]["vol"].mean() * 1.5:
                            if flow_type == "inflow":
                                matches.append({
                                    "stock_code": ts_code,
                                    "match_date": df.iloc[i]["trade_date"],
                                    "match_score": 0.7,
                                    "pattern_data": {
                                        "pattern": "主力资金流入（估算）",
                                        "pct_chg": round(float(df.iloc[i]["pct_chg"]), 2),
                                        "vol_ratio": round(float(df.iloc[i]["vol"] / df.iloc[i-5:i]["vol"].mean()), 2),
                                        "close": round(float(df.iloc[i]["close"]), 2)
                                    }
                                })
                                if len(matches) >= max_results:
                                    return matches
                                break
                    continue
                
                if df_moneyflow is None or df_moneyflow.empty:
                    continue
                
                df_moneyflow = df_moneyflow.sort_values("trade_date").reset_index(drop=True)
                
                # 分析主力资金净流入
                for i in range(len(df_moneyflow)):
                    row = df_moneyflow.iloc[i]
                    
                    # 主力净流入 = 超大单净流入 + 大单净流入
                    if "buy_elg_amount" in row and "buy_lg_amount" in row:
                        main_net_inflow = (row.get("buy_elg_amount", 0) - row.get("sell_elg_amount", 0) +
                                          row.get("buy_lg_amount", 0) - row.get("sell_lg_amount", 0))
                        
                        if flow_type == "inflow" and main_net_inflow > 0:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": row["trade_date"],
                                "match_score": 0.9,
                                "pattern_data": {
                                    "pattern": "主力资金流入",
                                    "main_net_inflow": round(float(main_net_inflow / 10000), 2),  # 转换为万元
                                    "close": round(float(row.get("close", 0)), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                            break
                        
                        elif flow_type == "outflow" and main_net_inflow < 0:
                            matches.append({
                                "stock_code": ts_code,
                                "match_date": row["trade_date"],
                                "match_score": 0.9,
                                "pattern_data": {
                                    "pattern": "主力资金流出",
                                    "main_net_outflow": round(float(abs(main_net_inflow) / 10000), 2),
                                    "close": round(float(row.get("close", 0)), 2)
                                }
                            })
                            if len(matches) >= max_results:
                                return matches
                            break
            
            except Exception as e:
                self.logger.debug(f"处理{ts_code}时出错: {e}")
                continue
        
        return matches

    
    def analyze_future_performance(
        self,
        matches: List[Dict],
        lookahead_days: List[int] = None
    ) -> Dict[str, Any]:
        """分析匹配案例的后续表现
        
        Args:
            matches: 匹配案例列表，每个案例需包含stock_code和match_date
            lookahead_days: 后续分析的天数列表，默认[5, 10, 20]
            
        Returns:
            {
                "success": bool,
                "matches_with_performance": List[Dict],  # 包含后续表现的匹配案例
                "statistics": Dict  # 统计摘要
            }
        """
        self.logger.info(f"开始分析{len(matches)}个匹配案例的后续表现")
        
        if not matches:
            return {
                "success": True,
                "matches_with_performance": [],
                "statistics": {
                    "total_analyzed": 0
                }
            }
        
        if lookahead_days is None:
            lookahead_days = [5, 10, 20]
        
        # 为每个匹配案例计算后续表现
        matches_with_performance = []
        
        for match in matches:
            ts_code = match.get("stock_code")
            match_date = match.get("match_date")
            
            if not ts_code or not match_date:
                continue
            
            # 获取后续走势
            future_perf = self._get_future_performance(ts_code, match_date, lookahead_days)
            
            # 添加到匹配案例
            match_copy = match.copy()
            match_copy["future_performance"] = future_perf
            matches_with_performance.append(match_copy)
        
        # 计算统计摘要
        statistics = self._calculate_performance_statistics(
            matches_with_performance, lookahead_days
        )
        
        self.logger.info(f"后续表现分析完成，成功分析{len(matches_with_performance)}个案例")
        
        return {
            "success": True,
            "matches_with_performance": matches_with_performance,
            "statistics": statistics
        }
    
    def _get_future_performance(
        self,
        ts_code: str,
        match_date: str,
        lookahead_days: List[int]
    ) -> Dict[str, Optional[float]]:
        """获取匹配日之后的N日涨跌幅
        
        Args:
            ts_code: 股票代码
            match_date: 匹配日期 YYYYMMDD
            lookahead_days: 后续天数列表
            
        Returns:
            {
                "5d_return": float,  # 5日涨跌幅（%）
                "10d_return": float,
                "20d_return": float,
                ...
            }
        """
        try:
            # 计算结束日期（匹配日 + 最大天数 + 10天缓冲）
            match_dt = datetime.strptime(match_date, "%Y%m%d")
            end_dt = match_dt + timedelta(days=max(lookahead_days) + 10)
            end_date = end_dt.strftime("%Y%m%d")
            
            # 获取后续数据
            df = self._get_daily_data(ts_code, match_date, end_date)
            
            if df is None or df.empty:
                return {f"{d}d_return": None for d in lookahead_days}
            
            # 确保数据按日期排序
            df = df.sort_values("trade_date").reset_index(drop=True)
            
            # 匹配日的收盘价
            close_at_match = df.iloc[0]["close"] if len(df) > 0 else None
            
            if close_at_match is None or close_at_match == 0:
                return {f"{d}d_return": None for d in lookahead_days}
            
            # 计算各天数的涨跌幅
            result = {}
            for d in lookahead_days:
                if len(df) > d:
                    close_future = df.iloc[d]["close"]
                    return_pct = (close_future / close_at_match - 1) * 100
                    result[f"{d}d_return"] = round(return_pct, 2)
                else:
                    result[f"{d}d_return"] = None
            
            return result
        
        except Exception as e:
            self.logger.debug(f"获取{ts_code}后续表现失败: {e}")
            return {f"{d}d_return": None for d in lookahead_days}
    
    def _calculate_performance_statistics(
        self,
        matches: List[Dict],
        lookahead_days: List[int]
    ) -> Dict[str, Any]:
        """计算后续表现的统计摘要
        
        Args:
            matches: 包含future_performance的匹配案例列表
            lookahead_days: 后续天数列表
            
        Returns:
            统计摘要字典
        """
        statistics = {
            "total_matches": len(matches),
            "valid_matches": 0
        }
        
        # 按天数收集收益率
        returns_by_day = defaultdict(list)
        
        for match in matches:
            future_perf = match.get("future_performance", {})
            
            has_valid_data = False
            for d in lookahead_days:
                key = f"{d}d_return"
                ret = future_perf.get(key)
                
                if ret is not None:
                    returns_by_day[d].append(ret)
                    has_valid_data = True
            
            if has_valid_data:
                statistics["valid_matches"] += 1
        
        # 计算各天数的统计指标
        for d in lookahead_days:
            returns = returns_by_day[d]
            
            if not returns:
                statistics[f"avg_{d}d_return"] = None
                statistics[f"median_{d}d_return"] = None
                statistics[f"positive_rate_{d}d"] = None
                statistics[f"max_{d}d_return"] = None
                statistics[f"min_{d}d_return"] = None
                statistics[f"risk_reward_ratio_{d}d"] = None
                continue
            
            # 平均收益率
            avg_return = sum(returns) / len(returns)
            statistics[f"avg_{d}d_return"] = round(avg_return, 2)
            
            # 中位数收益率
            sorted_returns = sorted(returns)
            median_return = sorted_returns[len(sorted_returns) // 2]
            statistics[f"median_{d}d_return"] = round(median_return, 2)
            
            # 上涨概率
            positive_count = sum(1 for r in returns if r > 0)
            positive_rate = positive_count / len(returns)
            statistics[f"positive_rate_{d}d"] = round(positive_rate, 2)
            
            # 最大/最小收益率
            statistics[f"max_{d}d_return"] = round(max(returns), 2)
            statistics[f"min_{d}d_return"] = round(min(returns), 2)
            
            # 风险收益比（平均收益 / 标准差）
            if len(returns) > 1:
                std_dev = np.std(returns)
                if std_dev > 0:
                    risk_reward = avg_return / std_dev
                    statistics[f"risk_reward_ratio_{d}d"] = round(risk_reward, 2)
                else:
                    statistics[f"risk_reward_ratio_{d}d"] = None
            else:
                statistics[f"risk_reward_ratio_{d}d"] = None
        
        return statistics

    
    def search_combined_pattern(
        self,
        patterns: List[Dict[str, Any]],
        combination_type: str = "AND",
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 20,
        lookahead_days: List[int] = None
    ) -> Dict[str, Any]:
        """搜索组合模式
        
        支持多个条件的AND/OR组合
        
        Args:
            patterns: 模式列表，每个模式包含:
                {
                    "type": "price" | "indicator" | "chip",
                    "description": str,
                    "params": dict  # 可选的额外参数
                }
            combination_type: 组合类型，"AND" 或 "OR"
            stock_code: 指定股票代码（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            max_results: 最大返回结果数
            lookahead_days: 后续分析天数列表
            
        Returns:
            {
                "success": bool,
                "combination_type": str,
                "patterns": List[Dict],
                "matches": List[Dict],
                "statistics": Dict
            }
        """
        self.logger.info(f"开始搜索组合模式，组合类型: {combination_type}, 模式数: {len(patterns)}")
        
        # 检查可用性
        if not self._check_availability():
            return {
                "success": False,
                "error": "Tushare未配置或不可用",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        if not patterns:
            return {
                "success": False,
                "error": "未提供模式",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 设置默认日期范围
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=365 * 2)
            start_date = start_dt.strftime("%Y%m%d")
        
        # 执行每个模式的搜索
        pattern_results = []
        
        for i, pattern in enumerate(patterns):
            pattern_type = pattern.get("type")
            pattern_desc = pattern.get("description")
            pattern_params = pattern.get("params", {})
            
            self.logger.debug(f"执行模式{i+1}: {pattern_type} - {pattern_desc}")
            
            # 根据模式类型调用相应的搜索方法
            if pattern_type == "price":
                result = self.search_price_pattern(
                    pattern_desc=pattern_desc,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results * 2  # 获取更多结果用于组合
                )
            elif pattern_type == "indicator":
                indicator_type = pattern_params.get("indicator_type", "MACD")
                result = self.search_indicator_pattern(
                    pattern_desc=pattern_desc,
                    indicator_type=indicator_type,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results * 2
                )
            elif pattern_type == "chip":
                result = self.search_chip_pattern(
                    pattern_desc=pattern_desc,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results * 2
                )
            else:
                self.logger.warning(f"未识别的模式类型: {pattern_type}")
                continue
            
            if result.get("success"):
                pattern_results.append({
                    "pattern": pattern,
                    "matches": result.get("matches", [])
                })
        
        if not pattern_results:
            return {
                "success": False,
                "error": "所有模式搜索均失败",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 组合匹配结果
        if combination_type.upper() == "AND":
            combined_matches = self._combine_matches_and(pattern_results, max_results)
        elif combination_type.upper() == "OR":
            combined_matches = self._combine_matches_or(pattern_results, max_results)
        else:
            return {
                "success": False,
                "error": f"未识别的组合类型: {combination_type}",
                "matches": [],
                "statistics": {
                    "total_matches": 0
                }
            }
        
        # 计算匹配度评分
        for match in combined_matches:
            match["match_score"] = self._calculate_combined_score(match, len(patterns))
        
        # 按匹配度排序
        combined_matches.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        
        # 获取股票名称
        if combined_matches:
            ts_codes = [m["stock_code"] for m in combined_matches]
            name_map = self._get_stock_names(ts_codes)
            for m in combined_matches:
                m["stock_name"] = name_map.get(m["stock_code"], m["stock_code"])
        
        # 分析后续表现
        if lookahead_days and combined_matches:
            perf_result = self.analyze_future_performance(combined_matches, lookahead_days)
            combined_matches = perf_result.get("matches_with_performance", combined_matches)
            statistics = perf_result.get("statistics", {})
        else:
            statistics = {
                "total_matches": len(combined_matches)
            }
        
        statistics["combination_type"] = combination_type.upper()
        statistics["pattern_count"] = len(patterns)
        statistics["search_date_range"] = f"{start_date} ~ {end_date}"
        
        self.logger.info(f"组合模式搜索完成，找到{len(combined_matches)}个匹配案例")
        
        return {
            "success": True,
            "combination_type": combination_type.upper(),
            "patterns": patterns,
            "matches": combined_matches,
            "statistics": statistics,
            "search_params": {
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "max_results": max_results
            }
        }
    
    def _combine_matches_and(
        self,
        pattern_results: List[Dict],
        max_results: int
    ) -> List[Dict]:
        """AND组合：找出同时满足所有模式的匹配
        
        匹配条件：同一股票在相近日期（±3天）满足所有模式
        """
        if not pattern_results:
            return []
        
        # 以第一个模式的匹配为基准
        base_matches = pattern_results[0]["matches"]
        combined = []
        
        for base_match in base_matches:
            stock_code = base_match["stock_code"]
            match_date = base_match["match_date"]
            match_dt = datetime.strptime(match_date, "%Y%m%d")
            
            # 检查其他模式是否也有匹配
            all_matched = True
            matched_patterns = [pattern_results[0]["pattern"]]
            pattern_data_list = [base_match.get("pattern_data", {})]
            
            for i in range(1, len(pattern_results)):
                pattern_result = pattern_results[i]
                pattern_matches = pattern_result["matches"]
                
                # 在该模式的匹配中查找相同股票且日期相近的
                found = False
                for pm in pattern_matches:
                    if pm["stock_code"] == stock_code:
                        pm_date = pm["match_date"]
                        pm_dt = datetime.strptime(pm_date, "%Y%m%d")
                        
                        # 日期差在3天以内
                        if abs((pm_dt - match_dt).days) <= 3:
                            found = True
                            matched_patterns.append(pattern_result["pattern"])
                            pattern_data_list.append(pm.get("pattern_data", {}))
                            break
                
                if not found:
                    all_matched = False
                    break
            
            # 如果所有模式都匹配，添加到结果
            if all_matched:
                combined.append({
                    "stock_code": stock_code,
                    "match_date": match_date,
                    "matched_patterns": matched_patterns,
                    "pattern_data": pattern_data_list,
                    "match_count": len(matched_patterns)
                })
                
                if len(combined) >= max_results:
                    break
        
        return combined
    
    def _combine_matches_or(
        self,
        pattern_results: List[Dict],
        max_results: int
    ) -> List[Dict]:
        """OR组合：找出满足任一模式的匹配
        
        合并所有模式的匹配，去重
        """
        combined_dict = {}
        
        for pattern_result in pattern_results:
            pattern = pattern_result["pattern"]
            matches = pattern_result["matches"]
            
            for match in matches:
                stock_code = match["stock_code"]
                match_date = match["match_date"]
                key = f"{stock_code}_{match_date}"
                
                if key not in combined_dict:
                    combined_dict[key] = {
                        "stock_code": stock_code,
                        "match_date": match_date,
                        "matched_patterns": [pattern],
                        "pattern_data": [match.get("pattern_data", {})],
                        "match_count": 1
                    }
                else:
                    # 同一股票同一日期匹配多个模式
                    combined_dict[key]["matched_patterns"].append(pattern)
                    combined_dict[key]["pattern_data"].append(match.get("pattern_data", {}))
                    combined_dict[key]["match_count"] += 1
        
        # 转换为列表并限制数量
        combined = list(combined_dict.values())
        
        # 按匹配模式数量排序（匹配更多模式的排在前面）
        combined.sort(key=lambda x: x["match_count"], reverse=True)
        
        return combined[:max_results]
    
    def _calculate_combined_score(self, match: Dict, total_patterns: int) -> float:
        """计算组合模式的匹配度评分
        
        评分规则：
        - 匹配的模式数量占比
        - 各模式的匹配度平均值
        """
        match_count = match.get("match_count", 0)
        pattern_data_list = match.get("pattern_data", [])
        
        # 匹配数量得分（0-0.5）
        count_score = (match_count / total_patterns) * 0.5
        
        # 匹配度得分（0-0.5）
        if pattern_data_list:
            # 从pattern_data中提取匹配度（如果有）
            scores = []
            for pd in pattern_data_list:
                if isinstance(pd, dict) and "match_score" in pd:
                    scores.append(pd["match_score"])
            
            if scores:
                quality_score = (sum(scores) / len(scores)) * 0.5
            else:
                quality_score = 0.5  # 默认满分
        else:
            quality_score = 0.5
        
        total_score = count_score + quality_score
        return round(total_score, 2)


# 便捷函数
def create_pattern_search_engine(
    tushare_token: Optional[str] = None,
    enable_cache: bool = True
) -> PatternSearchEngine:
    """创建模式搜索引擎实例
    
    Args:
        tushare_token: Tushare Pro API Token
        enable_cache: 是否启用缓存
        
    Returns:
        PatternSearchEngine实例
    """
    return PatternSearchEngine(tushare_token=tushare_token, enable_cache=enable_cache)
