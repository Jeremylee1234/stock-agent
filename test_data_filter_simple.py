#!/usr/bin/env python3
"""
简单测试数据分析过滤工具
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.data_filter_tools import DataFilterTools
import json

def create_sample_data():
    """创建测试数据"""
    sample_data = {
        "success": True,
        "data": [
            {
                "ts_code": "600519.SH",
                "trade_date": "20260105",
                "close": 1750.50,
                "pct_chg": -9.95,
                "turnover_rate": 0.005,
                "vol": 50000,
                "amount": 87525000
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260105",
                "close": 9.50,
                "pct_chg": -9.90,
                "turnover_rate": 0.008,
                "vol": 1000000,
                "amount": 9500000
            },
            {
                "ts_code": "300750.SZ",
                "trade_date": "20260105",
                "close": 200.00,
                "pct_chg": -5.00,
                "turnover_rate": 0.015,
                "vol": 200000,
                "amount": 40000000
            },
            {
                "ts_code": "600036.SH",
                "trade_date": "20260104",
                "close": 35.00,
                "pct_chg": -9.95,
                "turnover_rate": 0.012,
                "vol": 800000,
                "amount": 28000000
            },
            {
                "ts_code": "000858.SZ",
                "trade_date": "20260104",
                "close": 150.00,
                "pct_chg": -2.00,
                "turnover_rate": 0.020,
                "vol": 300000,
                "amount": 45000000
            }
        ],
        "count": 5
    }
    return json.dumps(sample_data)

def test_direct():
    """直接测试DataFilterTools类"""
    print("=" * 60)
    print("直接测试DataFilterTools类")
    print("=" * 60)
    
    sample_data = create_sample_data()
    
    # 测试1：过滤跌停板股票
    print("\n1. 测试过滤跌停板股票:")
    filter_conditions = [
        {"column": "pct_chg", "operator": "le", "value": -9.9}
    ]
    result = DataFilterTools.filter_dataframe(sample_data, filter_conditions)
    
    if result.get('success'):
        print(f"   ✅ 成功过滤到 {result.get('filtered_count')} 只跌停板股票")
        print(f"   原始数据: {result.get('original_count')} 条")
        print(f"   过滤后: {result.get('filtered_count')} 条")
        for item in result.get('data', [])[:3]:
            print(f"     - {item['ts_code']}: {item['pct_chg']}%")
    else:
        print(f"   ❌ 失败: {result.get('error')}")
    
    # 测试2：过滤换手率低于1%的股票
    print("\n2. 测试过滤低换手率股票:")
    filter_conditions = [
        {"column": "turnover_rate", "operator": "lt", "value": 0.01}
    ]
    result = DataFilterTools.filter_dataframe(sample_data, filter_conditions)
    
    if result.get('success'):
        print(f"   ✅ 成功过滤到 {result.get('filtered_count')} 只低换手率股票")
        for item in result.get('data', []):
            print(f"     - {item['ts_code']}: 换手率={item['turnover_rate']*100:.2f}%")
    else:
        print(f"   ❌ 失败: {result.get('error')}")
    
    # 测试3：过滤跌停板且换手率低于1%的股票
    print("\n3. 测试过滤跌停板且低换手率股票:")
    filter_conditions = [
        {"column": "pct_chg", "operator": "le", "value": -9.9, "logical": "and"},
        {"column": "turnover_rate", "operator": "lt", "value": 0.01}
    ]
    result = DataFilterTools.filter_dataframe(sample_data, filter_conditions)
    
    if result.get('success'):
        count = result.get('filtered_count', 0)
        print(f"   ✅ 成功过滤到 {count} 只跌停板且低换手率股票")
        if count > 0:
            for item in result.get('data', []):
                print(f"     - {item['ts_code']}: 跌幅={item['pct_chg']}%, 换手率={item['turnover_rate']*100:.2f}%")
        else:
            print("     没有符合条件的股票")
    else:
        print(f"   ❌ 失败: {result.get('error')}")
    
    # 测试4：排序
    print("\n4. 测试排序（按涨跌幅降序）:")
    result = DataFilterTools.sort_dataframe(sample_data, ["pct_chg"], False)
    
    if result.get('success'):
        print(f"   ✅ 排序成功")
        print("   排序结果:")
        for i, item in enumerate(result.get('data', [])[:5], 1):
            print(f"     {i}. {item['ts_code']}: {item['pct_chg']}%")
    else:
        print(f"   ❌ 失败: {result.get('error')}")
    
    # 测试5：计算指标
    print("\n5. 测试计算指标:")
    calculations = [
        {"type": "count", "name": "股票数量"},
        {"type": "mean", "column": "pct_chg", "name": "平均涨跌幅"},
        {"type": "min", "column": "pct_chg", "name": "最大跌幅"},
        {"type": "max", "column": "pct_chg", "name": "最大涨幅"},
        {"type": "sum", "column": "vol", "name": "总成交量"}
    ]
    result = DataFilterTools.calculate_metrics(sample_data, calculations)
    
    if result.get('success'):
        print(f"   ✅ 计算成功")
        metrics = result.get('metrics', {})
        for name, value in metrics.items():
            print(f"     {name}: {value}")
    else:
        print(f"   ❌ 失败: {result.get('error')}")
    
    # 测试6：综合分析
    print("\n6. 测试综合分析（模拟用户问题）:")
    analysis_steps = [
        {
            "step_type": "filter",
            "parameters": {
                "filter_conditions": [
                    {"column": "turnover_rate", "operator": "lt", "value": 0.01},
                    {"column": "pct_chg", "operator": "le", "value": -9.9}
                ]
            }
        },
        {
            "step_type": "sort",
            "parameters": {
                "sort_columns": ["trade_date"],
                "ascending": False
            }
        }
    ]
    
    # 手动执行分析步骤
    current_data = sample_data
    steps_results = []
    
    for i, step in enumerate(analysis_steps):
        step_type = step.get('step_type')
        parameters = step.get('parameters', {})
        
        if step_type == 'filter':
            filter_conditions = parameters.get('filter_conditions', [])
            result = DataFilterTools.filter_dataframe(current_data, filter_conditions)
            if result.get('success'):
                current_data = result['data']
            steps_results.append({
                'step': i + 1,
                'type': 'filter',
                'result': result.get('filtered_count', 0) if result.get('success') else result.get('error'),
                'conditions': filter_conditions
            })
            
        elif step_type == 'sort':
            sort_columns = parameters.get('sort_columns', [])
            ascending = parameters.get('ascending', True)
            result = DataFilterTools.sort_dataframe(current_data, sort_columns, ascending)
            if result.get('success'):
                current_data = result['data']
            steps_results.append({
                'step': i + 1,
                'type': 'sort',
                'result': '成功' if result.get('success') else result.get('error'),
                'columns': sort_columns
            })
    
    print(f"   ✅ 分析成功")
    print(f"   最终数据量: {len(current_data) if isinstance(current_data, list) else 0} 条")
    print(f"   分析步骤结果:")
    for step in steps_results:
        print(f"     步骤{step['step']} ({step['type']}): {step['result']}")
    
    if isinstance(current_data, list) and len(current_data) > 0:
        print(f"   符合条件的股票:")
        for item in current_data:
            print(f"     - {item['ts_code']} ({item['trade_date']}): 跌幅={item['pct_chg']}%, 换手率={item['turnover_rate']*100:.2f}%")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

def test_tool_integration():
    """测试工具集成"""
    print("\n" + "=" * 60)
    print("测试工具集成")
    print("=" * 60)
    
    # 导入工具函数
    from tools.data_filter_tools import tool_filter_stock_data
    
    sample_data = create_sample_data()
    
    print("测试工具装饰器函数:")
    # 直接调用工具函数（不是装饰器）
    tool_func = tool_filter_stock_data.func
    filter_conditions = [
        {"column": "pct_chg", "operator": "le", "value": -9.9}
    ]
    
    result_str = tool_func(sample_data, filter_conditions)
    result = json.loads(result_str)
    
    if result.get('success'):
        print(f"   ✅ 工具函数调用成功")
        print(f"   过滤到 {result.get('filtered_count')} 条数据")
    else:
        print(f"   ❌ 失败: {result.get('error')}")

if __name__ == "__main__":
    test_direct()
    test_tool_integration()