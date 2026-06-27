"""
工具注册管理器

提供工具的注册、发现和统一调用机制：
- ToolRegistry: 工具注册中心
- 工具元数据管理
- 工具发现和查询
- 集成ToolExecutor进行统一调用
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from utils.error_handler import ToolExecutor
from utils.data_validator import DataValidator

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    func: Callable
    category: str = "general"  # general, data_source, indicator, pattern_search, etc.
    data_source: Optional[str] = None  # ifind, akshare, tushare, etc.
    requires_auth: bool = False
    is_async: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    registered_at: datetime = field(default_factory=datetime.now)


class ToolRegistry:
    """
    工具注册中心
    
    提供以下功能：
    - 工具注册和注销
    - 工具发现和查询
    - 工具分类管理
    - 统一的工具调用接口（集成ToolExecutor）
    - 工具元数据管理
    """
    
    def __init__(self):
        """初始化工具注册中心"""
        self._tools: Dict[str, ToolMetadata] = {}
        self._categories: Dict[str, List[str]] = {}
        self._executor = ToolExecutor()
        self._validator = DataValidator()
        self.logger = logging.getLogger(__name__)
    
    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        category: str = "general",
        data_source: Optional[str] = None,
        requires_auth: bool = False,
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        version: str = "1.0.0"
    ) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称（唯一标识符）
            func: 工具函数
            description: 工具描述
            category: 工具分类
            data_source: 数据源（如果适用）
            requires_auth: 是否需要认证
            parameters: 参数定义
            tags: 标签列表
            version: 版本号
        """
        if name in self._tools:
            self.logger.warning(f"Tool {name} already registered, overwriting")
        
        # 检测函数是否为异步
        is_async = asyncio.iscoroutinefunction(func)
        
        # 创建工具元数据
        metadata = ToolMetadata(
            name=name,
            description=description,
            func=func,
            category=category,
            data_source=data_source,
            requires_auth=requires_auth,
            is_async=is_async,
            parameters=parameters or {},
            tags=tags or [],
            version=version
        )
        
        # 注册工具
        self._tools[name] = metadata
        
        # 更新分类索引
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)
        
        self.logger.info(
            f"Registered tool: {name} (category: {category}, "
            f"data_source: {data_source}, async: {is_async})"
        )
    
    def unregister(self, name: str) -> bool:
        """
        注销工具
        
        Args:
            name: 工具名称
        
        Returns:
            是否成功注销
        """
        if name not in self._tools:
            self.logger.warning(f"Tool {name} not found")
            return False
        
        metadata = self._tools[name]
        
        # 从分类索引中移除
        if metadata.category in self._categories:
            if name in self._categories[metadata.category]:
                self._categories[metadata.category].remove(name)
        
        # 移除工具
        del self._tools[name]
        
        self.logger.info(f"Unregistered tool: {name}")
        return True
    
    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """
        获取工具元数据
        
        Args:
            name: 工具名称
        
        Returns:
            工具元数据，如果不存在则返回None
        """
        return self._tools.get(name)
    
    def list_tools(
        self,
        category: Optional[str] = None,
        data_source: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[ToolMetadata]:
        """
        列出工具
        
        Args:
            category: 按分类过滤
            data_source: 按数据源过滤
            tags: 按标签过滤（工具必须包含所有指定标签）
        
        Returns:
            工具元数据列表
        """
        tools = list(self._tools.values())
        
        # 按分类过滤
        if category:
            tools = [t for t in tools if t.category == category]
        
        # 按数据源过滤
        if data_source:
            tools = [t for t in tools if t.data_source == data_source]
        
        # 按标签过滤
        if tags:
            tools = [
                t for t in tools
                if all(tag in t.tags for tag in tags)
            ]
        
        return tools
    
    def list_categories(self) -> List[str]:
        """
        列出所有工具分类
        
        Returns:
            分类列表
        """
        return list(self._categories.keys())
    
    def list_data_sources(self) -> List[str]:
        """
        列出所有数据源
        
        Returns:
            数据源列表
        """
        sources = set()
        for tool in self._tools.values():
            if tool.data_source:
                sources.add(tool.data_source)
        return sorted(list(sources))
    
    async def execute(
        self,
        name: str,
        *args,
        validate_result: bool = True,
        add_data_source: bool = True,
        enable_retry: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具（异步）
        
        Args:
            name: 工具名称
            *args: 位置参数
            validate_result: 是否验证结果
            add_data_source: 是否添加数据来源标识
            enable_retry: 是否启用重试机制
            **kwargs: 关键字参数
        
        Returns:
            标准化的工具执行结果
        """
        # 获取工具元数据
        metadata = self.get_tool(name)
        if not metadata:
            return {
                "success": False,
                "error_code": "TOOL_NOT_FOUND",
                "error_message": f"工具 {name} 未注册",
                "tool_name": name,
                "timestamp": datetime.now().isoformat()
            }
        
        # 使用ToolExecutor执行工具
        result = await self._executor.execute_tool(
            metadata.func,
            *args,
            tool_name=name,
            enable_retry=enable_retry,
            **kwargs
        )
        
        # 如果执行成功，进行后处理
        if result.get("success"):
            # 添加数据来源标识
            if add_data_source and metadata.data_source:
                if isinstance(result.get("data"), dict):
                    result["data"]["data_source"] = metadata.data_source
                else:
                    result["data_source"] = metadata.data_source
            
            # 验证结果
            if validate_result and result.get("data"):
                validation_result = self._validate_tool_result(
                    name,
                    result["data"],
                    metadata
                )
                result["validation"] = validation_result
                
                if not validation_result.get("is_valid"):
                    self.logger.warning(
                        f"Tool {name} result validation failed: "
                        f"{validation_result.get('message')}"
                    )
        
        return result
    
    def execute_sync(
        self,
        name: str,
        *args,
        validate_result: bool = True,
        add_data_source: bool = True,
        enable_retry: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具（同步）
        
        Args:
            name: 工具名称
            *args: 位置参数
            validate_result: 是否验证结果
            add_data_source: 是否添加数据来源标识
            enable_retry: 是否启用重试机制
            **kwargs: 关键字参数
        
        Returns:
            标准化的工具执行结果
        """
        # 获取工具元数据
        metadata = self.get_tool(name)
        if not metadata:
            return {
                "success": False,
                "error_code": "TOOL_NOT_FOUND",
                "error_message": f"工具 {name} 未注册",
                "tool_name": name,
                "timestamp": datetime.now().isoformat()
            }
        
        # 使用ToolExecutor执行工具
        result = self._executor.execute_tool_sync(
            metadata.func,
            *args,
            tool_name=name,
            enable_retry=enable_retry,
            **kwargs
        )
        
        # 如果执行成功，进行后处理
        if result.get("success"):
            # 添加数据来源标识
            if add_data_source and metadata.data_source:
                if isinstance(result.get("data"), dict):
                    result["data"]["data_source"] = metadata.data_source
                else:
                    result["data_source"] = metadata.data_source
            
            # 验证结果
            if validate_result and result.get("data"):
                validation_result = self._validate_tool_result(
                    name,
                    result["data"],
                    metadata
                )
                result["validation"] = validation_result
                
                if not validation_result.get("is_valid"):
                    self.logger.warning(
                        f"Tool {name} result validation failed: "
                        f"{validation_result.get('message')}"
                    )
        
        return result
    
    def _validate_tool_result(
        self,
        tool_name: str,
        data: Any,
        metadata: ToolMetadata
    ) -> Dict[str, Any]:
        """
        验证工具结果
        
        Args:
            tool_name: 工具名称
            data: 工具返回的数据
            metadata: 工具元数据
        
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
        if metadata.category == "data_source":
            # 验证股票数据
            is_valid, message = self._validator.validate_stock_price_data(data)
            return {
                "is_valid": is_valid,
                "message": message
            }
        
        elif metadata.category == "indicator":
            # 验证技术指标结果
            # 尝试从工具名称或标签推断指标类型
            indicator_type = None
            if "macd" in tool_name.lower():
                indicator_type = "MACD"
            elif "kdj" in tool_name.lower():
                indicator_type = "KDJ"
            elif "rsi" in tool_name.lower():
                indicator_type = "RSI"
            elif "boll" in tool_name.lower():
                indicator_type = "BOLL"
            
            if indicator_type and isinstance(data, dict):
                is_valid, message = self._validator.validate_technical_indicator_result(
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
    
    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具信息（用于展示）
        
        Args:
            name: 工具名称
        
        Returns:
            工具信息字典
        """
        metadata = self.get_tool(name)
        if not metadata:
            return None
        
        return {
            "name": metadata.name,
            "description": metadata.description,
            "category": metadata.category,
            "data_source": metadata.data_source,
            "requires_auth": metadata.requires_auth,
            "is_async": metadata.is_async,
            "parameters": metadata.parameters,
            "tags": metadata.tags,
            "version": metadata.version,
            "registered_at": metadata.registered_at.isoformat()
        }
    
    def search_tools(self, query: str) -> List[ToolMetadata]:
        """
        搜索工具
        
        Args:
            query: 搜索关键词
        
        Returns:
            匹配的工具列表
        """
        query_lower = query.lower()
        results = []
        
        for tool in self._tools.values():
            # 在名称、描述和标签中搜索
            if (query_lower in tool.name.lower() or
                query_lower in tool.description.lower() or
                any(query_lower in tag.lower() for tag in tool.tags)):
                results.append(tool)
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取注册中心统计信息
        
        Returns:
            统计信息字典
        """
        total_tools = len(self._tools)
        async_tools = sum(1 for t in self._tools.values() if t.is_async)
        sync_tools = total_tools - async_tools
        
        category_counts = {
            cat: len(tools)
            for cat, tools in self._categories.items()
        }
        
        data_source_counts = {}
        for tool in self._tools.values():
            if tool.data_source:
                data_source_counts[tool.data_source] = \
                    data_source_counts.get(tool.data_source, 0) + 1
        
        return {
            "total_tools": total_tools,
            "async_tools": async_tools,
            "sync_tools": sync_tools,
            "categories": category_counts,
            "data_sources": data_source_counts,
            "total_categories": len(self._categories),
            "total_data_sources": len(data_source_counts)
        }


# 全局工具注册中心实例
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """
    获取全局工具注册中心实例
    
    Returns:
        全局ToolRegistry实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(
    name: str,
    func: Callable,
    description: str = "",
    category: str = "general",
    data_source: Optional[str] = None,
    requires_auth: bool = False,
    parameters: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    version: str = "1.0.0"
) -> None:
    """
    注册工具到全局注册中心（便捷函数）
    
    Args:
        name: 工具名称
        func: 工具函数
        description: 工具描述
        category: 工具分类
        data_source: 数据源
        requires_auth: 是否需要认证
        parameters: 参数定义
        tags: 标签列表
        version: 版本号
    """
    registry = get_global_registry()
    registry.register(
        name=name,
        func=func,
        description=description,
        category=category,
        data_source=data_source,
        requires_auth=requires_auth,
        parameters=parameters,
        tags=tags,
        version=version
    )


# 导出的公共接口
__all__ = [
    'ToolMetadata',
    'ToolRegistry',
    'get_global_registry',
    'register_tool'
]
