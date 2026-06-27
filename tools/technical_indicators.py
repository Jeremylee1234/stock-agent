"""
技术指标计算模块
提供常用技术指标的计算功能，包含完善的数据不足边界情况处理
"""
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np


class InsufficientDataError(Exception):
    """数据不足异常"""
    pass


class TechnicalIndicators:
    """技术指标计算器"""
    
    # 各指标所需的最小数据点数
    MIN_DATA_POINTS = {
        'MACD': 35,  # 需要至少35个数据点才能计算有效的MACD (26 + 9)
        'KDJ': 9,    # 需要至少9个数据点
        'RSI': 15,   # 默认14周期 + 1
        'BOLL': 20,  # 默认20周期
        'MA': 5,     # 最短均线周期
        'OBV': 2,    # 至少需要2个数据点
    }
    
    @staticmethod
    def _validate_data_length(data: Union[pd.Series, pd.DataFrame], 
                              min_length: int, 
                              indicator_name: str) -> Dict:
        """
        验证数据长度是否满足计算要求
        
        Args:
            data: 输入数据
            min_length: 所需最小长度
            indicator_name: 指标名称
            
        Returns:
            包含验证结果的字典，如果数据不足则返回错误信息
        """
        if data is None or len(data) == 0:
            return {
                "error": True,
                "error_code": "INSUFFICIENT_DATA",
                "error_message": f"{indicator_name}计算失败：数据为空",
                "required_length": min_length,
                "actual_length": 0,
                "indicator": indicator_name
            }
        
        actual_length = len(data)
        if actual_length < min_length:
            return {
                "error": True,
                "error_code": "INSUFFICIENT_DATA",
                "error_message": f"{indicator_name}计算失败：数据不足，需要至少{min_length}个数据点，实际只有{actual_length}个",
                "required_length": min_length,
                "actual_length": actual_length,
                "indicator": indicator_name
            }
        
        return {"error": False}
    
    @staticmethod
    def calculate_macd(prices: pd.Series, 
                       fast_period: int = 12,
                       slow_period: int = 26, 
                       signal_period: int = 9) -> Dict:
        """
        计算MACD指标
        
        Args:
            prices: 收盘价序列
            fast_period: 快线周期，默认12
            slow_period: 慢线周期，默认26
            signal_period: 信号线周期，默认9
            
        Returns:
            {
                "success": bool,
                "dif": pd.Series,  # 快线-慢线
                "dea": pd.Series,  # 信号线
                "macd": pd.Series, # MACD柱
                "signal": str,     # "金叉" or "死叉" or "中性"
                "indicator": "MACD"
            }
            或错误信息字典
        """
        # 计算所需最小数据点数
        min_length = slow_period + signal_period
        
        # 验证数据长度
        validation = TechnicalIndicators._validate_data_length(
            prices, min_length, "MACD"
        )
        if validation["error"]:
            return validation
        
        try:
            # 计算EMA
            ema_fast = prices.ewm(span=fast_period, adjust=False).mean()
            ema_slow = prices.ewm(span=slow_period, adjust=False).mean()
            
            # 计算DIF和DEA
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=signal_period, adjust=False).mean()
            macd = 2 * (dif - dea)
            
            # 判断信号
            signal = "中性"
            if len(dif) >= 2 and len(dea) >= 2:
                if not pd.isna(dif.iloc[-1]) and not pd.isna(dea.iloc[-1]) and \
                   not pd.isna(dif.iloc[-2]) and not pd.isna(dea.iloc[-2]):
                    # 金叉：DIF上穿DEA
                    if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                        signal = "金叉"
                    # 死叉：DIF下穿DEA
                    elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                        signal = "死叉"
            
            return {
                "success": True,
                "indicator": "MACD",
                "dif": dif,
                "dea": dea,
                "macd": macd,
                "signal": signal,
                "params": {
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                    "signal_period": signal_period
                }
            }
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"MACD计算过程中发生错误: {str(e)}",
                "indicator": "MACD"
            }
    
    @staticmethod
    def calculate_kdj(high: pd.Series,
                      low: pd.Series,
                      close: pd.Series,
                      period: int = 9,
                      k_smooth: int = 3,
                      d_smooth: int = 3) -> Dict:
        """
        计算KDJ指标
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: RSV周期，默认9
            k_smooth: K值平滑周期，默认3
            d_smooth: D值平滑周期，默认3
            
        Returns:
            {
                "success": bool,
                "k": pd.Series,
                "d": pd.Series,
                "j": pd.Series,
                "signal": str,  # "超买" or "超卖" or "中性"
                "indicator": "KDJ"
            }
            或错误信息字典
        """
        # 验证数据长度
        min_length = period
        for data, name in [(high, "最高价"), (low, "最低价"), (close, "收盘价")]:
            validation = TechnicalIndicators._validate_data_length(
                data, min_length, f"KDJ({name})"
            )
            if validation["error"]:
                return validation
        
        # 验证数据长度一致性
        if not (len(high) == len(low) == len(close)):
            return {
                "error": True,
                "error_code": "DATA_LENGTH_MISMATCH",
                "error_message": "KDJ计算失败：最高价、最低价、收盘价数据长度不一致",
                "indicator": "KDJ"
            }
        
        try:
            # 计算RSV (未成熟随机值)
            low_min = low.rolling(window=period, min_periods=period).min()
            high_max = high.rolling(window=period, min_periods=period).max()
            
            rsv = 100 * (close - low_min) / (high_max - low_min)
            rsv = rsv.fillna(50)  # 初始值设为50
            
            # 计算K值 (RSV的移动平均)
            k = rsv.ewm(alpha=1/k_smooth, adjust=False).mean()
            
            # 计算D值 (K值的移动平均)
            d = k.ewm(alpha=1/d_smooth, adjust=False).mean()
            
            # 计算J值
            j = 3 * k - 2 * d
            
            # 判断信号
            signal = "中性"
            if len(k) > 0 and not pd.isna(k.iloc[-1]):
                k_val = k.iloc[-1]
                d_val = d.iloc[-1] if not pd.isna(d.iloc[-1]) else k_val
                
                if k_val > 80 and d_val > 80:
                    signal = "超买"
                elif k_val < 20 and d_val < 20:
                    signal = "超卖"
            
            return {
                "success": True,
                "indicator": "KDJ",
                "k": k,
                "d": d,
                "j": j,
                "signal": signal,
                "params": {
                    "period": period,
                    "k_smooth": k_smooth,
                    "d_smooth": d_smooth
                }
            }
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"KDJ计算过程中发生错误: {str(e)}",
                "indicator": "KDJ"
            }
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> Dict:
        """
        计算RSI指标 (相对强弱指标)
        
        Args:
            prices: 收盘价序列
            period: 计算周期，默认14
            
        Returns:
            {
                "success": bool,
                "rsi": pd.Series,
                "signal": str,  # "超买" or "超卖" or "中性"
                "indicator": "RSI"
            }
            或错误信息字典
        """
        # 验证数据长度 (需要period+1个数据点来计算差值)
        min_length = period + 1
        validation = TechnicalIndicators._validate_data_length(
            prices, min_length, "RSI"
        )
        if validation["error"]:
            return validation
        
        try:
            # 计算价格变化
            delta = prices.diff()
            
            # 分离上涨和下跌
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # 计算平均涨幅和跌幅
            avg_gain = gain.rolling(window=period, min_periods=period).mean()
            avg_loss = loss.rolling(window=period, min_periods=period).mean()
            
            # 计算RS和RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            # 处理除零情况
            rsi = rsi.fillna(50)
            
            # 判断信号
            signal = "中性"
            if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]):
                rsi_val = rsi.iloc[-1]
                if rsi_val > 70:
                    signal = "超买"
                elif rsi_val < 30:
                    signal = "超卖"
            
            return {
                "success": True,
                "indicator": "RSI",
                "rsi": rsi,
                "signal": signal,
                "params": {
                    "period": period
                }
            }
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"RSI计算过程中发生错误: {str(e)}",
                "indicator": "RSI"
            }
    
    @staticmethod
    def calculate_boll(prices: pd.Series, 
                       period: int = 20,
                       std_dev: float = 2.0) -> Dict:
        """
        计算布林带指标
        
        Args:
            prices: 收盘价序列
            period: 计算周期，默认20
            std_dev: 标准差倍数，默认2.0
            
        Returns:
            {
                "success": bool,
                "upper": pd.Series,  # 上轨
                "middle": pd.Series, # 中轨
                "lower": pd.Series,  # 下轨
                "signal": str,       # "突破上轨" or "突破下轨" or "中性"
                "indicator": "BOLL"
            }
            或错误信息字典
        """
        # 验证数据长度
        min_length = period
        validation = TechnicalIndicators._validate_data_length(
            prices, min_length, "BOLL"
        )
        if validation["error"]:
            return validation
        
        try:
            # 计算中轨 (移动平均)
            middle = prices.rolling(window=period, min_periods=period).mean()
            
            # 计算标准差
            std = prices.rolling(window=period, min_periods=period).std()
            
            # 计算上下轨
            upper = middle + (std_dev * std)
            lower = middle - (std_dev * std)
            
            # 判断信号
            signal = "中性"
            if len(prices) > 0 and len(upper) > 0 and len(lower) > 0:
                if not pd.isna(prices.iloc[-1]) and not pd.isna(upper.iloc[-1]) and not pd.isna(lower.iloc[-1]):
                    current_price = prices.iloc[-1]
                    upper_val = upper.iloc[-1]
                    lower_val = lower.iloc[-1]
                    
                    if current_price > upper_val:
                        signal = "突破上轨"
                    elif current_price < lower_val:
                        signal = "突破下轨"
            
            return {
                "success": True,
                "indicator": "BOLL",
                "upper": upper,
                "middle": middle,
                "lower": lower,
                "signal": signal,
                "params": {
                    "period": period,
                    "std_dev": std_dev
                }
            }
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"BOLL计算过程中发生错误: {str(e)}",
                "indicator": "BOLL"
            }
    
    @staticmethod
    def calculate_ma(prices: pd.Series, periods: List[int] = None) -> Dict:
        """
        计算多条均线
        
        Args:
            prices: 收盘价序列
            periods: 均线周期列表，默认[5, 10, 20, 30, 60, 120, 250]
            
        Returns:
            {
                "success": bool,
                "ma_values": Dict[int, pd.Series],  # {周期: 均线序列}
                "signal": str,  # "多头排列" or "空头排列" or "中性"
                "indicator": "MA",
                "available_periods": List[int],  # 实际可计算的周期
                "skipped_periods": List[int]     # 因数据不足跳过的周期
            }
            或错误信息字典
        """
        if periods is None:
            periods = [5, 10, 20, 30, 60, 120, 250]
        
        # 验证至少有最短周期的数据
        min_period = min(periods) if periods else 5
        validation = TechnicalIndicators._validate_data_length(
            prices, min_period, "MA"
        )
        if validation["error"]:
            return validation
        
        try:
            actual_length = len(prices)
            ma_values = {}
            available_periods = []
            skipped_periods = []
            
            # 计算每条均线
            for period in sorted(periods):
                if actual_length >= period:
                    ma = prices.rolling(window=period, min_periods=period).mean()
                    ma_values[period] = ma
                    available_periods.append(period)
                else:
                    skipped_periods.append(period)
            
            # 判断多空排列 (使用可用的均线)
            signal = "中性"
            if len(available_periods) >= 3:
                # 取最后一个有效值
                last_values = []
                for period in sorted(available_periods)[:3]:  # 只看前3条均线
                    ma_series = ma_values[period]
                    if len(ma_series) > 0 and not pd.isna(ma_series.iloc[-1]):
                        last_values.append(ma_series.iloc[-1])
                
                if len(last_values) >= 3:
                    # 多头排列：短期均线 > 中期均线 > 长期均线
                    if last_values[0] > last_values[1] > last_values[2]:
                        signal = "多头排列"
                    # 空头排列：短期均线 < 中期均线 < 长期均线
                    elif last_values[0] < last_values[1] < last_values[2]:
                        signal = "空头排列"
            
            result = {
                "success": True,
                "indicator": "MA",
                "ma_values": ma_values,
                "signal": signal,
                "available_periods": available_periods,
                "params": {
                    "requested_periods": periods
                }
            }
            
            # 如果有跳过的周期，添加警告信息
            if skipped_periods:
                result["warning"] = f"数据不足，跳过以下周期的均线计算: {skipped_periods}"
                result["skipped_periods"] = skipped_periods
            
            return result
            
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"MA计算过程中发生错误: {str(e)}",
                "indicator": "MA"
            }
    
    @staticmethod
    def calculate_volume_indicators(volume: pd.Series, 
                                    prices: pd.Series) -> Dict:
        """
        计算成交量指标 (OBV和量比)
        
        Args:
            volume: 成交量序列
            prices: 收盘价序列
            
        Returns:
            {
                "success": bool,
                "obv": pd.Series,      # 能量潮指标
                "volume_ratio": float, # 量比 (最近一天相对于平均值)
                "indicator": "VOLUME"
            }
            或错误信息字典
        """
        # 验证数据长度
        min_length = 2  # OBV至少需要2个数据点
        for data, name in [(volume, "成交量"), (prices, "收盘价")]:
            validation = TechnicalIndicators._validate_data_length(
                data, min_length, f"成交量指标({name})"
            )
            if validation["error"]:
                return validation
        
        # 验证数据长度一致性
        if len(volume) != len(prices):
            return {
                "error": True,
                "error_code": "DATA_LENGTH_MISMATCH",
                "error_message": "成交量指标计算失败：成交量和收盘价数据长度不一致",
                "indicator": "VOLUME"
            }
        
        try:
            # 计算OBV (On Balance Volume)
            price_change = prices.diff()
            obv = pd.Series(index=volume.index, dtype=float)
            obv.iloc[0] = volume.iloc[0]
            
            for i in range(1, len(volume)):
                if pd.isna(price_change.iloc[i]):
                    obv.iloc[i] = obv.iloc[i-1]
                elif price_change.iloc[i] > 0:
                    obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                elif price_change.iloc[i] < 0:
                    obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i-1]
            
            # 计算量比 (需要至少5个数据点来计算平均值)
            volume_ratio = None
            if len(volume) >= 5:
                avg_volume = volume.iloc[-6:-1].mean()  # 前5天平均
                if avg_volume > 0 and not pd.isna(volume.iloc[-1]):
                    volume_ratio = round(volume.iloc[-1] / avg_volume, 2)
            
            return {
                "success": True,
                "indicator": "VOLUME",
                "obv": obv,
                "volume_ratio": volume_ratio,
                "params": {}
            }
            
        except Exception as e:
            return {
                "error": True,
                "error_code": "CALCULATION_ERROR",
                "error_message": f"成交量指标计算过程中发生错误: {str(e)}",
                "indicator": "VOLUME"
            }
