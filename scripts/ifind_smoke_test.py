#!/usr/bin/env python3
"""iFinD 接口联调 smoke test（不打印 token）。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 .env
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def main() -> int:
    from tools.ifind.client import IFindAPIError, get_ifind_client
    from tools.data_sources.ifind_adapter import get_ifind_adapter

    client = get_ifind_client()
    if not client.is_configured():
        print("FAIL: IFIND_REFRESH_TOKEN 未配置")
        return 1

    adapter = get_ifind_adapter()
    tests = []

    def run(name, fn):
        try:
            r = fn()
            ok = bool(r.get("success")) if isinstance(r, dict) else bool(r)
            cnt = r.get("count", 0) if isinstance(r, dict) else "-"
            err = r.get("error") if isinstance(r, dict) else None
            tests.append((name, ok))
            status = "OK" if ok else "FAIL"
            print(f"[{status}] {name}: count={cnt}" + (f" ({err})" if err else ""))
        except IFindAPIError as e:
            tests.append((name, False))
            print(f"[FAIL] {name}: {e}")
        except Exception as e:
            tests.append((name, False))
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")

    run("get_trade_dates", lambda: adapter.get_trade_dates("20250601", "20250605"))
    run("daily_quotation", lambda: adapter.get_daily_quotation(
        "600519.SH", "20250601", "20250605", "open,close,volume"
    ))
    run("realtime_quotation", lambda: adapter.get_realtime_quotation(
        "600519.SH", "latest,changeRatio,mainNetInflow"
    ))
    run("fina_indicator", lambda: adapter.get_fina_indicator(
        "600519.SH", period="20241231", fields="roe,eps"
    ))
    run("financial_series", lambda: adapter.get_financial_series(
        "600519.SH", "20230101", "20241231", "roe,eps"
    ))
    run("edb_gdp", lambda: adapter.get_edb("M001620326", "20240101", "20241231"))
    run("report_query", lambda: adapter.get_report_query(
        "600519.SH", "20240101", "20250601"
    ))
    run("smart_picking_limit_up", lambda: adapter.get_smart_stock_picking("涨停", "stock"))
    run("moneyflow_history", lambda: adapter.get_moneyflow_history(
        "600519.SH", "20250601", "20250605", "net_mf_amount"
    ))

    passed = sum(1 for _, ok in tests if ok)
    print(f"\nResult: {passed}/{len(tests)} passed (report_query 空数据通常为账号权限限制)")
    return 0 if passed >= 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
