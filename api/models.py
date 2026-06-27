"""
API数据模型定义

本模块定义了股票分析系统API的所有Pydantic数据模型，包括：
- 请求/响应模型
- SSE事件模型
- 工具输出模型

所有模型都使用Pydantic进行数据验证和序列化。
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from enum import Enum


# ============================================================================
# 枚举类型定义
# ============================================================================

class EventType(str, Enum):
    """SSE事件类型枚举"""
    WORKFLOW_START = "workflow_start"
    STAGE_START = "stage_start"
    STAGE_PROGRESS = "stage_progress"
    STAGE_COMPLETE = "stage_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ANALYSIS_CHUNK = "analysis_chunk"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"
    WORKFLOW_COMPLETE = "workflow_complete"


class WorkflowStage(str, Enum):
    """工作流阶段枚举"""
    ANALYZE_QUESTION = "analyze_question"
    COLLECT_DATA = "collect_data"
    ANALYZE_DATA = "analyze_data"
    GENERATE_ANSWER = "generate_answer"


class ToolStatus(str, Enum):
    """工具执行状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ErrorCode(str, Enum):
    """错误代码枚举"""
    TOOL_CALL_ERROR = "TOOL_CALL_ERROR"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_CONNECTION_ERROR = "TOOL_CONNECTION_ERROR"
    DATA_VALIDATION_ERROR = "DATA_VALIDATION_ERROR"
    WORKFLOW_ERROR = "WORKFLOW_ERROR"
    WORKFLOW_TIMEOUT = "WORKFLOW_TIMEOUT"
    LLM_CALL_ERROR = "LLM_CALL_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class IndicatorType(str, Enum):
    """技术指标类型"""
    MACD = "MACD"
    KDJ = "KDJ"
    RSI = "RSI"
    BOLL = "BOLL"
    MA = "MA"
    OBV = "OBV"
    VOLUME_RATIO = "VOLUME_RATIO"


class SignalType(str, Enum):
    """技术指标信号类型"""
    GOLDEN_CROSS = "金叉"
    DEATH_CROSS = "死叉"
    OVERBOUGHT = "超买"
    OVERSOLD = "超卖"
    NEUTRAL = "中性"
    BULLISH = "多头排列"
    BEARISH = "空头排列"
    DIVERGENCE = "背离"


# ============================================================================
# API请求/响应模型
# ============================================================================

class AnalysisOptions(BaseModel):
    """分析选项"""
    enable_trace: bool = Field(default=False, description="是否启用追踪")
    max_history: int = Field(default=30, description="最大历史消息数")
    enable_compression: bool = Field(default=True, description="是否启用数据压缩")
    timeout_seconds: int = Field(default=300, description="超时时间（秒）")


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    query: str = Field(..., description="用户查询问题", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID，用于追踪和恢复")
    options: Optional[AnalysisOptions] = Field(
        default_factory=AnalysisOptions,
        description="分析选项"
    )

    @validator('query')
    def validate_query(cls, v):
        """验证查询不为空"""
        if not v or not v.strip():
            raise ValueError("查询不能为空")
        return v.strip()


# ============================================================================
# SSE事件模型
# ============================================================================

class WorkflowStartEvent(BaseModel):
    """工作流开始事件"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户问题")
    timestamp: str = Field(..., description="时间戳")


class StageStartEvent(BaseModel):
    """阶段开始事件"""
    stage: WorkflowStage = Field(..., description="阶段名称")
    title: str = Field(..., description="阶段标题")
    description: Optional[str] = Field(None, description="阶段描述")
    timestamp: str = Field(..., description="时间戳")


class StageProgressEvent(BaseModel):
    """阶段进度事件"""
    stage: WorkflowStage = Field(..., description="阶段名称")
    progress: Dict[str, Any] = Field(..., description="进度信息")
    timestamp: str = Field(..., description="时间戳")

    class Config:
        json_schema_extra = {
            "example": {
                "stage": "collect_data",
                "progress": {
                    "current": 2,
                    "total": 5,
                    "message": "正在调用工具: tool_get_stock_history_price"
                },
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }


class StageCompleteEvent(BaseModel):
    """阶段完成事件"""
    stage: WorkflowStage = Field(..., description="阶段名称")
    summary: str = Field(..., description="阶段总结")
    duration_ms: Optional[int] = Field(None, description="执行时长（毫秒）")
    timestamp: str = Field(..., description="时间戳")


class ToolCallEvent(BaseModel):
    """工具调用事件"""
    tool_name: str = Field(..., description="工具名称")
    tool_id: str = Field(..., description="工具调用ID")
    args: Dict[str, Any] = Field(..., description="工具参数")
    timestamp: str = Field(..., description="时间戳")


class ToolResultEvent(BaseModel):
    """工具结果事件"""
    tool_name: str = Field(..., description="工具名称")
    tool_id: str = Field(..., description="工具调用ID")
    status: ToolStatus = Field(..., description="执行状态")
    summary: str = Field(..., description="结果摘要")
    data_id: Optional[str] = Field(None, description="数据ID（用于压缩数据）")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: str = Field(..., description="时间戳")


class AnalysisChunkEvent(BaseModel):
    """分析内容增量事件"""
    stage: WorkflowStage = Field(..., description="阶段名称")
    content: str = Field(..., description="分析内容")
    is_final: bool = Field(default=False, description="是否为最终内容")
    timestamp: str = Field(..., description="时间戳")


class FinalAnswerMetadata(BaseModel):
    """最终答案元数据"""
    total_duration_ms: int = Field(..., description="总执行时长（毫秒）")
    tools_used: List[str] = Field(..., description="使用的工具列表")
    data_sources: List[str] = Field(..., description="数据来源列表")


class FinalAnswerEvent(BaseModel):
    """最终答案事件"""
    content: str = Field(..., description="完整的分析结论")
    metadata: FinalAnswerMetadata = Field(..., description="元数据")
    timestamp: str = Field(..., description="时间戳")


class ErrorEvent(BaseModel):
    """错误事件"""
    error_code: ErrorCode = Field(..., description="错误代码")
    error_message: str = Field(..., description="错误消息")
    error_detail: Optional[str] = Field(None, description="错误详情")
    stage: Optional[WorkflowStage] = Field(None, description="发生错误的阶段")
    recoverable: bool = Field(default=False, description="是否可恢复")
    timestamp: str = Field(..., description="时间戳")


class WorkflowCompleteEvent(BaseModel):
    """工作流完成事件"""
    session_id: str = Field(..., description="会话ID")
    status: str = Field(..., description="完成状态：success或error")
    total_duration_ms: Optional[int] = Field(None, description="总执行时长（毫秒）")
    timestamp: str = Field(..., description="时间戳")


# ============================================================================
# 工具输出模型
# ============================================================================

class StockBasicInfo(BaseModel):
    """股票基本信息"""
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票名称")
    industry: Optional[str] = Field(None, description="所属行业")
    market: Optional[str] = Field(None, description="市场（主板/创业板等）")
    list_date: Optional[str] = Field(None, description="上市日期")


class StockPriceData(BaseModel):
    """股票价格数据点"""
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    
    @validator('open', 'high', 'low', 'close', 'volume')
    def validate_positive(cls, v):
        """验证价格和成交量为正数"""
        if v < 0:
            raise ValueError("价格和成交量必须为非负数")
        return v


class StockHistoryData(BaseModel):
    """股票历史数据"""
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票名称")
    data: List[StockPriceData] = Field(..., description="历史价格数据")
    indicators: Optional[Dict[str, List[float]]] = Field(
        None,
        description="技术指标数据（如均线）"
    )
    data_source: str = Field(..., description="数据来源")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")


class TechnicalIndicatorValues(BaseModel):
    """技术指标值"""
    dates: List[str] = Field(..., description="日期列表")
    values: Dict[str, List[float]] = Field(..., description="指标值字典")


class TechnicalIndicatorResult(BaseModel):
    """技术指标计算结果"""
    indicator_type: IndicatorType = Field(..., description="指标类型")
    values: Dict[str, List[float]] = Field(..., description="指标值")
    signal: Optional[SignalType] = Field(None, description="信号类型")
    interpretation: Optional[str] = Field(None, description="指标解读")
    calculation_params: Optional[Dict[str, Any]] = Field(
        None,
        description="计算参数"
    )


class PatternMatchResult(BaseModel):
    """模式匹配结果"""
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票名称")
    match_date: str = Field(..., description="匹配日期")
    match_score: float = Field(..., description="匹配度评分", ge=0.0, le=1.0)
    pattern_description: str = Field(..., description="模式描述")
    pattern_data: Optional[Dict[str, Any]] = Field(
        None,
        description="模式相关数据"
    )
    future_performance: Dict[str, float] = Field(
        ...,
        description="后续表现（如5日涨跌幅、10日涨跌幅等）"
    )


class PatternSearchStatistics(BaseModel):
    """模式搜索统计信息"""
    total_matches: int = Field(..., description="总匹配数")
    avg_5d_return: Optional[float] = Field(None, description="平均5日收益率")
    avg_10d_return: Optional[float] = Field(None, description="平均10日收益率")
    avg_20d_return: Optional[float] = Field(None, description="平均20日收益率")
    win_rate_5d: Optional[float] = Field(None, description="5日上涨概率")
    win_rate_10d: Optional[float] = Field(None, description="10日上涨概率")
    win_rate_20d: Optional[float] = Field(None, description="20日上涨概率")
    risk_reward_ratio: Optional[float] = Field(None, description="风险收益比")


class PatternSearchResult(BaseModel):
    """模式搜索结果"""
    pattern_description: str = Field(..., description="模式描述")
    matches: List[PatternMatchResult] = Field(..., description="匹配案例列表")
    statistics: PatternSearchStatistics = Field(..., description="统计信息")
    total_matches: int = Field(..., description="总匹配数")
    search_params: Dict[str, Any] = Field(..., description="搜索参数")


class FinancialData(BaseModel):
    """财务数据"""
    stock_code: str = Field(..., description="股票代码")
    report_date: str = Field(..., description="报告期")
    revenue: Optional[float] = Field(None, description="营业收入")
    net_profit: Optional[float] = Field(None, description="净利润")
    eps: Optional[float] = Field(None, description="每股收益")
    roe: Optional[float] = Field(None, description="净资产收益率")
    debt_ratio: Optional[float] = Field(None, description="资产负债率")
    data_source: str = Field(..., description="数据来源")


class ChipDistributionData(BaseModel):
    """筹码分布数据"""
    stock_code: str = Field(..., description="股票代码")
    date: str = Field(..., description="日期")
    concentration: Optional[float] = Field(None, description="筹码集中度")
    main_inflow: Optional[float] = Field(None, description="主力资金流入")
    retail_outflow: Optional[float] = Field(None, description="散户资金流出")
    data_source: str = Field(..., description="数据来源")


class NewsData(BaseModel):
    """新闻数据"""
    title: str = Field(..., description="新闻标题")
    content: Optional[str] = Field(None, description="新闻内容")
    publish_date: str = Field(..., description="发布日期")
    source: str = Field(..., description="新闻来源")
    sentiment: Optional[str] = Field(None, description="情感倾向")


class ResearchReportData(BaseModel):
    """研报数据"""
    title: str = Field(..., description="研报标题")
    analyst: Optional[str] = Field(None, description="分析师")
    institution: Optional[str] = Field(None, description="机构")
    publish_date: str = Field(..., description="发布日期")
    rating: Optional[str] = Field(None, description="评级")
    target_price: Optional[float] = Field(None, description="目标价")
    summary: Optional[str] = Field(None, description="摘要")


# ============================================================================
# 工作流状态模型
# ============================================================================

class WorkflowStep(BaseModel):
    """工作流步骤"""
    stage: WorkflowStage = Field(..., description="阶段名称")
    title: str = Field(..., description="步骤标题")
    summary: Optional[str] = Field(None, description="步骤摘要")
    detail: Optional[str] = Field(None, description="步骤详情")
    timestamp: str = Field(..., description="时间戳")


class ExecutionPlan(BaseModel):
    """执行计划"""
    workflow_stages: List[Dict[str, Any]] = Field(..., description="工作流阶段列表")
    total_stages: int = Field(..., description="总阶段数")
    estimated_duration_seconds: Optional[int] = Field(
        None,
        description="预估执行时长（秒）"
    )


# ============================================================================
# 辅助模型
# ============================================================================

class DataCompressionInfo(BaseModel):
    """数据压缩信息"""
    compressed: bool = Field(..., description="是否已压缩")
    data_id: Optional[str] = Field(None, description="压缩数据ID")
    original_size: int = Field(..., description="原始大小（字节）")
    compressed_size: Optional[int] = Field(None, description="压缩后大小（字节）")
    summary: Optional[str] = Field(None, description="数据摘要")


class ToolExecutionResult(BaseModel):
    """工具执行结果"""
    success: bool = Field(..., description="是否成功")
    tool_name: str = Field(..., description="工具名称")
    data: Optional[Any] = Field(None, description="返回数据")
    error_code: Optional[ErrorCode] = Field(None, description="错误代码")
    error_message: Optional[str] = Field(None, description="错误消息")
    error_detail: Optional[str] = Field(None, description="错误详情")
    recoverable: bool = Field(default=False, description="是否可恢复")
    retry_suggested: bool = Field(default=False, description="是否建议重试")
    timestamp: str = Field(..., description="时间戳")


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="版本号")
    timestamp: str = Field(..., description="时间戳")
    dependencies: Optional[Dict[str, str]] = Field(
        None,
        description="依赖服务状态"
    )


# ============================================================================
# 配置模型
# ============================================================================

class DataSourceConfig(BaseModel):
    """数据源配置"""
    name: str = Field(..., description="数据源名称")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=0, description="优先级（数字越大优先级越高）")
    timeout_seconds: int = Field(default=30, description="超时时间（秒）")
    retry_count: int = Field(default=3, description="重试次数")


# ============================================================================
# 工具函数
# ============================================================================

def get_current_timestamp() -> str:
    """获取当前时间戳（ISO 8601格式）"""
    return datetime.now().isoformat()


def create_event_data(event_type: EventType, data: BaseModel) -> Dict[str, Any]:
    """创建SSE事件数据
    
    Args:
        event_type: 事件类型
        data: 事件数据模型
        
    Returns:
        格式化的事件字典
    """
    return {
        "event": event_type.value,
        "data": data.dict(exclude_none=True),
        "timestamp": get_current_timestamp()
    }
