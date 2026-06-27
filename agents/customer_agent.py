"""客户信息智能体"""
from typing import Dict, Any
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL
from agents.state import AgentState, update_state
from tools.database_tools import DatabaseTools


class CustomerAgent:
    """客户信息智能体
    
    功能：
    - 客户账户信息
    - 账户近期收益
    - 历史收益率/夏普/回撤等指标计算
    """
    
    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.7,
            extra_body={"reasoning": False}  # 禁用思考模式
        )
        
        # 获取数据库工具
        tools = DatabaseTools.get_tools()
        
        # 创建ReAct智能体
        self.agent = create_react_agent(self.model, tools)
        
        self.system_prompt = """你是GOLDRIVEN的客户服务助手，专门处理客户账户相关信息查询。

你的职责包括：
1. **客户账户信息**：查询客户的账户余额、总资产、可用资金等
2. **账户近期收益**：查询客户最近一段时间的收益情况
3. **性能指标计算**：计算客户的历史收益率、夏普比率、最大回撤、胜率等指标

重要安全要求：
- **严格保密**：只能查询当前登录客户的账户信息
- **禁止泄露**：绝对不能泄露其他客户的任何信息
- **权限验证**：每次查询前必须验证客户ID是否匹配

使用工具时，确保customer_id参数正确。
"""
    
    async def process(self, state: AgentState) -> AgentState:
        """处理客户信息查询"""
        messages = state.get("messages", [])
        user_query = state.get("user_query", "")
        customer_id = state.get("customer_id")
        
        if not customer_id:
            # 如果没有客户ID，返回提示
            error_msg = "需要客户ID才能查询账户信息，请先登录或提供客户ID"
            return update_state(state, [AIMessage(content=error_msg)])
        
        # 构建提示词
        prompt = f"""{self.system_prompt}

                当前客户ID: {customer_id}

                用户问题：{user_query}

                注意：所有查询必须使用customer_id={customer_id}，不能查询其他客户的信息。
                """
        
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
        customer_id = state.get("customer_id")
        
        if not customer_id:
            error_msg = "需要客户ID才能查询账户信息，请先登录或提供客户ID"
            return update_state(state, [AIMessage(content=error_msg)])
        
        prompt = f"""{self.system_prompt}

当前客户ID: {customer_id}

用户问题：{user_query}

注意：所有查询必须使用customer_id={customer_id}，不能查询其他客户的信息。
"""
        
        response = self.agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        
        new_messages = response.get("messages", [])
        return update_state(state, new_messages)

