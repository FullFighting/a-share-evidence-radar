#!/usr/bin/env python3
"""Fuse A-share event observations into evidence-gated alert cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SHANGHAI = timezone(timedelta(hours=8))
MATERIALITY = {
    "regulatory": 20,
    "merger": 20,
    "earnings": 16,
    "litigation": 15,
    "policy": 15,
    "insider_change": 14,
    "contract": 12,
    "buyback": 12,
    "operations": 10,
    "market_anomaly": 8,
    "rumor": 2,
    "other": 5,
}
EVENT_TERMS = {
    "regulatory": ("监管", "问询", "调查", "处罚", "警示"),
    "merger": ("并购", "重组", "收购", "控制权"),
    "earnings": ("业绩", "盈利", "亏损", "营收", "净利润"),
    "litigation": ("诉讼", "仲裁", "判决"),
    "policy": ("政策", "条例", "办法", "通知"),
    "insider_change": ("增持", "减持", "解禁", "质押"),
    "contract": ("合同", "订单", "中标"),
    "buyback": ("回购",),
    "operations": ("停产", "复产", "事故", "投产"),
}
AUTHORITY = {1: 35, 2: 24, 3: 12, 4: 3}
OFFICIAL_HINTS = (
    "上海证券交易所",
    "深圳证券交易所",
    "北京证券交易所",
    "中国证监会",
    "证监局",
    "人民法院",
    "人民政府",
    "国务院",
    "财政部",
    "国家发展改革委",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cluster, score, and evidence-gate A-share event observations."
    )
    parser.add_argument("--events", required=True, help="JSON array or JSONL event file")
    parser.add_argument("--watchlist", help="Optional watchlist JSON file")
    parser.add_argument(
        "--source-registry",
        help="JSON registry used to verify source tiers and canonical references",
    )
    parser.add_argument("--state", help="Optional deduplication state JSON file")
    parser.add_argument(
        "--commit-state",
        action="store_true",
        help="Persist newly eligible cluster IDs; off by default",
    )
    parser.add_argument("--window-minutes", type=int, default=180)
    parser.add_argument("--cooldown-minutes", type=int, default=360)
    parser.add_argument("--min-score", type=int, default=60)
    parser.add_argument("--max-age-minutes", type=int, default=1440)
    parser.add_argument("--max-future-skew-minutes", type=int, default=5)
    parser.add_argument("--now", help="ISO-8601 evaluation time; default is current time")
    parser.add_argument("--format", choices=("json", "jsonl", "markdown"), default="json")
    parser.add_argument("--output", help="Write output to a file instead of stdout")
    parser.add_argument(
        "--include-held",
        action="store_true",
        help="Include held cards in Markdown/JSONL output",
    )
    return parser.parse_args()


def parse_time(value: str | None, *, default_now: bool = False) -> datetime:
    if not value:
        if default_now:
            return datetime.now(timezone.utc)
        raise ValueError("published_at is required")
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(timezone.utc)


def load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if text.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("JSON input must be an array")
        return [item for item in value if isinstance(item, dict)]
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        records.append(value)
    return records


def load_watchlist(path: str | None) -> dict[str, Any]:
    if not path:
        return {"symbols": {}, "keywords": [], "sectors": []}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("watchlist must be a JSON object")
    symbols = value.get("symbols", {})
    if isinstance(symbols, list):
        symbols = {normalize_symbol(item): {} for item in symbols}
    if not isinstance(symbols, dict):
        raise ValueError("watchlist.symbols must be an object or array")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_symbol, metadata in symbols.items():
        symbol = normalize_symbol(raw_symbol)
        if symbol:
            normalized[symbol] = metadata if isinstance(metadata, dict) else {}
    return {
        "symbols": normalized,
        "keywords": [str(x) for x in value.get("keywords", [])],
        "sectors": [str(x) for x in value.get("sectors", [])],
    }


def load_source_registry(path: str | None) -> dict[str, dict[str, Any]]:
    """Load the trust root used by fusion; event-file booleans are never trusted."""
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    sources = value.get("sources", {}) if isinstance(value, dict) else {}
    if not isinstance(sources, dict):
        raise ValueError("source registry must contain a sources object")
    return {str(name): entry for name, entry in sources.items() if isinstance(entry, dict)}


def registry_tier_and_reference(
    event: dict[str, Any], registry: dict[str, dict[str, Any]]
) -> tuple[int | None, bool]:
    """Return a registry tier and whether the event has an allowed canonical reference."""
    entry = registry.get(str(event.get("source", "")).strip())
    if entry is None:
        return None, False
    try:
        tier = int(entry["tier"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("registry source tier must be an integer from 1 to 4") from exc
    if tier not in AUTHORITY:
        raise ValueError("registry source tier must be an integer from 1 to 4")

    parsed = urlparse(str(event.get("url", "")).strip())
    allowed_hosts = {
        str(host).strip().lower()
        for host in entry.get("hosts", [])
        if str(host).strip()
    }
    host = str(parsed.hostname or "").lower()
    canonical_url = bool(
        parsed.scheme == "https"
        and host
        and not parsed.username
        and not parsed.password
        and host in allowed_hosts
    )
    origin = str(event.get("evidence_origin", "")).strip()
    prefixes = [
        str(prefix).strip()
        for prefix in entry.get("evidence_origin_prefixes", [])
        if str(prefix).strip()
    ]
    canonical_origin = bool(origin and any(origin.startswith(prefix) for prefix in prefixes))
    return tier, canonical_url or canonical_origin


def normalize_symbol(value: Any) -> str:
    text = str(value or "").upper().strip()
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    return match.group(1) if match else ""


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"(?:公告|快讯|最新|突发)[:：\s-]*", "", text)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def ngrams(text: str, size: int = 2) -> set[str]:
    if len(text) <= size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def title_similarity(left: str, right: str) -> float:
    left_n = normalize_text(left)
    right_n = normalize_text(right)
    if not left_n or not right_n:
        return 0.0
    sequence = SequenceMatcher(None, left_n, right_n).ratio()
    a, b = ngrams(left_n), ngrams(right_n)
    jaccard = len(a & b) / len(a | b) if a | b else 0.0
    return max(sequence, jaccard)


def infer_tier(event: dict[str, Any]) -> int:
    try:
        tier = int(event.get("source_tier", 0))
        if tier in AUTHORITY:
            return tier
    except (TypeError, ValueError):
        pass
    source = str(event.get("source", ""))
    return 1 if any(hint in source for hint in OFFICIAL_HINTS) else 3


def source_key(event: dict[str, Any]) -> str:
    evidence_origin = str(event.get("evidence_origin", "")).strip()
    normalized_origin = normalize_text(evidence_origin)
    if normalized_origin:
        return "origin:" + normalized_origin
    content_fingerprint = str(event.get("content_fingerprint", "")).strip().lower()
    if re.fullmatch(r"[0-9a-f]{12,64}", content_fingerprint):
        return "content:" + content_fingerprint
    url = str(event.get("url", "")).strip()
    host = urlparse(url).hostname or ""
    host = re.sub(r"^www\.", "", host.lower())
    if host:
        return host
    return normalize_text(event.get("source")) or "unknown"


def normalize_event(
    event: dict[str, Any],
    index: int,
    registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    title = str(event.get("title", "")).strip()
    source = str(event.get("source", "")).strip()
    if not title or not source:
        raise ValueError(f"event {index} requires title and source")
    published = parse_time(event.get("published_at"))
    event_time_value = event.get("event_at") or event.get("first_published_at")
    event_time = parse_time(event_time_value) if event_time_value else published
    symbols = sorted(
        {symbol for raw in event.get("symbols", []) if (symbol := normalize_symbol(raw))}
    )
    sectors = sorted({str(x).strip() for x in event.get("sectors", []) if str(x).strip()})
    claimed_tier = infer_tier(event)
    registry_tier, canonical_reference = registry_tier_and_reference(event, registry or {})
    tier_verified = registry_tier is not None and canonical_reference
    effective_tier = registry_tier if tier_verified else claimed_tier
    tier_downgraded = False
    if effective_tier == 1 and not tier_verified:
        effective_tier = 3
        tier_downgraded = True
    normalized = dict(event)
    normalized.update(
        {
            "title": title,
            "summary": str(event.get("summary", "")).strip(),
            "source": source,
            "source_tier": effective_tier,
            "source_tier_claimed": claimed_tier,
            "source_tier_verified": tier_verified,
            "source_tier_downgraded": tier_downgraded,
            "published_dt": published,
            "published_at": published.isoformat().replace("+00:00", "Z"),
            "event_dt": event_time,
            "event_at": event_time.isoformat().replace("+00:00", "Z"),
            "symbols": symbols,
            "sectors": sectors,
            "event_type": str(event.get("event_type", "other")).lower(),
            "stance": str(event.get("stance", "uncertain")).lower(),
            "source_key": source_key(event),
            "input_index": index,
        }
    )
    return normalized


def same_cluster(event: dict[str, Any], cluster: list[dict[str, Any]], window: timedelta) -> bool:
    anchor = cluster[0]
    if abs(event["published_dt"] - anchor["published_dt"]) > window:
        return False
    same_url = bool(event.get("url") and event.get("url") == anchor.get("url"))
    symbol_overlap = bool(set(event["symbols"]) & set(anchor["symbols"]))
    sector_overlap = bool(set(event["sectors"]) & set(anchor["sectors"]))
    similarity = title_similarity(event["title"], anchor["title"])
    event_type = event["event_type"]
    same_typed_event = event_type == anchor["event_type"] and event_type in EVENT_TERMS
    shared_event_term = any(
        event_term in event["title"] and event_term in anchor["title"]
        for event_term in EVENT_TERMS.get(event_type, ())
    )
    typed_match = same_typed_event and symbol_overlap and shared_event_term and similarity >= 0.45
    return same_url or typed_match or (similarity >= 0.72 and (symbol_overlap or sector_overlap))


def cluster_events(events: list[dict[str, Any]], window: timedelta) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda item: item["published_dt"]):
        target = next((cluster for cluster in clusters if same_cluster(event, cluster, window)), None)
        if target is None:
            clusters.append([event])
        else:
            target.append(event)
    return clusters


def freshness_points(age_minutes: float) -> int:
    if age_minutes < 0:
        return 0
    if age_minutes <= 15:
        return 15
    if age_minutes <= 60:
        return 12
    if age_minutes <= 180:
        return 8
    if age_minutes <= 1440:
        return 3
    return 0


def reaction_points(cluster: list[dict[str, Any]]) -> tuple[int, list[str]]:
    best_price = 0.0
    best_volume = 0.0
    for event in cluster:
        metrics = event.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        try:
            best_price = max(best_price, abs(float(metrics.get("price_change_pct", 0))))
        except (TypeError, ValueError):
            pass
        try:
            best_volume = max(best_volume, float(metrics.get("volume_ratio", 0)))
        except (TypeError, ValueError):
            pass
    points = 0
    notes: list[str] = []
    if best_price >= 5:
        points += 10
    elif best_price >= 2:
        points += 6
    if best_volume >= 2:
        points += 5
    if best_price:
        notes.append(f"observed price move {best_price:.2f}%")
    if best_volume:
        notes.append(f"observed volume ratio {best_volume:.2f}")
    return points, notes


def relevance_points(
    symbols: set[str], sectors: set[str], text: str, watchlist: dict[str, Any]
) -> tuple[int, list[str]]:
    points = 0
    reasons: list[str] = []
    watched = set(watchlist["symbols"])
    direct = sorted(symbols & watched)
    if direct:
        points += 20
        reasons.append("direct watchlist match: " + ", ".join(direct))
    watched_sectors = set(watchlist["sectors"])
    for metadata in watchlist["symbols"].values():
        watched_sectors.update(str(x) for x in metadata.get("sectors", []))
    sector_hits = sorted(sectors & watched_sectors)
    if sector_hits:
        points += 10
        reasons.append("watched sector match: " + ", ".join(sector_hits))
    keyword_hits = sorted({word for word in watchlist["keywords"] if word and word in text})
    if keyword_hits:
        points += min(10, 4 + 2 * len(keyword_hits))
        reasons.append("keyword match: " + ", ".join(keyword_hits))
    if not watchlist["symbols"] and not watchlist["keywords"] and not watchlist["sectors"]:
        reasons.append("no watchlist filter supplied")
    return points, reasons


def make_cluster_id(primary: dict[str, Any], symbols: set[str]) -> str:
    payload = "|".join(
        [",".join(sorted(symbols)), primary["event_type"], normalize_text(primary["title"])]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_card(
    cluster: list[dict[str, Any]],
    watchlist: dict[str, Any],
    now: datetime,
    min_score: int,
    max_age_minutes: int = 1440,
    max_future_skew_minutes: int = 5,
) -> dict[str, Any]:
    primary = min(cluster, key=lambda item: (item["source_tier"], -item["published_dt"].timestamp()))
    symbols = {symbol for item in cluster for symbol in item["symbols"]}
    sectors = {sector for item in cluster for sector in item["sectors"]}
    independent_sources = sorted({item["source_key"] for item in cluster})
    best_tier = min(item["source_tier"] for item in cluster)
    latest = max(item["published_dt"] for item in cluster)
    underlying_event_time = min(item["event_dt"] for item in cluster)
    raw_age_minutes = (now - underlying_event_time).total_seconds() / 60
    age_minutes = max(0.0, raw_age_minutes)
    freshness_gate = (
        raw_age_minutes >= -max_future_skew_minutes and raw_age_minutes <= max_age_minutes
    )
    materiality = max(MATERIALITY.get(item["event_type"], 5) for item in cluster)
    text = " ".join(str(item.get(key, "")) for item in cluster for key in ("title", "summary"))
    relevance, relevance_reasons = relevance_points(symbols, sectors, text, watchlist)
    corroboration = min(20, max(0, len(independent_sources) - 1) * 10)
    reaction, reaction_notes = reaction_points(cluster)
    freshness = freshness_points(age_minutes)
    score = AUTHORITY[best_tier] + materiality + freshness
    score += relevance + corroboration + reaction
    stances = {item["stance"] for item in cluster}
    uncertainty: list[str] = []
    denial_sources = {
        item["source_key"] for item in cluster if item["stance"] == "deny"
    }
    credible_denial = any(
        item["stance"] == "deny" and item["source_tier"] == 1 for item in cluster
    ) or len(denial_sources) >= 2
    has_conflict = "confirm" in stances and credible_denial
    conflict_penalty = 0
    rumor_penalty = 0
    if has_conflict:
        score -= 12
        conflict_penalty = -12
        uncertainty.append("conflicting confirm and deny observations")
    if primary["event_type"] == "rumor" and best_tier > 1:
        score -= 15
        rumor_penalty = -15
        uncertainty.append("unverified rumor")
    score = max(0, min(100, score))
    evidence_gate = best_tier == 1 or len(independent_sources) >= 2
    watchlist_active = bool(
        watchlist["symbols"] or watchlist["keywords"] or watchlist["sectors"]
    )
    relevance_gate = not watchlist_active or relevance > 0
    eligible = (
        evidence_gate
        and relevance_gate
        and not has_conflict
        and freshness_gate
        and score >= min_score
    )
    reasons = [
        f"best source tier {best_tier}",
        f"{len(independent_sources)} independent source(s)",
        *relevance_reasons,
        *reaction_notes,
    ]
    invalidations = sorted(
        {str(item.get("invalidation", "")).strip() for item in cluster if item.get("invalidation")}
    )
    evidence = [
        {
            "source": item["source"],
            "tier": item["source_tier"],
            "claimed_tier": item["source_tier_claimed"],
            "tier_verified": item["source_tier_verified"],
            "published_at": item["published_at"],
            "event_at": item["event_at"],
            "url": str(item.get("url", "")),
            "stance": item["stance"],
        }
        for item in sorted(cluster, key=lambda item: (item["source_tier"], item["published_dt"]))
    ]
    if not evidence_gate:
        uncertainty.append("evidence gate not met")
    if not relevance_gate:
        uncertainty.append("no configured watchlist, sector, or keyword match")
    if score < min_score:
        uncertainty.append(f"score below configured threshold {min_score}")
    if raw_age_minutes < -max_future_skew_minutes:
        uncertainty.append(
            f"event time exceeds allowed future skew of {max_future_skew_minutes} minutes"
        )
    elif raw_age_minutes > max_age_minutes:
        uncertainty.append(f"event is older than {max_age_minutes} minutes")
    if any(item["source_tier_downgraded"] for item in cluster):
        uncertainty.append(
            "unverified Tier 1 claim downgraded; require a verified source registry and canonical reference"
        )
    return {
        "cluster_id": make_cluster_id(primary, symbols),
        "status": "eligible" if eligible else "held",
        "score": score,
        "score_breakdown": {
            "authority": AUTHORITY[best_tier],
            "materiality": materiality,
            "freshness": freshness,
            "relevance": relevance,
            "corroboration": corroboration,
            "market_reaction": reaction,
            "conflict_penalty": conflict_penalty,
            "rumor_penalty": rumor_penalty,
        },
        "evidence_gate": evidence_gate,
        "relevance_gate": relevance_gate,
        "conflict_gate": not has_conflict,
        "freshness_gate": freshness_gate,
        "title": primary["title"],
        "summary": primary["summary"],
        "event_type": primary["event_type"],
        "symbols": sorted(symbols),
        "sectors": sorted(sectors),
        "latest_at": latest.isoformat().replace("+00:00", "Z"),
        "event_at": underlying_event_time.isoformat().replace("+00:00", "Z"),
        "age_minutes": round(age_minutes, 1),
        "best_source_tier": best_tier,
        "independent_source_count": len(independent_sources),
        "why_relevant": reasons,
        "uncertainty": uncertainty,
        "invalidation": invalidations,
        "evidence": evidence,
        "research_label": "information triage only; not investment advice",
    }


def load_state(path: str | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {"emitted": {}}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("emitted", {}), dict):
        raise ValueError("state must contain an emitted object")
    value.setdefault("emitted", {})
    return value


def apply_cooldown(
    cards: list[dict[str, Any]], state: dict[str, Any], now: datetime, cooldown: timedelta
) -> None:
    for card in cards:
        if card["status"] != "eligible":
            continue
        previous = state["emitted"].get(card["cluster_id"])
        if previous and now - parse_time(previous) < cooldown:
            card["status"] = "suppressed"
            card["why_relevant"].append("inside notification cooldown")


def commit_state(path: str, cards: list[dict[str, Any]], state: dict[str, Any], now: datetime) -> None:
    cutoff = now - timedelta(days=30)
    retained = {
        key: value
        for key, value in state["emitted"].items()
        if parse_time(value) >= cutoff
    }
    for card in cards:
        if card["status"] == "eligible":
            retained[card["cluster_id"]] = now.isoformat().replace("+00:00", "Z")
    payload = {"emitted": retained}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def card_markdown(card: dict[str, Any]) -> str:
    symbols = ", ".join(card["symbols"]) or "market/sector"
    lines = [
        f"### [{card['score']}/100] {card['title']}",
        "",
        f"- Status: `{card['status']}`; type: `{card['event_type']}`; target: {symbols}",
        f"- Freshness: {card['age_minutes']} minutes; evidence: Tier {card['best_source_tier']} / {card['independent_source_count']} independent source(s)",
        f"- Gates: evidence={card['evidence_gate']}; relevance={card['relevance_gate']}; conflict-clear={card['conflict_gate']}; fresh={card['freshness_gate']}",
        "- Score: " + "; ".join(f"{key}={value}" for key, value in card["score_breakdown"].items()),
        f"- Why: {'; '.join(card['why_relevant'])}",
    ]
    if card["summary"]:
        lines.append(f"- Fact summary: {card['summary']}")
    if card["uncertainty"]:
        lines.append(f"- Uncertainty: {'; '.join(card['uncertainty'])}")
    if card["invalidation"]:
        lines.append(f"- Invalidation: {'; '.join(card['invalidation'])}")
    lines.append("- Evidence:")
    for item in card["evidence"]:
        link = f" [{item['url']}]({item['url']})" if item["url"] else ""
        lines.append(
            f"  - Tier {item['tier']} · {item['source']} · {item['stance']} · {item['published_at']}{link}"
        )
    lines.extend(["", "> Information triage only; verify primary sources. Not investment advice."])
    return "\n".join(lines)


def render(cards: list[dict[str, Any]], output_format: str, include_held: bool) -> str:
    summary = {
        status: sum(1 for card in cards if card["status"] == status)
        for status in ("eligible", "held", "suppressed")
    }
    if output_format == "json":
        return json.dumps({"summary": summary, "cards": cards}, ensure_ascii=False, indent=2)
    selected = [card for card in cards if card["status"] == "eligible" or include_held]
    if output_format == "jsonl":
        return "\n".join(json.dumps(card, ensure_ascii=False) for card in selected)
    header = (
        f"# A-share evidence radar\n\n"
        f"Eligible: {summary['eligible']} · Held: {summary['held']} · Suppressed: {summary['suppressed']}"
    )
    if not selected:
        return header + "\n\nNo push-worthy event found."
    return header + "\n\n" + "\n\n---\n\n".join(card_markdown(card) for card in selected)


def main() -> int:
    args = parse_args()
    try:
        if args.max_age_minutes < 0 or args.max_future_skew_minutes < 0:
            raise ValueError("freshness limits must be non-negative")
        now = parse_time(args.now, default_now=True)
        raw_events = load_json_or_jsonl(Path(args.events))
        registry = load_source_registry(args.source_registry)
        events = [
            normalize_event(item, index, registry)
            for index, item in enumerate(raw_events, start=1)
        ]
        watchlist = load_watchlist(args.watchlist)
        clusters = cluster_events(events, timedelta(minutes=args.window_minutes))
        cards = [
            build_card(
                cluster,
                watchlist,
                now,
                args.min_score,
                args.max_age_minutes,
                args.max_future_skew_minutes,
            )
            for cluster in clusters
        ]
        cards.sort(key=lambda item: (-item["score"], item["latest_at"]))
        state = load_state(args.state)
        apply_cooldown(cards, state, now, timedelta(minutes=args.cooldown_minutes))
        if args.commit_state:
            if not args.state:
                raise ValueError("--commit-state requires --state")
            commit_state(args.state, cards, state, now)
        result = render(cards, args.format, args.include_held)
        if args.output:
            Path(args.output).write_text(result + "\n", encoding="utf-8")
        else:
            sys.stdout.write(result + "\n")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
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
