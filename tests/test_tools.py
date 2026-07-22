import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "monitor-a-share-events"
FUSE = SKILL / "scripts" / "fuse_events.py"
PUSH = SKILL / "scripts" / "push_alert.py"
COLLECT = SKILL / "scripts" / "collect_feeds.py"
COLLECT_SSE = SKILL / "scripts" / "collect_sse_disclosures.py"
COLLECT_SZSE = SKILL / "scripts" / "collect_szse_disclosures.py"
EVALUATE = SKILL / "scripts" / "evaluate_radar.py"
DOCTOR = SKILL / "scripts" / "doctor.py"
RUN = SKILL / "scripts" / "run_radar.py"
VALIDATE = SKILL / "scripts" / "validate_config.py"
PROPOSE = SKILL / "scripts" / "propose_regression.py"
RUNTIME = ROOT / "tests" / ".runtime"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))
import http_client  # noqa: E402


class FakeResponse:
    def __init__(self, body=b"{}", headers=None, url="https://example.com/feed"):
        self.body = body
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ToolTests(unittest.TestCase):
    def runtime_path(self, suffix: str) -> Path:
        path = RUNTIME / f"{uuid.uuid4().hex}-{suffix}"
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def write_json(self, directory: Path, name: str, value) -> Path:
        path = directory / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def run_fuse(self, events, watchlist=None, extra=None):
        events_path = self.runtime_path("events.json")
        events_path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            "-X",
            "utf8",
            str(FUSE),
            "--events",
            str(events_path),
            "--now",
            "2026-07-21T10:00:00+08:00",
            "--format",
            "json",
            "--source-registry",
            str(SKILL / "assets" / "examples" / "source-registry.json"),
        ]
        if watchlist is not None:
            watchlist_path = self.runtime_path("watchlist.json")
            watchlist_path.write_text(json.dumps(watchlist, ensure_ascii=False), encoding="utf-8")
            command.extend(["--watchlist", str(watchlist_path)])
        if extra:
            command.extend(extra)
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_official_watchlist_event_is_eligible(self):
        events = [
            {
                "title": "示例公司披露回购方案",
                "summary": "董事会审议通过回购方案",
                "source": "上海证券交易所",
                "source_tier": 1,
                "source_tier_verified": True,
                "url": "https://example.invalid/sse/official-1",
                "published_at": "2026-07-21T09:42:00+08:00",
                "symbols": ["600000.SH"],
                "event_type": "buyback",
                "stance": "confirm",
            }
        ]
        watchlist = {"symbols": {"600000": {"sectors": ["银行"]}}, "keywords": ["回购"]}
        output = self.run_fuse(events, watchlist)
        self.assertEqual(output["summary"]["eligible"], 1)
        self.assertEqual(output["cards"][0]["symbols"], ["600000"])
        self.assertTrue(output["cards"][0]["evidence_gate"])
        self.assertTrue(output["cards"][0]["relevance_gate"])
        self.assertTrue(output["cards"][0]["conflict_gate"])
        self.assertIn("authority", output["cards"][0]["score_breakdown"])

    def test_independent_reports_cluster(self):
        events = [
            {
                "title": "示例公司发布股份回购计划",
                "source": "财经通讯社A",
                "source_tier": 2,
                "url": "https://a.example/story/1",
                "published_at": "2026-07-21T09:40:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
            },
            {
                "title": "示例公司披露股份回购计划",
                "source": "财经媒体B",
                "source_tier": 2,
                "url": "https://b.example/story/2",
                "published_at": "2026-07-21T09:45:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
            },
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(len(output["cards"]), 1)
        self.assertEqual(output["cards"][0]["independent_source_count"], 2)
        self.assertEqual(output["summary"]["eligible"], 1)

    def test_single_social_rumor_is_held(self):
        events = [
            {
                "title": "网传示例公司获得重大订单",
                "source": "社交平台",
                "source_tier": 4,
                "published_at": "2026-07-21T09:50:00+08:00",
                "symbols": ["600000"],
                "event_type": "rumor",
                "stance": "uncertain",
            }
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(output["summary"]["held"], 1)
        self.assertFalse(output["cards"][0]["evidence_gate"])

    def test_syndicated_copies_share_one_evidence_origin(self):
        events = [
            {
                "title": "示例公司发布股份回购计划",
                "source": source,
                "source_tier": 3,
                "evidence_origin": "wire-story-001",
                "published_at": published_at,
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "confirm",
            }
            for source, published_at in (
                ("转载站A", "2026-07-21T09:40:00+08:00"),
                ("转载站B", "2026-07-21T09:45:00+08:00"),
            )
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(output["cards"][0]["independent_source_count"], 1)
        self.assertEqual(output["summary"]["held"], 1)

    def test_confirmation_denial_conflict_is_held(self):
        events = [
            {
                "title": "示例公司公告拟实施股份回购",
                "source": "上海证券交易所",
                "source_tier": 1,
                "source_tier_verified": True,
                "url": "https://example.invalid/sse/official-2",
                "published_at": "2026-07-21T09:35:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "confirm",
            },
            {
                "title": "示例公司否认拟实施股份回购",
                "source": "示例公司公告",
                "source_tier": 1,
                "source_tier_verified": True,
                "url": "https://example.invalid/issuer/official-3",
                "published_at": "2026-07-21T09:48:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "deny",
            },
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(output["summary"]["held"], 1)
        self.assertFalse(output["cards"][0]["conflict_gate"])

    def test_single_weak_denial_does_not_override_official_confirmation(self):
        events = [
            {
                "title": "示例公司公告拟实施股份回购",
                "source": "上海证券交易所",
                "source_tier": 1,
                "source_tier_verified": True,
                "url": "https://example.invalid/sse/official-4",
                "published_at": "2026-07-21T09:35:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "confirm",
            },
            {
                "title": "网传示例公司否认拟实施股份回购",
                "source": "社交平台",
                "source_tier": 4,
                "published_at": "2026-07-21T09:48:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "deny",
            },
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(output["summary"]["eligible"], 1)
        self.assertTrue(output["cards"][0]["conflict_gate"])

    def test_active_watchlist_holds_unrelated_event(self):
        events = [
            {
                "title": "另一家公司披露重大合同",
                "source": "深圳证券交易所",
                "source_tier": 1,
                "source_tier_verified": True,
                "url": "https://example.invalid/szse/official-5",
                "published_at": "2026-07-21T09:42:00+08:00",
                "symbols": ["000001"],
                "event_type": "contract",
                "stance": "confirm",
            }
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}, "keywords": ["回购"]})
        self.assertEqual(output["summary"]["held"], 1)
        self.assertFalse(output["cards"][0]["relevance_gate"])

    def test_stale_and_future_events_fail_freshness_gate(self):
        for label, published_at in (
            ("stale", "2026-07-19T09:42:00+08:00"),
            ("future", "2026-07-21T10:30:00+08:00"),
        ):
            with self.subTest(label=label):
                event = {
                    "title": "示例公司披露股份回购方案",
                    "source": "上海证券交易所",
                    "source_tier": 1,
                    "source_tier_verified": True,
                    "url": f"https://example.invalid/sse/{label}",
                    "published_at": published_at,
                    "symbols": ["600000"],
                    "event_type": "buyback",
                    "stance": "confirm",
                }
                output = self.run_fuse([event], {"symbols": {"600000": {}}})
                self.assertEqual(output["summary"]["held"], 1)
                self.assertFalse(output["cards"][0]["freshness_gate"])

    def test_unverified_tier_one_claim_is_downgraded(self):
        event = {
            "title": "自称官方来源发布回购消息",
            "source": "上海证券交易所镜像",
            "source_tier": 1,
            "url": "https://mirror.example/story",
            "published_at": "2026-07-21T09:42:00+08:00",
            "symbols": ["600000"],
            "event_type": "buyback",
            "stance": "confirm",
        }
        output = self.run_fuse([event], {"symbols": {"600000": {}}})
        card = output["cards"][0]
        self.assertEqual(card["best_source_tier"], 3)
        self.assertFalse(card["evidence_gate"])
        self.assertEqual(card["status"], "held")

    def test_forged_verified_tier_one_with_noncanonical_url_is_downgraded(self):
        event = {
            "title": "伪造的一手来源回购消息",
            "source": "上海证券交易所",
            "source_tier": 1,
            "source_tier_verified": True,
            "url": "javascript:not-canonical",
            "published_at": "2026-07-21T09:42:00+08:00",
            "symbols": ["600000"],
            "event_type": "buyback",
            "stance": "confirm",
        }
        output = self.run_fuse([event], {"symbols": {"600000": {}}})
        card = output["cards"][0]
        self.assertEqual(card["best_source_tier"], 3)
        self.assertFalse(card["evidence"][0]["tier_verified"])
        self.assertEqual(card["status"], "held")

    def test_republication_does_not_refresh_old_event_time(self):
        events = [
            {
                "title": "示例公司重新报道股份回购计划",
                "source": source,
                "source_tier": 2,
                "url": url,
                "published_at": published_at,
                "event_at": "2026-07-18T09:40:00+08:00",
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "confirm",
            }
            for source, url, published_at in (
                ("财经通讯社A", "https://a.example/repost/1", "2026-07-21T09:40:00+08:00"),
                ("财经媒体B", "https://b.example/repost/2", "2026-07-21T09:45:00+08:00"),
            )
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        card = output["cards"][0]
        self.assertEqual(card["independent_source_count"], 2)
        self.assertFalse(card["freshness_gate"])
        self.assertEqual(card["status"], "held")

    def test_committed_event_is_suppressed_during_cooldown(self):
        event = {
            "title": "示例公司披露监管问询回复",
            "source": "深圳证券交易所",
            "source_tier": 1,
            "source_tier_verified": True,
            "url": "https://example.invalid/szse/official-6",
            "published_at": "2026-07-21T09:45:00+08:00",
            "symbols": ["000001"],
            "event_type": "regulatory",
            "stance": "confirm",
        }
        events_path = self.runtime_path("events.json")
        events_path.write_text(json.dumps([event], ensure_ascii=False), encoding="utf-8")
        watchlist_path = self.runtime_path("watchlist.json")
        watchlist_path.write_text(
            json.dumps({"symbols": {"000001": {}}}, ensure_ascii=False), encoding="utf-8"
        )
        state_path = self.runtime_path("state.json")
        base = [
            sys.executable,
            "-X",
            "utf8",
            str(FUSE),
            "--events",
            str(events_path),
            "--watchlist",
            str(watchlist_path),
            "--source-registry",
            str(SKILL / "assets" / "examples" / "source-registry.json"),
            "--state",
            str(state_path),
            "--now",
            "2026-07-21T10:00:00+08:00",
            "--format",
            "json",
        ]
        first = subprocess.run(
            base + ["--commit-state"], capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads(second.stdout)
        self.assertEqual(output["summary"]["suppressed"], 1)

    def test_push_defaults_to_redacted_preview(self):
        alert = self.runtime_path("alert.md")
        alert.write_text("test alert", encoding="utf-8")
        environment = os.environ.copy()
        environment["FEISHU_WEBHOOK_URL"] = (
            "https://user-secret:password@example.invalid/tenant-secret/hook-id?token=query-secret"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(PUSH),
                "--channel",
                "feishu",
                "--input",
                str(alert),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preview_only", result.stdout)
        self.assertIn("***REDACTED***", result.stdout)
        for secret in ("user-secret", "password", "tenant-secret", "hook-id", "query-secret"):
            self.assertNotIn(secret, result.stdout)

    def test_telegram_preview_redacts_chat_id_and_token(self):
        alert = self.runtime_path("telegram-alert.md")
        alert.write_text("中文测试提醒", encoding="utf-8")
        environment = os.environ.copy()
        environment["TELEGRAM_BOT_TOKEN"] = "123456:token-secret"
        environment["TELEGRAM_CHAT_ID"] = "-100987654321"
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(PUSH),
                "--channel",
                "telegram",
                "--input",
                str(alert),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("***REDACTED***", result.stdout)
        self.assertNotIn("token-secret", result.stdout)
        self.assertNotIn("-100987654321", result.stdout)

    def test_local_feed_collector_maps_watchlist_symbol(self):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(COLLECT),
                "--feed",
                str(SKILL / "assets" / "examples" / "feed.xml"),
                "--watchlist",
                str(SKILL / "assets" / "examples" / "watchlist.json"),
                "--source-registry",
                str(SKILL / "assets" / "examples" / "source-registry.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["symbols"], ["600000"])
        self.assertEqual(event["event_type"], "buyback")
        self.assertTrue(event["source_tier_verified"])

    def test_atom_collector_parses_entry(self):
        feed = self.runtime_path("feed.atom")
        feed.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>示例 Atom</title>
  <entry>
    <id>atom-1</id><title>600000 发布业绩预告</title>
    <link href="https://example.invalid/atom/1"/>
    <updated>2026-07-21T01:45:00Z</updated><summary>净利润数据以公告为准，本测试文本足够长用于生成稳定内容指纹</summary>
  </entry>
</feed>""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(COLLECT), "--feed", str(feed)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["symbols"], ["600000"])
        self.assertEqual(event["event_type"], "earnings")
        self.assertRegex(event["content_fingerprint"], r"^[0-9a-f]{20}$")

    def test_content_fingerprint_collapses_exact_cross_site_copies(self):
        events = [
            {
                "title": "示例公司披露股份回购方案",
                "summary": "完全相同的长篇上游稿件内容用于识别跨站原样转载",
                "source": source,
                "source_tier": 3,
                "url": url,
                "content_fingerprint": "a" * 20,
                "published_at": published_at,
                "symbols": ["600000"],
                "event_type": "buyback",
                "stance": "confirm",
            }
            for source, url, published_at in (
                ("转载站A", "https://a.example/copy", "2026-07-21T09:40:00+08:00"),
                ("转载站B", "https://b.example/copy", "2026-07-21T09:45:00+08:00"),
            )
        ]
        output = self.run_fuse(events, {"symbols": {"600000": {}}})
        self.assertEqual(len(output["cards"]), 1)
        self.assertEqual(output["cards"][0]["independent_source_count"], 1)
        self.assertEqual(output["cards"][0]["status"], "held")

    def test_json_feed_collector_parses_item(self):
        feed = self.runtime_path("feed.json")
        feed.write_text(
            json.dumps(
                {
                    "version": "https://jsonfeed.org/version/1.1",
                    "title": "示例 JSON Feed",
                    "items": [
                        {
                            "id": "json-1",
                            "title": "000001 披露重大合同",
                            "url": "https://example.invalid/json/1",
                            "date_published": "2026-07-21T01:46:00Z",
                            "content_text": "合同金额以公告为准",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(COLLECT), "--feed", str(feed)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["symbols"], ["000001"])
        self.assertEqual(event["event_type"], "contract")

    def test_public_benchmark_and_doctor_pass(self):
        for command in ([sys.executable, str(EVALUATE)], [sys.executable, str(DOCTOR)]):
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_sse_adapter_contract_fixture(self):
        result = subprocess.run(
            [
                sys.executable,
                str(COLLECT_SSE),
                "--fixture",
                str(FIXTURES / "sse" / "valid.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["source"], "上海证券交易所")
        self.assertEqual(event["symbols"], ["600000"])
        self.assertEqual(event["event_type"], "buyback")
        self.assertTrue(event["url"].startswith("https://www.sse.com.cn/"))
        self.assertTrue(event["evidence_origin"].startswith("sse-announcement:"))

    def test_szse_adapter_contract_fixture(self):
        result = subprocess.run(
            [
                sys.executable,
                str(COLLECT_SZSE),
                "--fixture",
                str(FIXTURES / "szse" / "valid.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["source"], "深圳证券交易所")
        self.assertEqual(event["symbols"], ["000001"])
        self.assertEqual(event["event_type"], "contract")
        self.assertTrue(event["published_at"].endswith("+08:00"))
        self.assertTrue(event["url"].startswith("https://disc.static.szse.cn/"))
        self.assertTrue(event["evidence_origin"].startswith("szse-announcement:"))

    def test_primary_adapters_reject_failed_contract_fixtures(self):
        cases = (
            (COLLECT_SSE, FIXTURES / "sse" / "missing-date.json", "publication time"),
            (COLLECT_SSE, FIXTURES / "sse" / "malformed-envelope.json", "result array"),
            (COLLECT_SSE, FIXTURES / "sse" / "external-url.json", "outside the adapter contract"),
            (COLLECT_SZSE, FIXTURES / "szse" / "invalid-code.json", "six-digit"),
            (COLLECT_SZSE, FIXTURES / "szse" / "malformed-envelope.json", "data array"),
        )
        for script, fixture, message in cases:
            with self.subTest(fixture=fixture.name):
                result = subprocess.run(
                    [sys.executable, str(script), "--fixture", str(fixture)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_primary_adapter_output_passes_registry_evidence_gate(self):
        collected = subprocess.run(
            [
                sys.executable,
                str(COLLECT_SSE),
                "--fixture",
                str(FIXTURES / "sse" / "valid.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(collected.returncode, 0, collected.stderr)
        event_path = self.runtime_path("sse-event.jsonl")
        event_path.write_text(collected.stdout, encoding="utf-8")
        watchlist_path = self.runtime_path("sse-watchlist.json")
        watchlist_path.write_text(json.dumps({"symbols": {"600000": {}}}), encoding="utf-8")
        fused = subprocess.run(
            [
                sys.executable,
                str(FUSE),
                "--events",
                str(event_path),
                "--watchlist",
                str(watchlist_path),
                "--source-registry",
                str(SKILL / "assets" / "source-registry.official.json"),
                "--now",
                "2026-07-21T10:00:00+08:00",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(fused.returncode, 0, fused.stderr)
        self.assertTrue(json.loads(fused.stdout)["cards"][0]["evidence_gate"])

    def test_remote_feed_requires_https(self):
        config_path = self.runtime_path("http-feed-config.json")
        config_path.write_text(
            json.dumps({"feeds": [{"location": "http://example.com/feed.xml"}]}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(VALIDATE), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("remote collection requires HTTPS", result.stdout)

    def test_http_client_blocks_non_public_addresses(self):
        command = (
            "import sys; "
            f"sys.path.insert(0, {str(SKILL / 'scripts')!r}); "
            "import http_client; "
            "http_client.validate_url('https://127.0.0.1/x', allowed_hosts={'127.0.0.1'})"
        )
        result = subprocess.run(
            [sys.executable, "-c", command],
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-public address", result.stderr.decode("utf-8", errors="replace"))

    def test_http_client_rejects_credential_like_query_parameters(self):
        with self.assertRaisesRegex(ValueError, "credential-like query"):
            http_client.validate_url(
                "https://example.com/feed?token=do-not-cache",
                allowed_hosts={"example.com"},
                resolver=lambda *args, **kwargs: [],
            )

    def test_http_client_reuses_etag_cache_on_304(self):
        first = FakeOpener(
            [FakeResponse(b"cached-body", {"Content-Type": "application/json", "ETag": '"v1"'})]
        )
        not_modified = HTTPError(
            "https://example.com/feed", 304, "Not Modified", {}, None
        )
        second = FakeOpener([not_modified])
        metadata_path, body_path = http_client._cache_paths(
            RUNTIME, "https://example.com/feed"
        )
        self.addCleanup(metadata_path.unlink, missing_ok=True)
        self.addCleanup(body_path.unlink, missing_ok=True)
        with mock.patch.object(http_client, "_public_addresses", return_value=["93.184.216.34"]), mock.patch.object(
            http_client, "build_opener", side_effect=[first, second]
        ):
            body, _, cached = http_client.fetch_bytes(
                "https://example.com/feed",
                allowed_hosts={"example.com"},
                cache_dir=RUNTIME,
                min_interval=0,
                retries=0,
            )
            self.assertEqual(body, b"cached-body")
            self.assertFalse(cached)
            body, _, cached = http_client.fetch_bytes(
                "https://example.com/feed",
                allowed_hosts={"example.com"},
                cache_dir=RUNTIME,
                min_interval=0,
                retries=0,
            )
        self.assertEqual(body, b"cached-body")
        self.assertTrue(cached)
        self.assertEqual(second.requests[0].get_header("If-none-match"), '"v1"')

    def test_http_client_retries_transient_status_once(self):
        unavailable = HTTPError(
            "https://example.com/feed", 503, "Unavailable", {"Retry-After": "0"}, None
        )
        opener = FakeOpener([unavailable, FakeResponse(b"ok")])
        with mock.patch.object(http_client, "_public_addresses", return_value=["93.184.216.34"]), mock.patch.object(
            http_client, "build_opener", return_value=opener
        ), mock.patch.object(http_client.time, "sleep"):
            body, _, cached = http_client.fetch_bytes(
                "https://example.com/feed",
                allowed_hosts={"example.com"},
                min_interval=0,
                retries=1,
            )
        self.assertEqual(body, b"ok")
        self.assertFalse(cached)
        self.assertEqual(len(opener.requests), 2)

    def test_http_client_rejects_oversized_response(self):
        opener = FakeOpener(
            [FakeResponse(b"012345", {"Content-Type": "application/json", "Content-Length": "6"})]
        )
        with mock.patch.object(http_client, "_public_addresses", return_value=["93.184.216.34"]), mock.patch.object(
            http_client, "build_opener", return_value=opener
        ):
            with self.assertRaisesRegex(ValueError, "response exceeds"):
                http_client.fetch_bytes(
                    "https://example.com/feed",
                    allowed_hosts={"example.com"},
                    max_bytes=5,
                    min_interval=0,
                    retries=0,
                )

    def test_regression_proposal_defaults_to_api_preview_and_redacts_secrets(self):
        issue_path = self.runtime_path("public-issue.json")
        issue_path.write_text(
            json.dumps(
                {
                    "number": 99,
                    "title": "Parser misses one disclosure",
                    "body": "token=do-not-print https://example.com/private-secret-path?token=hidden",
                    "url": "https://github.com/example/repo/issues/99",
                }
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["OPENAI_API_KEY"] = "also-do-not-print"
        result = subprocess.run(
            [sys.executable, str(PROPOSE), "--issue", str(issue_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["mode"], "preview_only")
        self.assertNotIn("do-not-print", result.stdout)
        self.assertNotIn("private-secret-path", result.stdout)
        self.assertNotIn("also-do-not-print", result.stdout)

    def test_example_config_passes_offline_validation(self):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(VALIDATE),
                "--config",
                str(SKILL / "assets" / "examples" / "radar-config.json"),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        output = json.loads(result.stdout)
        self.assertTrue(output["ready"])
        self.assertFalse(any(item["status"] == "fail" for item in output["checks"]))

    def test_config_validation_rejects_inline_notification_secret(self):
        config = json.loads(
            (SKILL / "assets" / "examples" / "radar-config.json").read_text(encoding="utf-8")
        )
        config["feeds"][0]["location"] = str(SKILL / "assets" / "examples" / "feed.xml")
        config["watchlist"] = str(SKILL / "assets" / "examples" / "watchlist.json")
        config["source_registry"] = str(
            SKILL / "assets" / "examples" / "source-registry.json"
        )
        config["notification"] = {
            "channel": "feishu",
            "webhook_url": "https://example.invalid/private-hook",
        }
        config_path = self.runtime_path("unsafe-config.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATE), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        inline = next(item for item in output["checks"] if item["name"] == "inline_secrets")
        self.assertEqual(inline["status"], "fail")
        self.assertIn("config.notification.webhook_url", inline["detail"])
        self.assertNotIn("private-hook", result.stdout)

    def test_config_validation_accepts_absolute_windows_paths(self):
        config = {
            "feeds": [{"location": str(SKILL / "assets" / "examples" / "feed.xml")}],
            "watchlist": str(SKILL / "assets" / "examples" / "watchlist.json"),
            "source_registry": str(SKILL / "assets" / "examples" / "source-registry.json"),
            "output": str(self.runtime_path("report.md")),
        }
        config_path = self.runtime_path("absolute-path-config.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATE), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        output = json.loads(result.stdout)
        feed = next(item for item in output["checks"] if item["name"] == "feed[1]")
        self.assertEqual(feed["status"], "pass")

    def test_config_validation_reports_missing_local_feed(self):
        config = {
            "feeds": [{"location": "missing-feed.xml"}],
            "format": "markdown",
        }
        config_path = self.runtime_path("missing-feed-config.json")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATE), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        feed = next(item for item in output["checks"] if item["name"] == "feed[1]")
        self.assertEqual(feed["status"], "fail")
        self.assertIn("local file not found", feed["detail"])

    def test_doctor_can_validate_user_config_without_network(self):
        result = subprocess.run(
            [
                sys.executable,
                str(DOCTOR),
                "--config",
                str(SKILL / "assets" / "examples" / "radar-config.json"),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        output = json.loads(result.stdout)
        self.assertTrue(output["ready"])
        self.assertTrue(any(item["name"] == "config.feed[1]" for item in output["checks"]))

    def test_doctor_requires_configured_webhook_environment(self):
        config = json.loads(
            (SKILL / "assets" / "examples" / "radar-config.json").read_text(encoding="utf-8")
        )
        config["feeds"][0]["location"] = str(SKILL / "assets" / "examples" / "feed.xml")
        config["watchlist"] = str(SKILL / "assets" / "examples" / "watchlist.json")
        config["source_registry"] = str(
            SKILL / "assets" / "examples" / "source-registry.json"
        )
        config["notification"] = {"channel": "feishu"}
        config_path = self.runtime_path("doctor-feishu-config.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("FEISHU_WEBHOOK_URL", None)
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        check = next(
            item for item in output["checks"] if item["name"] == "config.notification.environment"
        )
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["detail"], "missing environment variable(s): FEISHU_WEBHOOK_URL")

    def test_doctor_requires_both_telegram_environment_variables(self):
        config = json.loads(
            (SKILL / "assets" / "examples" / "radar-config.json").read_text(encoding="utf-8")
        )
        config["feeds"][0]["location"] = str(SKILL / "assets" / "examples" / "feed.xml")
        config["watchlist"] = str(SKILL / "assets" / "examples" / "watchlist.json")
        config["source_registry"] = str(
            SKILL / "assets" / "examples" / "source-registry.json"
        )
        config["notification"] = {"channel": "telegram"}
        config_path = self.runtime_path("doctor-telegram-config.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment["TELEGRAM_BOT_TOKEN"] = "not-printed"
        environment.pop("TELEGRAM_CHAT_ID", None)
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--config", str(config_path), "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("TELEGRAM_CHAT_ID", result.stdout)
        self.assertNotIn("not-printed", result.stdout)

    def test_run_radar_no_notify_does_not_require_notification_environment(self):
        config = json.loads(
            (SKILL / "assets" / "examples" / "radar-config.json").read_text(encoding="utf-8")
        )
        config["feeds"][0]["location"] = str(SKILL / "assets" / "examples" / "feed.xml")
        config["watchlist"] = str(SKILL / "assets" / "examples" / "watchlist.json")
        config["source_registry"] = str(
            SKILL / "assets" / "examples" / "source-registry.json"
        )
        config["notification"] = {"channel": "feishu"}
        config_path = self.runtime_path("no-notify-config.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("FEISHU_WEBHOOK_URL", None)
        result = subprocess.run(
            [sys.executable, str(RUN), "--config", str(config_path), "--no-notify"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_command_pipeline_uses_self_contained_config(self):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(RUN),
                "--config",
                str(SKILL / "assets" / "examples" / "radar-config.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("示例公司", result.stdout)
        self.assertIn("Eligible: 1", result.stdout)

    def test_cli_emits_utf8_without_python_utf8_flag(self):
        result = subprocess.run(
            [
                sys.executable,
                str(FUSE),
                "--events",
                str(SKILL / "assets" / "examples" / "events.jsonl"),
                "--watchlist",
                str(SKILL / "assets" / "examples" / "watchlist.json"),
                "--source-registry",
                str(SKILL / "assets" / "examples" / "source-registry.json"),
                "--now",
                "2026-07-21T10:00:00+08:00",
                "--format",
                "markdown",
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        output = result.stdout.decode("utf-8")
        self.assertIn("示例公司", output)


if __name__ == "__main__":
    unittest.main()
