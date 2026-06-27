"""
工具参数推断指南 — 供 Planner / ReAct Agent 理解「用户问题 → 工具参数」映射。

LangChain 会从函数签名生成 JSON Schema，但 agent 仍需要业务层规则才能填对
stock_code、日期范围、fields 等。本模块提供可注入 prompt 的规范文本，以及
规则化的实体提取与参数推断（Planner 失败时的兜底 + Act 阶段提示）。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

TODAY_YMD = datetime.now().strftime("%Y%m%d")
TODAY_HYPHEN = datetime.now().strftime("%Y-%m-%d")

# 6 位 A 股代码（0/3/6 开头）
_STOCK_CODE_RE = re.compile(r"(?<![.\d])([036]\d{5})(?![.\d])")
# 带后缀的 ts_code
_TS_CODE_RE = re.compile(r"(\d{6}\.(?:SH|SZ|BJ))", re.I)

_INDEX_ALIASES: Dict[str, str] = {
    "上证指数": "000001.SH",
    "上证综指": "000001.SH",
    "大盘": "000001.SH",
    "沪指": "000001.SH",
    "深证成指": "399001.SZ",
    "深成指": "399001.SZ",
    "创业板指": "399006.SZ",
    "创业板": "399006.SZ",
    "科创50": "000688.SH",
    "沪深300": "000300.SH",
    "中证500": "000905.SH",
}

_STOCK_NAME_ALIASES: Dict[str, str] = {
    "贵州茅台": "600519",
    "茅台": "600519",
    "平安银行": "000001",
    "招商银行": "600036",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "中国平安": "601318",
    "工商银行": "601398",
    "建设银行": "601939",
    "中国移动": "600941",
    "腾讯": "00700",  # 港股，agent 需换工具
}

_INTENT_KEYWORDS: Dict[str, List[str]] = {
    "valuation": ["估值", "pe", "pb", "市盈率", "市净率", "市值"],
    "trend": ["走势", "涨跌", "k线", "k 线", "行情", "价格", "收盘", "技术分析"],
    "finance": ["财务", "roe", "利润", "营收", "毛利率", "净利率", "负债", "报表"],
    "moneyflow": ["资金", "主力", "净流入", "净流出", "大单", "北向"],
    "limit": ["涨停", "跌停", "打板", "连板"],
    "top_list": ["龙虎榜"],
    "macro": ["gdp", "cpi", "ppi", "宏观", "货币", "m2", "shibor", "利率"],
    "concept": ["概念", "板块", "题材"],
}

# 核心工具参数规格（required=调用前必须推断/填写）
TOOL_PARAM_SPECS: Dict[str, Dict[str, Any]] = {
    "tool_get_stock_history": {
        "required": ["stock_code", "fields"],
        "optional": ["start_date", "end_date"],
        "defaults": {"start_date": "最近30个交易日", "end_date": "今天"},
        "fields_examples": {
            "走势/技术": "trade_date,close,pct_chg,vol",
            "K线+均线": "trade_date,open,high,low,close,vol",
        },
        "infer": "从用户问题提取股票代码/名称；时间未说明则 start 默认30个交易日前，end=今天",
    },
    "tool_get_daily_basic": {
        "required": ["stock_code", "fields"],
        "optional": ["trade_date", "start_date", "end_date"],
        "fields_examples": {
            "估值": "trade_date,pe_ttm,pb,total_mv,circ_mv",
            "流动性": "trade_date,turnover_rate,volume_ratio",
        },
        "infer": "估值类问题用 pe_ttm,pb,total_mv；单日快照用 trade_date",
    },
    "tool_get_fina_indicator": {
        "required": ["stock_code", "fields"],
        "optional": ["period", "start_date", "end_date"],
        "fields_examples": {
            "盈利": "end_date,roe,roa,netprofit_margin,grossprofit_margin,netprofit_yoy",
            "偿债": "end_date,debt_to_assets,current_ratio,quick_ratio",
        },
        "infer": "财务分析必须指定 fields；未指定报告期则取最近4个报告期",
    },
    "tool_get_income": {
        "required": ["stock_code"],
        "optional": ["period", "start_date", "end_date", "fields"],
        "infer": "利润表；需 fields 时选 revenue,n_income,total_revenue 等",
    },
    "tool_get_balancesheet": {
        "required": ["stock_code"],
        "optional": ["period", "start_date", "end_date", "fields"],
        "infer": "资产负债表",
    },
    "tool_get_cashflow": {
        "required": ["stock_code"],
        "optional": ["period", "start_date", "end_date", "fields"],
        "infer": "现金流量表",
    },
    "tool_get_moneyflow": {
        "required": ["stock_code"],
        "optional": ["start_date", "end_date", "fields"],
        "fields_examples": {"主力": "trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount"},
        "infer": "仅问「今日/实时资金」可不填日期；历史区间需 start_date+end_date",
    },
    "tool_get_moneyflow_ths": {
        "required": ["stock_code"],
        "optional": ["start_date", "end_date", "fields"],
        "infer": "同花顺口径资金流；实时可用无日期，历史需日期范围",
    },
    "tool_get_moneyflow_ind_ths": {
        "optional": ["trade_date", "ts_code", "fields"],
        "infer": "同花顺行业/板块资金流；trade_date 默认今天",
    },
    "tool_get_index_daily": {
        "required": ["ts_code", "fields"],
        "optional": ["start_date", "end_date"],
        "fields_examples": {"大盘": "trade_date,close,pct_chg,vol"},
        "infer": "上证指数=000001.SH，深证成指=399001.SZ，创业板指=399006.SZ",
    },
    "tool_get_index_dailybasic": {
        "required": ["ts_code"],
        "optional": ["trade_date", "start_date", "end_date", "fields"],
        "infer": "指数每日指标；ts_code 同 index_daily",
    },
    "tool_get_limit_list": {
        "required": ["trade_date"],
        "optional": ["limit_type", "fields"],
        "defaults": {"limit_type": "U"},
        "infer": "「今日涨停」→ trade_date=今天, limit_type=U；跌停用 D",
    },
    "tool_get_limit_list_d": {
        "optional": ["trade_date", "ts_code", "limit_type"],
        "defaults": {"trade_date": "今天"},
        "infer": "涨跌停池（打板）；trade_date 必填",
    },
    "tool_get_top_list": {
        "optional": ["trade_date", "stock_code", "fields"],
        "defaults": {"trade_date": "今天"},
        "infer": "龙虎榜需 trade_date；指定个股时加 stock_code",
    },
    "tool_get_macro_data": {
        "required": ["data_type"],
        "optional": ["start_date", "end_date", "fields"],
        "infer": "data_type 只能是 gdp/cpi/ppi/m/shibor 之一",
    },
    "tool_get_concept": {
        "required": ["action"],
        "optional": ["concept_id", "stock_code", "fields"],
        "defaults": {"action": "list"},
        "infer": "action=list 列板块；action=detail 需 concept_id",
    },
    "tool_get_trade_cal": {
        "optional": ["exchange", "start_date", "end_date", "is_open"],
        "defaults": {"exchange": "SSE"},
        "infer": "查是否交易日/日历时用；exchange: SSE/SZSE",
    },
    "tool_get_ths_index": {
        "optional": ["trade_date", "ts_code"],
        "defaults": {"trade_date": "今天"},
        "infer": "同花顺板块指数行情；可指定 ts_code 或 trade_date",
    },
    "tool_get_adj_factor": {
        "required": ["stock_code"],
        "optional": ["start_date", "end_date", "fields"],
        "infer": "复权因子；日期范围同 history",
    },
    "tool_get_weekly_monthly": {
        "required": ["stock_code", "freq"],
        "optional": ["start_date", "end_date", "fields"],
        "defaults": {"freq": "W"},
        "infer": "freq=W 周线 / M 月线",
    },
    "tool_search_similar_pattern": {
        "required": ["pattern_description"],
        "optional": ["stock_code", "start_date", "end_date", "fields"],
        "infer": "pattern_description 用自然语言描述形态",
    },
    "tool_smart_stock_picking": {
        "required": ["searchstring"],
        "optional": ["searchtype"],
        "defaults": {"searchtype": "stock"},
        "infer": "涨停/跌停/龙虎榜/高ROE/低市盈率/破净 等自然语言；用户原话可直接作 searchstring",
    },
    "tool_get_segmented_history": {
        "required": ["stock_code", "fields"],
        "optional": ["start_date", "end_date", "segment_days"],
        "infer": "长区间历史分段拉取；fields 同 tool_get_stock_history",
    },
}

# 用户表述 → 参数推断（通用）
INTENT_TO_PARAMS = """
## 工具参数推断规范（CRITICAL — 调用任何工具前必须完成）

今天日期：{today}（YYYYMMDD 格式写 {today_ymd}）

### 第一步：从用户问题提取实体
| 用户表述 | 参数 | 示例 |
|---------|------|------|
| 600519、茅台、贵州茅台 | stock_code | "600519" 或 "600519.SH" |
| 上证指数、大盘 | ts_code | "000001.SH" |
| 深证成指 | ts_code | "399001.SZ" |
| 创业板指 | ts_code | "399006.SZ" |
| 今天、最新、当前 | end_date / trade_date | {today_ymd} |
| 昨天、昨日 | trade_date | 前一个交易日（可先 tool_get_trade_cal） |
| 最近一周/一个月/三个月 | start_date | 从今天往前推约 7/30/90 个自然日，格式 YYYYMMDD |
| 2024年、去年 | start_date/end_date | 20240101–20241231 |
| 估值、PE、PB | fields 含 pe_ttm,pb,total_mv | tool_get_daily_basic |
| 走势、涨跌、K线 | fields 含 trade_date,close,pct_chg,vol | tool_get_stock_history |
| 财务、ROE、利润 | fields 含 roe,eps 等 | tool_get_fina_indicator / income |
| 资金、主力、净流入 | tool_get_moneyflow 或 tool_get_moneyflow_ths | fields 含 net_mf_amount 或实时指标 |
| 涨停、跌停 | tool_get_limit_list / tool_smart_stock_picking | trade_date + limit_type U/D 或 searchstring=涨停 |
| 龙虎榜 | tool_get_top_list / tool_smart_stock_picking | searchstring=龙虎榜 |
| 选股、筛选、高ROE、低PE | tool_smart_stock_picking | searchstring=用户条件 |
| GDP/CPI/宏观 | tool_get_macro_data | data_type=gdp/cpi/ppi/m/shibor |

### 第二步：为每个工具填参（必填项不可省略）
1. **stock_code** — 个股类工具必填；仅数字 6 位即可，工具会自动补 .SH/.SZ
2. **fields** — 带 fields 参数的工具**必须显式传入**（逗号分隔，最小字段集）；不传会报错 FIELDS_REQUIRED
3. **start_date / end_date** — 格式 YYYYMMDD；未说明时：短期分析 end=今天，start≈30天前
4. **trade_date** — 单日查询用（涨跌停、龙虎榜、某日指标）
5. **ts_code** — 指数/板块代码，与 stock_code 不同

### 第三步：调用前自检清单
- [ ] 是否已从用户问题解析出 stock_code / ts_code / data_type？
- [ ] 是否已根据分析目的选定 fields（非空字符串）？
- [ ] 日期是否与用户时间范围一致？未说明是否用了合理默认？
- [ ] 工具名是否与数据类型匹配（行情 vs 财务 vs 资金 vs 宏观）？

### 第四步：参考执行计划
若本次对话注入了「执行计划」或「参数推断提示」，其中的 args_hint **必须优先采用**；
仅在用户问题与计划冲突时以用户最新意图为准。
""".strip()


def get_tool_param_prompt() -> str:
    return INTENT_TO_PARAMS.format(today=TODAY_HYPHEN, today_ymd=TODAY_YMD)


def get_tool_spec_summary(tool_names: Optional[List[str]] = None) -> str:
    """生成精简的工具参数摘要，供 planner 使用。"""
    lines = ["## 常用工具参数速查"]
    names = tool_names or list(TOOL_PARAM_SPECS.keys())
    for name in names:
        spec = TOOL_PARAM_SPECS.get(name)
        if not spec:
            continue
        req = ", ".join(spec.get("required", []))
        opt = ", ".join(spec.get("optional", []))
        lines.append(f"- **{name}**: 必填=[{req}] 可选=[{opt}] | {spec.get('infer', '')}")
    return "\n".join(lines)


def get_tool_param_hint(tool_name: str) -> Optional[Dict[str, Any]]:
    """返回某工具的参数规格，供校验错误提示使用。"""
    spec = TOOL_PARAM_SPECS.get(tool_name)
    if not spec:
        return None
    return {
        "required": spec.get("required", []),
        "optional": spec.get("optional", []),
        "defaults": spec.get("defaults", {}),
        "fields_examples": spec.get("fields_examples", {}),
        "infer": spec.get("infer", ""),
    }


def suggest_date_range(query: str) -> Dict[str, str]:
    """根据常见中文时间表述给出 start/end（自然日近似，agent 可再 refine）。"""
    end = TODAY_YMD
    q = query or ""
    q_lower = q.lower()

    year_match = re.search(r"(20\d{2})年?", q)
    if year_match and "最近" not in q and "近" not in q[:10]:
        y = year_match.group(1)
        return {"start_date": f"{y}0101", "end_date": f"{y}1231", "note": f"{y}全年"}

    if "去年" in q:
        y = str(datetime.now().year - 1)
        return {"start_date": f"{y}0101", "end_date": f"{y}1231", "note": "去年"}

    if "一年" in q or "12个月" in q:
        start = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    elif "半年" in q or "6个月" in q:
        start = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
    elif "三个月" in q or "90天" in q or "季度" in q or "一季" in q:
        start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    elif "两个月" in q or "60天" in q:
        start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
    elif "一个月" in q or "30天" in q or "近月" in q:
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    elif "两周" in q or "14天" in q:
        start = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
    elif "一周" in q or "7天" in q or "本周" in q:
        start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    elif "今天" in q or "今日" in q or "最新" in q:
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    else:
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    note = "默认近30日"
    if "一周" in q or "7天" in q:
        note = "近一周"
    elif "三个月" in q or "90天" in q:
        note = "近三个月"

    return {"start_date": start, "end_date": end, "note": note}


def _detect_intents(query: str) -> List[str]:
    q = (query or "").lower()
    found = []
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            found.append(intent)
    if not found:
        found.append("trend")
    return found


def extract_entities_from_query(query: str) -> Dict[str, Any]:
    """从用户自然语言问题中提取股票代码、指数、日期与意图标签。"""
    q = query or ""
    stock_codes: List[str] = []
    ts_codes: List[str] = []

    for m in _TS_CODE_RE.finditer(q):
        ts_codes.append(m.group(1).upper())

    for m in _STOCK_CODE_RE.finditer(q):
        code = m.group(1)
        if code not in stock_codes:
            stock_codes.append(code)

    for name, code in _STOCK_NAME_ALIASES.items():
        if name in q and code not in stock_codes:
            stock_codes.append(code)

    for alias, code in _INDEX_ALIASES.items():
        if alias in q and code not in ts_codes:
            ts_codes.append(code)

    dates = suggest_date_range(q)
    trade_date = TODAY_YMD
    if "昨天" in q or "昨日" in q:
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    return {
        "stock_codes": stock_codes,
        "ts_codes": ts_codes,
        "start_date": dates.get("start_date"),
        "end_date": dates.get("end_date"),
        "trade_date": trade_date,
        "date_note": dates.get("note", ""),
        "intents": _detect_intents(q),
    }


def _infer_fields(tool_name: str, intents: List[str]) -> Optional[str]:
    spec = TOOL_PARAM_SPECS.get(tool_name, {})
    examples: Dict[str, str] = spec.get("fields_examples") or {}
    if not examples:
        return None

    intent_to_key = {
        "valuation": "估值",
        "trend": "走势/技术",
        "finance": "盈利",
        "moneyflow": "主力",
    }
    for intent in intents:
        key = intent_to_key.get(intent)
        if key and key in examples:
            return examples[key]
        for ex_key, val in examples.items():
            if intent in ex_key.lower() or key and key in ex_key:
                return val

    return next(iter(examples.values()), None)


def _infer_macro_data_type(query: str) -> Optional[str]:
    q = (query or "").lower()
    if "shibor" in q or "银行间" in q:
        return "shibor"
    if "cpi" in q or "消费物价" in q:
        return "cpi"
    if "ppi" in q or "工业物价" in q:
        return "ppi"
    if "m2" in q or "货币供应" in q or "m0" in q or "m1" in q:
        return "m"
    if "gdp" in q or "国内生产总值" in q:
        return "gdp"
    if "宏观" in q:
        return "gdp"
    return None


def infer_tool_args(tool_name: str, query: str, entities: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """根据用户问题与工具规格推断单工具调用参数（规则兜底，供 Planner/Act 参考）。"""
    entities = entities or extract_entities_from_query(query)
    spec = TOOL_PARAM_SPECS.get(tool_name, {})
    args: Dict[str, Any] = {}

    all_params = set(spec.get("required", []) + spec.get("optional", []))
    defaults = spec.get("defaults", {})

    if "stock_code" in all_params and entities.get("stock_codes"):
        args["stock_code"] = entities["stock_codes"][0]

    if "ts_code" in all_params:
        if entities.get("ts_codes"):
            args["ts_code"] = entities["ts_codes"][0]
        elif entities.get("stock_codes") and tool_name.startswith("tool_get_index"):
            pass
        elif "大盘" in (query or "") or "指数" in (query or ""):
            args["ts_code"] = "000001.SH"

    if "start_date" in all_params and entities.get("start_date"):
        args["start_date"] = entities["start_date"]
    if "end_date" in all_params and entities.get("end_date"):
        args["end_date"] = entities["end_date"]

    if "trade_date" in all_params:
        args["trade_date"] = entities.get("trade_date", TODAY_YMD)

    if "data_type" in all_params:
        dt = _infer_macro_data_type(query)
        if dt:
            args["data_type"] = dt

    if "action" in all_params and "action" not in args:
        args["action"] = defaults.get("action", "list")

    if "limit_type" in all_params:
        if "跌停" in (query or ""):
            args["limit_type"] = "D"
        else:
            args["limit_type"] = defaults.get("limit_type", "U")

    if "freq" in all_params:
        if "月" in (query or ""):
            args["freq"] = "M"
        else:
            args["freq"] = defaults.get("freq", "W")

    if "pattern_description" in all_params:
        args["pattern_description"] = query.strip()[:500]

    if "fields" in spec.get("required", []) or "fields" in all_params:
        fields = _infer_fields(tool_name, entities.get("intents", []))
        if fields:
            args["fields"] = fields

    for k, v in defaults.items():
        if k not in args and k in all_params and isinstance(v, str) and v not in ("今天", "最近30个交易日"):
            args[k] = v

    return args


def enrich_plan_with_inferred_args(plan: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Planner 输出后补全 stock_codes、date_hints、各步 args_hint 中的缺失字段。"""
    if not plan:
        plan = {"steps": []}

    entities = extract_entities_from_query(query)

    if not plan.get("stock_codes") and entities.get("stock_codes"):
        plan["stock_codes"] = entities["stock_codes"]

    if not plan.get("date_hints"):
        plan["date_hints"] = {
            "start_date": entities.get("start_date"),
            "end_date": entities.get("end_date"),
            "note": entities.get("date_note", ""),
        }

    for step in plan.get("steps") or []:
        tools = step.get("tools") or []
        args_hint = dict(step.get("args_hint") or {})
        for tool_name in tools:
            inferred = infer_tool_args(tool_name, query, entities)
            existing = dict(args_hint.get(tool_name) or {})
            merged = {**inferred, **{k: v for k, v in existing.items() if v not in (None, "", [])}}
            if merged:
                args_hint[tool_name] = merged
        if args_hint:
            step["args_hint"] = args_hint

        if not step.get("fields_hint") and args_hint:
            hints = []
            for tn, ta in args_hint.items():
                if ta.get("fields"):
                    hints.append(f"{tn}: {ta['fields']}")
            if hints:
                step["fields_hint"] = "; ".join(hints)

    return plan


def format_inferred_params_message(query: str, plan: Optional[Dict[str, Any]] = None) -> str:
    """生成注入 Act 阶段用户消息旁的参数推断提示（不替代 agent 思考，仅作锚点）。"""
    entities = extract_entities_from_query(query)
    lines: List[str] = []

    if entities.get("stock_codes"):
        lines.append(f"- 识别股票代码: {', '.join(entities['stock_codes'])}")
    if entities.get("ts_codes"):
        lines.append(f"- 识别指数/板块代码: {', '.join(entities['ts_codes'])}")
    if entities.get("start_date") and entities.get("end_date"):
        lines.append(
            f"- 推断日期范围: {entities['start_date']} ~ {entities['end_date']}"
            f"（{entities.get('date_note', '')}）"
        )
    if entities.get("intents"):
        lines.append(f"- 分析意图: {', '.join(entities['intents'])}")

    if plan and plan.get("steps"):
        for step in plan.get("steps") or []:
            ah = step.get("args_hint") or {}
            if ah:
                lines.append(
                    f"- 步骤{step.get('step_id', '?')} 建议参数: "
                    f"{json_dumps_compact(ah)}"
                )

    if not lines:
        return ""
    return "【系统参数推断提示 — 调用工具时请采用或校验以下参数】\n" + "\n".join(lines)


def json_dumps_compact(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build_act_user_message(query: str, plan: Optional[Dict[str, Any]] = None) -> str:
    """组装 Act Agent 的 HumanMessage 内容：原问题 + 参数推断提示。"""
    hint = format_inferred_params_message(query, plan)
    if hint:
        return f"{query.strip()}\n\n{hint}"
    return query.strip()
