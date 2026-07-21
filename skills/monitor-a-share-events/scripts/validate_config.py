#!/usr/bin/env python3
"""Validate an evidence-radar config without reading remote feeds or sending data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse


SUPPORTED_CHANNELS = {"bark", "dingtalk", "feishu", "telegram", "webhook", "wecom"}
SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:api_?key|authorization|chat_?id|cookie|password|secret|signature|token|webhook_?url)(?:$|_)",
    re.IGNORECASE,
)
POSITIVE_INTEGERS = {
    "window_minutes",
    "cooldown_minutes",
    "max_age_minutes",
    "max_future_skew_minutes",
}


def result(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_local(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def find_sensitive_keys(value: Any, prefix: str = "config") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if SENSITIVE_KEY.search(str(key)) and child not in (None, "", [], {}):
                found.append(path)
            found.extend(find_sensitive_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_sensitive_keys(child, f"{prefix}[{index}]"))
    return found


def check_location(base: Path, value: str, name: str) -> dict[str, str]:
    path_value = Path(value)
    if path_value.is_absolute():
        if not path_value.is_file():
            return result(name, "fail", f"local file not found: {path_value}")
        return result(name, "pass", f"local file: {path_value.name}")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if parsed.username or parsed.password:
            return result(name, "fail", "remote URL must not contain embedded credentials")
        sensitive_query = [key for key, _ in parse_qsl(parsed.query) if SENSITIVE_KEY.search(key)]
        if sensitive_query:
            return result(
                name,
                "fail",
                "remote URL contains a credential-like query key: " + ", ".join(sensitive_query),
            )
        if parsed.scheme == "http":
            return result(name, "warn", "plain HTTP feed; prefer HTTPS when the source supports it")
        return result(name, "pass", f"remote HTTPS feed: {parsed.hostname or 'unknown host'}")
    if parsed.scheme:
        return result(name, "fail", f"unsupported location scheme: {parsed.scheme}")
    path = resolve_local(base, value)
    if not path.is_file():
        return result(name, "fail", f"local file not found: {path}")
    return result(name, "pass", f"local file: {path.name}")


def check_watchlist(base: Path, value: Any) -> dict[str, str]:
    if not value:
        return result("watchlist", "warn", "no watchlist configured; all relevant events may be considered")
    path = resolve_local(base, str(value))
    if not path.is_file():
        return result("watchlist", "fail", f"file not found: {path}")
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return result("watchlist", "fail", str(exc))
    if not isinstance(data, dict):
        return result("watchlist", "fail", "watchlist must be a JSON object")
    symbols = data.get("symbols", {})
    if not isinstance(symbols, (dict, list)):
        return result("watchlist", "fail", "watchlist.symbols must be an object or array")
    count = len(symbols)
    status = "pass" if count else "warn"
    detail = f"{count} symbol(s)" if count else "watchlist contains no symbols"
    return result("watchlist", status, detail)


def check_registry(base: Path, value: Any, name: str = "source_registry") -> dict[str, str]:
    if not value:
        return result(
            name,
            "warn",
            "no source registry configured; claimed Tier 1 observations will be downgraded",
        )
    path = resolve_local(base, str(value))
    if not path.is_file():
        return result(name, "fail", f"file not found: {path}")
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return result(name, "fail", str(exc))
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, dict):
        return result(name, "fail", "registry must contain a sources object")
    errors: list[str] = []
    for source, entry in sources.items():
        if not isinstance(entry, dict):
            errors.append(f"{source}: entry must be an object")
            continue
        try:
            tier = int(entry.get("tier"))
        except (TypeError, ValueError):
            tier = 0
        if tier not in {1, 2, 3, 4}:
            errors.append(f"{source}: tier must be 1-4")
        hosts = entry.get("hosts", [])
        if not isinstance(hosts, list) or any(not isinstance(host, str) for host in hosts):
            errors.append(f"{source}: hosts must be an array of strings")
    if errors:
        return result(name, "fail", "; ".join(errors[:5]))
    return result(name, "pass", f"{len(sources)} source(s)")


def check_output_path(base: Path, value: Any, name: str) -> dict[str, str] | None:
    if not value:
        return None
    text = str(value)
    path_value = Path(text)
    if path_value.is_absolute():
        path = path_value
        parent = path.parent
        if not parent.exists():
            return result(name, "warn", f"parent directory will need to be created: {parent}")
        return result(name, "pass", f"local path: {path.name}")
    parsed = urlparse(text)
    if parsed.scheme:
        return result(name, "fail", f"{name} must be a local path")
    path = resolve_local(base, text)
    parent = path.parent
    if not parent.exists():
        return result(name, "warn", f"parent directory will need to be created: {parent}")
    return result(name, "pass", f"local path: {path.name}")


def validate_config(path: Path) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if not path.is_file():
        return [result("config", "fail", f"file not found: {path}")]
    try:
        config = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [result("config", "fail", str(exc))]
    if not isinstance(config, dict):
        return [result("config", "fail", "config must be a JSON object")]
    checks.append(result("config", "pass", f"parsed {path.name}"))

    sensitive = find_sensitive_keys(config)
    checks.append(
        result(
            "inline_secrets",
            "fail" if sensitive else "pass",
            "move credentials to environment variables: " + ", ".join(sensitive)
            if sensitive
            else "no credential-like values found",
        )
    )

    feeds = config.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        checks.append(result("feeds", "fail", "config.feeds must be a non-empty array"))
    else:
        for index, raw in enumerate(feeds, start=1):
            feed = raw if isinstance(raw, dict) else {"location": raw}
            location = str(feed.get("location", "")).strip()
            if not location:
                checks.append(result(f"feed[{index}]", "fail", "location is required"))
                continue
            checks.append(check_location(path.parent, location, f"feed[{index}]"))
            if feed.get("source_registry"):
                checks.append(
                    check_registry(
                        path.parent,
                        feed["source_registry"],
                        f"feed[{index}].source_registry",
                    )
                )
            if "max_items" in feed:
                try:
                    max_items = int(feed["max_items"])
                except (TypeError, ValueError):
                    max_items = 0
                if max_items <= 0:
                    checks.append(result(f"feed[{index}].max_items", "fail", "must be positive"))

    checks.append(check_watchlist(path.parent, config.get("watchlist")))
    per_feed_registry = isinstance(feeds, list) and any(
        isinstance(feed, dict) and feed.get("source_registry") for feed in feeds
    )
    if config.get("source_registry"):
        checks.append(check_registry(path.parent, config["source_registry"]))
    elif per_feed_registry:
        checks.append(result("source_registry", "pass", "using per-feed source registries"))
    else:
        checks.append(check_registry(path.parent, None))

    output_format = str(config.get("format", "markdown"))
    checks.append(
        result(
            "format",
            "pass" if output_format in {"json", "jsonl", "markdown"} else "fail",
            output_format,
        )
    )
    try:
        min_score = int(config.get("min_score", 60))
        score_ok = 0 <= min_score <= 100
    except (TypeError, ValueError):
        min_score, score_ok = config.get("min_score"), False
    checks.append(result("min_score", "pass" if score_ok else "fail", str(min_score)))
    for name in POSITIVE_INTEGERS:
        if name not in config:
            continue
        try:
            numeric = int(config[name])
            valid = numeric >= 0 if name == "max_future_skew_minutes" else numeric > 0
        except (TypeError, ValueError):
            numeric, valid = config[name], False
        checks.append(result(name, "pass" if valid else "fail", str(numeric)))

    notification = config.get("notification")
    if notification is not None:
        if not isinstance(notification, dict):
            checks.append(result("notification", "fail", "must be an object"))
        else:
            channel = str(notification.get("channel", "")).strip()
            checks.append(
                result(
                    "notification.channel",
                    "pass" if channel in SUPPORTED_CHANNELS else "fail",
                    channel or "missing",
                )
            )

    for name in ("output", "state"):
        path_check = check_output_path(path.parent, config.get(name), name)
        if path_check:
            checks.append(path_check)
    return checks


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a radar config offline before collection or notification."
    )
    parser.add_argument("--config", required=True, help="UTF-8 JSON configuration file")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    checks = validate_config(Path(args.config).resolve())
    ready = all(item["status"] != "fail" for item in checks)
    if args.format == "json":
        print(json.dumps({"ready": ready, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        markers = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}
        for item in checks:
            print(f"{markers[item['status']]} {item['name']}: {item['detail']}")
        print("CONFIG READY" if ready else "CONFIG NOT READY")
    return 0 if ready else 1


if __name__ == "__main__":
    configure_utf8_stdio()
    raise SystemExit(main())
