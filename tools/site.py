# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the public site: a landing page, one page per rule, a sample report; with the
things a machine needs to read it (canonical, structured data, sitemap, robots, llms.txt).

    python3 tools/site.py [--out site] [--sample path/to/report.html]
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from omtal import grid  # noqa: E402
from omtal.report import LAYER_WORDS  # noqa: E402

e = html.escape
SITE = "https://editerra.se/omtal"
ROOT = Path(__file__).resolve().parent.parent
MARK = (ROOT / "assets" / "omtal-mark.svg").read_text()
SEVERITY = {"fail": ("Keeps machines out", "s-fail"), "risk": ("Weakens understanding", "s-risk"), "note": ("Worth knowing", "s-note")}
ORG = {"@type": "Organization", "@id": "https://www.editerra.se/#org", "name": "Editerra AB", "url": "https://www.editerra.se", "identifier": "559441-6454", "email": "contact@editerra.se"}
APP = {"@type": "SoftwareApplication", "@id": SITE + "/#omtal", "name": "Omtal", "applicationCategory": "DeveloperApplication", "operatingSystem": "Linux, macOS, Windows",
       "description": "Checks whether AI systems can find, understand, cite and recommend a product, by reading its site the way a crawler does and asking the engines.",
       "url": SITE + "/", "downloadUrl": "https://github.com/petresandu-cloud/omtal", "softwareVersion": "0.1.0", "license": "https://www.gnu.org/licenses/agpl-3.0.html",
       "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}, "author": {"@id": "https://www.editerra.se/#org"}}
CSS = """
:root{--ink:#141414;--muted:#5a5a5a;--rule:#cfcfcf;--indigo:#3A2E7A;--paper:#fff;--c-fail:#a11c1c;--c-risk:#a35d00;--c-note:#5a5a5a}
body{font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--paper);margin:0}
.wrap{max-width:900px;margin:0 auto;padding:32px 24px} header.top{display:flex;align-items:center;gap:14px;padding:18px 24px;border-bottom:1px solid var(--rule)}
header.top svg{width:36px;height:36px} header.top .word{font-weight:800;font-size:26px;letter-spacing:-.5px} header.top nav{margin-left:auto;display:flex;gap:18px;font-size:15px}
header.top a{color:var(--ink);text-decoration:none} header.top a:hover{text-decoration:underline}
h1{font-size:34px;line-height:1.15;margin:0 0 14px;letter-spacing:-.5px;text-wrap:balance} h2{font-size:20px;margin:36px 0 10px;padding-top:8px;border-top:1px solid var(--rule)}
.lead{font-size:20px;color:var(--muted);margin:0 0 24px;max-width:46em} pre{background:#f4f4f4;border:1px solid var(--rule);padding:12px 14px;overflow-x:auto;font-size:14px} code{font-size:14px}
.status{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;padding:2px 8px;color:#fff;background:var(--muted);vertical-align:middle;margin-right:8px}
.s-fail{background:var(--c-fail)} .s-risk{background:var(--c-risk)} .s-note{background:var(--c-note)} .tag{font-size:12px;border:1px solid var(--rule);padding:1px 6px;color:var(--muted);vertical-align:middle}
ul.rules{list-style:none;padding:0} ul.rules li{padding:8px 0;border-bottom:1px solid var(--rule)} ul.rules a{color:var(--ink);text-decoration:none;font-weight:600} ul.rules a:hover{text-decoration:underline}
.lbl{display:inline-block;min-width:9em;color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.04em}
.cta{display:inline-block;background:var(--indigo);color:#fff;padding:10px 16px;text-decoration:none;font-weight:600;margin-right:10px} .cta.alt{background:#fff;color:var(--ink);border:1px solid var(--ink)}
footer{margin-top:48px;padding:16px 24px;border-top:3px solid var(--ink);font-size:14px;color:var(--muted)}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin:24px 0} .grid3 div{border-top:4px solid var(--indigo);padding-top:10px} .grid3 b{display:block;margin-bottom:4px}
.ladder{list-style:none;padding:0;margin:16px 0;border:1px solid var(--ink)} .ladder li{padding:10px 14px;border-bottom:1px solid var(--rule)} .ladder li:last-child{border-bottom:0} .ladder b{display:inline-block;min-width:9em}
"""


def page(title, body, path="", depth=0, description="", ld=None):
    up = "../" * depth
    canonical = (SITE + "/" + path).replace("/index.html", "/")
    if path == "":
        canonical = SITE + "/"
    graph = {"@context": "https://schema.org", "@graph": [ORG, APP] + (ld or [])}
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description or title)}"><meta name="generator" content="Omtal site generator (Editerra AB)">
<link rel="canonical" href="{e(canonical)}"><meta property="og:site_name" content="Omtal"><meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description or title)}"><meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{SITE}/assets/omtal-social-preview.png">
<script type="application/ld+json">{json.dumps(graph, ensure_ascii=False)}</script><style>{CSS}</style></head><body>
<header class="top"><a href="{up}index.html" style="display:flex;align-items:center;gap:12px">{MARK}<span class="word">omtal</span></a>
<nav><a href="{up}rules/index.html">Rules</a><a href="{up}sample-report.html">Sample report</a><a href="https://github.com/petresandu-cloud/omtal">GitHub</a></nav></header>
<div class="wrap">{body}</div>
<footer>Omtal is open source under the AGPL-3.0-or-later and a trademark of Editerra AB, Org.nr 559441-6454, Sweden. <a href="https://github.com/petresandu-cloud/omtal/blob/main/COMMERCIAL-LICENSE.md">Commercial terms</a> · <a href="mailto:contact@editerra.se">contact@editerra.se</a></footer></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--sample", default=None)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    (out / "rules").mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    (out / "sample").mkdir(exist_ok=True)
    shutil.copy(ROOT / "assets" / "omtal-social-preview.png", out / "assets" / "omtal-social-preview.png")
    rules = grid.load_rules()
    for r in rules:
        sev, cls = SEVERITY[r["severity"]]
        what = (f"<p><span class=lbl>What is checked</span> Decided by code from: {e(', '.join(r['consumes']))}.</p>" if r["kind"] == "mechanical"
                else f"<p><span class=lbl>The question</span> {e(r['question'])}</p>")
        body = f"""<p><span class="status {cls}">{e(sev)}</span><span class=tag>{e(LAYER_WORDS[r['layer']])}</span></p><h1>{e(r['title'])}</h1>{what}
<h2>Why it matters</h2><p>{e(r['why'])}</p>
<h2>Check your site</h2><pre>pip install git+https://github.com/petresandu-cloud/omtal
omtal audit https://your-product.example</pre><p>The report names this rule as <code>{e(r['id'])}</code>.</p>"""
        ld = [{"@type": "TechArticle", "headline": r["title"], "about": ["AI discoverability", LAYER_WORDS[r["layer"]]], "author": {"@id": "https://www.editerra.se/#org"}}]
        (out / "rules" / f"{r['id']}.html").write_text(page(f"{r['title']} · Omtal", body, path=f"rules/{r['id']}.html", depth=1, description=f"{sev}: {r['title']}. {r['why'][:150]}", ld=ld), encoding="utf-8")
    by_layer = {}
    for r in rules:
        by_layer.setdefault(r["layer"], []).append(r)
    sections = "".join(f"<h2>{e(LAYER_WORDS[l])} ({len(rs)})</h2><ul class=rules>" + "".join(f'<li><span class="status {SEVERITY[r["severity"]][1]}">{e(SEVERITY[r["severity"]][0])}</span><a href="{e(r["id"])}.html">{e(r["title"])}</a></li>' for r in rs) + "</ul>" for l, rs in by_layer.items())
    (out / "rules" / "index.html").write_text(page("Every rule Omtal checks", f"<h1>Every rule Omtal checks</h1><p class=lead>{len(rules)} rules in four layers, each with why it matters.</p>{sections}", path="rules/index.html", depth=1), encoding="utf-8")
    if a.sample:
        shutil.copy(a.sample, out / "sample" / "report.html")
    if (out / "sample" / "report.html").exists():
        body = ('<h1>A sample report</h1><p class=lead>Family Ping, Editerra\'s own app site, audited with no engine key: what a first run looks like. The report below is the file Omtal writes, unedited; open it on its own <a href="sample/report.html">here</a>.</p>'
                '<iframe src="sample/report.html" title="Omtal report" style="width:100%;height:80vh;border:1px solid var(--rule);background:#fff"></iframe>')
        (out / "sample-report.html").write_text(page("Sample report · Omtal", body, path="sample-report.html", description="A real Omtal report on a real site."), encoding="utf-8")
    ladder = "".join(f"<li><b>{e(k)}</b> {e(v)}</li>" for k, v in (("unreachable", "the machines that answer questions cannot read the site"), ("reachable", "they can read it, but what the product is has to be guessed"), ("understood", "the product is declared in a form machines read"), ("cited", "engines use the site as a source when answering"), ("recommended", "engines name the product for the questions it answers")))
    landing = f"""<h1>Seen by the machines that answer.</h1>
<p class=lead>Omtal reads your site the way a crawler does, derives the questions your product answers, asks the engines, and says on every finding what was found, why it matters and how it knows.</p>
<p><a class=cta href="sample-report.html">See a sample report</a> <a class="cta alt" href="https://github.com/petresandu-cloud/omtal">Install from GitHub</a></p>
<pre>pip install git+https://github.com/petresandu-cloud/omtal
omtal audit https://your-product.example      # writes omtal-out/&lt;host&gt;/report.html</pre>
<h2>The ladder</h2><ul class=ladder>{ladder}</ul>
<div class=grid3><div><b>Reads what the engines read</b>robots policy per crawler, sitemap, llms.txt, and every page's title, description, canonical, headings, structured data and text.</div>
<div><b>Asks, then counts</b>With your key it asks Brave, OpenAI or Anthropic the questions your product answers, stores every answer, and speaks in fractions: mentioned, cited, recommended.</div>
<div><b>Says how it knows</b>Every finding carries its provenance and why it matters. No composite score, no page generation, no promises about ranking.</div></div>
<h2>What it checks</h2><p>{len(rules)} rules in four layers: reach, understanding, content and evidence, and what the engines do. <a href="rules/index.html">The full list.</a></p>
<h2>What it costs</h2><p>The command line is free and complete, under the AGPL. Editerra AB offers <a href="https://github.com/petresandu-cloud/omtal/blob/main/COMMERCIAL-LICENSE.md">commercial terms</a>: the engines asked on your behalf over time, signed reports, and support.</p>
<h2>The sibling</h2><p><a href="https://editerra.se/okkok/">Okkok</a> checks a built app against the App Store and Google Play rules the same way: facts with provenance, a report with a contract.</p>"""
    (out / "index.html").write_text(page("Omtal", landing, path="", description="Omtal checks whether AI systems can find, understand, cite and recommend your product, and says how it knows.", ld=[{"@type": "WebSite", "url": SITE + "/", "name": "Omtal", "publisher": {"@id": "https://www.editerra.se/#org"}}]), encoding="utf-8")
    pages = ["", "rules/index.html", "sample-report.html"] + [f"rules/{r['id']}.html" for r in rules]
    today = datetime.date.today().isoformat()
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{e(SITE + '/' + p)}</loc><lastmod>{today}</lastmod></url>" for p in pages) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    (out / "llms.txt").write_text("# Omtal\n\n> Omtal checks whether AI systems can find, understand, cite and recommend a product. It reads the site the way a crawler does, derives the questions the product answers, asks the engines with the operator's key, stores every answer and counts. Open source (AGPL-3.0-or-later) by Editerra AB, Sweden. Command: `omtal audit <url>`.\n\n"
                                  f"- [Every rule]({SITE}/rules/index.html)\n- [Sample report]({SITE}/sample-report.html)\n- [Source](https://github.com/petresandu-cloud/omtal)\n- [Sibling product, Okkok](https://editerra.se/okkok/llms.txt)\n- [Editerra AB](https://www.editerra.se/llms.txt)\n\n## Rules\n\n" +
                                  "".join(f"- [{r['title']}]({SITE}/rules/{r['id']}.html): {SEVERITY[r['severity']][0]}, {LAYER_WORDS[r['layer']]}.\n" for r in rules), encoding="utf-8")
    print(f"site: {len(rules)} rule pages at {out}")


if __name__ == "__main__":
    main()
