"""
数据分析过滤工具
让agent能够对获取到的数据进行过滤、排序、计算等操作
"""
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
from datetime import datetime


class DataFilter:
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
            # 转��数据为DataFrame
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