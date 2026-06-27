"""Tushare Pro 客户端单例（降级数据源）。"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

import tushare as ts

from config.settings import TUSHARE_TOKEN

_tushare_token = TUSHARE_TOKEN or os.getenv("DATA_SOURCE__TUSHARE_TOKEN", "")
pro = ts.pro_api(_tushare_token) if _tushare_token else ts.pro_api()
if _tushare_token:
    pro._DataApi__token = _tushare_token
_custom_tushare_url = os.getenv("TUSHARE_HTTP_URL")
if _custom_tushare_url:
    pro._DataApi__http_url = _custom_tushare_url

_tushare_semaphore = threading.Semaphore(2)
_tushare_retry_config = {
    "max_retries": 5,
    "base_delay": 2,
    "max_delay": 60,
    "retry_on_errors": ["每分钟最多访问", "最多访问", "rate limit", "too many", "并发"],
}


def tushare_api_call_with_retry(func: Callable, *args, **kwargs) -> Any:
    last_error = None
    for attempt in range(_tushare_retry_config["max_retries"]):
        acquired = _tushare_semaphore.acquire(timeout=120)
        if not acquired:
            time.sleep(5)
            continue
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            last_error = e
            is_rate_limit = any(err in error_msg for err in _tushare_retry_config["retry_on_errors"])
            if is_rate_limit:
                delay = min(
                    _tushare_retry_config["base_delay"] * (2 ** attempt),
                    _tushare_retry_config["max_delay"],
                )
                time.sleep(delay)
            else:
                raise
        finally:
            _tushare_semaphore.release()
    raise last_error
