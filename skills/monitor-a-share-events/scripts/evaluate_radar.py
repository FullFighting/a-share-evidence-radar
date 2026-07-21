#!/usr/bin/env python3
"""Evaluate evidence-gating behavior against a public, reviewable benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = SKILL_ROOT / "references" / "benchmark-cases.json"
DEFAULT_REGISTRY = SKILL_ROOT / "assets" / "examples" / "source-registry.json"


def load_fuse_module():
    path = SKILL_ROOT / "scripts" / "fuse_events.py"
    spec = importlib.util.spec_from_file_location("evidence_radar_fuse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load fuse_events.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_case(
    fuse, case: dict[str, Any], registry: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    events = [
        fuse.normalize_event(item, index, registry)
        for index, item in enumerate(case["events"], 1)
    ]
    raw_watchlist = case.get("watchlist", {})
    watchlist = {
        "symbols": {
            fuse.normalize_symbol(symbol): metadata if isinstance(metadata, dict) else {}
            for symbol, metadata in raw_watchlist.get("symbols", {}).items()
            if fuse.normalize_symbol(symbol)
        },
        "keywords": [str(x) for x in raw_watchlist.get("keywords", [])],
        "sectors": [str(x) for x in raw_watchlist.get("sectors", [])],
    }
    clusters = fuse.cluster_events(events, timedelta(minutes=case.get("window_minutes", 180)))
    cards = [
        fuse.build_card(cluster, watchlist, fuse.parse_time(case["now"]), case.get("min_score", 60))
        for cluster in clusters
    ]
    expected = case["expected"]
    actual = {
        "card_count": len(cards),
        "status": cards[0]["status"] if len(cards) == 1 else None,
        "evidence_gate": cards[0]["evidence_gate"] if len(cards) == 1 else None,
        "relevance_gate": cards[0]["relevance_gate"] if len(cards) == 1 else None,
        "conflict_gate": cards[0]["conflict_gate"] if len(cards) == 1 else None,
        "freshness_gate": cards[0]["freshness_gate"] if len(cards) == 1 else None,
        "independent_source_count": cards[0]["independent_source_count"] if len(cards) == 1 else None,
    }
    mismatches = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    return {
        "id": case["id"],
        "description": case.get("description", ""),
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the public evidence-radar benchmark.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--source-registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        cases = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))
        if not isinstance(cases, list):
            raise ValueError("benchmark file must contain a JSON array")
        fuse = load_fuse_module()
        registry = fuse.load_source_registry(args.source_registry)
        results = [evaluate_case(fuse, case, registry) for case in cases]
        passed = sum(result["passed"] for result in results)
        payload = {
            "score": round(100 * passed / len(results), 1) if results else 0.0,
            "passed": passed,
            "total": len(results),
            "results": results,
        }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for result in results:
                marker = "PASS" if result["passed"] else "FAIL"
                print(f"[{marker}] {result['id']}: {result['description']}")
                for key, values in result["mismatches"].items():
                    print(f"  {key}: expected {values['expected']!r}, got {values['actual']!r}")
            print(f"Benchmark: {passed}/{len(results)} ({payload['score']:.1f}%)")
        return 0 if passed == len(results) else 1
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
