#!/usr/bin/env python3
"""Preview or send an evidence-radar alert without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


CHANNEL_ENV = {
    "feishu": "FEISHU_WEBHOOK_URL",
    "dingtalk": "DINGTALK_WEBHOOK_URL",
    "wecom": "WECOM_WEBHOOK_URL",
    "webhook": "WEBHOOK_URL",
    "bark": "BARK_URL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview an alert payload or send it after explicit approval."
    )
    parser.add_argument(
        "--channel",
        required=True,
        choices=("feishu", "dingtalk", "wecom", "telegram", "bark", "webhook"),
    )
    parser.add_argument("--input", required=True, help="UTF-8 text or Markdown file")
    parser.add_argument("--title", default="A股证据链事件雷达")
    parser.add_argument("--max-chars", type=int, default=3500)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Perform the network write; without this flag only a redacted preview is printed",
    )
    return parser.parse_args()


def truncate(text: str, limit: int) -> str:
    if limit < 100:
        raise ValueError("--max-chars must be at least 100")
    if len(text) <= limit:
        return text
    suffix = "\n\n[truncated; open the generated report for complete evidence]"
    return text[: max(0, limit - len(suffix))] + suffix


def endpoint_and_payload(channel: str, title: str, text: str) -> tuple[str, dict[str, Any]]:
    if channel == "telegram":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            raise ValueError("telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        if not re.fullmatch(r"[A-Za-z0-9:_-]+", token):
            raise ValueError("TELEGRAM_BOT_TOKEN contains unsupported characters")
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        return endpoint, {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}

    env_name = CHANNEL_ENV[channel]
    endpoint = os.getenv(env_name, "").strip()
    if not endpoint:
        raise ValueError(f"{channel} requires {env_name}")
    if not endpoint.lower().startswith("https://"):
        raise ValueError("notification endpoints must use https")

    if channel == "feishu":
        return endpoint, {"msg_type": "text", "content": {"text": text}}
    if channel == "dingtalk":
        return endpoint, {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
    if channel == "wecom":
        return endpoint, {"msgtype": "markdown", "markdown": {"content": text}}
    if channel == "bark":
        return endpoint, {"title": title, "body": text}
    return endpoint, {"title": title, "text": text}


def redacted_endpoint(channel: str, endpoint: str) -> str:
    if channel == "telegram":
        return "https://api.telegram.org/bot***REDACTED***/sendMessage"
    parsed = urlsplit(endpoint)
    host = parsed.hostname or "redacted.invalid"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}/***REDACTED***"


def redacted_payload(payload: Any) -> Any:
    sensitive_keys = {"chat_id", "token", "secret", "authorization", "webhook_url"}
    if isinstance(payload, dict):
        return {
            key: "***REDACTED***" if str(key).lower() in sensitive_keys else redacted_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redacted_payload(value) for value in payload]
    return payload


def post_json(endpoint: str, payload: dict[str, Any]) -> int:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "a-share-evidence-radar/1"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        response.read(4096)
        return response.status


def main() -> int:
    args = parse_args()
    try:
        text = truncate(Path(args.input).read_text(encoding="utf-8-sig").strip(), args.max_chars)
        if not text:
            raise ValueError("input alert is empty")
        endpoint, payload = endpoint_and_payload(args.channel, args.title, text)
        if not args.send:
            preview = {
                "mode": "preview_only",
                "channel": args.channel,
                "endpoint": redacted_endpoint(args.channel, endpoint),
                "payload": redacted_payload(payload),
            }
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 0
        status = post_json(endpoint, payload)
        print(
            json.dumps(
                {
                    "mode": "sent",
                    "channel": args.channel,
                    "http_status": status,
                },
                ensure_ascii=False,
            )
        )
        return 0 if 200 <= status < 300 else 1
    except (OSError, ValueError, HTTPError, URLError) as exc:
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
