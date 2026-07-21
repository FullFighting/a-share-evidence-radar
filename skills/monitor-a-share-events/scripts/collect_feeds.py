#!/usr/bin/env python3
"""Normalize RSS, Atom, or JSON Feed items into evidence-radar JSONL events."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


EVENT_TERMS = {
    "regulatory": ("问询", "监管", "调查", "处罚", "警示"),
    "merger": ("并购", "重组", "收购", "控制权"),
    "earnings": ("业绩", "盈利", "亏损", "营收", "净利润"),
    "litigation": ("诉讼", "仲裁", "判决"),
    "policy": ("政策", "条例", "办法", "通知"),
    "insider_change": ("增持", "减持", "解禁", "质押"),
    "contract": ("合同", "订单", "中标"),
    "buyback": ("回购",),
    "operations": ("停产", "复产", "事故", "投产"),
    "rumor": ("网传", "传闻", "据传"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read RSS/Atom/JSON Feed inputs and emit normalized JSONL events."
    )
    parser.add_argument(
        "--feed",
        action="append",
        required=True,
        help="Local feed file or explicit http(s) feed URL; repeat for multiple feeds",
    )
    parser.add_argument("--watchlist", help="Optional watchlist JSON used for symbol mapping")
    parser.add_argument("--source", help="Override the source name for all inputs")
    parser.add_argument("--source-tier", type=int, choices=(1, 2, 3, 4), default=3)
    parser.add_argument(
        "--source-registry",
        help="Optional JSON registry that verifies a source name, tier, and allowed host",
    )
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", help="Write JSONL to this file instead of stdout")
    return parser.parse_args()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def strip_markup(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def normalize_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_input(location: str, timeout: float) -> tuple[bytes, str]:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        request = Request(
            location,
            headers={
                "Accept": "application/feed+json, application/atom+xml, application/rss+xml, application/xml, text/xml",
                "User-Agent": "a-share-evidence-radar/1 (+https://github.com/)",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            return response.read(5_000_000), response.headers.get("Content-Type", "")
    path = Path(location)
    if parsed.scheme and not path.is_absolute():
        raise ValueError(f"unsupported feed scheme: {parsed.scheme}")
    return path.read_bytes(), ""


def first_child_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if local_name(child.tag) in names and child.text:
            return strip_markup(child.text)
    return ""


def xml_link(node: ElementTree.Element) -> str:
    for child in node.iter():
        if local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "")).strip()
        relation = str(child.attrib.get("rel", "alternate")).lower()
        if href and relation in {"alternate", ""}:
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def parse_xml(data: bytes) -> tuple[str, list[dict[str, str]]]:
    root = ElementTree.fromstring(data)
    source = first_child_text(root, ("title",))
    nodes = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[dict[str, str]] = []
    for node in nodes:
        items.append(
            {
                "title": first_child_text(node, ("title",)),
                "summary": first_child_text(node, ("summary", "description", "content")),
                "url": xml_link(node),
                "published_at": normalize_time(
                    first_child_text(node, ("published", "updated", "pubdate", "date"))
                ),
                "id": first_child_text(node, ("id", "guid")),
            }
        )
    return source, items


def parse_json_feed(data: bytes) -> tuple[str, list[dict[str, str]]]:
    value = json.loads(data.decode("utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("JSON Feed must contain an items array")
    items: list[dict[str, str]] = []
    for raw in value["items"]:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "title": strip_markup(raw.get("title")),
                "summary": strip_markup(raw.get("summary") or raw.get("content_text") or raw.get("content_html")),
                "url": str(raw.get("url") or raw.get("external_url") or "").strip(),
                "published_at": normalize_time(raw.get("date_published") or raw.get("date_modified")),
                "id": str(raw.get("id", "")).strip(),
            }
        )
    return str(value.get("title", "")).strip(), items


def parse_feed(data: bytes, content_type: str) -> tuple[str, list[dict[str, str]]]:
    stripped = data.lstrip()
    if "json" in content_type.lower() or stripped.startswith((b"{", b"[")):
        return parse_json_feed(data)
    return parse_xml(data)


def load_symbol_aliases(path: str | None) -> dict[str, list[str]]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    symbols = value.get("symbols", {}) if isinstance(value, dict) else {}
    if isinstance(symbols, list):
        return {str(item): [str(item)] for item in symbols}
    result: dict[str, list[str]] = {}
    for raw_symbol, metadata in symbols.items():
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(raw_symbol))
        if not match:
            continue
        aliases = [match.group(1)]
        if isinstance(metadata, dict):
            aliases.extend(str(x).strip() for x in metadata.get("aliases", []) if str(x).strip())
            name = str(metadata.get("name", "")).strip()
            if name:
                aliases.append(name)
        result[match.group(1)] = aliases
    return result


def load_source_registry(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    sources = value.get("sources", {}) if isinstance(value, dict) else {}
    if not isinstance(sources, dict):
        raise ValueError("source registry must contain a sources object")
    return {str(name): entry for name, entry in sources.items() if isinstance(entry, dict)}


def resolve_source_tier(
    location: str,
    source: str,
    claimed_tier: int,
    registry: dict[str, dict[str, Any]],
) -> tuple[int, bool, str]:
    entry = registry.get(source)
    if entry is None:
        return claimed_tier, False, "operator_asserted"
    try:
        tier = int(entry["tier"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"registry source {source!r} requires tier 1-4") from exc
    if tier not in {1, 2, 3, 4}:
        raise ValueError(f"registry source {source!r} requires tier 1-4")
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        hosts = {str(host).lower() for host in entry.get("hosts", [])}
        if hosts and str(parsed.hostname or "").lower() not in hosts:
            raise ValueError(f"feed host is not allowed by registry source {source!r}")
    elif not bool(entry.get("allow_local", False)):
        raise ValueError(f"registry source {source!r} does not allow local fixtures")
    return tier, True, "registry"


def map_symbols(text: str, aliases: dict[str, list[str]]) -> list[str]:
    direct = set(re.findall(r"(?<!\d)(\d{6})(?!\d)", text))
    for symbol, names in aliases.items():
        if any(name and name in text for name in names):
            direct.add(symbol)
    return sorted(direct)


def infer_event_type(text: str) -> str:
    for event_type, terms in EVENT_TERMS.items():
        if any(term in text for term in terms):
            return event_type
    return "other"


def normalize_items(
    items: list[dict[str, str]],
    source: str,
    source_tier: int,
    source_tier_verified: bool,
    tier_basis: str,
    aliases: dict[str, list[str]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in items:
        title = item["title"].strip()
        published_at = item["published_at"].strip()
        if not title or not published_at:
            continue
        combined = f"{title} {item['summary']}"
        fingerprint_text = re.sub(r"\s+", "", combined).lower()
        event: dict[str, Any] = {
            "title": title,
            "summary": item["summary"],
            "source": source or "unnamed feed",
            "source_tier": source_tier,
            "source_tier_verified": source_tier_verified,
            "tier_basis": tier_basis,
            "url": item["url"],
            "published_at": published_at,
            "symbols": map_symbols(combined, aliases),
            "event_type": infer_event_type(combined),
            "stance": "uncertain" if infer_event_type(combined) == "rumor" else "context",
        }
        if len(fingerprint_text) >= 24:
            event["content_fingerprint"] = hashlib.sha256(
                fingerprint_text.encode("utf-8")
            ).hexdigest()[:20]
        if item["id"]:
            event["feed_item_id"] = item["id"]
        events.append(event)
    return events


def main() -> int:
    args = parse_args()
    try:
        if args.max_items < 1:
            raise ValueError("--max-items must be positive")
        aliases = load_symbol_aliases(args.watchlist)
        registry = load_source_registry(args.source_registry)
        events: list[dict[str, Any]] = []
        for location in args.feed:
            data, content_type = read_input(location, args.timeout)
            discovered_source, items = parse_feed(data, content_type)
            source = args.source or discovered_source or urlparse(location).hostname or Path(location).stem
            source_tier, tier_verified, tier_basis = resolve_source_tier(
                location, source, args.source_tier, registry
            )
            events.extend(
                normalize_items(
                    items,
                    source,
                    source_tier,
                    tier_verified,
                    tier_basis,
                    aliases,
                )
            )
            if len(events) >= args.max_items:
                break
        result = "\n".join(
            json.dumps(item, ensure_ascii=False) for item in events[: args.max_items]
        )
        if args.output:
            Path(args.output).write_text(result + ("\n" if result else ""), encoding="utf-8")
        else:
            sys.stdout.write(result + ("\n" if result else ""))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, ElementTree.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    configure_utf8_stdio()
    raise SystemExit(main())
