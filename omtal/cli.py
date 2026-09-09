# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""omtal: can AI systems find, understand, cite and recommend this product, and how do we know?

    omtal audit <url> [--out DIR] [--budget N] [--competitor NAME ...]   read the site, derive the questions, judge every rule, write the report
    omtal observe <url> [--engines ...] [--runs N]                        ask the engines the questions (keys from the environment) and record every answer
    omtal judge <url> <rule> PASS|FAIL|RISK|NOTE "<evidence>" --by <who> record a reviewer's answer to a judgement rule
    omtal intents <url> [--strike ID] [--add "question"]                 see or amend the questions
    omtal check <url>                                                    no network: the grid is well-formed and the page is what it renders
    omtal rule <id>                                                      one rule and why it matters
    omtal self-test                                                      every module checks itself

Results go to <out>/<host>/ (default: ./omtal-out): probes.json, intents.json, observations.jsonl, grid.json, report.html and the exports.
Engines: BRAVE_SEARCH_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY. Without a key an engine is skipped and the report says so.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from . import __version__, checks, grid as grid_mod, intents as intents_mod, judge, observe, report, web
from .probes import entity, pages, site
from .schema import make_probe, read_json, write_json


def out_dir_for(url: str, base: str) -> Path:
    p = urllib.parse.urlsplit(url)
    slug = (p.netloc + p.path.rstrip("/")).replace("/", "_").replace(":", "_")
    d = Path(base).resolve() / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def norm_url(u: str) -> str:
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def cmd_audit(a) -> int:
    url = norm_url(a.url)
    out = out_dir_for(url, a.out)
    pre_deploy = getattr(a, "pre_deploy", False)
    print(f"Reading {url} the way a crawler does" + (" (pre-deploy: a local build, HTTPS not required, sitemap followed against this host)" if pre_deploy else ""))
    probes = site.probe(url, pre_deploy=pre_deploy)
    sm = next((p["value"] for p in probes if p["id"] == "site.sitemap"), None) or {}
    probes += pages.probe(url, sm.get("pages"), budget=a.budget)
    pg = next(p["value"] for p in probes if p["id"] == "site.pages")
    probes += entity.probe(pg, url)
    g = next(p["value"] for p in probes if p["id"] == "product.graph")
    obs = observe.load(out)
    if obs:
        probes.append(make_probe("observations.summary", observe.summarise(obs), source_kind="file", source_ref=str(out / "observations.jsonl")))
    else:
        probes.append(make_probe("observations.summary", None, source_kind="file", source_ref=str(out / "observations.jsonl"), provenance="needs-engine-access",
                                 error="no engine was asked yet; set an engine key and run omtal observe"))
    write_json(out / "probes.json", probes)
    existing = read_json(out / "intents.json") if (out / "intents.json").exists() else []
    kept = [i for i in existing if i.get("added_by") != "omtal"]
    if g:
        derived = intents_mod.generate(g)
        struck = {i["question"] for i in existing if i.get("status") == "struck"}
        for i in derived:
            if i["question"] in struck:
                i["status"] = "struck"
        write_json(out / "intents.json", derived + kept)
    gd = grid_mod.build(out, probes)
    write_json(out / "grid.json", gd)
    report.render(out / "grid.json", out / "report.html", url)
    print(f"Site: robots {'present' if (next(p['value'] for p in probes if p['id']=='site.robots') or {}).get('present') else 'absent'}; sitemap {sm.get('count', 0)} pages; crawled {pg['crawled']} pages; product: {g.get('name') if g else 'unknown'}")
    print(f"Where it stands: {report.STAGE_WORDS[gd['stage']]}")
    for r in gd["rows"]:
        if r["verdict"] in ("FAIL", "RISK"):
            print(f"{report.VERDICT_WORDS[r['verdict']]:<22} {r['title']}\n    {r['evidence'][:220]}")
    c = gd["counts"]
    print(f"\n{c['FAIL']} keep machines out, {c['RISK']} weaken understanding, {c['UNKNOWN']} still to check, {c['PASS']} in order; report at {out / 'report.html'}")
    return 0


def cmd_observe(a) -> int:
    url = norm_url(a.url)
    out = out_dir_for(url, a.out)
    if not (out / "intents.json").exists():
        print("run omtal audit first; the questions come from the site", file=sys.stderr)
        return 1
    intents = read_json(out / "intents.json")
    g = next((p["value"] for p in read_json(out / "probes.json") if p["id"] == "product.graph"), {}) or {}
    host = urllib.parse.urlsplit(url).netloc.removeprefix("www.")
    avail = observe.available()
    print("Engines: " + ", ".join(f"{k} ({'key present' if v else 'no key, skipped'})" for k, v in avail.items()))
    if not any(avail.values()):
        print("No engine key in the environment; nothing observed. Set BRAVE_SEARCH_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2
    chosen = [i for i in intents if i.get("status") != "struck"][: a.limit]
    r = observe.observe(out, chosen, g.get("name") or "", host, a.competitor or [], engines=a.engines, runs=a.runs)
    print(f"{r['written']} observations written to {r['file']} from {', '.join(r['engines'])}" + (f"; skipped {', '.join(r['skipped'])}" if r["skipped"] else ""))
    print("Run omtal audit again to fold them into the report.")
    return 0


def cmd_judge(a) -> int:
    out = out_dir_for(norm_url(a.url), a.out)
    try:
        j = judge.add_judgement(out, a.rule, a.verdict, a.evidence, a.by)
    except (ValueError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(j, indent=2, ensure_ascii=False))
    gd = grid_mod.build(out, read_json(out / "probes.json"))
    write_json(out / "grid.json", gd)
    report.render(out / "grid.json", out / "report.html", norm_url(a.url))
    return 0


def cmd_intents(a) -> int:
    out = out_dir_for(norm_url(a.url), a.out)
    path = out / "intents.json"
    intents = read_json(path) if path.exists() else []
    changed = False
    for sid in a.strike or []:
        for i in intents:
            if i["id"] == sid:
                i["status"] = "struck"
                changed = True
    for q in a.add or []:
        intents.append({"id": f"u{len(intents) + 1:03d}", "question": q, "family": "added", "capability": None, "source": "added by " + (a.by or "a person"),
                        "provenance": "sub-agent-reported", "added_by": a.by or "a person", "added_at": __import__("omtal.schema", fromlist=["now_iso"]).now_iso(), "relevance": None, "status": "candidate"})
        changed = True
    if changed:
        write_json(path, intents)
    for i in intents:
        print(f"{i['id']}  {i.get('status', ''):<9} {i['family']:<15} {i['question']}")
    return 0


def cmd_check(a) -> int:
    out = out_dir_for(norm_url(a.url), a.out)
    gp, hp = out / "grid.json", out / "report.html"
    if not gp.exists():
        print("no grid; run audit", file=sys.stderr)
        return 1
    grid_mod.validate(read_json(gp))
    msg = report.check_render(gp, hp, norm_url(a.url))
    if msg:
        print(msg, file=sys.stderr)
        return 1
    print("all checks pass")
    return 0


def cmd_rule(a) -> int:
    try:
        r = judge.rule_by_id(a.rule)
    except KeyError:
        print(f"no rule {a.rule}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0


def cmd_self_test(a) -> int:
    for mod in (web, site, pages, entity, intents_mod, observe, checks, grid_mod):
        mod.self_test()
        print(f"ok  {mod.__name__}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="omtal", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, extra in (("audit", cmd_audit, True), ("observe", cmd_observe, True), ("judge", cmd_judge, False), ("intents", cmd_intents, False), ("check", cmd_check, False)):
        p = sub.add_parser(name)
        p.add_argument("url")
        p.add_argument("--out", default="omtal-out")
        if name == "audit":
            p.add_argument("--budget", type=int, default=pages.DEFAULT_BUDGET, help="pages to crawl at most")
            p.add_argument("--competitor", action="append", help="a name to look for in answers; repeatable")
            p.add_argument("--pre-deploy", action="store_true", dest="pre_deploy",
                           help="audit a local build before it ships: HTTPS is not required, and sitemap/Sitemap-line URLs on the production host are followed against this host")
        if name == "observe":
            p.add_argument("--engines", nargs="*", default=None, choices=list(observe.ENGINES))
            p.add_argument("--runs", type=int, default=1, help="times each question is asked per engine")
            p.add_argument("--limit", type=int, default=20, help="questions to ask at most")
            p.add_argument("--competitor", action="append")
        if name == "judge":
            p.add_argument("rule"); p.add_argument("verdict"); p.add_argument("evidence"); p.add_argument("--by", required=True)
        if name == "intents":
            p.add_argument("--strike", action="append"); p.add_argument("--add", action="append"); p.add_argument("--by", default=None)
        p.set_defaults(fn=fn)
    r = sub.add_parser("rule"); r.add_argument("rule"); r.set_defaults(fn=cmd_rule)
    s = sub.add_parser("self-test"); s.set_defaults(fn=cmd_self_test)
    args = ap.parse_args(argv)
    return args.fn(args)
