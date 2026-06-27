"""状态定义"""
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph.message import AnyMessage, add_messages


class AgentState(TypedDict):
    """多智能体系统的状态"""
    messages: List[AnyMessage]
    current_agent: Optional[str]  # 当前执行的智能体
    user_query: str  # 用户查询
    agent_type: Optional[str]  # 智能体类型：business, customer, analysis, stock_selection
    context: Dict[str, Any]  # 上下文信息
    results: Dict[str, Any]  # 各智能体的结果
    customer_id: Optional[str]  # 客户ID（用于客户信息查询）
    steps: List[Dict[str, Any]]  # 可展示的分析/思考步骤（用于流式UI）


def update_state(state: AgentState, new_messages: List[AnyMessage]) -> AgentState:
    """更新状态中的消息"""
    return {
        **state,
        "messages": add_messages(state.get("messages", []), new_messages)
    }

