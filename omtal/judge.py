# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Judgements: a person's or a model's answer to a judgement rule, with provenance forced.

Kept only while the facts it saw are unchanged; the grid discards it otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import grid as grid_mod
from .schema import now_iso, read_json


def rule_by_id(rule_id: str) -> dict:
    for r in grid_mod.load_rules():
        if r["id"] == rule_id:
            return r
    raise KeyError(rule_id)


def add_judgement(out_dir: Path, rule_id: str, verdict: str, evidence: str, by: str) -> dict:
    rule = rule_by_id(rule_id)
    if rule["kind"] != "judgement":
        raise ValueError(f"{rule_id} is decided by code, not by judgement")
    if verdict not in ("PASS", "FAIL", "RISK", "NOTE"):
        raise ValueError("verdict must be PASS, FAIL, RISK or NOTE")
    if len(evidence.strip()) < 20:
        raise ValueError("evidence must say what was looked at, in at least twenty characters")
    probes = read_json(out_dir / "probes.json")
    entry = {"rule": rule_id, "verdict": verdict, "evidence": evidence.strip(), "by": by, "at": now_iso(),
             "provenance": "sub-agent-reported", "probe_sha256": grid_mod.probe_hash(probes, rule["consumes"])}
    with open(out_dir / "judgements.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
