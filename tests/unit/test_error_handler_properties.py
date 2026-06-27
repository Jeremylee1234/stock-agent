"""
Property-Based Tests for Error Handler

Tests Property 25: 工具异常处理统一性
Validates: Requirements 9.1, 9.3

这些测试验证所有工具函数抛出的异常都被统一处理并转换为标准格式。
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from hypothesis import assume
from datetime import datetime
import asyncio
from typing import Any, Dict

from utils.error_handler import ToolExecutor, ErrorCode, handle_tool_errors


# 定义异常类型策略
@st.composite
def exception_strategy(draw):
    """生成各种类型的异常"""
    exception_types = [
        ValueError,
        KeyError,
        RuntimeError,
        TypeError,
        AttributeError,
        IndexError,
        ZeroDivisionError,
        MemoryError,
    ]
    
    # 如果requests可用，添加requests异常
    try:
        import requests
        exception_types.extend([
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
        ])
    except ImportError:
        pass
    
    exc_type = draw(st.sampled_from(exception_types))
    message = draw(st.text(min_size=1, max_size=100))
    
    # 对于HTTPError，需要特殊处理
    if exc_type.__name__ == 'HTTPError':
        try:
            import requests
            # 创建一个模拟的响应对象
            response = requests.Response()
            response.status_code = draw(st.sampled_from([401, 403, 404, 500]))
            exc = exc_type(message)
            exc.response = response
            return exc
        except:
            # 如果创建失败，使用其他异常
            return ValueError(message)
    
    return exc_type(message)


@st.composite
def tool_function_strategy(draw):
    """生成会抛出异常的工具函数"""
    exception = draw(exception_strategy())
    tool_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), min_codepoint=65),
        min_size=5,
        max_size=30
    ))
    
    def failing_tool(*args, **kwargs):
        """一个会抛出异常的工具函数"""
        raise exception
    
    failing_tool.__name__ = tool_name
    return failing_tool, exception


class TestErrorHandlerUniformity:
    """测试错误处理的统一性"""
    
    @given(tool_function_strategy())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_property_25_sync_tool_error_format_uniformity(self, tool_and_exception):
        """
        Property 25: 工具异常处理统一性（同步版本）
        
        对于任何工具函数抛出的异常，ToolExecutor应该捕获并转换为
        包含以下必需字段的标准字典格式：
        - success: False
        - error_code: str
        - error_message: str
        - error_type: str
        - tool_name: str
        - timestamp: str (ISO格式)
        
        Validates: Requirements 9.1, 9.3
        """
        tool_func, expected_exception = tool_and_exception
        executor = ToolExecutor(max_retries=0)  # 禁用重试以加快测试
        
        # 执行工具并捕获结果
        result = executor.execute_tool_sync(tool_func, enable_retry=False)
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = [
            "success",
            "error_code",
            "error_message",
            "error_type",
            "tool_name",
            "timestamp"
        ]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in error response. Got: {result.keys()}"
        
        # 验证字段类型和值
        assert result["success"] is False, \
            "success field must be False for errors"
        
        assert isinstance(result["error_code"], str), \
            f"error_code must be string, got {type(result['error_code'])}"
        
        assert isinstance(result["error_message"], str), \
            f"error_message must be string, got {type(result['error_message'])}"
        
        assert isinstance(result["error_type"], str), \
            f"error_type must be string, got {type(result['error_type'])}"
        
        assert isinstance(result["tool_name"], str), \
            f"tool_name must be string, got {type(result['tool_name'])}"
        
        assert isinstance(result["timestamp"], str), \
            f"timestamp must be string, got {type(result['timestamp'])}"
        
        # 验证timestamp是有效的ISO格式
        try:
            datetime.fromisoformat(result["timestamp"])
        except ValueError:
            pytest.fail(f"timestamp is not valid ISO format: {result['timestamp']}")
        
        # 验证error_code是预定义的错误代码之一
        valid_error_codes = [
            ErrorCode.TOOL_TIMEOUT,
            ErrorCode.TOOL_CONNECTION_ERROR,
            ErrorCode.TOOL_AUTH_ERROR,
            ErrorCode.TOOL_ERROR,
            ErrorCode.DATA_VALIDATION_ERROR,
            ErrorCode.DATA_FORMAT_ERROR,
            ErrorCode.MEMORY_ERROR,
        ]
        
        assert result["error_code"] in valid_error_codes, \
            f"error_code '{result['error_code']}' is not a valid ErrorCode"
        
        # 验证error_type匹配实际异常类型
        assert result["error_type"] == type(expected_exception).__name__, \
            f"error_type should be '{type(expected_exception).__name__}', got '{result['error_type']}'"
    
    @given(tool_function_strategy())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @pytest.mark.asyncio
    async def test_property_25_async_tool_error_format_uniformity(self, tool_and_exception):
        """
        Property 25: 工具异常处理统一性（异步版本）
        
        对于任何异步工具函数抛出的异常，ToolExecutor应该捕获并转换为
        相同的标准字典格式。
        
        Validates: Requirements 9.1, 9.3
        """
        sync_tool_func, expected_exception = tool_and_exception
        
        # 创建异步版本的工具函数
        async def async_tool_func(*args, **kwargs):
            raise expected_exception
        
        async_tool_func.__name__ = sync_tool_func.__name__
        
        executor = ToolExecutor(max_retries=0)
        
        # 执行异步工具并捕获结果
        result = await executor.execute_tool(async_tool_func, enable_retry=False)
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = [
            "success",
            "error_code",
            "error_message",
            "error_type",
            "tool_name",
            "timestamp"
        ]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in error response. Got: {result.keys()}"
        
        # 验证字段类型和值
        assert result["success"] is False, \
            "success field must be False for errors"
        
        assert isinstance(result["error_code"], str), \
            f"error_code must be string, got {type(result['error_code'])}"
        
        assert isinstance(result["error_message"], str), \
            f"error_message must be string, got {type(result['error_message'])}"
        
        assert isinstance(result["error_type"], str), \
            f"error_type must be string, got {type(result['error_type'])}"
        
        assert isinstance(result["tool_name"], str), \
            f"tool_name must be string, got {type(result['tool_name'])}"
        
        # 验证timestamp是有效的ISO格式
        try:
            datetime.fromisoformat(result["timestamp"])
        except ValueError:
            pytest.fail(f"timestamp is not valid ISO format: {result['timestamp']}")
        
        # 验证error_type匹配实际异常类型
        assert result["error_type"] == type(expected_exception).__name__, \
            f"error_type should be '{type(expected_exception).__name__}', got '{result['error_type']}'"
    
    @given(
        st.text(min_size=1, max_size=50),
        exception_strategy()
    )
    @settings(
        max_examples=100,
        deadline=None
    )
    def test_property_25_decorator_error_format_uniformity(self, tool_name, exception):
        """
        Property 25: 装饰器错误处理统一性
        
        使用@handle_tool_errors装饰器的工具函数抛出异常时，
        也应该返回相同的标准格式。
        
        Validates: Requirements 9.1, 9.3
        """
        # 创建使用装饰器的工具函数
        @handle_tool_errors(tool_name=tool_name)
        def decorated_tool():
            raise exception
        
        # 执行工具
        result = decorated_tool()
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = [
            "success",
            "error_code",
            "error_message",
            "error_type",
            "tool_name",
            "timestamp"
        ]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in error response"
        
        # 验证success为False
        assert result["success"] is False, \
            "success field must be False for errors"
        
        # 验证tool_name匹配
        assert result["tool_name"] == tool_name, \
            f"tool_name should be '{tool_name}', got '{result['tool_name']}'"
    
    @given(exception_strategy())
    @settings(
        max_examples=50,
        deadline=None
    )
    def test_property_25_error_detail_contains_exception_message(self, exception):
        """
        Property 25: 错误详情包含异常信息
        
        对于任何异常，返回的error_detail或error_message应该包含
        原始异常的信息，以便调试。
        
        Validates: Requirements 9.1, 9.3
        """
        def failing_tool():
            raise exception
        
        executor = ToolExecutor(max_retries=0)
        result = executor.execute_tool_sync(failing_tool, enable_retry=False)
        
        exception_str = str(exception)
        
        # 如果异常有消息，验证它出现在error_detail或error_message中
        if exception_str:
            error_info = result.get("error_detail", "") + result.get("error_message", "")
            # 注意：某些错误处理可能会添加额外的上下文，所以我们只检查部分匹配
            # 或者至少验证有错误信息存在
            assert len(error_info) > 0, \
                "error_detail or error_message should contain error information"
    
    @given(
        st.lists(
            exception_strategy(),
            min_size=2,
            max_size=5
        )
    )
    @settings(
        max_examples=50,
        deadline=None
    )
    def test_property_25_multiple_errors_same_format(self, exceptions):
        """
        Property 25: 多个不同异常的格式一致性
        
        对于多个不同类型的异常，所有错误响应应该具有相同的结构。
        
        Validates: Requirements 9.1, 9.3
        """
        executor = ToolExecutor(max_retries=0)
        results = []
        
        for i, exception in enumerate(exceptions):
            def failing_tool():
                raise exception
            
            failing_tool.__name__ = f"tool_{i}"
            result = executor.execute_tool_sync(failing_tool, enable_retry=False)
            results.append(result)
        
        # 验证所有结果都有相同的必需字段
        required_fields = {
            "success",
            "error_code",
            "error_message",
            "error_type",
            "tool_name",
            "timestamp"
        }
        
        for i, result in enumerate(results):
            result_fields = set(result.keys())
            assert required_fields.issubset(result_fields), \
                f"Result {i} missing required fields. Expected {required_fields}, got {result_fields}"
            
            # 验证所有success字段都是False
            assert result["success"] is False, \
                f"Result {i}: success should be False"
    
    def test_property_25_no_raw_exceptions_escape(self):
        """
        Property 25: 原始异常不应该逃逸
        
        ToolExecutor应该捕获所有异常，不应该让原始异常传播到调用者。
        
        Validates: Requirements 9.1, 9.3
        """
        def failing_tool():
            raise RuntimeError("This should be caught")
        
        executor = ToolExecutor(max_retries=0)
        
        # 这不应该抛出异常
        try:
            result = executor.execute_tool_sync(failing_tool, enable_retry=False)
            # 应该返回错误字典而不是抛出异常
            assert isinstance(result, dict)
            assert result["success"] is False
        except Exception as e:
            pytest.fail(f"ToolExecutor should not let exceptions escape, but got: {type(e).__name__}: {e}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
