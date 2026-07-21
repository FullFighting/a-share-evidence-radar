#!/usr/bin/env python3
"""Run an offline readiness check for the A-share evidence radar."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = SKILL_ROOT / "assets" / "examples"


def load_fuse_module():
    path = SKILL_ROOT / "scripts" / "fuse_events.py"
    spec = importlib.util.spec_from_file_location("evidence_radar_fuse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load fuse_events.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline configuration and smoke-test check.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    checks: list[dict[str, Any]] = []
    checks.append(
        check(
            "python",
            sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    required = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "agents" / "openai.yaml",
        SKILL_ROOT / "references" / "event-schema.md",
        SKILL_ROOT / "references" / "source-policy.md",
        EXAMPLES / "events.jsonl",
        EXAMPLES / "watchlist.json",
        EXAMPLES / "source-registry.json",
        EXAMPLES / "radar-config.json",
    ]
    missing = [str(path.relative_to(SKILL_ROOT)) for path in required if not path.exists()]
    checks.append(check("required_files", not missing, "ok" if not missing else ", ".join(missing)))
    try:
        fuse = load_fuse_module()
        raw_events = fuse.load_json_or_jsonl(EXAMPLES / "events.jsonl")
        registry = fuse.load_source_registry(str(EXAMPLES / "source-registry.json"))
        events = [
            fuse.normalize_event(item, index, registry)
            for index, item in enumerate(raw_events, 1)
        ]
        watchlist = fuse.load_watchlist(str(EXAMPLES / "watchlist.json"))
        clusters = fuse.cluster_events(events, timedelta(minutes=180))
        cards = [
            fuse.build_card(cluster, watchlist, fuse.parse_time("2026-07-21T10:00:00+08:00"), 60)
            for cluster in clusters
        ]
        eligible = sum(card["status"] == "eligible" for card in cards)
        checks.append(check("offline_smoke_test", eligible >= 1, f"{len(cards)} cards, {eligible} eligible"))
    except Exception as exc:  # Keep doctor useful even when an unexpected import error occurs.
        checks.append(check("offline_smoke_test", False, str(exc)))
    notification_env = {
        "feishu": "FEISHU_WEBHOOK_URL",
        "dingtalk": "DINGTALK_WEBHOOK_URL",
        "wecom": "WECOM_WEBHOOK_URL",
        "telegram": "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID",
        "bark": "BARK_URL",
        "webhook": "WEBHOOK_URL",
    }
    configured = []
    for channel, names in notification_env.items():
        if all(os.getenv(name.strip()) for name in names.split(" + ")):
            configured.append(channel)
    checks.append(
        {
            "name": "notification_channels",
            "status": "info",
            "detail": ", ".join(configured) if configured else "none (preview and local reports still work)",
        }
    )
    ok = all(item["status"] != "fail" for item in checks)
    if args.format == "json":
        print(json.dumps({"ready": ok, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            marker = {"pass": "[PASS]", "fail": "[FAIL]", "info": "[INFO]"}[item["status"]]
            print(f"{marker} {item['name']}: {item['detail']}")
        print("READY" if ok else "NOT READY")
    return 0 if ok else 1


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    configure_utf8_stdio()
    raise SystemExit(main())
