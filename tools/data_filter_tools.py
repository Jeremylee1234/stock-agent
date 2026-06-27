"""
数据分析过滤工具 - 供agent使用
"""
import json
import pandas as pd
from typing import Dict, List, Any, Optional, Union
from langchain_core.tools import tool


class DataFilterTools:
    """数据分析过滤工具类"""
    
    @staticmethod
    def filter_dataframe(
        data: Union[str, List[Dict], pd.DataFrame],
        filter_conditions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        对数据进行过滤
        
        Args:
            data: 数据，可以是JSON字符串、字典列表或DataFrame
            filter_conditions: 过滤条件列表，每个条件格式：
                {
                    "column": "列名",
                    "operator": "操作符",  # eq, ne, gt, lt, ge, le, contains, in, not_in
                    "value": 值,
                    "logical": "and"  # 或 "or"（与下一个条件的关系）
                }
        
        Returns:
            过滤后的数据
        """
        try:
            # 转换数据为DataFrame
            if isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    if isinstance(data_dict, dict) and 'data' in data_dict:
                        df = pd.DataFrame(data_dict['data'])
                    elif isinstance(data_dict, list):
                        df = pd.DataFrame(data_dict)
                    else:
                        df = pd.DataFrame([data_dict])
                except:
                    df = pd.DataFrame()
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                return {"error": "不支持的数据格式"}
            
            if df.empty:
                return {"error": "数据为空"}
            
            # 应用过滤条件
            filtered_df = df.copy()
            
            for i, condition in enumerate(filter_conditions):
                column = condition.get('column')
                operator = condition.get('operator', 'eq')
                value = condition.get('value')
                logical = condition.get('logical', 'and')
                
                if column not in df.columns:
                    continue
                
                # 根据操作符创建过滤条件
                if operator == 'eq':
                    mask = filtered_df[column] == value
                elif operator == 'ne':
                    mask = filtered_df[column] != value
                elif operator == 'gt':
                    mask = filtered_df[column] > value
                elif operator == 'lt':
                    mask = filtered_df[column] < value
                elif operator == 'ge':
                    mask = filtered_df[column] >= value
                elif operator == 'le':
                    mask = filtered_df[column] <= value
                elif operator == 'contains':
                    mask = filtered_df[column].astype(str).str.contains(str(value), case=False, na=False)
                elif operator == 'in':
                    if isinstance(value, list):
                        mask = filtered_df[column].isin(value)
                    else:
                        mask = filtered_df[column] == value
                elif operator == 'not_in':
                    if isinstance(value, list):
                        mask = ~filtered_df[column].isin(value)
                    else:
                        mask = filtered_df[column] != value
                else:
                    continue
                
                # 应用逻辑关系
                if i == 0:
                    combined_mask = mask
                else:
                    if logical == 'and':
                        combined_mask = combined_mask & mask
                    else:  # 'or'
                        combined_mask = combined_mask | mask
            
            filtered_df = filtered_df[combined_mask] if 'combined_mask' in locals() else filtered_df
            
            return {
                "success": True,
                "data": filtered_df.to_dict('records'),
                "count": len(filtered_df),
                "original_count": len(df),
                "filtered_count": len(filtered_df),
                "filter_conditions": filter_conditions
            }
            
        except Exception as e:
            return {"error": f"过滤数据时出错: {str(e)}"}
    
    @staticmethod
    def sort_dataframe(
        data: Union[str, List[Dict], pd.DataFrame],
        sort_columns: List[str],
        ascending: Union[bool, List[bool]] = True
    ) -> Dict[str, Any]:
        """
        对数据进行排序
        
        Args:
            data: 数据
            sort_columns: 排序的列名列表
            ascending: 是否升序，可以是单个bool或列表
        
        Returns:
            排序后的数据
        """
        try:
            # 转换数据为DataFrame
            if isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    if isinstance(data_dict, dict) and 'data' in data_dict:
                        df = pd.DataFrame(data_dict['data'])
                    elif isinstance(data_dict, list):
                        df = pd.DataFrame(data_dict)
                    else:
                        df = pd.DataFrame([data_dict])
                except:
                    df = pd.DataFrame()
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                return {"error": "不支持的数据格式"}
            
            if df.empty:
                return {"error": "数据为空"}
            
            # 确保sort_columns在DataFrame中
            valid_columns = [col for col in sort_columns if col in df.columns]
            if not valid_columns:
                return {"error": "没有有效的排序列"}
            
            # 排序
            sorted_df = df.sort_values(by=valid_columns, ascending=ascending)
            
            return {
                "success": True,
                "data": sorted_df.to_dict('records'),
                "count": len(sorted_df),
                "sort_columns": valid_columns,
                "ascending": ascending
            }
            
        except Exception as e:
            return {"error": f"排序数据时出错: {str(e)}"}
    
    @staticmethod
    def calculate_metrics(
        data: Union[str, List[Dict], pd.DataFrame],
        calculations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        计算数据指标
        
        Args:
            data: 数据
            calculations: 计算列表，每个计算格式：
                {
                    "type": "统计类型",  # count, sum, mean, median, min, max, std, var, etc.
                    "column": "列名",  # 可选，某些统计需要
                    "name": "结果名称"  # 结果字段名
                }
        
        Returns:
            计算结果
        """
        try:
            # 转换数据为DataFrame
            if isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    if isinstance(data_dict, dict) and 'data' in data_dict:
                        df = pd.DataFrame(data_dict['data'])
                    elif isinstance(data_dict, list):
                        df = pd.DataFrame(data_dict)
                    else:
                        df = pd.DataFrame([data_dict])
                except:
                    df = pd.DataFrame()
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                return {"error": "不支持的数据格式"}
            
            if df.empty:
                return {"error": "数据为空"}
            
            results = {}
            
            for calc in calculations:
                calc_type = calc.get('type')
                column = calc.get('column')
                name = calc.get('name', f"{calc_type}_{column}" if column else calc_type)
                
                try:
                    if calc_type == 'count':
                        results[name] = len(df)
                    elif calc_type == 'sum' and column in df.columns:
                        results[name] = float(df[column].sum())
                    elif calc_type == 'mean' and column in df.columns:
                        results[name] = float(df[column].mean())
                    elif calc_type == 'median' and column in df.columns:
                        results[name] = float(df[column].median())
                    elif calc_type == 'min' and column in df.columns:
                        results[name] = float(df[column].min())
                    elif calc_type == 'max' and column in df.columns:
                        results[name] = float(df[column].max())
                    elif calc_type == 'std' and column in df.columns:
                        results[name] = float(df[column].std())
                    elif calc_type == 'var' and column in df.columns:
                        results[name] = float(df[column].var())
                    elif calc_type == 'first' and column in df.columns:
                        results[name] = df[column].iloc[0] if not df.empty else None
                    elif calc_type == 'last' and column in df.columns:
                        results[name] = df[column].iloc[-1] if not df.empty else None
                    elif calc_type == 'unique_count' and column in df.columns:
                        results[name] = int(df[column].nunique())
                    elif calc_type == 'missing_count' and column in df.columns:
                        results[name] = int(df[column].isna().sum())
                except Exception as e:
                    results[name] = f"计算错误: {str(e)}"
            
            return {
                "success": True,
                "metrics": results,
                "calculations": calculations
            }
            
        except Exception as e:
            return {"error": f"计算指标时出错: {str(e)}"}
    
    @staticmethod
    def group_and_aggregate(
        data: Union[str, List[Dict], pd.DataFrame],
        group_by: List[str],
        aggregations: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        分组和聚合数据
        
        Args:
            data: 数据
            group_by: 分组的列名列表
            aggregations: 聚合操作，格式 {"列名": ["聚合函数1", "聚合函数2"]}
        
        Returns:
            分组聚合结果
        """
        try:
            # 转换数据为DataFrame
            if isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    if isinstance(data_dict, dict) and 'data' in data_dict:
                        df = pd.DataFrame(data_dict['data'])
                    elif isinstance(data_dict, list):
                        df = pd.DataFrame(data_dict)
                    else:
                        df = pd.DataFrame([data_dict])
                except:
                    df = pd.DataFrame()
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                return {"error": "不支持的数据格式"}
            
            if df.empty:
                return {"error": "数据为空"}
            
            # 确保分组列存在
            valid_group_cols = [col for col in group_by if col in df.columns]
            if not valid_group_cols:
                return {"error": "没有有效的分组列"}
            
            # 创建聚合字典
            agg_dict = {}
            for column, funcs in aggregations.items():
                if column in df.columns:
                    for func in funcs:
                        agg_name = f"{column}_{func}"
                        if func == 'sum':
                            agg_dict[agg_name] = (column, 'sum')
                        elif func == 'mean':
                            agg_dict[agg_name] = (column, 'mean')
                        elif func == 'count':
                            agg_dict[agg_name] = (column, 'count')
                        elif func == 'min':
                            agg_dict[agg_name] = (column, 'min')
                        elif func == 'max':
                            agg_dict[agg_name] = (column, 'max')
                        elif func == 'std':
                            agg_dict[agg_name] = (column, 'std')
                        elif func == 'first':
                            agg_dict[agg_name] = (column, 'first')
                        elif func == 'last':
                            agg_dict[agg_name] = (column, 'last')
            
            if not agg_dict:
                return {"error": "没有有效的聚合列"}
            
            # 分组聚合
            grouped = df.groupby(valid_group_cols).agg(**{k: v for k, v in agg_dict.items()})
            grouped = grouped.reset_index()
            
            return {
                "success": True,
                "data": grouped.to_dict('records'),
                "group_by": valid_group_cols,
                "aggregations": aggregations,
                "count": len(grouped)
            }
            
        except Exception as e:
            return {"error": f"分组聚合时出错: {str(e)}"}


# ============================================================================
# LangChain 工具定义
# ============================================================================

@tool(description="""对获取到的股票数据进行过滤。
data: 需要过滤的数据，通常是工具调用返回的JSON数据
filter_conditions: 过滤条件列表，每个条件包含：
  - column: 列名（如 'turnover_rate', 'pct_chg', 'close'）
  - operator: 操作符 ('eq'等于, 'ne'不等于, 'gt'大于, 'lt'小于, 'ge'大于等于, 'le'小于等于, 'contains'包含, 'in'在列表中, 'not_in'不在列表中)
  - value: 比较值
  - logical: 与下一个条件的逻辑关系 ('and' 或 'or')
示例：过滤换手率低于1%且跌幅超过9%的股票：
  [
    {"column": "turnover_rate", "operator": "lt", "value": 0.01, "logical": "and"},
    {"column": "pct_chg", "operator": "lt", "value": -9.0}
  ]
注意：数据中需要包含指定的列才能进行过滤。""")
def tool_filter_stock_data(data: str, filter_conditions: list) -> str:
    """过滤股票数据"""
    result = DataFilterTools.filter_dataframe(data, filter_conditions)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(description="""对股票数据进行排序。
data: 需要排序的数据，通常是工具调用返回的JSON数据
sort_columns: 排序的列名列表，如 ['pct_chg', 'vol'] 表示先按涨跌幅排序，再按成交量排序
ascending: 是否升序，True为升序，False为降序，也可以是列表如 [True, False] 表示第一列升序第二列降序
示例：按涨跌幅降序排列：sort_columns=['pct_chg'], ascending=False
注意：数据中需要包含指定的列才能进行排序。""")
def tool_sort_stock_data(data: str, sort_columns: list, ascending: bool = True) -> str:
    """排序股票数据"""
    result = DataFilterTools.sort_dataframe(data, sort_columns, ascending)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(description="""计算股票数据的统计指标。
data: 需要计算的数据，通常是工具调用返回的JSON数据
calculations: 计算列表，每个计算包含：
  - type: 统计类型 ('count'计数, 'sum'求和, 'mean'平均值, 'median'中位数, 'min'最小值, 'max'最大值, 'std'标准差, 'var'方差, 'first'第一个值, 'last'最后一个值, 'unique_count'唯一值计数, 'missing_count'缺失值计数)
  - column: 列名（某些统计类型需要）
  - name: 结果名称（可选）
示例：计算平均涨跌幅和最大成交量：
  [
    {"type": "mean", "column": "pct_chg", "name": "平均涨跌幅"},
    {"type": "max", "column": "vol", "name": "最大成交量"},
    {"type": "count", "name": "股票数量"}
  ]""")
def tool_calculate_stock_metrics(data: str, calculations: list) -> str:
    """计算股票数据指标"""
    result = DataFilterTools.calculate_metrics(data, calculations)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(description="""对股票数据进行分组和聚合分析。
data: 需要分组的数据，通常是工具调用返回的JSON数据
group_by: 分组的列名列表，如 ['industry', 'trade_date']
aggregations: 聚合操作，格式 {"列名": ["聚合函数"]}，聚合函数包括：'sum', 'mean', 'count', 'min', 'max', 'std', 'first', 'last'
示例：按行业分组，计算每个行业的平均涨跌幅和总成交量：
  {
    "pct_chg": ["mean"],
    "vol": ["sum"]
  }
注意：数据中需要包含指定的列才能进行分组聚合。""")
def tool_group_stock_data(data: str, group_by: list, aggregations: dict) -> str:
    """分组聚合股票数据"""
    result = DataFilterTools.group_and_aggregate(data, group_by, aggregations)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(description="""分析和筛选符合特定条件的股票。
这是一个高级工具，可以组合多个操作：获取数据、过滤、排序、计算指标。
data: 原始数据（通常来自其他工具如 tool_get_stock_history）
analysis_steps: 分析步骤列表，每个步骤包含：
  - step_type: 步骤类型 ('filter'过滤, 'sort'排序, 'calculate'计算, 'group'分组)
  - parameters: 步骤参数
示例：查找2026年以来换手率低于1%的跌停板股票：
  [
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
注意：这是一个组合工具，用于复杂的数据分析任务。""")
def tool_analyze_stock_data(data: str, analysis_steps: list) -> str:
    """分析股票数据（组合操作）"""
    try:
        current_data = data
        results = []
        
        for i, step in enumerate(analysis_steps):
            step_type = step.get('step_type')
            parameters = step.get('parameters', {})
            
            if step_type == 'filter':
                filter_conditions = parameters.get('filter_conditions', [])
                result = DataFilterTools.filter_dataframe(current_data, filter_conditions)
                if result.get('success'):
                    current_data = result['data']
                results.append({
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
                results.append({
                    'step': i + 1,
                    'type': 'sort',
                    'result': '成功' if result.get('success') else result.get('error'),
                    'columns': sort_columns
                })
                
            elif step_type == 'calculate':
                calculations = parameters.get('calculations', [])
                result = DataFilterTools.calculate_metrics(current_data, calculations)
                results.append({
                    'step': i + 1,
                    'type': 'calculate',
                    'result': result.get('metrics') if result.get('success') else result.get('error'),
                    'calculations': calculations
                })
                
            elif step_type == 'group':
                group_by = parameters.get('group_by', [])
                aggregations = parameters.get('aggregations', {})
                result = DataFilterTools.group_and_aggregate(current_data, group_by, aggregations)
                if result.get('success'):
                    current_data = result['data']
                results.append({
                    'step': i + 1,
                    'type': 'group',
                    'result': result.get('count', 0) if result.get('success') else result.get('error'),
                    'group_by': group_by
                })
        
        final_result = {
            "success": True,
            "analysis_steps": results,
            "final_data": current_data if isinstance(current_data, list) else [],
            "final_data_count": len(current_data) if isinstance(current_data, list) else 0
        }
        
        return json.dumps(final_result, ensure_ascii=False, default=str)
        
    except Exception as e:
        return json.dumps({"error": f"分析数据时出错: {str(e)}"}, ensure_ascii=False)


def get_data_filter_tools():
    """获取所有数据分析过滤工具"""
    return [
        tool_filter_stock_data,
        tool_sort_stock_data,
        tool_calculate_stock_metrics,
        tool_group_stock_data,
        tool_analyze_stock_data
    ]