#!/usr/bin/env python3
"""Run collection, fusion, state, and optional delivery from one JSON config."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    path = SKILL_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the evidence-radar pipeline from one config.")
    parser.add_argument("--config", required=True, help="UTF-8 JSON configuration file")
    parser.add_argument(
        "--commit-state",
        action="store_true",
        help="Persist eligible cluster IDs to the configured state file",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Perform configured notification network write; requires explicit authorization",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip even notification preview when a channel is configured",
    )
    return parser.parse_args()


def resolve_location(base: Path, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return value
    path = Path(value)
    return str(path if path.is_absolute() else (base / path).resolve())


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("config must be a JSON object")
    if not isinstance(value.get("feeds"), list) or not value["feeds"]:
        raise ValueError("config.feeds must be a non-empty array")
    return value


def collect_events(collect, config: dict[str, Any], base: Path) -> list[dict[str, Any]]:
    watchlist_path = config.get("watchlist")
    aliases = collect.load_symbol_aliases(
        resolve_location(base, str(watchlist_path)) if watchlist_path else None
    )
    default_registry = config.get("source_registry")
    events: list[dict[str, Any]] = []
    for index, raw_feed in enumerate(config["feeds"], start=1):
        feed = raw_feed if isinstance(raw_feed, dict) else {"location": raw_feed}
        location_value = str(feed.get("location", "")).strip()
        if not location_value:
            raise ValueError(f"config.feeds[{index}] requires location")
        location = resolve_location(base, location_value)
        registry_value = feed.get("source_registry", default_registry)
        registry = collect.load_source_registry(
            resolve_location(base, str(registry_value)) if registry_value else None
        )
        cache_value = feed.get("cache_dir", config.get("cache_dir"))
        data, content_type = collect.read_input(
            location,
            float(feed.get("timeout", 15.0)),
            retries=int(feed.get("retries", 2)),
            min_interval=float(feed.get("min_interval", 1.0)),
            max_bytes=int(feed.get("max_bytes", 5_000_000)),
            cache_dir=resolve_location(base, str(cache_value)) if cache_value else None,
        )
        discovered_source, items = collect.parse_feed(data, content_type)
        source = (
            str(feed.get("source", "")).strip()
            or discovered_source
            or urlparse(location).hostname
            or Path(location).stem
        )
        claimed_tier = int(feed.get("source_tier", 3))
        tier, verified, basis = collect.resolve_source_tier(
            location, source, claimed_tier, registry
        )
        normalized = collect.normalize_items(items, source, tier, verified, basis, aliases)
        max_items = int(feed.get("max_items", 100))
        events.extend(normalized[:max_items])
    return events


def load_fusion_registry(fuse, config: dict[str, Any], base: Path) -> dict[str, dict[str, Any]]:
    values: list[Any] = []
    if config.get("source_registry"):
        values.append(config["source_registry"])
    for raw_feed in config["feeds"]:
        if isinstance(raw_feed, dict) and raw_feed.get("source_registry"):
            values.append(raw_feed["source_registry"])
    merged: dict[str, dict[str, Any]] = {}
    for value in values:
        current = fuse.load_source_registry(resolve_location(base, str(value)))
        for source, entry in current.items():
            if source in merged and merged[source] != entry:
                raise ValueError(f"conflicting registry entries for source {source!r}")
            merged[source] = entry
    return merged


def run_fusion(fuse, config: dict[str, Any], base: Path, events: list[dict[str, Any]], commit: bool):
    watchlist_value = config.get("watchlist")
    watchlist = fuse.load_watchlist(
        resolve_location(base, str(watchlist_value)) if watchlist_value else None
    )
    registry = load_fusion_registry(fuse, config, base)
    normalized = [
        fuse.normalize_event(item, index, registry) for index, item in enumerate(events, 1)
    ]
    window = int(config.get("window_minutes", 180))
    clusters = fuse.cluster_events(normalized, timedelta(minutes=window))
    now = fuse.parse_time(config.get("now"), default_now=True)
    min_score = int(config.get("min_score", 60))
    max_age = int(config.get("max_age_minutes", 1440))
    future_skew = int(config.get("max_future_skew_minutes", 5))
    cards = [
        fuse.build_card(cluster, watchlist, now, min_score, max_age, future_skew)
        for cluster in clusters
    ]
    cards.sort(key=lambda item: (-item["score"], item["latest_at"]))
    state_value = config.get("state")
    state_path = resolve_location(base, str(state_value)) if state_value else None
    state = fuse.load_state(state_path)
    fuse.apply_cooldown(
        cards,
        state,
        now,
        timedelta(minutes=int(config.get("cooldown_minutes", 360))),
    )
    if commit:
        if not state_path:
            raise ValueError("--commit-state requires config.state")
        fuse.commit_state(state_path, cards, state, now)
    output_format = str(config.get("format", "markdown"))
    if output_format not in {"json", "jsonl", "markdown"}:
        raise ValueError("config.format must be json, jsonl, or markdown")
    report = fuse.render(cards, output_format, bool(config.get("include_held", False)))
    return report, cards


def handle_notification(push, config: dict[str, Any], report: str, send: bool) -> dict[str, Any] | None:
    notification = config.get("notification")
    if notification is None:
        return None
    if not isinstance(notification, dict):
        raise ValueError("config.notification must be an object")
    channel = str(notification.get("channel", "")).strip()
    title = str(notification.get("title", "A股证据链事件雷达"))
    text = push.truncate(report, int(notification.get("max_chars", 3500)))
    endpoint, payload = push.endpoint_and_payload(channel, title, text)
    if not send:
        return {
            "mode": "preview_only",
            "channel": channel,
            "endpoint": push.redacted_endpoint(channel, endpoint),
            "payload": push.redacted_payload(payload),
        }
    status = push.post_json(endpoint, payload)
    return {"mode": "sent", "channel": channel, "http_status": status}


def main() -> int:
    args = parse_args()
    try:
        config_path = Path(args.config).resolve()
        validator = load_module("evidence_radar_config_validator", "validate_config.py")
        validation = validator.validate_config(config_path)
        failures = [item for item in validation if item["status"] == "fail"]
        if failures:
            details = "; ".join(f"{item['name']}: {item['detail']}" for item in failures)
            raise ValueError(f"config validation failed: {details}")
        config = load_config(config_path)
        collect = load_module("evidence_radar_collect", "collect_feeds.py")
        fuse = load_module("evidence_radar_fuse", "fuse_events.py")
        push = load_module("evidence_radar_push", "push_alert.py")
        events = collect_events(collect, config, config_path.parent)
        report, cards = run_fusion(fuse, config, config_path.parent, events, args.commit_state)
        output_value = config.get("output")
        if output_value:
            output_path = Path(resolve_location(config_path.parent, str(output_value)))
            output_path.write_text(report + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "report": str(output_path),
                        "events": len(events),
                        "cards": len(cards),
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(report)
        if not args.no_notify:
            delivery = handle_notification(push, config, report, args.send)
            if delivery is not None:
                print(json.dumps(delivery, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
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
