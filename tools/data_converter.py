#!/usr/bin/env python3
"""
将A股日线CSV数据转换为Parquet格式，并建立索引
提高查询效率
"""
import os
import glob
import pandas as pd
from pathlib import Path
from datetime import datetime
import pyarrow as pa
import pyarrow.parquet as pq

# 数据目录
DATA_DIR = Path("/Users/sh-data-03/Desktop/ai agent/Daily_data")
OUTPUT_DIR = Path("/Users/sh-data-03/Desktop/ai agent/Daily_data_parquet")

# CSV文件到年份的映射
CSV_FILES = {
    "ifind_daily_forward1_2010.csv": "2010",
    "ifind_daily_forward1_2011.csv": "2011",
    "ifind_daily_forward1_2012.csv": "2012",
    "ifind_daily_forward1_2013.csv": "2013",
    "ifind_daily_forward1_2014.csv": "2014",
    "ifind_daily_forward1_2015.csv": "2015",
    "ifind_daily_forward1_2016.csv": "2016",
    "ifind_daily_forward1_2017.csv": "2017",
    "ifind_daily_forward1_2018.csv": "2018",
    "ifind_daily_forward1_2019.csv": "2019",
    "ifind_daily_forward1_2020.csv": "2020",
    "ifind_daily_forward1_2021.csv": "2021",
    "ifind_daily_forward1_2022.csv": "2022",
    "ifind_daily_forward1_20230101_20241231.csv": "2023-2024",
    "ifind_daily_forward1_20250101_20260403.csv": "2025-2026",
}

# CSV列名映射到标准名称（兼容不同格式）
COLUMN_MAPPING_OLD = {
    'trade_date': 'trade_date',
    'THSCODE': 'ts_code',
    'preClose': 'pre_close',
    'open': 'open',
    'high': 'high',
    'low': 'low',
    'close': 'close',
    'avgPrice': 'avg_price',
    'change_amount': 'change_amount',
    'change_Ratio': 'pct_chg',
    'volume': 'vol',
    'amount': 'amount',
    'turnoverRatio': 'turnover_rate',
}

COLUMN_MAPPING_NEW = {
    'trade_date': 'trade_date',
    'thscode': 'ts_code',
    'preClose': 'pre_close',
    'open': 'open',
    'high': 'high',
    'low': 'low',
    'close': 'close',
    'avgPrice': 'avg_price',
    'change_amount': 'change_amount',
    'change_Ratio': 'pct_chg',
    'volume': 'vol',
    'amount': 'amount',
    'turnoverRatio': 'turnover_rate',
}


def get_ts_code(code: str) -> str:
    """将THSCODE转换为标准股票代码"""
    if pd.isna(code):
        return ""
    code = str(code).strip()
    if not code:
        return ""
    
    # 处理后缀
    if '.' in code:
        parts = code.split('.')
        symbol = parts[0]
        exchange = parts[1] if len(parts) > 1 else ''
    else:
        symbol = code
        exchange = ''
    
    # 补全代码
    if exchange == 'BJ':
        return f"{symbol.zfill(6)}.BJ"
    elif symbol.startswith('6'):
        return f"{symbol.zfill(6)}.SH"
    else:  # 0, 3 开头为深圳
        return f"{symbol.zfill(6)}.SZ"


def convert_csv_to_parquet(csv_path: Path, year_label: str) -> Path:
    """转换单个CSV文件为Parquet"""
    print(f"处理 {csv_path.name}...")
    
    # 读取CSV
    df = pd.read_csv(csv_path, dtype=str)
    
    # 根据列名选择映射方式
    if 'THSCODE' in df.columns:
        df = df.rename(columns=COLUMN_MAPPING_OLD)
    else:
        df = df.rename(columns=COLUMN_MAPPING_NEW)
    
    # 删除id列（如果存在）
    if 'id' in df.columns:
        df = df.drop(columns=['id'])
    
    # 转换日期
    df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
    
    # 转换数值列
    numeric_cols = ['pre_close', 'open', 'high', 'low', 'close', 'avg_price', 
                    'change_amount', 'pct_chg', 'vol', 'amount', 'turnover_rate']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 转换股票代码
    df['ts_code'] = df['ts_code'].apply(get_ts_code)
    
    # 添加年份列（用于分区）
    df['year'] = df['trade_date'].dt.year
    
    # 删除不需要的列
    if 'fetch_time' in df.columns:
        df = df.drop(columns=['fetch_time'])
    
    # 保存为Parquet（按年分区）
    output_path = OUTPUT_DIR / f"daily_{year_label}.parquet"
    df.to_parquet(
        output_path,
        engine='pyarrow',
        compression='snappy',
        index=False
    )
    
    print(f"  → 保存到 {output_path}")
    print(f"  → 数据量: {len(df):,} 行")
    print(f"  → 股票数: {df['ts_code'].nunique():,}")
    print(f"  → 日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    
    return output_path


def build_stock_index():
    """构建股票代码索引"""
    print("\n构建股票索引...")
    
    # 读取所有Parquet文件，获取唯一的股票代码
    stock_codes = set()
    date_ranges = {}
    
    parquet_files = list(OUTPUT_DIR.glob("*.parquet"))
    
    for pf in parquet_files:
        df = pd.read_parquet(pf, columns=['ts_code', 'trade_date'])
        stock_codes.update(df['ts_code'].dropna().unique().tolist())
        
        # 获取每个文件的日期范围
        min_date = df['trade_date'].min()
        max_date = df['trade_date'].max()
        date_ranges[pf.stem] = (min_date, max_date)
    
    # 创建索引DataFrame
    index_df = pd.DataFrame({'ts_code': sorted(stock_codes)})
    
    # 保存索引
    index_path = OUTPUT_DIR / "stock_index.parquet"
    index_df.to_parquet(index_path, engine='pyarrow', compression='snappy')
    
    print(f"  → 索引保存到 {index_path}")
    print(f"  → 总股票数: {len(index_df):,}")
    
    # 保存日期范围信息
    ranges_path = OUTPUT_DIR / "date_ranges.json"
    import json
    ranges_dict = {k: (str(v[0])[:10], str(v[1])[:10]) for k, v in date_ranges.items()}
    with open(ranges_path, 'w') as f:
        json.dump(ranges_dict, f, indent=2)
    
    print(f"  → 日期范围保存到 {ranges_path}")
    
    return index_df


def main():
    """主函数"""
    print("=" * 60)
    print("A股日线数据 CSV → Parquet 转换工具")
    print("=" * 60)
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 转换所有CSV文件
    for csv_name, year_label in CSV_FILES.items():
        csv_path = DATA_DIR / csv_name
        if csv_path.exists():
            convert_csv_to_parquet(csv_path, year_label)
        else:
            print(f"文件不存在: {csv_path}")
    
    # 构建索引
    build_stock_index()
    
    print("\n" + "=" * 60)
    print("转换完成!")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()