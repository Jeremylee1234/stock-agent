"""
信号扫描器 - 在历史数据中扫描满足策略条件的进场信号

核心逻辑：
1. 根据 stock_filter 筛选候选股票池
2. 对每只股票拉取历史行情（前复权）
3. 扫描 prerequisite_events（连板、断板、强势确认等）
4. 在事件发生后的 trigger_window_days 内寻找 entry_conditions
5. 返回所有命中的进场信号
"""
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

# 复用统一 Tushare 客户端（从 .env 的 DATA_SOURCE__TUSHARE_TOKEN 读取）
from tools.tushare_client import pro

TODAY_YMD = datetime.now().strftime("%Y%m%d")


def _to_ts_code(code: str) -> str:
    if not code:
        return ""
    code = str(code).strip()
    if "." in code:
        return code
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith("0") or code.startswith("3"):
        return f"{code}.SZ"
    if code.startswith("4") or code.startswith("8") or code.startswith("9"):
        return f"{code}.BJ"
    return f"{code}.SH"


def _get_board_type(ts_code: str) -> str:
    """根据代码判断板块类型"""
    code = ts_code.split(".")[0]
    suffix = ts_code.split(".")[-1] if "." in ts_code else ""
    if suffix == "SH" and code.startswith("688"):
        return "科创板"
    if suffix == "SZ" and code.startswith("3"):
        return "创业板"
    if suffix == "BJ":
        return "北交所"
    return "主板"


def _get_limit_pct(ts_code: str) -> float:
    """获取涨停幅度"""
    board = _get_board_type(ts_code)
    if board in ("创业板", "科创板"):
        return 0.20
    if board == "北交所":
        return 0.30
    return 0.10


def _fetch_daily_qfq(ts_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    获取前复权日线数据，计算常用均线
    返回按日期升序排列的 DataFrame
    """
    try:
        # 多拉60天用于均线预热
        sd_dt = datetime.strptime(start_date, "%Y%m%d") - timedelta(days=90)
        sd = sd_dt.strftime("%Y%m%d")

        df = pro.daily(ts_code=ts_code, start_date=sd, end_date=end_date,
                       fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount")
        if df is None or df.empty:
            return None

        # 获取复权因子
        adj = pro.adj_factor(ts_code=ts_code, start_date=sd, end_date=end_date,
                             fields="trade_date,adj_factor")
        if adj is not None and not adj.empty:
            df = df.merge(adj, on="trade_date", how="left")
            df["adj_factor"] = df["adj_factor"].fillna(method="ffill").fillna(1.0)
            # 前复权：以最新复权因子为基准
            latest_factor = df["adj_factor"].iloc[-1] if len(df) > 0 else 1.0
            for col in ["open", "high", "low", "close", "pre_close"]:
                df[col] = df[col] * df["adj_factor"] / latest_factor
        else:
            df["adj_factor"] = 1.0

        df = df.sort_values("trade_date").reset_index(drop=True)

        # 计算均线
        for p in [5, 10, 20, 30, 60]:
            df[f"ma{p}"] = df["close"].rolling(p, min_periods=1).mean().round(4)

        # 计算成交量均线
        df["vol_ma5"] = df["vol"].rolling(5, min_periods=1).mean()

        # 过滤到目标日期范围
        df = df[df["trade_date"] >= start_date].reset_index(drop=True)
        return df

    except Exception as e:
        return None


def _get_stock_universe(strategy: Dict[str, Any], start_date: str) -> List[str]:
    """
    根据策略的 universe 和 stock_filter 获取候选股票池
    返回 ts_code 列表
    """
    universe_cfg = strategy.get("universe", {})
    boards = universe_cfg.get("board", ["主板", "创业板", "科创板"])
    exclude_st = universe_cfg.get("exclude_st", True)

    try:
        # 获取全量股票列表
        df = pro.stock_basic(list_status="L",
                             fields="ts_code,symbol,name,market,list_date,is_hs")
        if df is None or df.empty:
            return []

        # 按板块过滤
        board_map = {
            "主板": lambda r: (r["ts_code"].endswith(".SH") and not r["ts_code"].startswith("688")) or
                              (r["ts_code"].endswith(".SZ") and not r["ts_code"].startswith("3")),
            "创业板": lambda r: r["ts_code"].startswith("3") and r["ts_code"].endswith(".SZ"),
            "科创板": lambda r: r["ts_code"].startswith("688") and r["ts_code"].endswith(".SH"),
            "北交所": lambda r: r["ts_code"].endswith(".BJ"),
        }

        filtered = []
        for _, row in df.iterrows():
            for board in boards:
                if board in board_map and board_map[board](row):
                    filtered.append(row["ts_code"])
                    break

        # 排除ST
        if exclude_st:
            try:
                st_df = pro.namechange(fields="ts_code,name,start_date,end_date")
                if st_df is not None and not st_df.empty:
                    st_codes = set(
                        st_df[st_df["name"].str.contains("ST|退", na=False)]["ts_code"].tolist()
                    )
                    filtered = [c for c in filtered if c not in st_codes]
            except Exception:
                pass

        # 最小上市天数过滤
        min_days = universe_cfg.get("min_list_days", 180)
        if min_days > 0:
            cutoff = (datetime.strptime(start_date, "%Y%m%d") - timedelta(days=min_days)).strftime("%Y%m%d")
            df_map = df.set_index("ts_code")["list_date"].to_dict()
            filtered = [c for c in filtered if df_map.get(c, "99999999") <= cutoff]

        return filtered

    except Exception:
        return []


# ── 事件检测函数 ─────────────────────────────────────────────────────────────

def _detect_limit_up_streaks(df: pd.DataFrame, ts_code: str, min_count: int) -> List[Dict]:
    """
    检测连板序列
    返回每段连板的信息：{start_date, end_date, count, max_high, last_close, dates}
    """
    limit_pct = _get_limit_pct(ts_code)
    threshold = limit_pct * 0.98  # 允许2%误差（一字板等）

    streaks = []
    i = 0
    n = len(df)

    while i < n:
        # 判断当天是否涨停
        if df.iloc[i]["pct_chg"] / 100 >= threshold:
            # 开始一段连板
            streak_start = i
            streak_dates = [df.iloc[i]["trade_date"]]
            j = i + 1
            while j < n and df.iloc[j]["pct_chg"] / 100 >= threshold:
                streak_dates.append(df.iloc[j]["trade_date"])
                j += 1

            count = len(streak_dates)
            if count >= min_count:
                streak_slice = df.iloc[streak_start:j]
                streaks.append({
                    "start_date": streak_dates[0],
                    "end_date": streak_dates[-1],
                    "count": count,
                    "max_high": float(streak_slice["high"].max()),
                    "last_close": float(df.iloc[j - 1]["close"]),
                    "dates": streak_dates,
                    "end_idx": j - 1,  # 最后连板日在 df 中的索引
                })
            i = j
        else:
            i += 1

    return streaks


def _check_break_condition(df: pd.DataFrame, streak: Dict, ts_code: str) -> Optional[Dict]:
    """
    检查断板条件：
    - 连板结束后第一个交易日未涨停
    - 收盘价 >= 最后连板日收盘价
    返回断板日信息，不满足则返回 None
    """
    limit_pct = _get_limit_pct(ts_code)
    threshold = limit_pct * 0.98

    end_idx = streak["end_idx"]
    break_idx = end_idx + 1

    if break_idx >= len(df):
        return None

    break_row = df.iloc[break_idx]

    # 未涨停
    if break_row["pct_chg"] / 100 >= threshold:
        return None

    # 收盘价 >= 最后连板日收盘价
    if break_row["close"] < streak["last_close"]:
        return None

    return {
        "date": break_row["trade_date"],
        "close": float(break_row["close"]),
        "pct_chg": float(break_row["pct_chg"]),
        "idx": break_idx,
    }


def _check_strength_confirm(df: pd.DataFrame, break_info: Dict, streak: Dict, window_days: int = 5) -> bool:
    """
    强势确认：断板后 window_days 个交易日内，最高价 > 连板期间最高价
    """
    break_idx = break_info["idx"]
    end_idx = min(break_idx + window_days, len(df) - 1)

    if end_idx <= break_idx:
        return False

    window_slice = df.iloc[break_idx + 1: end_idx + 1]
    if window_slice.empty:
        return False

    window_max_high = float(window_slice["high"].max())
    return window_max_high > streak["max_high"]


def _find_entry_signal(
    df: pd.DataFrame,
    break_info: Dict,
    entry_conditions: Dict[str, Any],
    trigger_window_days: int,
) -> Optional[Dict]:
    """
    在断板日后的 trigger_window_days 内寻找进场信号

    支持的进场条件类型：
    - price_vs_ma: 收盘价与均线的关系（如 close <= ma10）
    - price_vs_value: 收盘价与固定值的关系
    - volume_condition: 成交量条件
    """
    break_idx = break_info["idx"]
    search_start = break_idx + 1
    search_end = min(break_idx + trigger_window_days + 1, len(df))

    conditions = entry_conditions.get("conditions", [])
    logic = entry_conditions.get("logic", "AND")

    for i in range(search_start, search_end):
        row = df.iloc[i]
        results = []

        for cond in conditions:
            cond_type = cond.get("type", "")
            met = False

            if cond_type == "price_vs_ma":
                ma_period = cond.get("ma_period", 10)
                op = cond.get("op", "<=")
                ma_col = f"ma{ma_period}"
                if ma_col in df.columns:
                    ma_val = float(row[ma_col])
                    price = float(row["close"])
                    met = _compare(price, op, ma_val)

            elif cond_type == "price_vs_value":
                op = cond.get("op", "<=")
                value = cond.get("value", 0)
                price = float(row["close"])
                met = _compare(price, op, value)

            elif cond_type == "volume_condition":
                op = cond.get("op", ">")
                ref = cond.get("reference", "vol_ma5")
                multiplier = cond.get("multiplier", 1.0)
                if ref in df.columns:
                    ref_val = float(row[ref]) * multiplier
                    vol = float(row["vol"])
                    met = _compare(vol, op, ref_val)

            elif cond_type == "pct_chg_condition":
                op = cond.get("op", ">")
                value = cond.get("value", 0)
                pct = float(row["pct_chg"])
                met = _compare(pct, op, value)

            results.append(met)

        # 逻辑组合
        if not results:
            continue
        if logic == "AND" and all(results):
            return {
                "date": row["trade_date"],
                "entry_price": float(row["close"]),
                "idx": i,
                "days_after_break": i - break_idx,
                "conditions_met": [c.get("description", "") for c, r in zip(conditions, results) if r],
            }
        elif logic == "OR" and any(results):
            return {
                "date": row["trade_date"],
                "entry_price": float(row["close"]),
                "idx": i,
                "days_after_break": i - break_idx,
                "conditions_met": [c.get("description", "") for c, r in zip(conditions, results) if r],
            }

    return None


def _compare(a: float, op: str, b: float) -> bool:
    ops = {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": abs(a - b) < 1e-9}
    return ops.get(op, False)


# ── 主扫描函数 ───────────────────────────────────────────────────────────────

def scan_signals(
    strategy: Dict[str, Any],
    start_date: str,
    end_date: str,
    stock_list: Optional[List[str]] = None,
    max_stocks: int = 200,
    progress_callback=None,
) -> List[Dict[str, Any]]:
    """
    扫描历史数据，找出所有满足策略条件的进场信号

    Args:
        strategy: 解析后的策略结构
        start_date: 回测开始日期 YYYYMMDD
        end_date: 回测结束日期 YYYYMMDD
        stock_list: 指定股票池（None则自动筛选）
        max_stocks: 最多扫描股票数量
        progress_callback: 进度回调 fn(current, total, ts_code)

    Returns:
        进场信号列表，每个信号包含完整的上下文信息
    """
    signals = []

    # 获取候选股票池
    if stock_list is None:
        stock_list = _get_stock_universe(strategy, start_date)

    if not stock_list:
        return []

    stock_list = stock_list[:max_stocks]

    # 解析策略参数
    stock_filter = strategy.get("stock_filter", {})
    entry_cfg = strategy.get("entry_conditions", {})
    trigger_window = entry_cfg.get("trigger_window_days", 30)
    prereq_events = entry_cfg.get("prerequisite_events", [])
    confirm_window = 5  # 强势确认窗口默认5天

    # 从 prerequisite_events 提取参数
    for evt in prereq_events:
        if evt.get("type") == "new_high_confirm":
            confirm_window = evt.get("window_days", 5)

    # 从 stock_filter 提取连板参数
    limit_up_filter = None
    for tf in stock_filter.get("technical", []):
        if tf.get("type") == "limit_up_streak":
            limit_up_filter = tf
            break

    if limit_up_filter is None:
        # 非连板策略，使用通用扫描
        return _scan_generic(strategy, stock_list, start_date, end_date, progress_callback)

    # 连板策略扫描
    total = len(stock_list)
    for idx, ts_code in enumerate(stock_list):
        if progress_callback:
            progress_callback(idx + 1, total, ts_code)

        # 按板块过滤
        board = _get_board_type(ts_code)
        board_type = limit_up_filter.get("board_type", "")
        if board_type == "20cm" and board not in ("创业板", "科创板"):
            continue
        if board_type == "10cm" and board not in ("主板",):
            continue

        min_count = limit_up_filter.get("min_count", 2)

        # 拉取前复权数据（多拉120天用于均线预热）
        fetch_start = (datetime.strptime(start_date, "%Y%m%d") - timedelta(days=120)).strftime("%Y%m%d")
        df = _fetch_daily_qfq(ts_code, fetch_start, end_date)
        if df is None or len(df) < 20:
            continue

        # 检测连板序列
        streaks = _detect_limit_up_streaks(df, ts_code, min_count)

        for streak in streaks:
            # 只处理回测区间内的连板
            if streak["end_date"] < start_date or streak["end_date"] > end_date:
                continue

            # 检查断板条件
            break_info = _check_break_condition(df, streak, ts_code)
            if break_info is None:
                continue

            # 检查强势确认（如果策略要求）
            has_confirm_req = any(e.get("type") == "new_high_confirm" for e in prereq_events)
            if has_confirm_req:
                confirmed = _check_strength_confirm(df, break_info, streak, confirm_window)
                if not confirmed:
                    continue

            # 寻找进场信号
            entry = _find_entry_signal(df, break_info, entry_cfg, trigger_window)
            if entry is None:
                continue

            # 构建信号记录
            signal = {
                "ts_code": ts_code,
                "board": board,
                "limit_pct": _get_limit_pct(ts_code),
                "streak": {
                    "start_date": streak["start_date"],
                    "end_date": streak["end_date"],
                    "count": streak["count"],
                    "max_high": streak["max_high"],
                    "last_close": streak["last_close"],
                },
                "break_date": break_info["date"],
                "break_close": break_info["close"],
                "break_pct_chg": break_info["pct_chg"],
                "entry_date": entry["date"],
                "entry_price": entry["entry_price"],
                "days_after_break": entry["days_after_break"],
                "conditions_met": entry["conditions_met"],
                "entry_idx": entry["idx"],
                "df": df,  # 保留 df 供回测引擎使用
            }
            signals.append(signal)

        # Tushare 限流保护
        time.sleep(0.05)

    return signals


def _scan_generic(
    strategy: Dict[str, Any],
    stock_list: List[str],
    start_date: str,
    end_date: str,
    progress_callback=None,
) -> List[Dict[str, Any]]:
    """通用信号扫描（非连板策略的兜底实现）"""
    # 通用扫描：直接在每日数据上检查 entry_conditions
    signals = []
    entry_cfg = strategy.get("entry_conditions", {})
    total = len(stock_list)

    for idx, ts_code in enumerate(stock_list):
        if progress_callback:
            progress_callback(idx + 1, total, ts_code)

        fetch_start = (datetime.strptime(start_date, "%Y%m%d") - timedelta(days=90)).strftime("%Y%m%d")
        df = _fetch_daily_qfq(ts_code, fetch_start, end_date)
        if df is None or len(df) < 20:
            continue

        df_range = df[df["trade_date"] >= start_date]
        for i, row in df_range.iterrows():
            conditions = entry_cfg.get("conditions", [])
            results = []
            for cond in conditions:
                cond_type = cond.get("type", "")
                met = False
                if cond_type == "price_vs_ma":
                    ma_col = f"ma{cond.get('ma_period', 10)}"
                    if ma_col in df.columns:
                        met = _compare(float(row["close"]), cond.get("op", "<="), float(row[ma_col]))
                results.append(met)

            if results and all(results):
                signals.append({
                    "ts_code": ts_code,
                    "entry_date": row["trade_date"],
                    "entry_price": float(row["close"]),
                    "entry_idx": i,
                    "df": df,
                })

        time.sleep(0.05)

    return signals
