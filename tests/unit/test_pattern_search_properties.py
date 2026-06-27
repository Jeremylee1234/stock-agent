"""
Property-Based Tests for Pattern Search Engine

Tests Property 31: 模式搜索结果完整性
Validates: Requirements 11.1

这些测试验证历史模式搜索引擎返回的结果具有完整的数据结构。
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from datetime import datetime, timedelta
from typing import Dict, Any, List

from tools.pattern_search import PatternSearchEngine
from config.settings import get_settings


# 定义策略
@st.composite
def valid_date_range_strategy(draw):
    """生成有效的日期范围"""
    # 生成过去2年内的日期
    days_ago_end = draw(st.integers(min_value=1, max_value=365))
    days_ago_start = draw(st.integers(min_value=days_ago_end + 30, max_value=days_ago_end + 730))
    
    end_date = datetime.now() - timedelta(days=days_ago_end)
    start_date = datetime.now() - timedelta(days=days_ago_start)
    
    return (
        start_date.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d")
    )


@st.composite
def price_pattern_strategy(draw):
    """生成价格形态模式描述"""
    patterns = [
        "连续2天涨停",
        "连续3天涨停",
        "连续2天跌停",
        "V型反转",
        "W底",
        "头肩顶"
    ]
    return draw(st.sampled_from(patterns))


@st.composite
def indicator_pattern_strategy(draw):
    """生成技术指标模式描述和类型"""
    indicator_patterns = [
        ("MACD", "金叉"),
        ("MACD", "死叉"),
        ("KDJ", "超买"),
        ("KDJ", "超卖"),
        ("KDJ", "金叉"),
        ("RSI", "超买"),
        ("RSI", "超卖"),
        ("MA", "多头排列"),
        ("MA", "空头排列"),
    ]
    indicator_type, pattern_desc = draw(st.sampled_from(indicator_patterns))
    return indicator_type, pattern_desc


@st.composite
def chip_pattern_strategy(draw):
    """生成筹码分布模式描述"""
    patterns = [
        "筹码集中度上升",
        "主力资金流入",
    ]
    return draw(st.sampled_from(patterns))


@st.composite
def max_results_strategy(draw):
    """生成合理的最大结果数"""
    return draw(st.integers(min_value=1, max_value=50))


class TestPatternSearchResultCompleteness:
    """测试模式搜索结果完整性"""
    
    @pytest.fixture(scope="class")
    def pattern_engine(self):
        """创建模式搜索引擎实例"""
        # 从配置获取token
        config = get_settings()
        token = config.get_tushare_token()
        
        if not token:
            pytest.skip("TUSHARE_TOKEN not configured")
        
        return PatternSearchEngine(tushare_token=token, enable_cache=True)
    
    @given(
        price_pattern_strategy(),
        valid_date_range_strategy(),
        max_results_strategy()
    )
    @settings(
        max_examples=20,  # 减少示例数以避免API限流
        deadline=60000,  # 60秒超时
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_price_pattern_result_structure(
        self,
        pattern_engine,
        pattern_desc,
        date_range,
        max_results
    ):
        """
        Property 31: 价格模式搜索结果完整性
        
        对于任何有效的价格模式搜索，返回结果应该包含：
        - matches: 列表类型
        - statistics: 字典类型
        
        Validates: Requirements 11.1
        """
        start_date, end_date = date_range
        
        # 执行搜索
        result = pattern_engine.search_price_pattern(
            pattern_desc=pattern_desc,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results
        )
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = ["matches", "statistics"]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in search result. Got: {result.keys()}"
        
        # 验证matches是列表
        assert isinstance(result["matches"], list), \
            f"matches must be list, got {type(result['matches'])}"
        
        # 验证statistics是字典
        assert isinstance(result["statistics"], dict), \
            f"statistics must be dict, got {type(result['statistics'])}"
        
        # 如果搜索成功，验证额外字段
        if result.get("success", False):
            assert "pattern_description" in result, \
                "Successful result should contain pattern_description"
            
            assert "search_params" in result, \
                "Successful result should contain search_params"
            
            # 验证search_params结构
            search_params = result["search_params"]
            assert isinstance(search_params, dict), \
                "search_params must be dict"
            
            assert "start_date" in search_params, \
                "search_params should contain start_date"
            
            assert "end_date" in search_params, \
                "search_params should contain end_date"
            
            assert "max_results" in search_params, \
                "search_params should contain max_results"
    
    @given(
        indicator_pattern_strategy(),
        valid_date_range_strategy(),
        max_results_strategy()
    )
    @settings(
        max_examples=20,
        deadline=60000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_indicator_pattern_result_structure(
        self,
        pattern_engine,
        indicator_and_pattern,
        date_range,
        max_results
    ):
        """
        Property 31: 技术指标模式搜索结果完整性
        
        对于任何有效的技术指标模式搜索，返回结果应该包含：
        - matches: 列表类型
        - statistics: 字典类型
        
        Validates: Requirements 11.1
        """
        indicator_type, pattern_desc = indicator_and_pattern
        start_date, end_date = date_range
        
        # 执行搜索
        result = pattern_engine.search_indicator_pattern(
            pattern_desc=pattern_desc,
            indicator_type=indicator_type,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results
        )
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = ["matches", "statistics"]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in search result. Got: {result.keys()}"
        
        # 验证matches是列表
        assert isinstance(result["matches"], list), \
            f"matches must be list, got {type(result['matches'])}"
        
        # 验证statistics是字典
        assert isinstance(result["statistics"], dict), \
            f"statistics must be dict, got {type(result['statistics'])}"
        
        # 如果搜索成功，验证额外字段
        if result.get("success", False):
            assert "pattern_description" in result, \
                "Successful result should contain pattern_description"
            
            assert "indicator_type" in result, \
                "Successful result should contain indicator_type"
            
            assert "search_params" in result, \
                "Successful result should contain search_params"
    
    @given(
        chip_pattern_strategy(),
        valid_date_range_strategy(),
        max_results_strategy()
    )
    @settings(
        max_examples=15,
        deadline=60000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_chip_pattern_result_structure(
        self,
        pattern_engine,
        pattern_desc,
        date_range,
        max_results
    ):
        """
        Property 31: 筹码分布模式搜索结果完整性
        
        对于任何有效的筹码分布模式搜索，返回结果应该包含：
        - matches: 列表类型
        - statistics: 字典类型
        
        Validates: Requirements 11.1
        """
        start_date, end_date = date_range
        
        # 执行搜索
        result = pattern_engine.search_chip_pattern(
            pattern_desc=pattern_desc,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results
        )
        
        # 验证返回的是字典
        assert isinstance(result, dict), \
            f"Expected dict, got {type(result)}"
        
        # 验证必需字段存在
        required_fields = ["matches", "statistics"]
        
        for field in required_fields:
            assert field in result, \
                f"Missing required field '{field}' in search result. Got: {result.keys()}"
        
        # 验证matches是列表
        assert isinstance(result["matches"], list), \
            f"matches must be list, got {type(result['matches'])}"
        
        # 验证statistics是字典
        assert isinstance(result["statistics"], dict), \
            f"statistics must be dict, got {type(result['statistics'])}"
    
    @given(
        price_pattern_strategy(),
        valid_date_range_strategy()
    )
    @settings(
        max_examples=15,
        deadline=60000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_statistics_contains_total_matches(
        self,
        pattern_engine,
        pattern_desc,
        date_range
    ):
        """
        Property 31: 统计信息包含匹配总数
        
        对于任何模式搜索，statistics字典应该包含total_matches字段。
        
        Validates: Requirements 11.1
        """
        start_date, end_date = date_range
        
        # 执行搜索
        result = pattern_engine.search_price_pattern(
            pattern_desc=pattern_desc,
            start_date=start_date,
            end_date=end_date,
            max_results=10
        )
        
        # 验证statistics包含total_matches
        statistics = result.get("statistics", {})
        
        assert "total_matches" in statistics, \
            f"statistics should contain total_matches. Got: {statistics.keys()}"
        
        # 验证total_matches是整数
        total_matches = statistics["total_matches"]
        assert isinstance(total_matches, int), \
            f"total_matches must be int, got {type(total_matches)}"
        
        # 验证total_matches非负
        assert total_matches >= 0, \
            f"total_matches must be non-negative, got {total_matches}"
        
        # 验证total_matches与matches列表长度一致
        matches = result.get("matches", [])
        assert total_matches == len(matches), \
            f"total_matches ({total_matches}) should equal len(matches) ({len(matches)})"
    
    @given(
        price_pattern_strategy(),
        valid_date_range_strategy(),
        max_results_strategy()
    )
    @settings(
        max_examples=15,
        deadline=60000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_matches_respect_max_results(
        self,
        pattern_engine,
        pattern_desc,
        date_range,
        max_results
    ):
        """
        Property 31: 匹配结果数量不超过max_results
        
        对于任何模式搜索，返回的matches列表长度不应超过max_results参数。
        
        Validates: Requirements 11.1
        """
        start_date, end_date = date_range
        
        # 执行搜索
        result = pattern_engine.search_price_pattern(
            pattern_desc=pattern_desc,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results
        )
        
        # 验证matches长度不超过max_results
        matches = result.get("matches", [])
        
        assert len(matches) <= max_results, \
            f"len(matches) ({len(matches)}) should not exceed max_results ({max_results})"
    
    @given(price_pattern_strategy())
    @settings(
        max_examples=10,
        deadline=60000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_error_result_has_required_fields(
        self,
        pattern_engine,
        pattern_desc
    ):
        """
        Property 31: 错误结果也包含必需字段
        
        即使搜索失败（如Tushare不可用），返回结果也应该包含
        matches和statistics字段（可能为空）。
        
        Validates: Requirements 11.1
        """
        # 使用无效的日期范围触发错误
        result = pattern_engine.search_price_pattern(
            pattern_desc=pattern_desc,
            start_date="invalid_date",
            end_date="invalid_date",
            max_results=10
        )
        
        # 即使失败，也应该有基本结构
        assert isinstance(result, dict), \
            "Result should be dict even on error"
        
        assert "matches" in result, \
            "Error result should contain matches field"
        
        assert "statistics" in result, \
            "Error result should contain statistics field"
        
        # 错误情况下，matches应该是空列表
        assert isinstance(result["matches"], list), \
            "matches should be list even on error"
    
    def test_property_31_unavailable_tushare_returns_complete_structure(
        self
    ):
        """
        Property 31: Tushare不可用时返回完整结构
        
        当Tushare未配置或不可用时，搜索应该返回包含
        matches和statistics的完整结构。
        
        Validates: Requirements 11.1
        """
        # 创建没有token的引擎
        engine = PatternSearchEngine(tushare_token=None, enable_cache=False)
        
        # 执行搜索
        result = engine.search_price_pattern(
            pattern_desc="连续3天涨停",
            max_results=10
        )
        
        # 验证返回完整结构
        assert isinstance(result, dict), \
            "Result should be dict"
        
        assert "matches" in result, \
            "Result should contain matches"
        
        assert "statistics" in result, \
            "Result should contain statistics"
        
        assert "success" in result, \
            "Result should contain success field"
        
        # 应该标记为失败
        assert result["success"] is False, \
            "Result should indicate failure when Tushare unavailable"
        
        # 应该包含错误信息
        assert "error" in result, \
            "Result should contain error message"
    
    @given(
        st.lists(
            price_pattern_strategy(),
            min_size=2,
            max_size=3,
            unique=True
        ),
        valid_date_range_strategy()
    )
    @settings(
        max_examples=10,
        deadline=90000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_property_31_multiple_searches_consistent_structure(
        self,
        pattern_engine,
        pattern_list,
        date_range
    ):
        """
        Property 31: 多次搜索结果结构一致性
        
        对于多个不同的模式搜索，所有结果应该具有相同的基本结构。
        
        Validates: Requirements 11.1
        """
        start_date, end_date = date_range
        results = []
        
        # 执行多次搜索
        for pattern_desc in pattern_list:
            result = pattern_engine.search_price_pattern(
                pattern_desc=pattern_desc,
                start_date=start_date,
                end_date=end_date,
                max_results=5
            )
            results.append(result)
        
        # 验证所有结果都有相同的必需字段
        required_fields = {"matches", "statistics"}
        
        for i, result in enumerate(results):
            result_fields = set(result.keys())
            assert required_fields.issubset(result_fields), \
                f"Result {i} missing required fields. Expected {required_fields}, got {result_fields}"
            
            # 验证字段类型一致
            assert isinstance(result["matches"], list), \
                f"Result {i}: matches should be list"
            
            assert isinstance(result["statistics"], dict), \
                f"Result {i}: statistics should be dict"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
