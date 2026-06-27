"""SSE事件类型定义和验证

定义所有支持的SSE事件类型及其数据结构。
"""
from typing import Literal, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# 事件类型常量
EVENT_WORKFLOW_START = "workflow_start"
EVENT_STAGE_START = "stage_start"
EVENT_STAGE_PROGRESS = "stage_progress"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_ANALYSIS_CHUNK = "analysis_chunk"
EVENT_STAGE_COMPLETE = "stage_complete"
EVENT_FINAL_ANSWER = "final_answer"
EVENT_ERROR = "error"
EVENT_WORKFLOW_COMPLETE = "workflow_complete"
EVENT_EXECUTION_PLAN = "execution_plan"  # 额外的执行计划事件

# 所有支持的事件类型
SUPPORTED_EVENT_TYPES = {
    EVENT_WORKFLOW_START,
    EVENT_STAGE_START,
    EVENT_STAGE_PROGRESS,
    EVENT_TOOL_CALL,
    EVENT_TOOL_RESULT,
    EVENT_ANALYSIS_CHUNK,
    EVENT_STAGE_COMPLETE,
    EVENT_FINAL_ANSWER,
    EVENT_ERROR,
    EVENT_WORKFLOW_COMPLETE,
    EVENT_EXECUTION_PLAN,
}

# 工作流阶段常量
STAGE_ANALYZE_QUESTION = "analyze_question"
STAGE_COLLECT_DATA = "collect_data"
STAGE_ANALYZE_DATA = "analyze_data"
STAGE_GENERATE_ANSWER = "generate_answer"
STAGE_EXECUTION_PLAN = "execution_plan"

# 所有工作流阶段
WORKFLOW_STAGES = {
    STAGE_ANALYZE_QUESTION,
    STAGE_COLLECT_DATA,
    STAGE_ANALYZE_DATA,
    STAGE_GENERATE_ANSWER,
}


class WorkflowStartData(BaseModel):
    """工作流开始事件数据"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户查询")
    timestamp: str = Field(..., description="时间戳")


class StageStartData(BaseModel):
    """阶段开始事件数据"""
    stage: str = Field(..., description="阶段名称")
    title: str = Field(..., description="阶段标题")
    description: Optional[str] = Field(None, description="阶段描述")
    timestamp: str = Field(..., description="时间戳")


class StageProgressData(BaseModel):
    """阶段进度事件数据"""
    stage: str = Field(..., description="阶段名称")
    progress: Dict[str, Any] = Field(..., description="进度信息")
    timestamp: str = Field(..., description="时间戳")


class ToolCallData(BaseModel):
    """工具调用事件数据"""
    tool_name: str = Field(..., description="工具名称")
    tool_id: str = Field(..., description="工具调用ID")
    args: Dict[str, Any] = Field(..., description="工具参数")
    timestamp: str = Field(..., description="时间戳")


class ToolResultData(BaseModel):
    """工具结果事件数据"""
    tool_name: str = Field(..., description="工具名称")
    tool_id: str = Field(..., description="工具调用ID")
    status: Literal["success", "error"] = Field(..., description="执行状态")
    summary: str = Field(..., description="结果摘要")
    data_id: Optional[str] = Field(None, description="数据ID（如果数据被压缩）")
    error: Optional[str] = Field(None, description="错误信息（如果失败）")
    timestamp: str = Field(..., description="时间戳")


class AnalysisChunkData(BaseModel):
    """分析内容增量事件数据"""
    stage: str = Field(..., description="阶段名称")
    content: str = Field(..., description="分析内容")
    is_final: bool = Field(False, description="是否为最终内容")
    timestamp: str = Field(..., description="时间戳")


class StageCompleteData(BaseModel):
    """阶段完成事件数据"""
    stage: str = Field(..., description="阶段名称")
    summary: str = Field(..., description="阶段摘要")
    duration_ms: int = Field(..., description="阶段耗时（毫秒）")
    timestamp: str = Field(..., description="时间戳")


class FinalAnswerData(BaseModel):
    """最终答案事件数据"""
    content: str = Field(..., description="答案内容")
    metadata: Dict[str, Any] = Field(..., description="元数据")
    timestamp: str = Field(..., description="时间戳")


class ErrorData(BaseModel):
    """错误事件数据"""
    error_code: str = Field(..., description="错误代码")
    error_message: str = Field(..., description="错误消息")
    error_detail: Optional[str] = Field(None, description="错误详情")
    error_type: Optional[str] = Field(None, description="错误类型")
    stage: Optional[str] = Field(None, description="发生错误的阶段")
    recoverable: bool = Field(False, description="是否可恢复")
    timestamp: str = Field(..., description="时间戳")


class WorkflowCompleteData(BaseModel):
    """工作流完成事件数据"""
    session_id: str = Field(..., description="会话ID")
    status: Literal["success", "error", "need_clarification", "cancelled", "timeout"] = Field(..., description="完成状态")
    timestamp: str = Field(..., description="时间戳")


class ExecutionPlanData(BaseModel):
    """执行计划事件数据"""
    question_type: str = Field(..., description="问题类型")
    stock_codes: List[str] = Field(default_factory=list, description="涉及的股票代码")
    workflow_stages: List[Dict[str, Any]] = Field(default_factory=list, description="工作流阶段")
    key_points: List[str] = Field(default_factory=list, description="关键点")
    risk_points: List[str] = Field(default_factory=list, description="风险点")
    timestamp: str = Field(..., description="时间戳")


class SSEEvent(BaseModel):
    """SSE事件基类"""
    event_type: str = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(..., description="事件数据")
    event_id: Optional[str] = Field(None, description="事件ID")


def validate_event_type(event_type: str) -> bool:
    """验证事件类型是否支持
    
    Args:
        event_type: 事件类型
    
    Returns:
        是否为支持的事件类型
    """
    return event_type in SUPPORTED_EVENT_TYPES


def validate_stage(stage: str) -> bool:
    """验证阶段名称是否有效
    
    Args:
        stage: 阶段名称
    
    Returns:
        是否为有效的阶段
    """
    return stage in WORKFLOW_STAGES


def validate_event_data(event_type: str, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """验证事件数据格式
    
    Args:
        event_type: 事件类型
        data: 事件数据
    
    Returns:
        (是否有效, 错误信息)
    """
    try:
        # 根据事件类型选择对应的数据模型
        model_map = {
            EVENT_WORKFLOW_START: WorkflowStartData,
            EVENT_STAGE_START: StageStartData,
            EVENT_STAGE_PROGRESS: StageProgressData,
            EVENT_TOOL_CALL: ToolCallData,
            EVENT_TOOL_RESULT: ToolResultData,
            EVENT_ANALYSIS_CHUNK: AnalysisChunkData,
            EVENT_STAGE_COMPLETE: StageCompleteData,
            EVENT_FINAL_ANSWER: FinalAnswerData,
            EVENT_ERROR: ErrorData,
            EVENT_WORKFLOW_COMPLETE: WorkflowCompleteData,
            EVENT_EXECUTION_PLAN: ExecutionPlanData,
        }
        
        model_class = model_map.get(event_type)
        if not model_class:
            return False, f"未知的事件类型: {event_type}"
        
        # 验证数据
        model_class(**data)
        return True, None
        
    except Exception as e:
        return False, f"数据验证失败: {str(e)}"


def create_event(event_type: str, data: Dict[str, Any], event_id: Optional[str] = None) -> SSEEvent:
    """创建SSE事件
    
    Args:
        event_type: 事件类型
        data: 事件数据
        event_id: 事件ID（可选）
    
    Returns:
        SSE事件对象
    
    Raises:
        ValueError: 事件类型或数据格式无效
    """
    if not validate_event_type(event_type):
        raise ValueError(f"不支持的事件类型: {event_type}")
    
    is_valid, error_msg = validate_event_data(event_type, data)
    if not is_valid:
        raise ValueError(f"事件数据无效: {error_msg}")
    
    return SSEEvent(
        event_type=event_type,
        data=data,
        event_id=event_id
    )


def get_event_type_description(event_type: str) -> str:
    """获取事件类型的描述
    
    Args:
        event_type: 事件类型
    
    Returns:
        事件类型描述
    """
    descriptions = {
        EVENT_WORKFLOW_START: "工作流开始",
        EVENT_STAGE_START: "阶段开始",
        EVENT_STAGE_PROGRESS: "阶段进度",
        EVENT_TOOL_CALL: "工具调用",
        EVENT_TOOL_RESULT: "工具结果",
        EVENT_ANALYSIS_CHUNK: "分析内容增量",
        EVENT_STAGE_COMPLETE: "阶段完成",
        EVENT_FINAL_ANSWER: "最终答案",
        EVENT_ERROR: "错误",
        EVENT_WORKFLOW_COMPLETE: "工作流完成",
        EVENT_EXECUTION_PLAN: "执行计划",
    }
    return descriptions.get(event_type, "未知事件")
