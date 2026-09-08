# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rules to rows. Every row carries exactly one provenance marker or the build fails.

Overlay order per rule: the mechanical check or the recorded judgement; a
judgement is kept only while the facts it saw are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from . import checks
from .schema import PROVENANCE, VERDICTS, LAYERS, now_iso, read_json

RULES_DIR = Path(__file__).resolve().parent / "rules"
STAGE_ORDER = ("unreachable", "reachable", "understood", "cited", "recommended")


def load_rules() -> list[dict]:
    rules = []
    for f in sorted(RULES_DIR.glob("*.toml")):
        for r in tomllib.load(open(f, "rb"))["rule"]:
            assert_rule(r)
            rules.append(r)
    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids)), "duplicate rule id"
    return rules


def assert_rule(r: dict) -> None:
    for k in ("id", "layer", "title", "consumes", "kind", "severity", "why"):
        if k not in r:
            raise ValueError(f"rule {r.get('id')}: missing {k}")
    if r["layer"] not in LAYERS:
        raise ValueError(f"rule {r['id']}: layer must be one of {LAYERS}")
    if r["kind"] == "mechanical" and not hasattr(checks, r.get("check", "")):
        raise ValueError(f"rule {r['id']}: no check function {r.get('check')}")
    if r["kind"] == "judgement" and not r.get("question"):
        raise ValueError(f"rule {r['id']}: a judgement rule needs a question")
    if r["severity"] not in ("fail", "risk", "note"):
        raise ValueError(f"rule {r['id']}: severity must be fail, risk or note")


def probe_hash(probes: list[dict], ids: list[str]) -> str:
    by = {p["id"]: p for p in probes}
    return hashlib.sha256(json.dumps([by[i]["value"] for i in ids if i in by], sort_keys=True, default=str).encode()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def stage_from_rows(rows: list[dict], facts: checks.Facts) -> str:
    """How far the product has got: the ladder in the design, from the verdicts and the stored observations."""
    v = {r["id"]: r["verdict"] for r in rows}
    if v.get("access.home-answers") == "FAIL" or v.get("access.robots-admits-ai-crawlers") == "FAIL":
        return "unreachable"
    if v.get("entity.product-declared") != "PASS":
        return "reachable"
    # once an engine has done it at all, the ladder moves; the report's fractions say how often
    obs = facts.val("observations.summary") or {}
    if any(b.get("recommended", 0) > 0 for b in obs.values()):
        return "recommended"
    if any(b.get("cited", 0) > 0 for b in obs.values()):
        return "cited"
    return "understood"


def build(out_dir: Path, probes: list[dict]) -> dict:
    rules = load_rules()
    facts = checks.Facts(probes)
    judgements = load_jsonl(out_dir / "judgements.jsonl")
    rows = []
    for rule in rules:
        row = {"id": rule["id"], "layer": rule["layer"], "title": rule["title"], "severity": rule["severity"], "kind": rule["kind"], "why": rule["why"],
               "probes": [{"id": i, "observed_at": facts.by[i]["observed_at"]} for i in rule["consumes"] if i in facts.by]}
        if rule["kind"] == "mechanical":
            verdict, evidence, prov = getattr(checks, rule["check"])(facts)
            if rule["severity"] == "risk" and verdict == "FAIL":
                verdict = "RISK"
            if rule["severity"] == "note" and verdict in ("FAIL", "RISK"):
                verdict = "NOTE"
        else:
            h = probe_hash(probes, rule["consumes"])
            j = next((j for j in reversed(judgements) if j["rule"] == rule["id"]), None)
            if j is None:
                verdict, evidence, prov = "UNKNOWN", "awaiting judgement: " + rule["question"], "needs-owner-answer"
            elif j.get("probe_sha256") != h:
                verdict, evidence, prov = "UNKNOWN", f"a judgement by {j.get('by')} on {j.get('at')} was discarded because the facts it saw have changed; ask again: " + rule["question"], "needs-owner-answer"
            else:
                verdict, evidence, prov = j["verdict"], j["evidence"], "sub-agent-reported"
                row["judgement"] = {"by": j.get("by"), "at": j.get("at")}
        row.update(verdict=verdict, evidence=evidence, provenance=prov)
        rows.append(row)
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    grid = {"built_at": now_iso(), "stage": stage_from_rows(rows, facts), "counts": counts, "rows": rows}
    validate(grid)
    return grid


def validate(grid: dict) -> None:
    if not grid["rows"]:
        raise ValueError("a grid with no rows is not a grid")
    for r in grid["rows"]:
        if r.get("verdict") not in VERDICTS:
            raise ValueError(f"{r['id']}: verdict {r.get('verdict')!r}")
        if r.get("provenance") not in PROVENANCE:
            raise ValueError(f"{r['id']}: exactly one provenance marker is required, got {r.get('provenance')!r}")
        if not r.get("evidence"):
            raise ValueError(f"{r['id']}: evidence is empty")
    if grid["stage"] not in STAGE_ORDER:
        raise ValueError("stage")


def self_test() -> None:
    rules = load_rules()
    assert len(rules) >= 20
    try:
        validate({"rows": [{"id": "x", "verdict": "PASS", "evidence": "e", "provenance": "made-up"}], "stage": "reachable"})
        raise AssertionError("a row without a real provenance marker must fail")
    except ValueError:
        pass
