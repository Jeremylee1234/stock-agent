"""LangGraph主图 - 多智能体状态机"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agents.state import AgentState
from agents.router import Router
from agents import BusinessAgent, CustomerAgent, AnalysisAgent
from agents.backtest_agent import BacktestAgent


class MultiAgentGraph:
    """多智能体图"""
    
    def __init__(self):
        # 初始化路由器
        self.router = Router()
        
        # 初始化各个智能体
        self.business_agent = BusinessAgent()
        self.customer_agent = CustomerAgent()
        self.analysis_agent = AnalysisAgent()
        self.backtest_agent = BacktestAgent()
        # self.stock_selection_agent = StockSelectionAgent()
        
        # 构建图
        self.graph = self._build_graph()
        
        # 添加检查点（用于对话历史）
        self.memory = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.memory)
    
    def _build_graph(self) -> StateGraph:
        """构建LangGraph状态机"""
        workflow = StateGraph(AgentState)
        
        # 添加节点
        workflow.add_node("router", self._route_node)
        workflow.add_node("business", self._business_node)
        workflow.add_node("customer", self._customer_node)
        workflow.add_node("analysis", self._analysis_node)
        workflow.add_node("stock_selection", self._stock_selection_node)
        workflow.add_node("backtest", self._backtest_node)
        
        # 设置入口
        workflow.set_entry_point("router")
        
        # 添加条件边（从router到各个智能体）
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "business": "business",
                "customer": "customer",
                "analysis": "analysis",
                "stock_selection": "stock_selection",
                "backtest": "backtest",
            }
        )
        
        # 所有智能体节点都连接到END
        workflow.add_edge("business", END)
        workflow.add_edge("customer", END)
        workflow.add_edge("analysis", END)
        workflow.add_edge("stock_selection", END)
        workflow.add_edge("backtest", END)
        
        return workflow
    
    def _route_node(self, state: AgentState) -> AgentState:
        """路由节点"""
        agent_type = self.router.route(state)
        state["agent_type"] = agent_type
        state["current_agent"] = agent_type
        return state
    
    def _route_decision(self, state: AgentState) -> str:
        """路由决策"""
        return state.get("agent_type", "business")
    
    def _business_node(self, state: AgentState) -> AgentState:
        """业务智能体节点"""
        return self.business_agent.process_sync(state)
    
    def _customer_node(self, state: AgentState) -> AgentState:
        """客户信息智能体节点"""
        return self.customer_agent.process_sync(state)
    
    def _analysis_node(self, state: AgentState) -> AgentState:
        """金融分析智能体节点"""
        return self.analysis_agent.process_sync(state)
    
    def _stock_selection_node(self, state: AgentState) -> AgentState:
        """选股智能体节点"""
        return self.stock_selection_agent.process_sync(state)
    
    def _backtest_node(self, state: AgentState) -> AgentState:
        """回测智能体节点（同步包装）"""
        import asyncio
        query = state.get("user_query", "")
        thread_id = state.get("customer_id") or "default"
        config = {"configurable": {"thread_id": thread_id}}

        async def _collect():
            events = []
            async for evt in self.backtest_agent.astream_with_events(query, config):
                events.append(evt)
            return events

        try:
            loop = asyncio.get_event_loop()
            events = loop.run_until_complete(_collect())
        except RuntimeError:
            events = asyncio.run(_collect())

        # 提取 final_answer 写入 state
        final_answer = ""
        for evt in events:
            if evt.get("event_type") == "final_answer":
                final_answer = evt.get("data", {}).get("content", "")
                break

        from langchain_core.messages import AIMessage
        from agents.state import update_state
        return update_state(state, [AIMessage(content=final_answer)])
    
    def invoke(self, query: str, customer_id: str = None, config: dict = None):
        """调用图处理查询"""
        initial_state = {
            "messages": [],
            "user_query": query,
            "customer_id": customer_id,
            "agent_type": None,
            "current_agent": None,
            "context": {},
            "results": {}
        }
        
        if config is None:
            config = {"configurable": {"thread_id": "default"}}
        
        result = self.app.invoke(initial_state, config)
        return result
    
    async def ainvoke(self, query: str, customer_id: str = None, config: dict = None):
        """异步调用图处理查询"""
        initial_state = {
            "messages": [],
            "user_query": query,
            "user_id": customer_id,
            "agent_type": None,
            "current_agent": None,
            "context": {},
            "results": {}
        }
        
        if config is None:
            config = {"configurable": {"thread_id": "default"}}
        
        result = await self.app.ainvoke(initial_state, config)
        return result

