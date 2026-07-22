#!/usr/bin/env python3
"""Collect and normalize Shenzhen Stock Exchange disclosure metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import disclosure_common as common
import http_client


SOURCE = "深圳证券交易所"
BASE_URL = "https://disc.static.szse.cn/"
REFERER_URL = "https://www.szse.cn/disclosure/listed/notice/index.html"
DEFAULT_ENDPOINT = "https://www.szse.cn/api/disc/announcement/annList"
ALLOWED_HOSTS = {"www.szse.cn", "disc.static.szse.cn"}


def response_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("SZSE response must be a JSON object")
    rows: Any = payload.get("data")
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("list") or rows.get("announcements")
    if rows is None:
        rows = payload.get("result")
    if not isinstance(rows, list):
        raise ValueError("SZSE response requires a data array")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("SZSE data entries must be objects")
    return rows


def _symbol(row: dict[str, Any]) -> Any:
    value = row.get("secCode") or row.get("securityCode") or row.get("code")
    if isinstance(value, list):
        return value[0] if value else ""
    return value


def normalize_response(payload: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, row in enumerate(response_rows(payload), start=1):
        try:
            events.append(
                common.make_event(
                    source=SOURCE,
                    symbol=_symbol(row),
                    title=row.get("title") or row.get("announcementTitle"),
                    published_at=row.get("publishTime") or row.get("publishDate"),
                    url=row.get("attachPath") or row.get("url") or row.get("announcementUrl"),
                    identifier=row.get("id") or row.get("announcementId") or row.get("attachPath"),
                    base_url=BASE_URL,
                    origin_prefix="szse-announcement",
                    allowed_url_hosts={"disc.static.szse.cn"},
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SZSE data[{index}]: {exc}") from exc
    return events


def build_request(endpoint: str, symbol: str | None, max_items: int) -> tuple[str, bytes]:
    payload: dict[str, Any] = {
        "seDate": ["", ""],
        "channelCode": ["listedNotice_disc"],
        "pageSize": max_items,
        "pageNum": 1,
    }
    if symbol:
        payload["stock"] = [symbol]
    return endpoint, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def fetch_payload(url: str, data: bytes, args: argparse.Namespace) -> Any:
    body, _, _ = http_client.fetch_bytes(
        url,
        allowed_hosts=ALLOWED_HOSTS,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://www.szse.cn",
            "Referer": REFERER_URL,
            "X-Request-Type": "ajax",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        retries=args.retries,
        min_interval=args.min_interval,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        method="POST",
        data=data,
    )
    return json.loads(body.decode("utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect official SZSE disclosure metadata.")
    parser.add_argument("--fixture", help="Offline SZSE JSON response fixture")
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
            requests = [build_request(args.endpoint, symbol, args.max_items) for symbol in symbols]
            payloads = [fetch_payload(url, data, args) for url, data in requests]
        events = [event for payload in payloads for event in normalize_response(payload)]
        common.emit_jsonl(events[: args.max_items], args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    common.configure_utf8_stdio()
    raise SystemExit(main())
