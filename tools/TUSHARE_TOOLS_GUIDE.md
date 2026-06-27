# Tushare Pro API 工具使用指南

本文档详细说明如何使用基于Tushare Pro API的股票分析工具集。

## 目录

1. [工具概览](#工具概览)
2. [基础数据工具](#基础数据工具)
3. [行情数据工具](#行情数据工具)
4. [财务数据工具](#财务数据工具)
5. [市场数据工具](#市场数据工具)
6. [指数数据工具](#指数数据工具)
7. [概念板块工具](#概念板块工具)
8. [使用场景示例](#使用场景示例)

## 工具概览

所有Tushare工具位于 `tools/tushare_tools.py` 文件中，共包含25+个工具函数，覆盖：

- **基础数据**: 股票列表、交易日历、公司信息
- **行情数据**: 日/周/月线、复权因子、停复牌、每日指标
- **财务数据**: 三大报表、财务指标、业绩预告/快报、分红送股
- **市场数据**: 沪深股通、融资融券、股东数据、龙虎榜
- **指数数据**: 指数信息、指数行情、成份股
- **概念板块**: 概念分类、成份股

## 基础数据工具

### 1. get_stock_basic - 获取股票基础信息列表

**用途**: 获取所有A股的基本信息

**参数**:
- `exchange`: 交易所代码 (SSE/SZSE/BSE)
- `list_status`: 上市状态 (L上市/D退市/P暂停)
- `fields`: 返回字段（可选）

**使用场景**:
- 获取所有上市公司列表
- 筛选特定交易所的股票
- 查询退市股票

**示例**:
```python
# 获取所有上市的股票
result = await get_stock_basic(list_status="L")

# 获取上交所的股票
result = await get_stock_basic(exchange="SSE", list_status="L")
```

### 2. get_trade_cal - 获取交易日历

**用途**: 查询交易日和休市日

**参数**:
- `exchange`: 交易所 (SSE/SZSE/BSE)
- `start_date`: 开始日期 YYYYMMDD
- `end_date`: 结束日期 YYYYMMDD
- `is_open`: 是否交易 (0休市/1交易)

**使用场景**:
- 判断某天是否交易日
- 获取一段时间内的所有交易日
- 计算交易日数量

**示例**:
```python
# 获取2024年1月的交易日
result = await get_trade_cal(
    exchange="SSE",
    start_date="20240101",
    end_date="20240131",
    is_open="1"
)
```

### 3. get_stock_company - 获取上市公司基本信息

**用途**: 获取公司详细信息（法人、董秘、注册资本等）

**参数**:
- `ts_code`: 股票代码
- `exchange`: 交易所代码
- `status`: 上市状态

**使用场景**:
- 查询公司基本面信息
- 了解公司管理层
- 获取公司注册信息

**示例**:
```python
# 获取贵州茅台的公司信息
result = await get_stock_company(ts_code="600519.SH")
```

## 行情数据工具

### 4. get_daily - 获取股票日线行情

**用途**: 获取股票每日的开高低收、成交量等数据

**参数**:
- `ts_code`: 股票代码
- `trade_date`: 交易日期
- `start_date`: 开始日期
- `end_date`: 结束日期

**使用场景**:
- 获取历史价格数据
- 计算技术指标
- 分析价格走势

**示例**:
```python
# 获取贵州茅台2024年的日线数据
result = await get_daily(
    ts_code="600519.SH",
    start_date="20240101",
    end_date="20241231"
)
```

### 5. get_weekly / get_monthly - 获取周线/月线行情

**用途**: 获取周线或月线数据

**使用场景**:
- 中长期趋势分析
- 减少数据量
- 周期性分析

### 6. get_adj_factor - 获取复权因子

**用途**: 获取复权因子用于计算复权价格

**使用场景**:
- 计算前复权价格
- 计算后复权价格
- 消除分红送股影响

**示例**:
```python
# 获取贵州茅台的复权因子
result = await get_adj_factor(
    ts_code="600519.SH",
    start_date="20240101",
    end_date="20241231"
)
```

### 7. get_suspend_d - 获取停复牌信息

**用途**: 查询股票停牌和复牌信息

**使用场景**:
- 判断股票是否停牌
- 了解停牌原因
- 预测复牌时间

### 8. get_daily_basic - 获取每日指标数据

**用途**: 获取换手率、量比、市盈率、市净率等技术指标

**参数**:
- `ts_code`: 股票代码
- `trade_date`: 交易日期
- `start_date`: 开始日期
- `end_date`: 结束日期

**使用场景**:
- 获取估值指标
- 分析换手率
- 计算量比

**示例**:
```python
# 获取贵州茅台的每日指标
result = await get_daily_basic(
    ts_code="600519.SH",
    start_date="20240101",
    end_date="20241231"
)
```

## 财务数据工具

### 9. get_income - 获取利润表数据

**用途**: 获取营业收入、净利润等利润表数据

**参数**:
- `ts_code`: 股票代码
- `ann_date`: 公告日期
- `start_date`: 报告期开始日期
- `end_date`: 报告期结束日期
- `period`: 报告期
- `report_type`: 报告类型

**使用场景**:
- 分析盈利能力
- 计算利润增长率
- 对比同行业公司

**示例**:
```python
# 获取贵州茅台的利润表
result = await get_income(
    ts_code="600519.SH",
    start_date="20230101",
    end_date="20231231"
)
```

### 10. get_balancesheet - 获取资产负债表数据

**用途**: 获取总资产、总负债、股东权益等数据

**使用场景**:
- 分析资产结构
- 计算负债率
- 评估偿债能力

### 11. get_cashflow - 获取现金流量表数据

**用途**: 获取经营/投资/筹资活动现金流

**使用场景**:
- 分析现金流状况
- 评估资金链安全
- 判断造血能力

### 12. get_fina_indicator - 获取财务指标数据

**用途**: 获取ROE、ROA、毛利率、净利率等综合指标

**使用场景**:
- 快速了解财务状况
- 计算杜邦分析
- 对比行业平均

**示例**:
```python
# 获取贵州茅台的财务指标
result = await get_fina_indicator(
    ts_code="600519.SH",
    start_date="20230101",
    end_date="20231231"
)
```

### 13. get_forecast - 获取业绩预告数据

**用途**: 获取公司业绩预告信息

**参数**:
- `type`: 预告类型 (预增/预减/扭亏/首亏/续亏/续盈/略增/略减)

**使用场景**:
- 提前了解业绩情况
- 预测股价走势
- 筛选业绩预增股

### 14. get_express - 获取业绩快报数据

**用途**: 获取业绩快报（比正式财报早）

**使用场景**:
- 快速了解业绩
- 抢先布局
- 验证预告准确性

### 15. get_dividend - 获取分红送股数据

**用途**: 获取分红、送股、转增信息

**使用场景**:
- 计算股息率
- 判断分红能力
- 预测除权除息日

**示例**:
```python
# 获取贵州茅台的分红记录
result = await get_dividend(ts_code="600519.SH")
```

## 市场数据工具

### 16. get_hs_const - 获取沪深股通成份股

**用途**: 查询沪股通、深股通成份股

**参数**:
- `hs_type`: 类型 (SH沪股通/SZ深股通)

**使用场景**:
- 筛选外资可买股票
- 分析北向资金流向
- 跟踪外资持仓

### 17. get_margin_detail - 获取融资融券交易明细

**用途**: 获取融资余额、融券余额等数据

**参数**:
- `trade_date`: 交易日期（必填）
- `ts_code`: 股票代码

**使用场景**:
- 分析融资情绪
- 判断市场热度
- 预警融资风险

**示例**:
```python
# 获取某日的融资融券数据
result = await get_margin_detail(trade_date="20240228")

# 获取贵州茅台的融资融券数据
result = await get_margin_detail(
    trade_date="20240228",
    ts_code="600519.SH"
)
```

### 18. get_top10_holders - 获取前十大股东数据

**用途**: 获取前十大股东持股信息

**使用场景**:
- 分析股东结构
- 跟踪大股东变化
- 识别机构持仓

### 19. get_top10_floatholders - 获取前十大流通股东数据

**用途**: 获取前十大流通股东信息

**使用场景**:
- 分析流通股东结构
- 跟踪机构调仓
- 识别游资

**示例**:
```python
# 获取贵州茅台的前十大流通股东
result = await get_top10_floatholders(
    ts_code="600519.SH",
    period="20231231"
)
```

### 20. get_top_list - 获取龙虎榜每日明细

**用途**: 获取龙虎榜上榜股票信息

**使用场景**:
- 跟踪游资动向
- 分析短线热点
- 识别主力操作

### 21. get_top_inst - 获取龙虎榜机构交易明细

**用途**: 获取龙虎榜机构席位交易

**使用场景**:
- 跟踪机构动向
- 分析机构偏好
- 判断主力意图

## 指数数据工具

### 22. get_index_basic - 获取指数基本信息

**用途**: 获取所有指数的基本信息

**参数**:
- `market`: 市场类型
- `publisher`: 发布商
- `category`: 指数类别

**使用场景**:
- 查询指数列表
- 了解指数构成
- 选择基准指数

### 23. get_index_daily - 获取指数日线行情

**用途**: 获取指数的历史行情数据

**使用场景**:
- 分析大盘走势
- 计算指数涨跌幅
- 对比个股表现

**示例**:
```python
# 获取上证指数行情
result = await get_index_daily(
    ts_code="000001.SH",
    start_date="20240101",
    end_date="20241231"
)
```

### 24. get_index_weight - 获取指数成份股

**用途**: 获取指数的成份股及权重

**使用场景**:
- 了解指数构成
- 跟踪成份股变化
- 构建指数基金

**示例**:
```python
# 获取沪深300成份股
result = await get_index_weight(
    index_code="000300.SH",
    trade_date="20240228"
)
```

## 概念板块工具

### 25. get_concept - 获取概念板块分类

**用途**: 获取所有概念板块列表

**参数**:
- `src`: 来源 (ts东财/sina新浪)

**使用场景**:
- 查询所有概念
- 了解热门板块
- 筛选主题投资

**示例**:
```python
# 获取所有概念板块
result = await get_concept(src="ts")
```

### 26. get_concept_detail - 获取概念板块成份股

**用途**: 获取指定概念的成份股

**参数**:
- `id`: 概念分类ID
- `ts_code`: 股票代码

**使用场景**:
- 查询概念成份股
- 筛选主题股票
- 分析板块联动

**示例**:
```python
# 获取某概念的成份股
result = await get_concept_detail(id="TS1")

# 查询某股票属于哪些概念
result = await get_concept_detail(ts_code="600519.SH")
```

## 使用场景示例

### 场景1: 分析一只股票的基本面

```python
# 1. 获取公司基本信息
company_info = await get_stock_company(ts_code="600519.SH")

# 2. 获取最新财务数据
income = await get_income(ts_code="600519.SH", period="20231231")
balance = await get_balancesheet(ts_code="600519.SH", period="20231231")
cashflow = await get_cashflow(ts_code="600519.SH", period="20231231")

# 3. 获取财务指标
indicators = await get_fina_indicator(ts_code="600519.SH", period="20231231")

# 4. 获取分红记录
dividend = await get_dividend(ts_code="600519.SH")

# 5. 获取股东信息
holders = await get_top10_floatholders(ts_code="600519.SH", period="20231231")
```

### 场景2: 分析股票的技术面

```python
# 1. 获取日线数据
daily = await get_daily(
    ts_code="600519.SH",
    start_date="20230101",
    end_date="20241231"
)

# 2. 获取每日指标（换手率、市盈率等）
daily_basic = await get_daily_basic(
    ts_code="600519.SH",
    start_date="20230101",
    end_date="20241231"
)

# 3. 获取复权因子
adj_factor = await get_adj_factor(
    ts_code="600519.SH",
    start_date="20230101",
    end_date="20241231"
)

# 4. 计算技术指标（使用stock_analysis_tool）
indicators = await calculate_technical_indicators(
    stock_code="600519.SH",
    start_date="20230101",
    end_date="20241231",
    indicators="MACD,KDJ,RSI,BOLL,MA"
)
```

### 场景3: 筛选符合条件的股票

```python
# 1. 获取所有上市股票
all_stocks = await get_stock_basic(list_status="L")

# 2. 获取沪深300成份股
hs300 = await get_index_weight(index_code="000300.SH")

# 3. 获取某概念板块的股票
concept_stocks = await get_concept_detail(id="TS1")

# 4. 获取沪股通标的
hs_stocks = await get_hs_const(hs_type="SH")

# 5. 筛选业绩预增的股票
forecast = await get_forecast(type="预增")
```

### 场景4: 分析市场情绪

```python
# 1. 获取龙虎榜数据
top_list = await get_top_list(trade_date="20240228")
top_inst = await get_top_inst(trade_date="20240228")

# 2. 获取融资融券数据
margin = await get_margin_detail(trade_date="20240228")

# 3. 获取大盘指数
index_daily = await get_index_daily(
    ts_code="000001.SH",
    start_date="20240101",
    end_date="20240228"
)
```

### 场景5: 搜索历史相似走势

```python
# 搜索MACD金叉的历史案例
result = await search_similar_pattern(
    pattern_description="MACD金叉",
    start_date="20230101",
    end_date="20231231",
    max_results=20,
    lookahead_days="5,10,20"
)

# 搜索连续三天涨停的案例
result = await search_similar_pattern(
    pattern_description="连续三天涨停",
    start_date="20230101",
    end_date="20231231",
    max_results=20
)
```

## 注意事项

1. **股票代码格式**: 必须带后缀，如 `600519.SH`、`000001.SZ`、`9开头.BJ`
2. **日期格式**: 统一使用 `YYYYMMDD` 格式，如 `20240228`
3. **数据权限**: 部分数据需要Tushare Pro积分权限
4. **调用频率**: 注意Tushare API的调用频率限制
5. **数据延迟**: 部分数据可能有1-2天延迟
6. **错误处理**: 所有工具都会返回包含 `error` 字段的字典表示错误

## 工具组合建议

根据不同的分析目标，建议组合使用以下工具：

**价值投资分析**:
- get_stock_company
- get_income / get_balancesheet / get_cashflow
- get_fina_indicator
- get_dividend
- get_top10_holders

**技术分析**:
- get_daily / get_weekly / get_monthly
- get_daily_basic
- get_adj_factor
- calculate_technical_indicators
- search_similar_pattern

**资金面分析**:
- get_margin_detail
- get_top_list / get_top_inst
- get_top10_floatholders
- get_hs_const

**板块轮动分析**:
- get_concept / get_concept_detail
- get_index_weight
- get_index_daily

## 更多资源

- [Tushare Pro官方文档](https://tushare.pro/document/2)
- [技术指标计算文档](./TOOL_ENHANCEMENT_GUIDE.md)
- [历史模式搜索文档](../PATTERN_PARSING_ENHANCEMENT.md)
