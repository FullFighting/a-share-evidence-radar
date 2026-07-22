#!/usr/bin/env python3
"""Shared normalization helpers for primary-disclosure adapters."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


EVENT_TERMS = {
    "regulatory": ("问询", "监管", "调查", "处罚", "警示"),
    "merger": ("并购", "重组", "收购", "控制权"),
    "earnings": ("业绩", "盈利", "亏损", "营收", "净利润", "年报", "季报"),
    "litigation": ("诉讼", "仲裁", "判决"),
    "insider_change": ("增持", "减持", "解禁", "质押"),
    "contract": ("合同", "订单", "中标"),
    "buyback": ("回购",),
    "operations": ("停产", "复产", "事故", "投产"),
}


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_symbol(value: Any) -> str:
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(value or ""))
    return match.group(1) if match else ""


def normalize_time(value: Any) -> str:
    text = str(value or "").strip().replace("/", "-")
    if not text:
        raise ValueError("disclosure requires a publication time")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00+08:00"
    else:
        text = text.replace(" ", "T", 1).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.isoformat()


def infer_event_type(title: str) -> str:
    for event_type, terms in EVENT_TERMS.items():
        if any(term in title for term in terms):
            return event_type
    return "other"


def make_event(
    *,
    source: str,
    symbol: Any,
    title: Any,
    published_at: Any,
    url: Any,
    identifier: Any,
    base_url: str,
    origin_prefix: str,
    allowed_url_hosts: set[str],
) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    normalized_title = re.sub(r"\s+", " ", str(title or "")).strip()
    canonical_url = urljoin(base_url, str(url or "").strip())
    if not normalized_symbol:
        raise ValueError("disclosure requires a six-digit security code")
    if not normalized_title:
        raise ValueError("disclosure requires a title")
    parsed_url = urlparse(canonical_url)
    if parsed_url.scheme != "https":
        raise ValueError("disclosure requires a canonical HTTPS URL")
    if str(parsed_url.hostname or "").lower() not in allowed_url_hosts:
        raise ValueError("disclosure URL host is outside the adapter contract")
    stable_id = str(identifier or "").strip() or hashlib.sha256(
        canonical_url.encode("utf-8")
    ).hexdigest()[:20]
    return {
        "title": normalized_title,
        "summary": "",
        "source": source,
        "source_tier": 1,
        "source_tier_verified": True,
        "tier_basis": "official_adapter_contract",
        "evidence_origin": f"{origin_prefix}:{stable_id}",
        "url": canonical_url,
        "published_at": normalize_time(published_at),
        "symbols": [normalized_symbol],
        "event_type": infer_event_type(normalized_title),
        "stance": "confirm",
    }


def emit_jsonl(events: list[dict[str, Any]], output: str | None) -> None:
    rendered = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        sys.stdout.write(rendered + ("\n" if rendered else ""))
