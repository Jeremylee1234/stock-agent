# Tushare工具快速参考卡

## 快速查找表

| 用户需求 | 使用工具 | 示例 |
|---------|---------|------|
| 获取所有股票列表 | `get_stock_basic` | `get_stock_basic(list_status="L")` |
| 判断是否交易日 | `get_trade_cal` | `get_trade_cal(trade_date="20240228", is_open="1")` |
| 查询公司信息 | `get_stock_company` | `get_stock_company(ts_code="600519.SH")` |
| 获取历史价格 | `get_daily` | `get_daily(ts_code="600519.SH", start_date="20240101")` |
| 获取周线/月线 | `get_weekly` / `get_monthly` | `get_weekly(ts_code="600519.SH")` |
| 计算复权价格 | `get_adj_factor` | `get_adj_factor(ts_code="600519.SH")` |
| 查询停复牌 | `get_suspend_d` | `get_suspend_d(ts_code="600519.SH")` |
| 获取估值指标 | `get_daily_basic` | `get_daily_basic(ts_code="600519.SH")` |
| 获取利润表 | `get_income` | `get_income(ts_code="600519.SH")` |
| 获取资产负债表 | `get_balancesheet` | `get_balancesheet(ts_code="600519.SH")` |
| 获取现金流量表 | `get_cashflow` | `get_cashflow(ts_code="600519.SH")` |
| 获取财务指标 | `get_fina_indicator` | `get_fina_indicator(ts_code="600519.SH")` |
| 查询业绩预告 | `get_forecast` | `get_forecast(type="预增")` |
| 查询业绩快报 | `get_express` | `get_express(ts_code="600519.SH")` |
| 查询分红记录 | `get_dividend` | `get_dividend(ts_code="600519.SH")` |
| 查询沪深股通 | `get_hs_const` | `get_hs_const(hs_type="SH")` |
| 查询融资融券 | `get_margin_detail` | `get_margin_detail(trade_date="20240228")` |
| 查询前十大股东 | `get_top10_holders` | `get_top10_holders(ts_code="600519.SH")` |
| 查询流通股东 | `get_top10_floatholders` | `get_top10_floatholders(ts_code="600519.SH")` |
| 查询龙虎榜 | `get_top_list` | `get_top_list(trade_date="20240228")` |
| 查询机构席位 | `get_top_inst` | `get_top_inst(trade_date="20240228")` |
| 查询指数列表 | `get_index_basic` | `get_index_basic(market="SSE")` |
| 获取指数行情 | `get_index_daily` | `get_index_daily(ts_code="000001.SH")` |
| 查询指数成份股 | `get_index_weight` | `get_index_weight(index_code="000300.SH")` |
| 查询概念板块 | `get_concept` | `get_concept(src="ts")` |
| 查询板块成份股 | `get_concept_detail` | `get_concept_detail(id="TS1")` |
| 计算技术指标 | `calculate_technical_indicators` | `calculate_technical_indicators(stock_code="600519.SH")` |
| 搜索历史模式 | `search_similar_pattern` | `search_similar_pattern(pattern_description="MACD金叉")` |

## 常用参数格式

- **股票代码**: `600519.SH` (上交所), `000001.SZ` (深交所), `9开头.BJ` (北交所)
- **日期格式**: `YYYYMMDD`, 如 `20240228`
- **交易所代码**: `SSE` (上交所), `SZSE` (深交所), `BSE` (北交所)
- **上市状态**: `L` (上市), `D` (退市), `P` (暂停)

## 典型分析流程

### 基本面分析
```
1. get_stock_company (公司信息)
2. get_income (利润表)
3. get_balancesheet (资产负债表)
4. get_cashflow (现金流量表)
5. get_fina_indicator (财务指标)
6. get_dividend (分红记录)
7. get_top10_holders (股东结构)
```

### 技术面分析
```
1. get_daily (历史价格)
2. get_daily_basic (每日指标)
3. get_adj_factor (复权因子)
4. calculate_technical_indicators (技术指标)
5. search_similar_pattern (历史模式)
```

### 资金面分析
```
1. get_margin_detail (融资融券)
2. get_top_list (龙虎榜)
3. get_top_inst (机构席位)
4. get_top10_floatholders (流通股东)
```

### 板块分析
```
1. get_concept (概念列表)
2. get_concept_detail (成份股)
3. get_index_weight (指数成份)
4. get_hs_const (沪深股通)
```

## 错误处理

所有工具返回格式：
```python
# 成功
{
    'success': True,
    'data': [...],
    'count': 100,
    'data_source': 'tushare'
}

# 失败
{
    'error': '错误信息'
}
```

## 注意事项

1. ⚠️ 股票代码必须带后缀
2. ⚠️ 日期格式必须是YYYYMMDD
3. ⚠️ 注意API调用频率限制
4. ⚠️ 部分数据需要积分权限
5. ⚠️ 数据可能有1-2天延迟

## 工具选择决策树

```
用户问题
├─ 关于公司基本信息？
│  └─ get_stock_company
├─ 关于财务数据？
│  ├─ 利润表 → get_income
│  ├─ 资产负债表 → get_balancesheet
│  ├─ 现金流量表 → get_cashflow
│  ├─ 综合指标 → get_fina_indicator
│  ├─ 业绩预告 → get_forecast
│  └─ 分红 → get_dividend
├─ 关于价格走势？
│  ├─ 日线 → get_daily
│  ├─ 周线 → get_weekly
│  ├─ 月线 → get_monthly
│  └─ 技术指标 → calculate_technical_indicators
├─ 关于估值？
│  └─ get_daily_basic
├─ 关于资金面？
│  ├─ 融资融券 → get_margin_detail
│  ├─ 龙虎榜 → get_top_list / get_top_inst
│  └─ 股东 → get_top10_holders / get_top10_floatholders
├─ 关于板块？
│  ├─ 概念板块 → get_concept / get_concept_detail
│  ├─ 指数成份 → get_index_weight
│  └─ 沪深股通 → get_hs_const
└─ 关于历史模式？
   └─ search_similar_pattern
```

## 快速示例

### 示例1: 分析茅台
```python
# 基本信息
company = await get_stock_company(ts_code="600519.SH")

# 最新财报
income = await get_income(ts_code="600519.SH", period="20231231")

# 近一年行情
daily = await get_daily(ts_code="600519.SH", start_date="20230101", end_date="20231231")

# 技术指标
indicators = await calculate_technical_indicators(
    stock_code="600519.SH",
    start_date="20230101",
    end_date="20231231",
    indicators="MACD,KDJ,RSI"
)
```

### 示例2: 筛选股票
```python
# 获取所有上市股票
all_stocks = await get_stock_basic(list_status="L")

# 获取沪深300成份股
hs300 = await get_index_weight(index_code="000300.SH")

# 获取业绩预增股票
forecast = await get_forecast(type="预增")
```

### 示例3: 市场情绪
```python
# 今日龙虎榜
top_list = await get_top_list(trade_date="20240228")

# 融资融券
margin = await get_margin_detail(trade_date="20240228")

# 大盘指数
index = await get_index_daily(ts_code="000001.SH", trade_date="20240228")
```
