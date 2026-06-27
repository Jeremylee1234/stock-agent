"""
数据验证模块

提供股票数据的验证和异常检测功能：
- DataValidator: 数据验证器类
- 股票数据验证方法
- 异常检测方法
- 数据合理性检查
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataValidator:
    """
    数据验证器
    
    提供以下功能：
    - 股票价格数据验证
    - 日期格式验证
    - 数据完整性检查
    - 异常检测（价格异常波动、成交量异常等）
    - 数据合理性验证
    """
    
    def __init__(self):
        """初始化数据验证器"""
        self.logger = logging.getLogger(__name__)
    
    def validate_stock_price_data(
        self,
        data: Union[Dict[str, Any], pd.DataFrame],
        required_fields: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        验证股票价格数据
        
        Args:
            data: 股票数据（字典或DataFrame）
            required_fields: 必需字段列表，默认为 ["time", "close", "open", "high", "low"]
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        if required_fields is None:
            required_fields = ["time", "close", "open", "high", "low"]
        
        # 检查数据是否为空
        if data is None:
            return False, "数据为空"
        
        if isinstance(data, dict):
            # 检查是否包含错误信息
            if "error" in data:
                return False, f"数据包含错误: {data.get('error')}"
            
            # 检查必需字段
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return False, f"缺少必需字段: {', '.join(missing_fields)}"
            
            # 验证数据合理性
            return self._validate_price_values(data)
        
        elif isinstance(data, pd.DataFrame):
            # 检查DataFrame是否为空
            if data.empty:
                return False, "DataFrame为空"
            
            # 检查必需列
            missing_columns = [col for col in required_fields if col not in data.columns]
            if missing_columns:
                return False, f"缺少必需列: {', '.join(missing_columns)}"
            
            # 验证数据合理性
            return self._validate_dataframe_prices(data)
        
        else:
            return False, f"不支持的数据类型: {type(data).__name__}"
    
    def _validate_price_values(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证价格数据的合理性
        
        Args:
            data: 包含价格数据的字典
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        # 检查价格字段
        price_fields = ["close", "open", "high", "low"]
        
        for field in price_fields:
            if field not in data:
                continue
            
            values = data[field]
            
            # 转换为列表（如果是Series或其他可迭代对象）
            if isinstance(values, pd.Series):
                values = values.tolist()
            elif not isinstance(values, (list, tuple)):
                values = [values]
            
            # 检查负值
            for i, price in enumerate(values):
                if price is not None and not pd.isna(price):
                    if price < 0:
                        return False, f"{field}字段包含负值: 索引{i}的值为{price}"
                    
                    # 检查异常大的值（可能是数据错误）
                    if price > 1000000:
                        self.logger.warning(
                            f"{field}字段包含异常大的值: 索引{i}的值为{price}"
                        )
        
        # 验证高开低收的关系
        if all(field in data for field in ["high", "low", "open", "close"]):
            high = data["high"]
            low = data["low"]
            open_price = data["open"]
            close = data["close"]
            
            # 转换为列表
            if isinstance(high, pd.Series):
                high = high.tolist()
                low = low.tolist()
                open_price = open_price.tolist()
                close = close.tolist()
            elif not isinstance(high, (list, tuple)):
                high = [high]
                low = [low]
                open_price = [open_price]
                close = [close]
            
            # 检查每个数据点
            for i in range(len(high)):
                h, l, o, c = high[i], low[i], open_price[i], close[i]
                
                # 跳过None或NaN值
                if any(pd.isna(v) or v is None for v in [h, l, o, c]):
                    continue
                
                # 最高价应该 >= 最低价
                if h < l:
                    return False, f"索引{i}: 最高价({h}) < 最低价({l})"
                
                # 开盘价和收盘价应该在最高价和最低价之间
                if not (l <= o <= h):
                    self.logger.warning(
                        f"索引{i}: 开盘价({o})不在最高价({h})和最低价({l})之间"
                    )
                
                if not (l <= c <= h):
                    self.logger.warning(
                        f"索引{i}: 收盘价({c})不在最高价({h})和最低价({l})之间"
                    )
        
        return True, "验证通过"
    
    def _validate_dataframe_prices(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        验证DataFrame中的价格数据
        
        Args:
            df: 包含价格数据的DataFrame
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        # 检查价格列
        price_columns = ["close", "open", "high", "low"]
        
        for col in price_columns:
            if col not in df.columns:
                continue
            
            # 检查负值
            negative_mask = df[col] < 0
            if negative_mask.any():
                negative_indices = df[negative_mask].index.tolist()
                return False, f"{col}列包含负值，索引: {negative_indices[:5]}"
            
            # 检查异常大的值
            extreme_mask = df[col] > 1000000
            if extreme_mask.any():
                extreme_indices = df[extreme_mask].index.tolist()
                self.logger.warning(
                    f"{col}列包含异常大的值，索引: {extreme_indices[:5]}"
                )
        
        # 验证高开低收的关系
        if all(col in df.columns for col in ["high", "low", "open", "close"]):
            # 最高价 >= 最低价
            invalid_hl = df[df["high"] < df["low"]]
            if not invalid_hl.empty:
                return False, f"发现{len(invalid_hl)}条记录的最高价 < 最低价"
            
            # 开盘价和收盘价应该在最高价和最低价之间
            invalid_open = df[(df["open"] < df["low"]) | (df["open"] > df["high"])]
            if not invalid_open.empty:
                self.logger.warning(
                    f"发现{len(invalid_open)}条记录的开盘价不在最高价和最低价之间"
                )
            
            invalid_close = df[(df["close"] < df["low"]) | (df["close"] > df["high"])]
            if not invalid_close.empty:
                self.logger.warning(
                    f"发现{len(invalid_close)}条记录的收盘价不在最高价和最低价之间"
                )
        
        return True, "验证通过"
    
    def validate_date_format(
        self,
        date_str: str,
        date_format: str = "%Y%m%d"
    ) -> Tuple[bool, str]:
        """
        验证日期格式
        
        Args:
            date_str: 日期字符串
            date_format: 期望的日期格式，默认为 "%Y%m%d"
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        try:
            datetime.strptime(date_str, date_format)
            return True, "日期格式有效"
        except ValueError as e:
            return False, f"无效的日期格式: {date_str}，应为{date_format}，错误: {str(e)}"
        except Exception as e:
            return False, f"日期验证失败: {str(e)}"
    
    def validate_stock_code(self, stock_code: str) -> Tuple[bool, str]:
        """
        验证股票代码格式
        
        Args:
            stock_code: 股票代码
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        if not stock_code:
            return False, "股票代码为空"
        
        # 移除可能的空格
        stock_code = stock_code.strip()
        
        # A股股票代码通常是6位数字
        if len(stock_code) == 6 and stock_code.isdigit():
            return True, "股票代码格式有效"
        
        # 也可能包含市场前缀（如 SH600519, SZ000001）
        if len(stock_code) == 8 and stock_code[:2].upper() in ["SH", "SZ"]:
            if stock_code[2:].isdigit():
                return True, "股票代码格式有效"
        
        return False, f"无效的股票代码格式: {stock_code}"
    
    def detect_anomalies(
        self,
        data: pd.DataFrame,
        price_threshold: float = 0.2,
        volume_multiplier: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        检测数据异常
        
        Args:
            data: 包含股票数据的DataFrame
            price_threshold: 价格异常波动阈值（默认20%）
            volume_multiplier: 成交量异常倍数（默认5倍）
        
        Returns:
            异常列表，每个异常包含类型、日期和详细信息
        """
        anomalies = []
        
        if data.empty:
            return anomalies
        
        # 检测价格异常波动（单日涨跌幅超过阈值）
        if "close" in data.columns and len(data) > 1:
            try:
                returns = data["close"].pct_change()
                extreme_moves = returns[abs(returns) > price_threshold]
                
                if not extreme_moves.empty:
                    anomalies.append({
                        "type": "extreme_price_movement",
                        "description": f"检测到{len(extreme_moves)}个交易日的价格异常波动（超过{price_threshold*100}%）",
                        "dates": extreme_moves.index.tolist(),
                        "values": extreme_moves.tolist(),
                        "severity": "high" if abs(extreme_moves).max() > 0.3 else "medium"
                    })
                    
                    self.logger.warning(
                        f"检测到价格异常波动: {len(extreme_moves)}个交易日"
                    )
            except Exception as e:
                self.logger.error(f"价格异常检测失败: {e}")
        
        # 检测成交量异常（超过平均值的N倍）
        if "volume" in data.columns and len(data) > 1:
            try:
                avg_volume = data["volume"].mean()
                
                if avg_volume > 0:
                    extreme_volume = data[data["volume"] > avg_volume * volume_multiplier]
                    
                    if not extreme_volume.empty:
                        anomalies.append({
                            "type": "extreme_volume",
                            "description": f"检测到{len(extreme_volume)}个交易日的成交量异常（超过平均值{volume_multiplier}倍）",
                            "dates": extreme_volume.index.tolist(),
                            "avg_volume": float(avg_volume),
                            "max_volume": float(extreme_volume["volume"].max()),
                            "severity": "medium"
                        })
                        
                        self.logger.warning(
                            f"检测到成交量异常: {len(extreme_volume)}个交易日"
                        )
            except Exception as e:
                self.logger.error(f"成交量异常检测失败: {e}")
        
        # 检测连续涨停或跌停
        if "close" in data.columns and len(data) > 1:
            try:
                returns = data["close"].pct_change()
                
                # 涨停（约10%）
                limit_up = returns > 0.095
                consecutive_limit_up = self._find_consecutive_days(limit_up)
                
                if consecutive_limit_up:
                    anomalies.append({
                        "type": "consecutive_limit_up",
                        "description": f"检测到连续涨停",
                        "sequences": consecutive_limit_up,
                        "severity": "high"
                    })
                    
                    self.logger.info(f"检测到连续涨停: {consecutive_limit_up}")
                
                # 跌停（约-10%）
                limit_down = returns < -0.095
                consecutive_limit_down = self._find_consecutive_days(limit_down)
                
                if consecutive_limit_down:
                    anomalies.append({
                        "type": "consecutive_limit_down",
                        "description": f"检测到连续跌停",
                        "sequences": consecutive_limit_down,
                        "severity": "high"
                    })
                    
                    self.logger.info(f"检测到连续跌停: {consecutive_limit_down}")
            except Exception as e:
                self.logger.error(f"涨跌停检测失败: {e}")
        
        # 检测数据缺失
        if data.isnull().any().any():
            null_counts = data.isnull().sum()
            null_columns = null_counts[null_counts > 0].to_dict()
            
            anomalies.append({
                "type": "missing_data",
                "description": f"检测到数据缺失",
                "columns": null_columns,
                "severity": "low"
            })
            
            self.logger.warning(f"检测到数据缺失: {null_columns}")
        
        return anomalies
    
    def _find_consecutive_days(
        self,
        condition: pd.Series,
        min_consecutive: int = 2
    ) -> List[Dict[str, Any]]:
        """
        查找满足条件的连续交易日
        
        Args:
            condition: 布尔Series，True表示满足条件
            min_consecutive: 最小连续天数
        
        Returns:
            连续序列列表
        """
        sequences = []
        current_sequence = []
        
        for idx, value in condition.items():
            if value:
                current_sequence.append(idx)
            else:
                if len(current_sequence) >= min_consecutive:
                    sequences.append({
                        "start_date": current_sequence[0],
                        "end_date": current_sequence[-1],
                        "days": len(current_sequence)
                    })
                current_sequence = []
        
        # 检查最后一个序列
        if len(current_sequence) >= min_consecutive:
            sequences.append({
                "start_date": current_sequence[0],
                "end_date": current_sequence[-1],
                "days": len(current_sequence)
            })
        
        return sequences
    
    def validate_technical_indicator_result(
        self,
        result: Dict[str, Any],
        indicator_type: str
    ) -> Tuple[bool, str]:
        """
        验证技术指标计算结果
        
        Args:
            result: 技术指标计算结果
            indicator_type: 指标类型（如 "MACD", "KDJ", "RSI"）
        
        Returns:
            (is_valid, message): 验证结果和消息
        """
        if not result:
            return False, "结果为空"
        
        # 检查必需字段
        if "values" not in result:
            return False, "缺少values字段"
        
        # 根据指标类型验证特定字段
        if indicator_type == "RSI":
            if "rsi" not in result["values"]:
                return False, "RSI结果缺少rsi字段"
            
            # 验证RSI值范围（0-100）
            rsi_values = result["values"]["rsi"]
            if isinstance(rsi_values, pd.Series):
                valid_rsi = rsi_values.dropna()
                if not valid_rsi.empty:
                    if (valid_rsi < 0).any() or (valid_rsi > 100).any():
                        return False, "RSI值超出范围[0, 100]"
        
        elif indicator_type == "MACD":
            required_fields = ["dif", "dea", "macd"]
            missing = [f for f in required_fields if f not in result["values"]]
            if missing:
                return False, f"MACD结果缺少字段: {', '.join(missing)}"
        
        elif indicator_type == "KDJ":
            required_fields = ["k", "d", "j"]
            missing = [f for f in required_fields if f not in result["values"]]
            if missing:
                return False, f"KDJ结果缺少字段: {', '.join(missing)}"
        
        elif indicator_type == "BOLL":
            required_fields = ["upper", "middle", "lower"]
            missing = [f for f in required_fields if f not in result["values"]]
            if missing:
                return False, f"BOLL结果缺少字段: {', '.join(missing)}"
            
            # 验证布林带轨道关系：上轨 >= 中轨 >= 下轨
            upper = result["values"]["upper"]
            middle = result["values"]["middle"]
            lower = result["values"]["lower"]
            
            if isinstance(upper, pd.Series):
                valid_indices = ~(upper.isna() | middle.isna() | lower.isna())
                if valid_indices.any():
                    if not (upper[valid_indices] >= middle[valid_indices]).all():
                        return False, "布林带上轨应该 >= 中轨"
                    if not (middle[valid_indices] >= lower[valid_indices]).all():
                        return False, "布林带中轨应该 >= 下轨"
        
        return True, "验证通过"
    
    def check_data_completeness(
        self,
        data: pd.DataFrame,
        required_columns: List[str],
        min_rows: int = 1
    ) -> Tuple[bool, str]:
        """
        检查数据完整性
        
        Args:
            data: 数据DataFrame
            required_columns: 必需的列
            min_rows: 最小行数
        
        Returns:
            (is_complete, message): 完整性检查结果和消息
        """
        if data is None or data.empty:
            return False, "数据为空"
        
        if len(data) < min_rows:
            return False, f"数据行数不足，需要至少{min_rows}行，实际{len(data)}行"
        
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            return False, f"缺少必需列: {', '.join(missing_columns)}"
        
        # 检查关键列的缺失值比例
        for col in required_columns:
            null_ratio = data[col].isnull().sum() / len(data)
            if null_ratio > 0.5:
                return False, f"列{col}的缺失值比例过高: {null_ratio:.1%}"
        
        return True, "数据完整"


# 导出的公共接口
__all__ = ['DataValidator']
