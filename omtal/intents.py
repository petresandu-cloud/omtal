# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Intents: the questions people ask an AI that this product could legitimately answer.

Not keywords. Starting from what the site says the product does, each capability
becomes a problem, then a situation, then the natural questions. This module
produces the deterministic candidate set from the product graph; a model or a
person may add, rank or strike intents with `omtal intents`, and every intent
records who put it there. An intent is never proof of demand; it is a question
worth asking an engine.
"""

from __future__ import annotations

import re

from .schema import now_iso

TEMPLATES = (
    ("recommendation", "What is a good {kind} for {capability}?"),
    ("recommendation", "Best app to {capability_verb}"),
    ("problem", "How can I {capability_verb}?"),
    ("comparison", "{name} vs alternatives for {capability}"),
    ("informational", "Is there a {kind} that can {capability_verb}?"),
)
STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "with", "your", "our", "you", "we", "get", "what", "how", "honest", "state", "things", "hear", "need", "try", "most", "want"}


def _kind(graph: dict) -> str:
    types = [t for p in graph["declared"]["products"] for t in p["types"]]
    if any(t in ("MobileApplication",) for t in types):
        return "mobile app"
    if any(t in ("SoftwareApplication", "WebApplication") for t in types):
        return "tool"
    if "Service" in types:
        return "service"
    return "product"


def _capabilities(graph: dict) -> list[str]:
    caps = []
    for p in graph["declared"]["products"]:
        for f in p.get("features") or []:
            if isinstance(f, str):
                caps.append(f.strip())
    for h in graph["apparent"]["features_from_headings"]:
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]+", h.lower())]
        if len(words) >= 2 and not (set(words) <= STOP) and not re.match(r"^\d", h) and words[0] not in STOP:
            caps.append(h.strip().rstrip(".:"))
    seen, out = set(), []
    for c in caps:
        k = c.lower()
        if k not in seen and 3 <= len(c) <= 80:
            seen.add(k)
            out.append(c)
    return out[:25]


def _verb(cap: str) -> str:
    c = cap.strip().rstrip(".")
    c = re.sub(r"^(get|what|how|why|the|a|an)\s+", "", c, flags=re.I)
    return c[0].lower() + c[1:] if c else c


def generate(graph: dict) -> list[dict]:
    name = graph.get("name") or "this product"
    kind = _kind(graph)
    intents = []
    for cap in _capabilities(graph):
        for family, tpl in TEMPLATES:
            q = tpl.format(kind=kind, capability=cap.lower(), capability_verb=_verb(cap), name=name)
            intents.append({"id": f"i{len(intents) + 1:03d}", "question": q, "family": family, "capability": cap, "source": "derived from the site's own headings and structured data",
                            "provenance": "inferred", "added_by": "omtal", "added_at": now_iso(), "relevance": None, "status": "candidate"})
    return intents


def self_test() -> None:
    g = {"name": "Foo", "declared": {"products": [{"types": ["MobileApplication"], "features": ["track lent books"]}]}, "apparent": {"features_from_headings": ["Lending history", "Get the beta"]}}
    it = generate(g)
    assert any("track lent books" in i["question"] for i in it) and it[0]["provenance"] == "inferred"
    assert not any("get the beta" in i["question"].lower() for i in it)
