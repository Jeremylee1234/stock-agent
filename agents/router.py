"""路由器 - 根据用户查询决定调用哪个智能体"""
from typing import Literal, Union
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL
from agents.state import AgentState
from langchain.agents import create_agent

class Router:
    """智能体路由器"""
    
    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.3,  # 路由需要更低的温度以保证稳定性
            extra_body={"thinking": {"type": "disabled"}}  # 禁用思考模式
        )
        
        self.router_prompt = """你是GOLDRIVEN（祝音科技）的一个智能路由系统，需要根据用户的问题判断应该调用哪个智能体。

智能体列表：
- business：公司业务、交易日历、宏观经济、策略介绍
- customer：客户账户、收益、回撤、持仓查询
- analysis：股票/黄金/外汇分析、金融新闻
- stock_selection：选股、基本面筛选、财报分析
- backtest：策略回测、收益评估、历史回测、进场条件验证、连板策略、均线策略等一切涉及"回测"、"历史验证"、"策略测试"的问题

请根据用户问题，只返回一个智能体类型名称，不要输出其他内容。"""

    def route(self, state: AgentState) -> Literal["business", "customer", "analysis", "stock_selection", "backtest"]:
        """路由到相应的智能体"""
        user_query = state.get("user_query", "")
        
        if not user_query:
            return "business"  # 默认返回业务智能体
        # 使用LLM进行路由决策
        messages = [
            SystemMessage(content=self.router_prompt),
            HumanMessage(content=f"用户问题：{user_query}\n\n请判断应该调用哪个智能体，只返回智能体类型。")
        ]
        
        response = self.model.invoke(messages)
        agent_type = response.content.strip().lower()
        
        # 验证返回的智能体类型
        valid_types = ["business", "customer", "analysis", "stock_selection", "backtest"]
        if agent_type in valid_types:
            return agent_type
        
        # 如果LLM返回无效类型，使用关键词匹配作为后备
        query_lower = user_query.lower()
        
        # 关键词匹配
        backtest_keywords = ["回测", "历史回测", "策略测试", "进场条件", "连板策略", "胜率", "收益评估",
                             "历史验证", "策略验证", "回踩", "断板", "连板回踩", "买入策略"]
        if any(keyword in query_lower for keyword in backtest_keywords):
            return "backtest"
        elif any(keyword in query_lower for keyword in ["账户", "回撤", "夏普", "客户"]):
            return "customer"
        elif any(keyword in query_lower for keyword in ["选股", "筛选", "基本面", "财报", "季报"]):
            return "stock_selection"
        elif any(keyword in query_lower for keyword in ["分析", "股票", "黄金", "外汇", "新闻"]):
            return "analysis"
        else:
            return "business"  # 默认

