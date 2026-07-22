#!/usr/bin/env python3
"""Collect and normalize Shanghai Stock Exchange disclosure metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import disclosure_common as common
import http_client


SOURCE = "上海证券交易所"
BASE_URL = "https://www.sse.com.cn/"
DEFAULT_ENDPOINT = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
ALLOWED_HOSTS = {"query.sse.com.cn", "www.sse.com.cn", "static.sse.com.cn"}


def response_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("SSE response must be a JSON object")
    rows = payload.get("result")
    if rows is None and isinstance(payload.get("pageHelp"), dict):
        rows = payload["pageHelp"].get("data")
    if not isinstance(rows, list):
        raise ValueError("SSE response requires a result array")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("SSE result entries must be objects")
    return rows


def normalize_response(payload: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, row in enumerate(response_rows(payload), start=1):
        try:
            events.append(
                common.make_event(
                    source=SOURCE,
                    symbol=row.get("SECURITY_CODE") or row.get("securityCode"),
                    title=row.get("TITLE") or row.get("title"),
                    published_at=(
                        row.get("SSEDATE")
                        or row.get("BULLETIN_DATE")
                        or row.get("publishTime")
                    ),
                    url=row.get("URL") or row.get("url"),
                    identifier=row.get("BULLETIN_ID") or row.get("bulletinId") or row.get("URL"),
                    base_url=BASE_URL,
                    origin_prefix="sse-announcement",
                    allowed_url_hosts={"www.sse.com.cn", "static.sse.com.cn"},
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SSE result[{index}]: {exc}") from exc
    return events


def build_url(endpoint: str, symbol: str | None, max_items: int) -> str:
    params = {
        "isPagination": "true",
        "productId": symbol or "",
        "keyWord": "",
        "securityType": "0101,120100,020100,020200,120200",
        "pageHelp.pageSize": str(max_items),
        "pageHelp.pageNo": "1",
    }
    return endpoint + ("&" if "?" in endpoint else "?") + urlencode(params)


def fetch_payload(url: str, args: argparse.Namespace) -> Any:
    body, _, _ = http_client.fetch_bytes(
        url,
        allowed_hosts=ALLOWED_HOSTS,
        headers={"Referer": BASE_URL},
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        retries=args.retries,
        min_interval=args.min_interval,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    return json.loads(body.decode("utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect official SSE disclosure metadata.")
    parser.add_argument("--fixture", help="Offline SSE JSON response fixture")
    parser.add_argument("--symbol", action="append", help="Six-digit symbol; repeat as needed")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--max-items", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--min-interval", type=float, default=1.0)
    parser.add_argument("--max-bytes", type=int, default=5_000_000)
    parser.add_argument("--cache-dir", help="Optional local directory for ETag/Last-Modified cache")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.max_items < 1 or args.timeout <= 0 or args.retries < 0:
            raise ValueError("max-items and timeout must be positive; retries must be non-negative")
        if args.fixture:
            payloads = [common.load_json(Path(args.fixture))]
        else:
            symbols = args.symbol or [None]
            payloads = [fetch_payload(build_url(args.endpoint, symbol, args.max_items), args) for symbol in symbols]
        events = [event for payload in payloads for event in normalize_response(payload)]
        common.emit_jsonl(events[: args.max_items], args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    common.configure_utf8_stdio()
    raise SystemExit(main())
