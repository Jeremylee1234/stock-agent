"""
增强的工具函数包装器

为现有工具函数添加：
- ToolExecutor统一错误处理
- 数据验证
- 数据来源标识
- 统一的返回格式
"""

import logging
from typing import Any, Dict, Optional
from functools import wraps
import asyncio

from utils.error_handler import ToolExecutor
from utils.data_validator import DataValidator
from tools.tool_registry import get_global_registry

logger = logging.getLogger(__name__)


class EnhancedToolWrapper:
    """
    增强的工具包装器
    
    为工具函数添加统一的错误处理、数据验证和数据来源标识
    """
    
    def __init__(self):
        """初始化包装器"""
        self.executor = ToolExecutor()
        self.validator = DataValidator()
        self.registry = get_global_registry()
        self.logger = logging.getLogger(__name__)
    
    async def execute_with_validation(
        self,
        tool_name: str,
        *args,
        validate_result: bool = True,
        add_data_source: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具并进行验证
        
        Args:
            tool_name: 工具名称
            *args: 位置参数
            validate_result: 是否验证结果
            add_data_source: 是否添加数据来源标识
            **kwargs: 关键字参数
        
        Returns:
            标准化的工具执行结果
        """
        # 从注册中心获取工具
        tool_metadata = self.registry.get_tool(tool_name)
        
        if not tool_metadata:
            self.logger.error(f"Tool {tool_name} not found in registry")
            return {
                "success": False,
                "error_code": "TOOL_NOT_FOUND",
                "error_message": f"工具 {tool_name} 未注册",
                "tool_name": tool_name
            }
        
        # 使用ToolExecutor执行工具
        result = await self.executor.execute_tool(
            tool_metadata.func,
            *args,
            tool_name=tool_name,
            **kwargs
        )
        
        # 如果执行成功，进行后处理
        if result.get("success"):
            data = result.get("data")
            
            # 添加数据来源标识
            if add_data_source and tool_metadata.data_source:
                if isinstance(data, dict):
                    data["data_source"] = tool_metadata.data_source
                    result["data"] = data
                else:
                    result["data_source"] = tool_metadata.data_source
            
            # 验证结果
            if validate_result and data:
                validation_result = self._validate_result(
                    tool_name,
                    data,
                    tool_metadata.category
                )
                result["validation"] = validation_result
                
                if not validation_result.get("is_valid"):
                    self.logger.warning(
                        f"Tool {tool_name} result validation failed: "
                        f"{validation_result.get('message')}"
                    )
        
        return result
    
    def _validate_result(
        self,
        tool_name: str,
        data: Any,
        category: str
    ) -> Dict[str, Any]:
        """
        验证工具结果
        
        Args:
            tool_name: 工具名称
            data: 工具返回的数据
            category: 工具分类
        
        Returns:
            验证结果字典
        """
        # 检查是否包含错误
        if isinstance(data, dict) and "error" in data:
            return {
                "is_valid": False,
                "message": f"工具返回包含错误: {data.get('error')}"
            }
        
        # 根据工具分类进行特定验证
        if category == "data_source":
            # 验证股票数据
            is_valid, message = self.validator.validate_stock_price_data(data)
            return {
                "is_valid": is_valid,
                "message": message
            }
        
        elif category == "indicator":
            # 验证技术指标结果
            indicator_type = self._infer_indicator_type(tool_name)
            if indicator_type and isinstance(data, dict):
                is_valid, message = self.validator.validate_technical_indicator_result(
                    data,
                    indicator_type
                )
                return {
                    "is_valid": is_valid,
                    "message": message
                }
        
        # 默认验证：检查数据不为空
        if data is None:
            return {
                "is_valid": False,
                "message": "工具返回数据为空"
            }
        
        return {
            "is_valid": True,
            "message": "验证通过"
        }
    
    def _infer_indicator_type(self, tool_name: str) -> Optional[str]:
        """
        从工具名称推断指标类型
        
        Args:
            tool_name: 工具名称
        
        Returns:
            指标类型（MACD, KDJ, RSI, BOLL等）或None
        """
        tool_name_lower = tool_name.lower()
        
        if "macd" in tool_name_lower:
            return "MACD"
        elif "kdj" in tool_name_lower:
            return "KDJ"
        elif "rsi" in tool_name_lower:
            return "RSI"
        elif "boll" in tool_name_lower:
            return "BOLL"
        
        return None


# 全局包装器实例
_global_wrapper: Optional[EnhancedToolWrapper] = None


def get_global_wrapper() -> EnhancedToolWrapper:
    """
    获取全局工具包装器实例
    
    Returns:
        全局EnhancedToolWrapper实例
    """
    global _global_wrapper
    if _global_wrapper is None:
        _global_wrapper = EnhancedToolWrapper()
    return _global_wrapper


def enhanced_tool(
    tool_name: Optional[str] = None,
    validate_result: bool = True,
    add_data_source: bool = True
):
    """
    装饰器：为工具函数添加增强功能
    
    使用示例：
        @enhanced_tool(tool_name="get_stock_price", validate_result=True)
        async def get_stock_price(stock_code: str):
            # 工具逻辑
            pass
    
    Args:
        tool_name: 工具名称（可选，默认使用函数名）
        validate_result: 是否验证结果
        add_data_source: 是否添加数据来源标识
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            wrapper = get_global_wrapper()
            name = tool_name or func.__name__
            
            # 先注册工具（如果尚未注册）
            registry = get_global_registry()
            if not registry.get_tool(name):
                registry.register(
                    name=name,
                    func=func,
                    description=func.__doc__ or "",
                    category="general"
                )
            
            return await wrapper.execute_with_validation(
                name,
                *args,
                validate_result=validate_result,
                add_data_source=add_data_source,
                **kwargs
            )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 对于同步函数，直接执行并添加基本的错误处理
            try:
                result = func(*args, **kwargs)
                
                # 添加数据来源标识
                if add_data_source and isinstance(result, dict):
                    registry = get_global_registry()
                    tool_metadata = registry.get_tool(tool_name or func.__name__)
                    if tool_metadata and tool_metadata.data_source:
                        result["data_source"] = tool_metadata.data_source
                
                return {
                    "success": True,
                    "data": result,
                    "tool_name": tool_name or func.__name__
                }
            except Exception as e:
                logger.error(f"Tool {tool_name or func.__name__} failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "error_code": "TOOL_ERROR",
                    "error_message": str(e),
                    "tool_name": tool_name or func.__name__
                }
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 便捷函数：执行已注册的工具
async def execute_tool(
    tool_name: str,
    *args,
    validate_result: bool = True,
    add_data_source: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    执行已注册的工具（便捷函数）
    
    Args:
        tool_name: 工具名称
        *args: 位置参数
        validate_result: 是否验证结果
        add_data_source: 是否添加数据来源标识
        **kwargs: 关键字参数
    
    Returns:
        标准化的工具执行结果
    """
    wrapper = get_global_wrapper()
    return await wrapper.execute_with_validation(
        tool_name,
        *args,
        validate_result=validate_result,
        add_data_source=add_data_source,
        **kwargs
    )


# 导出的公共接口
__all__ = [
    'EnhancedToolWrapper',
    'get_global_wrapper',
    'enhanced_tool',
    'execute_tool'
]
