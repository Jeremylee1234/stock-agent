"""
回测引擎 - 对每个进场信号模拟持仓，计算收益指标

输入：进场信号列表（来自 signal_scanner）+ 出场规则
输出：每笔交易记录 + 汇总统计指标
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def _calc_trade(
    df: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    exit_rules: Dict[str, Any],
) -> Dict[str, Any]:
    """
    模拟单笔交易，返回交易结果

    出场优先级：止损 > 止盈 > 最大持仓天数
    """
    stop_loss_pct = exit_rules.get("stop_loss_pct", -8) / 100      # 默认 -8%
    take_profit_pct = exit_rules.get("take_profit_pct")             # None = 不设止盈
    max_hold_days = exit_rules.get("max_hold_days", 30)
    commission = exit_rules.get("commission_rate", 0.0003)
    slippage = exit_rules.get("slippage_pct", 0.001)

    if take_profit_pct is not None:
        take_profit_pct = take_profit_pct / 100

    # 实际买入价（含滑点）
    actual_entry = entry_price * (1 + slippage)

    n = len(df)
    exit_idx = None
    exit_price = None
    exit_reason = "max_hold"

    for i in range(entry_idx + 1, min(entry_idx + max_hold_days + 1, n)):
        row = df.iloc[i]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        # 日内先检查止损（用最低价）
        if (low - actual_entry) / actual_entry <= stop_loss_pct:
            exit_price = actual_entry * (1 + stop_loss_pct)
            exit_idx = i
            exit_reason = "stop_loss"
            break

        # 再检查止盈（用最高价）
        if take_profit_pct is not None and (high - actual_entry) / actual_entry >= take_profit_pct:
            exit_price = actual_entry * (1 + take_profit_pct)
            exit_idx = i
            exit_reason = "take_profit"
            break

        # 到期出场（收盘价）
        if i == entry_idx + max_hold_days:
            exit_price = close
            exit_idx = i
            exit_reason = "max_hold"
            break

    # 如果数据不足，用最后一天收盘价出场
    if exit_idx is None:
        exit_idx = min(entry_idx + max_hold_days, n - 1)
        exit_price = float(df.iloc[exit_idx]["close"])
        exit_reason = "data_end"

    # 实际卖出价（含滑点，卖出方向）
    actual_exit = exit_price * (1 - slippage)

    # 收益计算（含双边手续费）
    gross_return = (actual_exit - actual_entry) / actual_entry
    net_return = gross_return - commission * 2  # 买卖各一次

    hold_days = exit_idx - entry_idx

    # 持仓期间最大回撤
    hold_slice = df.iloc[entry_idx: exit_idx + 1]
    prices = hold_slice["close"].values
    peak = actual_entry
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (p - peak) / peak
        if dd < max_dd:
            max_dd = dd

    return {
        "entry_date": df.iloc[entry_idx]["trade_date"],
        "entry_price": round(actual_entry, 4),
        "exit_date": df.iloc[exit_idx]["trade_date"],
        "exit_price": round(actual_exit, 4),
        "exit_reason": exit_reason,
        "hold_days": hold_days,
        "gross_return_pct": round(gross_return * 100, 4),
        "net_return_pct": round(net_return * 100, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
    }


def run_backtest(
    signals: List[Dict[str, Any]],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    对所有进场信号执行回测

    Returns:
        {
            "trades": [...],          # 每笔交易详情
            "summary": {...},         # 汇总统计
            "equity_curve": [...],    # 资金曲线（按时间排序）
            "by_year": {...},         # 按年分析
            "by_board": {...},        # 按板块分析
        }
    """
    exit_rules = strategy.get("exit_rules", {})
    bt_cfg = strategy.get("backtest_config", {})
    initial_capital = bt_cfg.get("initial_capital", 1_000_000)

    trades = []

    for sig in signals:
        df = sig.get("df")
        if df is None:
            continue

        entry_idx = sig.get("entry_idx")
        entry_price = sig.get("entry_price")
        if entry_idx is None or entry_price is None:
            continue

        trade = _calc_trade(df, entry_idx, entry_price, exit_rules)

        # 附加信号上下文
        trade["ts_code"] = sig.get("ts_code", "")
        trade["board"] = sig.get("board", "")
        trade["streak_count"] = sig.get("streak", {}).get("count", 0)
        trade["break_date"] = sig.get("break_date", "")
        trade["days_after_break"] = sig.get("days_after_break", 0)
        trade["conditions_met"] = sig.get("conditions_met", [])

        trades.append(trade)

    if not trades:
        return {
            "trades": [],
            "summary": _empty_summary(),
            "equity_curve": [],
            "by_year": {},
            "by_board": {},
        }

    # ── 汇总统计 ─────────────────────────────────────────────────────────────
    returns = [t["net_return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate = len(wins) / len(returns) if returns else 0
    avg_return = float(np.mean(returns)) if returns else 0
    avg_win = float(np.mean(wins)) if wins else 0
    avg_loss = float(np.mean(losses)) if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")

    # 夏普比率（假设无风险利率 3%/年，每笔交易独立）
    if len(returns) > 1:
        std = float(np.std(returns, ddof=1))
        sharpe = (avg_return - 3 / 252 * float(np.mean([t["hold_days"] for t in trades]))) / std if std > 0 else 0
    else:
        sharpe = 0

    # 最大连续亏损
    max_consec_loss = _max_consecutive_losses(returns)

    # 资金曲线（简单累乘，假设每笔独立）
    equity = initial_capital
    equity_curve = []
    for t in sorted(trades, key=lambda x: x["entry_date"]):
        equity *= (1 + t["net_return_pct"] / 100)
        equity_curve.append({
            "date": t["exit_date"],
            "equity": round(equity, 2),
            "trade_return_pct": t["net_return_pct"],
        })

    total_return = (equity - initial_capital) / initial_capital * 100

    summary = {
        "total_trades": len(trades),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round(win_rate * 100, 2),
        "avg_return_pct": round(avg_return, 4),
        "avg_win_pct": round(avg_win, 4),
        "avg_loss_pct": round(avg_loss, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "∞",
        "max_return_pct": round(max(returns), 4),
        "min_return_pct": round(min(returns), 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_consecutive_losses": max_consec_loss,
        "avg_hold_days": round(float(np.mean([t["hold_days"] for t in trades])), 1),
        "total_return_pct": round(total_return, 4),
        "final_equity": round(equity, 2),
        "exit_reason_dist": _count_exit_reasons(trades),
    }

    # ── 按年分析 ─────────────────────────────────────────────────────────────
    by_year: Dict[str, Any] = {}
    for t in trades:
        year = t["entry_date"][:4]
        if year not in by_year:
            by_year[year] = {"trades": 0, "wins": 0, "returns": []}
        by_year[year]["trades"] += 1
        if t["net_return_pct"] > 0:
            by_year[year]["wins"] += 1
        by_year[year]["returns"].append(t["net_return_pct"])

    by_year_summary = {}
    for year, data in sorted(by_year.items()):
        r = data["returns"]
        by_year_summary[year] = {
            "trades": data["trades"],
            "win_rate_pct": round(data["wins"] / data["trades"] * 100, 1),
            "avg_return_pct": round(float(np.mean(r)), 4),
            "total_return_pct": round(float(np.sum(r)), 4),
        }

    # ── 按板块分析 ───────────────────────────────────────────────────────────
    by_board: Dict[str, Any] = {}
    for t in trades:
        board = t.get("board", "未知")
        if board not in by_board:
            by_board[board] = {"trades": 0, "wins": 0, "returns": []}
        by_board[board]["trades"] += 1
        if t["net_return_pct"] > 0:
            by_board[board]["wins"] += 1
        by_board[board]["returns"].append(t["net_return_pct"])

    by_board_summary = {}
    for board, data in by_board.items():
        r = data["returns"]
        by_board_summary[board] = {
            "trades": data["trades"],
            "win_rate_pct": round(data["wins"] / data["trades"] * 100, 1),
            "avg_return_pct": round(float(np.mean(r)), 4),
        }

    return {
        "trades": trades,
        "summary": summary,
        "equity_curve": equity_curve,
        "by_year": by_year_summary,
        "by_board": by_board_summary,
    }


def _max_consecutive_losses(returns: List[float]) -> int:
    max_streak = 0
    current = 0
    for r in returns:
        if r <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _count_exit_reasons(trades: List[Dict]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        dist[reason] = dist.get(reason, 0) + 1
    return dist


def _empty_summary() -> Dict[str, Any]:
    return {
        "total_trades": 0,
        "win_rate_pct": 0,
        "avg_return_pct": 0,
        "total_return_pct": 0,
        "message": "未找到满足条件的交易信号",
    }
