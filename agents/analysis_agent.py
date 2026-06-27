"""股票/黄金/外汇/金融新闻分析智能体"""
from typing import Dict, Any
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL
from agents.state import AgentState, update_state
from tools.mcp_tools import MCPTools
from tools.search_tools import SearchTools
from tools.financial_data_tools import FinancialDataTools


class AnalysisAgent:
    """金融分析智能体
    
    功能：
    - 股票分析（通过MCP接口获取数据）
    - 黄金分析
    - 外汇分析
    - 金融新闻分析（通过SerpAPI或Bing Search）
    """
    
    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.7,
            extra_body={"reasoning": False}  # 禁用思考模式
        )
        
        # 获取所有相关工具
        tools = (
            MCPTools.get_tools() + 
            SearchTools.get_tools() + 
            FinancialDataTools.get_tools()
        )
        
        # 创建ReAct智能体
        self.agent = create_agent(self.model, tools)
        
        self.system_prompt = """你是GOLDRIVEN的金融分析专家，专门进行股票、黄金、外汇和金融新闻的分析。

                    你的职责包括：
                    1. **股票分析**：
                    - 使用MCP接口或Wind/JoinQuant接口获取股票实时和历史数据
                    - 分析股票价格走势、技术指标、基本面
                    - 提供投资建议和风险评估

                    2. **黄金分析**：
                    - 获取黄金价格数据
                    - 分析黄金市场趋势
                    - 提供黄金投资建议

                    3. **外汇分析**：
                    - 获取外汇汇率数据
                    - 分析汇率走势
                    - 提供外汇市场观点

                    4. **金融新闻分析**：
                    - 使用SerpAPI或Bing Search获取最新金融新闻
                    - 分析新闻对市场的影响
                    - 提供新闻解读和投资建议

                    分析要求：
                    - 数据驱动：优先使用实时数据进行分析
                    - 多维度：结合技术面、基本面、消息面
                    - 风险提示：始终提醒投资风险
                    - 客观专业：基于数据给出客观分析，避免主观臆断
                    """
    
    async def process(self, state: AgentState) -> AgentState:
        """处理金融分析查询"""
        messages = state.get("messages", [])
        user_query = state.get("user_query", "")
        
        # 构建提示词
        prompt = f"{self.system_prompt}\n\n用户问题：{user_query}"
        
        # 调用智能体
        response = await self.agent.ainvoke({
            "messages": [HumanMessage(content=prompt)]
        })
        
        # 更新状态
        new_messages = response.get("messages", [])
        return update_state(state, new_messages)
    
    def process_sync(self, state: AgentState) -> AgentState:
        """同步处理"""
        user_query = state.get("user_query", "")
        
        prompt = f"{self.system_prompt}\n\n用户问题：{user_query}"
        
        response = self.agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        
        new_messages = response.get("messages", [])
        return update_state(state, new_messages)

