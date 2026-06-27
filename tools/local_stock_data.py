"""
本地股票日线数据读取模块
优先从Parquet文件读取，超出范围则fallback到Tushare
"""
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
import pyarrow.parquet as pq

# 数据目录
PARQUET_DIR = Path("/Users/sh-data-03/Desktop/ai agent/Daily_data_parquet")

# 本地数据日期范围
LOCAL_DATA_START = "2010-01-04"  # 最早日期
LOCAL_DATA_END = "2026-04-03"    # 最新日期

# 文件到日期范围的映射
PARQUET_FILES = {
    "daily_2010.parquet": ("2010-01-01", "2010-12-31"),
    "daily_2011.parquet": ("2011-01-01", "2011-12-31"),
    "daily_2012.parquet": ("2012-01-01", "2012-12-31"),
    "daily_2013.parquet": ("2013-01-01", "2013-12-31"),
    "daily_2014.parquet": ("2014-01-01", "2014-12-31"),
    "daily_2015.parquet": ("2015-01-01", "2015-12-31"),
    "daily_2016.parquet": ("2016-01-01", "2016-12-31"),
    "daily_2017.parquet": ("2017-01-01", "2017-12-31"),
    "daily_2018.parquet": ("2018-01-01", "2018-12-31"),
    "daily_2019.parquet": ("2019-01-01", "2019-12-31"),
    "daily_2020.parquet": ("2020-01-01", "2020-12-31"),
    "daily_2021.parquet": ("2021-01-01", "2021-12-31"),
    "daily_2022.parquet": ("2022-01-01", "2022-12-31"),
    "daily_2023-2024.parquet": ("2023-01-01", "2024-12-31"),
    "daily_2025-2026.parquet": ("2025-01-01", "2026-04-03"),
}

# 缓存
_parquet_cache = {}


def _get_ts_code_local(code: str) -> str:
    """将各种格式的股票代码转换为标准格式"""
    if not code:
        return ""
    code = str(code).strip()
    
    # 已经是标准格式
    if '.' in code:
        return code
    
    # 纯数字格式
    code = code.zfill(6)
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith('0') or code.startswith('3'):
        return f"{code}.SZ"
    elif code.startswith('4') or code.startswith('8') or code.startswith('9'):
        return f"{code}.BJ"
    return f"{code}.SH"


def _load_parquet_file(filename: str) -> pd.DataFrame:
    """加载Parquet文件（带缓存）"""
    if filename in _parquet_cache:
        return _parquet_cache[filename]
    
    filepath = PARQUET_DIR / filename
    if filepath.exists():
        df = pd.read_parquet(filepath)
        _parquet_cache[filename] = df
        return df
    return pd.DataFrame()


def get_stock_history_from_local(
    ts_code: str,
    start_date: str,
    end_date: str,
    fields: Optional[str] = None
) -> Dict[str, Any]:
    """
    从本地Parquet文件获取股票历史数据
    
    Args:
        ts_code: 股票代码（如 600519.SH）
        start_date: 开始日期 YYYYMMDD
        end_date: 结束日期 YYYYMMDD
        fields: 需要获取的字段列表
    
    Returns:
        包含数据的字典
    """
    # 转换日期格式
    try:
        sd = datetime.strptime(start_date, "%Y%m%d")
        ed = datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        return {"error": "日期格式错误，应为YYYYMMDD"}
    
    # 转换股票代码
    local_ts_code = _get_ts_code_local(ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''))
    if ts_code.endswith('.SH'):
        local_ts_code = f"{local_ts_code[:6]}.SH"
    elif ts_code.endswith('.SZ'):
        local_ts_code = f"{local_ts_code[:6]}.SZ"
    elif ts_code.endswith('.BJ'):
        local_ts_code = f"{local_ts_code[:6]}.BJ"
    
    # 找出需要读取的文件
    files_to_read = []
    for filename, (file_start, file_end) in PARQUET_FILES.items():
        file_start_dt = datetime.strptime(file_start, "%Y-%m-%d")
        file_end_dt = datetime.strptime(file_end, "%Y-%m-%d")
        
        # 检查日期范围是否有交集
        if not (ed < file_start_dt or sd > file_end_dt):
            files_to_read.append(filename)
    
    if not files_to_read:
        # 日期范围不在本地数据范围内
        return {"need_ifind": True, "error": "查询日期超出本地数据范围"}
    
    # 读取所有相关文件
    all_data = []
    for filename in files_to_read:
        df = _load_parquet_file(filename)
        if not df.empty:
            # 筛选股票和日期
            mask = (df['ts_code'] == local_ts_code) | (df['ts_code'] == ts_code)
            if 'THSCODE' in df.columns:
                # 兼容旧格式
                df['ts_code'] = df['THSCODE']
            filtered = df[mask].copy()
            
            if not filtered.empty:
                # 筛选日期
                filtered = filtered[
                    (filtered['trade_date'] >= pd.Timestamp(sd)) & 
                    (filtered['trade_date'] <= pd.Timestamp(ed))
                ]
                all_data.append(filtered)
    
    if not all_data:
        return {"error": f"未找到股票 {ts_code} 在指定日期范围的数据"}
    
    # 合并数据
    result_df = pd.concat(all_data, ignore_index=True)
    result_df = result_df.sort_values('trade_date')
    
    # 去重
    result_df = result_df.drop_duplicates(subset=['trade_date'], keep='last')
    
    # 转换列名以匹配Tushare格式
    column_mapping = {
        'ts_code': 'ts_code',
        'trade_date': 'trade_date',
        'pre_close': 'pre_close',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'avg_price': 'avg_price',
        'change_amount': 'change',
        'pct_chg': 'pct_chg',
        'vol': 'vol',
        'amount': 'amount',
        'turnover_rate': 'turnover_rate',
    }
    
    # 选择需要的字段
    if fields:
        requested_fields = [f.strip() for f in fields.split(',')]
        # 添加必需字段
        required_fields = ['ts_code', 'trade_date']
        all_needed = list(set(requested_fields + required_fields))
        
        # 映射字段名
        available_cols = []
        for col in all_needed:
            if col in column_mapping:
                orig_col = column_mapping[col]
                if orig_col in result_df.columns:
                    available_cols.append(orig_col)
            elif col in result_df.columns:
                available_cols.append(col)
        
        if available_cols:
            result_df = result_df[available_cols]
    
    # 转换日期格式
    result_df['trade_date'] = pd.to_datetime(result_df['trade_date']).dt.strftime('%Y%m%d').astype(str)
    
    records = result_df.to_dict("records")
    try:
        from tools.ifind.unit_registry import get_units_for_records
        field_units = get_units_for_records(records, source="local_parquet_ifind")
    except Exception:
        field_units = {}
    return {
        "success": True,
        "data": records,
        "count": len(records),
        "data_source": "local_parquet_ifind",
        "date_range": f"{start_date} - {end_date}",
        "_field_units": field_units,
        "_units_source": "local_parquet_ifind",
    }


def check_date_in_local_range(start_date: str, end_date: str) -> bool:
    """检查日期范围是否在本地数据范围内"""
    try:
        sd = datetime.strptime(start_date, "%Y%m%d")
        ed = datetime.strptime(end_date, "%Y%m%d")
        
        local_start = datetime.strptime(LOCAL_DATA_START, "%Y-%m-%d")
        local_end = datetime.strptime(LOCAL_DATA_END, "%Y-%m-%d")
        
        # 检查是否完全在本地数据范围内
        return sd >= local_start and ed <= local_end
    except:
        return False


def get_available_stocks() -> List[str]:
    """获取本地数据中所有可用的股票代码"""
    index_file = PARQUET_DIR / "stock_index.parquet"
    if index_file.exists():
        df = pd.read_parquet(index_file)
        return df['ts_code'].tolist()
    return []


def get_local_data_info() -> Dict[str, Any]:
    """获取本地数据信息"""
    # 读取日期范围
    ranges_file = PARQUET_DIR / "date_ranges.json"
    if ranges_file.exists():
        with open(ranges_file) as f:
            date_ranges = json.load(f)
    else:
        date_ranges = {}
    
    # 获取文件大小
    total_size = sum(f.stat().st_size for f in PARQUET_DIR.glob("*.parquet"))
    
    return {
        "data_dir": str(PARQUET_DIR),
        "date_range": f"{LOCAL_DATA_START} to {LOCAL_DATA_END}",
        "total_files": len(list(PARQUET_DIR.glob("*.parquet"))),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "date_ranges": date_ranges
    }


if __name__ == "__main__":
    # 测试
    print("本地数据信息:")
    info = get_local_data_info()
    for k, v in info.items():
        print(f"  {k}: {v}")
    
    print("\n测试读取股票数据:")
    result = get_stock_history_from_local(
        "600519.SH", 
        "20200101", 
        "20200110",
        "trade_date,open,high,low,close,vol"
    )
    print(f"  成功: {result.get('success')}")
    print(f"  数据量: {result.get('count')}")
    if result.get('data'):
        print(f"  首条: {result['data'][0]}")