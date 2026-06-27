"""公司业务相关智能体"""
from typing import Dict, Any
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from config.settings import DEEPSEEK_API_KEY, DEFAULT_MODEL
from agents.state import AgentState, update_state
from tools.mcp_tools import MCPTools
from tools.search_tools import SearchTools


class BusinessAgent:
    """公司业务相关智能体
    
    功能：
    - 公司背景
    - 交易日历
    - 经济数据
    - 策略介绍
    """
    
    def __init__(self):
        self.model = ChatDeepSeek(
            model_name=DEFAULT_MODEL,
            api_key=DEEPSEEK_API_KEY,
            temperature=0.7,
            extra_body={"reasoning": False}  # 禁用思考模式
        )
        
        # 获取工具
        tools = MCPTools.get_tools() + SearchTools.get_tools()
        
        # 创建ReAct智能体
        self.agent = create_agent(self.model, tools)
        # 可以用记忆(memory)机制，将公司背景信息保存在agent可用的长期消息/记忆中。
        # 这里我们用系统消息(SystemMessage)的方式直接作为agent的第一条memory注入，实现简单易用。
        from langchain_core.messages import SystemMessage

        self.company_background = (
            "GOLDRIVEN（祝音科技）是一家专注于人工智能与金融创新的高科技公司，"
            "致力于为客户提供智能投顾、量化投资、金融数据服务以及自主可控的金融大模型解决方案。"
            "公司凭借强大的研发团队和自主算法能力，为机构及个人客户提供高效、专业、合规的服务。"
            "核心业务包括量化策略开发、金融大数据处理、智能投研平台、金融工具API接口等。"
        )
        # 系统消息注入agent
        self.memory = [SystemMessage(content=self.company_background)]
        # 更新agent初始化，将memory作为对话上下文的一部分
        if hasattr(self.agent, "memory"):
            # 如果agent有memory属性，则赋值（适用于部分LangChain智能体实现）
            self.agent.memory.chat_memory.messages.extend(self.memory)
        else:
            # 若无memory属性，则在调用时用messages参数
            pass
        
        self.system_prompt = """你是GOLDRIVEN（祝音科技）的业务助手，专门回答公司业务相关问题。

            你的职责包括：
            1. **公司背景**：介绍GOLDRIVEN的公司背景、发展历程、核心业务等
            2. **交易日历**：提供交易日历信息，包括节假日、交易时间等
            3. **经济数据**：通过sql相关工具查询和解释经济数据，包括GDP、CPI、PMI等宏观经济指标
            4. **策略介绍**：介绍公司的投资策略、产品策略等

            回答要求：
            - 准确、专业、友好
            - 如果信息不确定，使用工具查询最新信息
            - 对于交易日历和经济数据，使用sql相关工具查询客户需要的数据，并根据查询结果回答用户问题。
            """
    
    async def process(self, state: AgentState) -> AgentState:
        """处理业务相关查询"""
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
        """同步处理（用于非异步环境）"""
        messages = state.get("messages", [])
        user_query = state.get("user_query", "")
        
        prompt = f"{self.system_prompt}\n\n用户问题：{user_query}"
        
        response = self.agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        
        new_messages = response.get("messages", [])
        return update_state(state, new_messages)

if __name__ == "__main__":
    agent = BusinessAgent()
    state = AgentState(messages=[HumanMessage(content="你好，我是GOLDRIVEN的客户，我想查询一下公司的背景信息")])
    response = agent.process_sync(state)
    print(response)