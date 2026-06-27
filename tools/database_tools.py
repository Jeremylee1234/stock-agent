"""数据库工具 - 客户信息查询"""
import pymysql
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool
from config.settings import DATABASE_URL
import pandas as pd
import numpy as np


class DatabaseTools:
    """数据库工具类 - 用于查询客户信息"""
    
    @staticmethod
    def _get_connection():
        """获取数据库连接"""
        if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
            # SQLite连接
            db_path = DATABASE_URL.replace("sqlite:///", "")
            return sqlite3.connect(db_path)
        # 这里可以添加其他数据库连接（PostgreSQL, MySQL等）
        return None
    
    @staticmethod
    @tool
    def get_customer_account_info(customer_id: str) -> str:
        """获取客户账户信息
        
        Args:
            customer_id: 客户ID
            
        Returns:
            客户账户信息JSON字符串
        """
        try:
            conn = DatabaseTools._get_connection()
            if not conn:
                return "数据库未配置"
            
            query = """
                SELECT account_id, balance, total_assets, available_cash
                FROM accounts
                WHERE customer_id = ?
            """
            df = pd.read_sql_query(query, conn, params=(customer_id,))
            conn.close()
            
            if df.empty:
                return f"未找到客户 {customer_id} 的账户信息"
            
            return df.to_json(orient="records", force_ascii=False)
        except Exception as e:
            return f"查询账户信息出错: {str(e)}"
    
    @staticmethod
    @tool
    def get_customer_recent_returns(customer_id: str, days: int = 30) -> str:
        """获取客户近期收益
        
        Args:
            customer_id: 客户ID
            days: 查询天数，默认30天
            
        Returns:
            近期收益数据JSON字符串
        """
        try:
            conn = DatabaseTools._get_connection()
            if not conn:
                return "数据库未配置"
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            query = """
                SELECT date, daily_return, cumulative_return
                FROM account_returns
                WHERE customer_id = ? AND date >= ? AND date <= ?
                ORDER BY date
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(customer_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            )
            conn.close()
            
            if df.empty:
                return f"未找到客户 {customer_id} 的近期收益数据"
            
            return df.to_json(orient="records", force_ascii=False, date_format="iso")
        except Exception as e:
            return f"查询近期收益出错: {str(e)}"
    
    @staticmethod
    @tool
    def calculate_performance_metrics(customer_id: str, start_date: str = None, end_date: str = None) -> str:
        """计算客户历史收益率、夏普比率、最大回撤等指标
        
        Args:
            customer_id: 客户ID
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            
        Returns:
            性能指标JSON字符串
        """
        try:
            conn = DatabaseTools._get_connection()
            if not conn:
                return "数据库未配置"
            
            query = """
                SELECT date, daily_return, cumulative_return
                FROM account_returns
                WHERE customer_id = ?
            """
            params = [customer_id]
            
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            
            query += " ORDER BY date"
            
            df = pd.read_sql_query(query, conn, params=tuple(params))
            conn.close()
            
            if df.empty:
                return f"未找到客户 {customer_id} 的收益数据"
            
            # 计算指标
            returns = df['daily_return'].values
            
            # 年化收益率
            total_return = df['cumulative_return'].iloc[-1] if len(df) > 0 else 0
            days = len(df)
            annualized_return = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0
            
            # 年化波动率
            volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
            
            # 夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03
            sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
            
            # 最大回撤
            cumulative = df['cumulative_return'].values
            running_max = np.maximum.accumulate(cumulative)
            drawdown = cumulative - running_max
            max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
            
            # 胜率
            win_rate = np.sum(returns > 0) / len(returns) if len(returns) > 0 else 0
            
            metrics = {
                "customer_id": customer_id,
                "total_return": float(total_return),
                "annualized_return": float(annualized_return),
                "volatility": float(volatility),
                "sharpe_ratio": float(sharpe_ratio),
                "max_drawdown": float(max_drawdown),
                "win_rate": float(win_rate),
                "period_days": int(days)
            }
            
            import json
            return json.dumps(metrics, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"计算性能指标出错: {str(e)}"
    
    @staticmethod
    def get_tools() -> List:
        """获取所有数据库工具"""
        return [
            DatabaseTools.get_customer_account_info,
            DatabaseTools.get_customer_recent_returns,
            DatabaseTools.calculate_performance_metrics
        ]

