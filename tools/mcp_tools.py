"""MCP工具 - 万得或其他金融服务商的MCP接口"""
import requests
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from config.settings import MCP_SERVER_URL


class MCPTools:
    """MCP工具类"""
    
    @staticmethod
    @tool
    def mcp_get_stock_data(symbol: str, data_type: str = "realtime") -> str:
        """通过MCP接口获取股票数据
        
        Args:
            symbol: 股票代码
            data_type: 数据类型（realtime/historical）
            
        Returns:
            股票数据JSON字符串
        """
        if not MCP_SERVER_URL:
            return "MCP Server URL not configured"
        
        try:
            url = f"{MCP_SERVER_URL}/stock/data"
            params = {
                "symbol": symbol,
                "type": data_type
            }
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"获取MCP股票数据出错: {str(e)}"
    
    @staticmethod
    @tool
    def mcp_get_market_data(market: str = "A股") -> str:
        """通过MCP接口获取市场数据
        
        Args:
            market: 市场类型（A股/港股/美股等）
            
        Returns:
            市场数据JSON字符串
        """
        if not MCP_SERVER_URL:
            return "MCP Server URL not configured"
        
        try:
            url = f"{MCP_SERVER_URL}/market/data"
            params = {"market": market}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"获取MCP市场数据出错: {str(e)}"
    
    @staticmethod
    @tool
    def mcp_get_economic_calendar(date: str = None) -> str:
        """通过MCP接口获取经济日历
        
        Args:
            date: 日期（格式：YYYYMMDD），默认为今天
            
        Returns:
            经济日历数据JSON字符串
        """
        if not MCP_SERVER_URL:
            return "MCP Server URL not configured"
        
        try:
            url = f"{MCP_SERVER_URL}/economic/calendar"
            params = {"date": date} if date else {}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"获取经济日历出错: {str(e)}"
    
    @staticmethod
    def get_tools() -> List:
        """获取所有MCP工具"""
        return [
            MCPTools.mcp_get_stock_data,
            MCPTools.mcp_get_market_data,
            MCPTools.mcp_get_economic_calendar
        ]

