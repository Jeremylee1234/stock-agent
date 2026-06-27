"""iFinD 量化 API HTTP 客户端（标准库 + 项目配置）。"""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

IFIND_BASE_URL = "https://quantapi.51ifind.com/api/v1"
TOKEN_CACHE_TTL = 86400
# 无数据时 iFinD 返回非零 errorcode，应视为空结果而非异常
IFIND_EMPTY_DATA_CODES = frozenset({-4001})
LOG_MAX_BYTES = 1 * 1024 * 1024
LOG_KEEP_BYTES = 500 * 1024

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / ".data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class IFindAPIError(Exception):
    """iFinD API 业务或网络错误。"""

    def __init__(self, message: str, errorcode: Optional[int] = None):
        super().__init__(message)
        self.errorcode = errorcode


class IFindClient:
    """iFinD API 调用：token 缓存、过期重试、限流友好。"""

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        timeout: int = 30,
        cache_dir: Optional[Path] = None,
    ):
        self.refresh_token = (
            refresh_token
            or os.getenv("IFIND_REFRESH_TOKEN")
            or os.getenv("DATA_SOURCE__IFIND_REFRESH_TOKEN")
        )
        if self.refresh_token:
            self.refresh_token = self.refresh_token.strip().strip("'").strip('"')
        self.timeout = timeout
        self.cache_dir = cache_dir or DATA_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._token_cache_file = self.cache_dir / "access_token"
        self._log_file = self.cache_dir / "ifind.log"

    def is_configured(self) -> bool:
        return bool(self.refresh_token and self.refresh_token.strip())

    def _http_post(self, url: str, headers: Optional[Dict[str, str]] = None, body: bytes = b"") -> bytes:
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            body_bytes = e.read() if hasattr(e, "read") else b""
            raise IFindAPIError(
                f"HTTP {e.code}: {body_bytes.decode('utf-8', errors='replace')}"
            ) from e
        except urllib.error.URLError as e:
            raise IFindAPIError(f"网络请求失败: {e.reason}") from e

    def _rotate_log(self) -> None:
        try:
            size = self._log_file.stat().st_size
        except OSError:
            return
        if size <= LOG_MAX_BYTES:
            return
        try:
            data = self._log_file.read_bytes()
        except OSError:
            return
        if len(data) > LOG_KEEP_BYTES:
            data = data[-LOG_KEEP_BYTES:]
            idx = data.find(b"\n")
            if idx >= 0:
                data = data[idx + 1 :]
        self._log_file.write_bytes(data)

    def _log(self, endpoint: str, status: str, err_msg: str = "", latency_ms: int = 0) -> None:
        self._rotate_log()
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] endpoint={endpoint} status={status} latency={latency_ms}ms"
            if err_msg:
                line += f' error="{err_msg}"'
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def get_access_token(self, force_refresh: bool = False) -> str:
        if not self.is_configured():
            raise IFindAPIError("缺少 IFIND_REFRESH_TOKEN，请在 .env 中配置")

        if not force_refresh:
            try:
                stat = self._token_cache_file.stat()
                age = time.time() - stat.st_mtime
                if age < TOKEN_CACHE_TTL:
                    token = self._token_cache_file.read_text(encoding="utf-8").strip()
                    if token:
                        return token
            except OSError:
                pass

        start = time.time()
        try:
            data = self._http_post(
                IFIND_BASE_URL + "/get_access_token",
                headers={"refresh_token": self.refresh_token},
                body=b"{}",
            )
        except IFindAPIError as e:
            self._log("get_access_token", "error", str(e), int((time.time() - start) * 1000))
            raise

        try:
            result = json.loads(data)
        except json.JSONDecodeError as e:
            raise IFindAPIError(f"get_access_token 响应非 JSON: {data[:200]!r}") from e

        data_obj = result.get("data")
        if not isinstance(data_obj, dict):
            raise IFindAPIError("get_access_token 失败，请检查 refresh_token 是否有效")

        token = data_obj.get("access_token", "")
        if not token:
            raise IFindAPIError("get_access_token 未返回 access_token")

        self._token_cache_file.write_text(token, encoding="utf-8")
        self._log("get_access_token", "ok", latency_ms=int((time.time() - start) * 1000))
        return token

    def _clear_token_cache(self) -> None:
        try:
            self._token_cache_file.unlink(missing_ok=True)
        except OSError:
            pass

    def call(self, endpoint: str, body: Dict[str, Any], retry_on_expired: bool = True) -> Dict[str, Any]:
        """调用 iFinD API，返回解析后的 JSON dict。"""
        access_token = self.get_access_token()
        start = time.time()
        raw = self._call_raw(access_token, endpoint, body)

        errorcode = raw.get("errorcode")
        if retry_on_expired and errorcode is not None:
            try:
                if int(errorcode) == -1302:
                    self._clear_token_cache()
                    access_token = self.get_access_token(force_refresh=True)
                    raw = self._call_raw(access_token, endpoint, body)
            except (TypeError, ValueError):
                pass

        latency_ms = int((time.time() - start) * 1000)
        errorcode = raw.get("errorcode", 0)
        try:
            ec = int(errorcode)
        except (TypeError, ValueError):
            ec = 0

        if ec != 0:
            if ec in IFIND_EMPTY_DATA_CODES:
                raw = dict(raw)
                raw["errorcode"] = 0
                raw.setdefault("tables", [])
                raw["_ifind_empty"] = True
                self._log(endpoint, "empty", latency_ms=latency_ms)
                return raw
            errmsg = raw.get("errmsg") or raw.get("errMsg") or f"errorcode={errorcode}"
            self._log(endpoint, "error", str(errmsg), latency_ms)
            raise IFindAPIError(str(errmsg), errorcode=ec)

        self._log(endpoint, "ok", latency_ms=latency_ms)
        return raw

    def _call_raw(self, access_token: str, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = IFIND_BASE_URL + "/" + endpoint
        headers = {
            "access_token": access_token,
            "Accept-Encoding": "gzip,deflate",
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        data = self._http_post(url, headers=headers, body=payload)
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise IFindAPIError(f"API 响应非 JSON: {data[:300]!r}") from e


_client: Optional[IFindClient] = None


def get_ifind_client() -> IFindClient:
    global _client
    if _client is None:
        _client = IFindClient()
    return _client
