"""搜索工具 - SerpAPI和Bing Search"""
import os
import requests
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from config.settings import SERPAPI_API_KEY, BING_SEARCH_API_KEY, BING_SEARCH_ENDPOINT


class SearchTools:
    """搜索工具类"""
    
    @staticmethod
    @tool
    def serpapi_search(query: str, num_results: int = 10) -> str:
        """使用SerpAPI搜索实时信息
        
        Args:
            query: 搜索查询
            num_results: 返回结果数量
            
        Returns:
            搜索结果文本
        """
        if not SERPAPI_API_KEY:
            return "SerpAPI API key not configured"
        
        try:
            params = {
                "q": query,
                "api_key": SERPAPI_API_KEY,
                "num": num_results,
                "engine": "google"
            }
            response = requests.get("https://serpapi.com/search", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "organic_results" in data:
                for item in data["organic_results"][:num_results]:
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    link = item.get("link", "")
                    results.append(f"标题: {title}\n摘要: {snippet}\n链接: {link}\n")
            
            return "\n".join(results) if results else "未找到相关结果"
        except Exception as e:
            return f"搜索出错: {str(e)}"
    
    @staticmethod
    @tool
    def bing_search(query: str, num_results: int = 10) -> str:
        """使用Bing Search API搜索实时信息
        
        Args:
            query: 搜索查询
            num_results: 返回结果数量
            
        Returns:
            搜索结果文本
        """
        if not BING_SEARCH_API_KEY:
            return "Bing Search API key not configured"
        
        try:
            headers = {
                "Ocp-Apim-Subscription-Key": BING_SEARCH_API_KEY
            }
            params = {
                "q": query,
                "count": num_results,
                "textDecorations": True,
                "textFormat": "HTML"
            }
            response = requests.get(BING_SEARCH_ENDPOINT, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "webPages" in data and "value" in data["webPages"]:
                for item in data["webPages"]["value"][:num_results]:
                    name = item.get("name", "")
                    snippet = item.get("snippet", "")
                    url = item.get("url", "")
                    results.append(f"标题: {name}\n摘要: {snippet}\n链接: {url}\n")
            
            return "\n".join(results) if results else "未找到相关结果"
        except Exception as e:
            return f"搜索出错: {str(e)}"
    
    @staticmethod
    def get_tools() -> List:
        """获取所有搜索工具"""
        return [
            SearchTools.serpapi_search,
            SearchTools.bing_search
        ]

