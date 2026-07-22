#!/usr/bin/env python3
"""Small standard-library HTTP client with conservative network defaults."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|signature|token)", re.IGNORECASE
)
_LAST_REQUEST: dict[str, float] = {}


def _public_addresses(host: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> list[str]:
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        records = resolver(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({str(record[4][0]).split("%", 1)[0] for record in records})
    else:
        addresses = [str(literal)]
    if not addresses:
        raise ValueError(f"host did not resolve: {host}")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ValueError(f"remote host resolves to a non-public address: {address}")
    return addresses


def validate_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("remote collection requires HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("remote URL must not contain embedded credentials")
    sensitive_keys = [key for key, _ in parse_qsl(parsed.query) if SENSITIVE_QUERY_KEY.search(key)]
    if sensitive_keys:
        raise ValueError("remote URL must not contain credential-like query parameters")
    host = str(parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("remote URL requires a hostname")
    if parsed.port not in (None, 443):
        raise ValueError("remote collection only permits HTTPS port 443")
    normalized_hosts = {item.lower().rstrip(".") for item in allowed_hosts or set()}
    if normalized_hosts and host not in normalized_hosts:
        raise ValueError(f"remote host is not allowed: {host}")
    _public_addresses(host, resolver)
    return url


class SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str], max_redirects: int = 3):
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.max_redirections = max_redirects
        self.max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_url(target, allowed_hosts=self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _cache_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.json", cache_dir / f"{key}.body"


def _load_cache(cache_dir: Path | None, url: str) -> tuple[dict[str, str], bytes | None]:
    if cache_dir is None:
        return {}, None
    metadata_path, body_path = _cache_paths(cache_dir, url)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        body = body_path.read_bytes()
    except (OSError, json.JSONDecodeError):
        return {}, None
    return metadata if isinstance(metadata, dict) else {}, body


def _save_cache(cache_dir: Path | None, url: str, headers: Any, body: bytes) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    metadata_path, body_path = _cache_paths(cache_dir, url)
    metadata = {
        "etag": str(headers.get("ETag", "")),
        "last_modified": str(headers.get("Last-Modified", "")),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    body_path.write_bytes(body)


def _retry_delay(error: HTTPError | None, attempt: int, cap: float) -> float:
    if error is not None:
        value = str(error.headers.get("Retry-After", "")).strip()
        if value.isdigit():
            return min(float(value), cap)
        if value:
            try:
                return min(max(parsedate_to_datetime(value).timestamp() - time.time(), 0), cap)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(0.5 * (2**attempt), cap)


def fetch_bytes(
    url: str,
    *,
    allowed_hosts: set[str],
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_bytes: int = 5_000_000,
    retries: int = 2,
    min_interval: float = 1.0,
    retry_delay_cap: float = 30.0,
    cache_dir: Path | None = None,
    method: str = "GET",
    data: bytes | None = None,
) -> tuple[bytes, str, bool]:
    """Fetch a public HTTPS resource and return body, content type, cache-hit flag."""

    validate_url(url, allowed_hosts=allowed_hosts)
    parsed = urlparse(url)
    host = str(parsed.hostname).lower()
    normalized_method = method.upper()
    if normalized_method not in {"GET", "POST"}:
        raise ValueError("HTTP method must be GET or POST")
    cache_key = url
    if normalized_method != "GET":
        digest = hashlib.sha256(data or b"").hexdigest()
        cache_key = f"{normalized_method} {url} {digest}"
    cache_metadata, cached_body = _load_cache(cache_dir, cache_key)
    request_headers = {
        "Accept": "application/json, application/feed+json, application/atom+xml, application/rss+xml, application/xml, text/xml",
        "User-Agent": "a-share-evidence-radar/0.3 (+https://github.com/FullFighting/a-share-evidence-radar)",
    }
    request_headers.update(headers or {})
    if cache_metadata.get("etag"):
        request_headers["If-None-Match"] = cache_metadata["etag"]
    if cache_metadata.get("last_modified"):
        request_headers["If-Modified-Since"] = cache_metadata["last_modified"]
    opener = build_opener(SafeRedirectHandler(allowed_hosts))

    for attempt in range(retries + 1):
        remaining = min_interval - (time.monotonic() - _LAST_REQUEST.get(host, 0.0))
        if remaining > 0:
            time.sleep(remaining)
        request = Request(url, data=data, headers=request_headers, method=normalized_method)
        error: HTTPError | None = None
        try:
            _LAST_REQUEST[host] = time.monotonic()
            with opener.open(request, timeout=timeout) as response:
                validate_url(response.geturl(), allowed_hosts=allowed_hosts)
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise ValueError(f"response exceeds {max_bytes} bytes")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ValueError(f"response exceeds {max_bytes} bytes")
                _save_cache(cache_dir, cache_key, response.headers, body)
                return body, str(response.headers.get("Content-Type", "")), False
        except HTTPError as exc:
            if exc.code == 304 and cached_body is not None:
                return cached_body, "", True
            error = exc
            if exc.code not in RETRYABLE_STATUS or attempt >= retries:
                raise
        except URLError:
            if attempt >= retries:
                raise
        time.sleep(_retry_delay(error, attempt, retry_delay_cap))
    raise RuntimeError("unreachable retry loop")
