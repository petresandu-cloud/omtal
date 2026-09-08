# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The observatory: ask the engines the intents and record exactly what came back.

Adapters use documented APIs with keys from the environment, never private
endpoints. Without a key an engine is skipped and the report says so. Every
observation is immutable and appended to observations.jsonl; what was extracted
from it (mentions, citations, recommendation) is stored beside the raw answer,
never instead of it. Answers are stochastic, so each intent is asked `runs`
times per engine and the report speaks in fractions.

    BRAVE_SEARCH_API_KEY   Brave Web Search API: the sources a search-grounded answer draws on
    OPENAI_API_KEY         OpenAI Responses API with web search: an answer with citations
    ANTHROPIC_API_KEY      Anthropic Messages API with web search: an answer with citations
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .schema import now_iso

ENGINES = {
    "brave-search": {"env": "BRAVE_SEARCH_API_KEY", "kind": "search", "what": "the ten sources Brave returns for the question"},
    "openai-web": {"env": "OPENAI_API_KEY", "kind": "answer", "what": "an OpenAI answer with web search on, and the pages it cites"},
    "anthropic-web": {"env": "ANTHROPIC_API_KEY", "kind": "answer", "what": "a Claude answer with web search on, and the pages it cites"},
}


def available() -> dict[str, bool]:
    return {name: bool(os.environ.get(spec["env"])) for name, spec in ENGINES.items()}


def _post(url: str, body: dict, headers: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url: str, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def run_engine(engine: str, question: str) -> dict:
    """One raw observation. Raises on transport failure; the caller records the failure."""
    if engine == "brave-search":
        d = _get("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": question, "count": 10}),
                 {"Accept": "application/json", "X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"]})
        results = [{"url": r.get("url"), "title": r.get("title"), "description": r.get("description")} for r in (d.get("web") or {}).get("results", [])]
        return {"answer": "\n".join(f"{r['title']}: {r['description']}" for r in results), "citations": [r["url"] for r in results if r.get("url")], "raw": d}
    if engine == "openai-web":
        d = _post("https://api.openai.com/v1/responses", {"model": os.environ.get("OMTAL_OPENAI_MODEL", "gpt-5"), "tools": [{"type": "web_search"}], "input": question},
                  {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        text, cites = "", []
        for item in d.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    text += c.get("text", "")
                    for a in c.get("annotations", []) or []:
                        if a.get("type") == "url_citation" and a.get("url"):
                            cites.append(a["url"])
        return {"answer": text, "citations": cites, "raw": d}
    if engine == "anthropic-web":
        d = _post("https://api.anthropic.com/v1/messages", {"model": os.environ.get("OMTAL_ANTHROPIC_MODEL", "claude-sonnet-5"), "max_tokens": 1500,
                  "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}], "messages": [{"role": "user", "content": question}]},
                  {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        text, cites = "", []
        for c in d.get("content", []):
            if c.get("type") == "text":
                text += c.get("text", "")
                for cit in c.get("citations", []) or []:
                    if cit.get("url"):
                        cites.append(cit["url"])
        return {"answer": text, "citations": cites, "raw": d}
    raise ValueError(f"unknown engine {engine}")


def extract(answer: str, citations: list[str], name: str, host: str, competitors: list[str]) -> dict:
    """What the answer did with us: mentioned, cited, recommended; and who else it named."""
    text = answer or ""
    ours = bool(name) and re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text, re.I) is not None
    cited = [c for c in citations if host and host.lower() in c.lower()]
    domains = sorted({urllib.parse.urlsplit(c).netloc.lower().removeprefix("www.") for c in citations if c})
    recommended = ours and re.search(r"\b(recommend|best|top|try|consider|use)\b", text, re.I) is not None
    others = [c for c in competitors if re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", text, re.I)]
    return {"mentioned": ours, "cited": bool(cited), "our_citations": cited, "recommended": recommended, "domains_cited": domains, "competitors_mentioned": others}


def observe(out_dir: Path, intents: list[dict], name: str, host: str, competitors: list[str], engines: list[str] | None = None, runs: int = 1) -> dict:
    avail = available()
    chosen = [e for e in (engines or list(ENGINES)) if avail.get(e)]
    skipped = [e for e in (engines or list(ENGINES)) if not avail.get(e)]
    path = out_dir / "observations.jsonl"
    n = 0
    with open(path, "a", encoding="utf-8") as f:
        for it in intents:
            if it.get("status") == "struck":
                continue
            for eng in chosen:
                for run in range(runs):
                    rec = {"intent": it["id"], "question": it["question"], "engine": eng, "run": run + 1, "at": now_iso()}
                    try:
                        r = run_engine(eng, it["question"])
                        rec.update(answer=r["answer"], citations=r["citations"], extracted=extract(r["answer"], r["citations"], name, host, competitors), error=None)
                    except Exception as e:  # noqa: BLE001
                        rec.update(answer=None, citations=[], extracted=None, error=str(e)[:300])
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
    return {"written": n, "engines": chosen, "skipped": skipped, "file": str(path)}


def load(out_dir: Path) -> list[dict]:
    p = out_dir / "observations.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def summarise(obs: list[dict]) -> dict:
    """Fractions per engine, from the stored observations. The report speaks from this, never from a model's memory."""
    by = {}
    for o in obs:
        if o.get("error") or not o.get("extracted"):
            by.setdefault(o["engine"], {"asked": 0, "mentioned": 0, "cited": 0, "recommended": 0, "failed": 0, "domains": {}, "competitors": {}})["failed"] += 1
            by[o["engine"]]["asked"] += 1
            continue
        b = by.setdefault(o["engine"], {"asked": 0, "mentioned": 0, "cited": 0, "recommended": 0, "failed": 0, "domains": {}, "competitors": {}})
        x = o["extracted"]
        b["asked"] += 1
        b["mentioned"] += x["mentioned"]
        b["cited"] += x["cited"]
        b["recommended"] += x["recommended"]
        for d in x["domains_cited"]:
            b["domains"][d] = b["domains"].get(d, 0) + 1
        for c in x["competitors_mentioned"]:
            b["competitors"][c] = b["competitors"].get(c, 0) + 1
    for b in by.values():
        b["domains"] = sorted(b["domains"].items(), key=lambda kv: -kv[1])[:15]
        b["competitors"] = sorted(b["competitors"].items(), key=lambda kv: -kv[1])
    return by


def self_test() -> None:
    x = extract("I recommend Foo (foo.example) and Bar.", ["https://www.foo.example/a", "https://reddit.com/r/x"], "Foo", "foo.example", ["Bar", "Baz"])
    assert x["mentioned"] and x["cited"] and x["recommended"] and x["competitors_mentioned"] == ["Bar"] and "reddit.com" in x["domains_cited"]
    s = summarise([{"engine": "e", "extracted": x, "error": None}, {"engine": "e", "extracted": None, "error": "boom"}])
    assert s["e"]["asked"] == 2 and s["e"]["mentioned"] == 1 and s["e"]["failed"] == 1
