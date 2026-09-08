# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report. Generated only; REPORT-PRINCIPLES.md is the contract and the tests enforce it."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .schema import read_json

VERDICT_WORDS = {"FAIL": "Keeps machines out", "RISK": "Weakens understanding", "UNKNOWN": "Not checked yet", "PENDING": "Starts later",
                 "NOTE": "Worth knowing", "PASS": "In order", "RESOLVED": "Fixed and confirmed", "N/A": "Does not apply"}
STATUS_CLASS = {"FAIL": "s-fail", "RISK": "s-risk", "UNKNOWN": "s-open", "PENDING": "s-open", "NOTE": "s-note", "PASS": "s-met", "RESOLVED": "s-met", "N/A": "s-na"}
HOW_WE_KNOW = {"verified-directly": "fetched the pages and ran the queries directly", "sub-agent-reported": "a reviewer or model said so",
               "inferred": "inferred from what the pages say", "needs-engine-access": "needs an engine key to ask", "needs-owner-answer": "needs the product's owner to answer"}
LAYER_WORDS = {"access": "Reach", "entity": "Understanding", "content": "Content", "evidence": "Evidence", "observation": "What the engines do"}
STAGE_WORDS = {"unreachable": "unreachable: the machines that answer questions cannot read it", "reachable": "reachable, but not yet stated in a form machines understand",
               "understood": "understood: the product is declared in a form machines read", "cited": "cited: engines use the site as a source", "recommended": "recommended: engines name the product for its intents"}
MACHINE_WORDS = ("provenance", "probe", "sub-agent", "verified-directly", "needs-engine-access", "needs-owner-answer", "grid.json", "toml", "jsonl", "UNKNOWN", "PASS", "FAIL")
REPLACE = [("needs-engine-access", "needs an engine key"), ("needs-owner-answer", "needs the owner's answer"), ("verified-directly", "checked directly"), ("sub-agent-reported", "a reviewer said so"), ("probe", "fact")]
OMTAL_MARK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Omtal">'
              '<rect x="5" y="5" width="54" height="54" rx="12" fill="none" stroke="currentColor" stroke-width="6"/>'
              '<path d="M14 32 Q32 14 50 32 Q32 50 14 32 Z" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/>'
              '<circle cx="32" cy="32" r="6" fill="currentColor"/></svg>')


def plain(t: str) -> str:
    for a, b in REPLACE:
        t = t.replace(a, b)
    return t


def human_date(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return d.strftime("%A %-d %B %Y, %H:%M UTC")


def grid_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_texts(grid: dict, name: str) -> dict:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["status", "rule", "layer", "what we found", "why it matters", "how we know", "rule reference"])
    for r in grid["rows"]:
        w.writerow([VERDICT_WORDS[r["verdict"]], r["title"], LAYER_WORDS[r["layer"]], plain(r["evidence"]), r["why"], HOW_WE_KNOW[r["provenance"]], r["id"]])
    lines = [f"# AI Discoverability Check: {name}", "", f"Run on {human_date(grid['built_at'])}. Where it stands: {STAGE_WORDS[grid['stage']]}.", ""]
    for title, vs in (("What keeps machines out", ("FAIL",)), ("What weakens understanding", ("RISK",)), ("What is still to be checked", ("UNKNOWN", "PENDING")), ("Worth knowing", ("NOTE",))):
        items = [r for r in grid["rows"] if r["verdict"] in vs]
        lines += [f"## {title} ({len(items)})", ""] + [f"- **{r['title']}** ({LAYER_WORDS[r['layer']]}). {plain(r['evidence'])}" for r in items] + [""]
    met = [r for r in grid["rows"] if r["verdict"] in ("PASS", "RESOLVED")]
    lines += [f"## In order ({len(met)})", ""] + [f"- {r['title']}" for r in met] + [""]
    actions = [{"rule": r["id"], "title": r["title"], "status": VERDICT_WORDS[r["verdict"]], "layer": LAYER_WORDS[r["layer"]], "what_we_found": plain(r["evidence"]),
                "why_it_matters": r["why"], "how_we_know": HOW_WE_KNOW[r["provenance"]]} for r in grid["rows"] if r["verdict"] in ("FAIL", "RISK", "NOTE", "UNKNOWN", "PENDING")]
    doc = {"report": "AI Discoverability Check", "product": name, "run": grid["built_at"], "run_human": human_date(grid["built_at"]), "stage": grid["stage"], "actions": actions,
           "how_to_use": "Each entry says what was found and why it matters. Change the site, run the audit again; a finding is gone only when its check passes."}
    return {"findings.md": "\n".join(lines) + "\n", "findings.csv": out.getvalue(), "actions.json": json.dumps(doc, indent=2, ensure_ascii=False) + "\n"}


def render_text(grid_path: Path, name_hint: str = "") -> str:
    grid = read_json(grid_path)
    sc = grid_path.parent
    probes = read_json(sc / "probes.json") if (sc / "probes.json").exists() else []
    by = {p["id"]: p["value"] for p in probes}
    g = by.get("product.graph") or {}
    name = g.get("name") or name_hint or "the product"
    url = (by.get("site.home") or {}).get("final_url") or name_hint
    intents = read_json(sc / "intents.json") if (sc / "intents.json").exists() else []
    obs = by.get("observations.summary") or {}
    e = html.escape
    h = grid_hash(grid_path)
    exports = export_texts(grid, name)
    rows = grid["rows"]
    blocks = [r for r in rows if r["verdict"] == "FAIL"]
    risks = [r for r in rows if r["verdict"] == "RISK"]
    opens = [r for r in rows if r["verdict"] in ("UNKNOWN", "PENDING")]
    notes = [r for r in rows if r["verdict"] == "NOTE"]
    met = [r for r in rows if r["verdict"] in ("PASS", "RESOLVED")]

    def sclass(r):
        return STATUS_CLASS[r["verdict"]]

    def finding(r, n=None):
        num = f"{n}. " if n else ""
        return (f"<li class={sclass(r)}><p class=head><span class=\"status {sclass(r)}\">{e(VERDICT_WORDS[r['verdict']])}</span>{num}<b>{e(r['title'])}</b> <span class=tag>{e(LAYER_WORDS[r['layer']])}</span></p>"
                f"<p><span class=lbl>What we found</span> {e(plain(r['evidence']))}</p>"
                f"<p class=why><span class=lbl>Why it matters</span> {e(r['why'])}</p>"
                f"<p class=small>How we know: {e(HOW_WE_KNOW[r['provenance']])}. Rule reference: {e(r['id'])}.</p></li>")

    def h2(title, cls):
        return f"<h2><span class=\"sw {cls}\"></span>{e(title)}</h2>"

    def section(title, items, cls, numbered=True):
        if not items:
            return f"{h2(title, cls)}<p class=none>None.</p>"
        tag = "ol" if numbered else "ul"
        return f"{h2(title, cls)}<{tag} class=findings>" + "".join(finding(r, i + 1 if numbered else None) for i, r in enumerate(items)) + f"</{tag}>"

    groups = [("With an engine key", [r for r in opens if r["provenance"] == "needs-engine-access"]),
              ("By the product's owner or a reader", [r for r in opens if r["provenance"] in ("needs-owner-answer", "sub-agent-reported")]),
              ("Other", [r for r in opens if r["provenance"] not in ("needs-engine-access", "needs-owner-answer", "sub-agent-reported")])]
    open_html = "".join(f"<h3>{e(t)} ({len(v)})</h3><ul class=findings>" + "".join(finding(r) for r in v) + "</ul>" for t, v in groups if v) or "<p class=none>None.</p>"
    met_html = "<details><summary>" + f"{len(met)} checks. Show them.</summary><ul class=plainlist>" + "".join(f"<li class=s-met><b>{e(r['title'])}</b><br><span class=small>{e(plain(r['evidence']))}</span></li>" for r in met) + "</ul></details>" if met else "<p class=none>None.</p>"

    obs_html = ""
    if obs:
        rows_html = "".join(f"<tr><td>{e(eng)}</td><td>{b['asked'] - b['failed']}</td><td>{b['mentioned']}</td><td>{b['cited']}</td><td>{b['recommended']}</td><td>{e(', '.join(d for d, _ in b['domains'][:5]))}</td></tr>" for eng, b in obs.items())
        obs_html = f"<table class=obs><tr><th>Engine</th><th>Answers</th><th>Mentioned us</th><th>Cited the site</th><th>Recommended</th><th>Sources cited most</th></tr>{rows_html}</table>"
    else:
        obs_html = "<p class=none>No engine was asked. Set an engine key and run the observe step; every answer is stored and counted, never summarised from memory.</p>"
    intents_html = ("<details><summary>" + f"{len(intents)} questions derived from the site. Show them.</summary><ul class=plainlist>" +
                    "".join(f"<li>{e(i['question'])} <span class=tag>{e(i['family'])}</span></li>" for i in intents[:60]) + "</ul></details>") if intents else "<p class=none>No intents yet.</p>"
    generator = f"Omtal {__version__} (Editerra AB, AGPL-3.0-or-later)"

    page = f"""<meta charset="utf-8">
<meta name="generator" content="{e(generator)}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="omtal-grid-sha256" content="{h}">
<title>AI Discoverability Check: {e(name)}</title>
<style>
:root{{--ink:#141414;--muted:#5a5a5a;--rule:#cfcfcf;--accent:#3A2E7A;--paper:#fff;--c-fail:#a11c1c;--c-risk:#a35d00;--c-open:#2f5f9e;--c-note:#5a5a5a;--c-met:#1d6b3b;--c-na:#8a8a8a}}
body{{font:16px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--paper);max-width:900px;margin:0 auto;padding:40px 24px}}
header{{border-bottom:3px solid var(--ink);padding-bottom:16px;margin-bottom:24px}} .eyebrow{{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0}}
h1{{font-size:40px;line-height:1.1;margin:4px 0 0;letter-spacing:-.5px}} .when{{color:var(--muted);margin:6px 0 0}} .standing{{margin:10px 0 0}}
h2{{font-size:19px;margin:36px 0 10px;padding-top:8px;border-top:1px solid var(--rule)}} h3{{font-size:16px;margin:20px 0 6px}}
.glance{{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--ink);margin-top:18px}}
.glance div{{padding:10px 12px;border-right:1px solid var(--rule);border-top:6px solid var(--muted)}} .glance div:last-child{{border-right:0}} .glance b{{display:block;font-size:26px}} .glance span{{font-size:13px;color:var(--muted)}}
.glance .s-fail{{border-top-color:var(--c-fail)}} .glance .s-fail b{{color:var(--c-fail)}} .glance .s-risk{{border-top-color:var(--c-risk)}} .glance .s-risk b{{color:var(--c-risk)}} .glance .s-open{{border-top-color:var(--c-open)}} .glance .s-open b{{color:var(--c-open)}} .glance .s-met{{border-top-color:var(--c-met)}} .glance .s-met b{{color:var(--c-met)}}
ol.findings,ul.findings{{padding-left:0;margin:0;list-style:none}} .findings li{{padding:12px 0 14px 14px;border-bottom:1px solid var(--rule);border-left:5px solid var(--muted)}}
.findings li.s-fail{{border-left-color:var(--c-fail)}} .findings li.s-risk{{border-left-color:var(--c-risk)}} .findings li.s-open{{border-left-color:var(--c-open)}} .findings li.s-note{{border-left-color:var(--c-note)}} .findings li.s-met{{border-left-color:var(--c-met)}}
.status{{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;padding:2px 8px;margin-right:8px;color:#fff;background:var(--muted);vertical-align:middle}}
.status.s-fail{{background:var(--c-fail)}} .status.s-risk{{background:var(--c-risk)}} .status.s-open{{background:var(--c-open)}} .status.s-note{{background:var(--c-note)}} .status.s-met{{background:var(--c-met)}}
h2 .sw{{display:inline-block;width:14px;height:14px;margin-right:10px;vertical-align:-1px;background:var(--muted)}} h2 .sw.s-fail{{background:var(--c-fail)}} h2 .sw.s-risk{{background:var(--c-risk)}} h2 .sw.s-open{{background:var(--c-open)}} h2 .sw.s-note{{background:var(--c-note)}} h2 .sw.s-met{{background:var(--c-met)}} h2 .sw.s-obs{{background:var(--accent)}}
.findings p{{margin:4px 0}} .head{{font-size:17px}} .lbl{{display:inline-block;min-width:8.5em;color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
.why{{border-left:3px solid var(--accent);padding-left:10px}} .tag{{font-size:12px;border:1px solid var(--rule);padding:1px 6px;margin-left:6px;color:var(--muted);vertical-align:middle}}
.small{{font-size:13px;color:var(--muted)}} .none{{color:var(--muted)}} ul.plainlist{{padding-left:18px}} ul.plainlist li{{margin:6px 0}} ul.plainlist li.s-met{{border-left:3px solid var(--c-met);padding-left:8px;list-style:none}} details summary{{cursor:pointer;color:var(--accent)}}
table.obs{{border-collapse:collapse;width:100%;font-size:14px}} .obs th,.obs td{{border:1px solid var(--rule);padding:6px 8px;text-align:left;vertical-align:top}} .obs th{{background:#f4f4f4}}
.exports button{{display:inline-block;margin:0 10px 8px 0;padding:6px 12px;border:1px solid var(--ink);background:#fff;color:var(--ink);font:inherit;cursor:pointer}}
.export-panel{{margin-top:12px;border:1px solid var(--rule);padding:10px 12px}} .export-panel textarea{{width:100%;height:220px;font:13px ui-monospace,Menlo,Consolas,monospace;border:1px solid var(--rule);padding:8px;box-sizing:border-box}} textarea[hidden]{{display:none}}
.made{{display:flex;align-items:center;gap:10px}} .made .mark svg{{width:20px;height:20px;display:block}}
footer{{margin-top:36px;padding-top:12px;border-top:3px solid var(--ink);font-size:14px;color:var(--muted)}}
@media print{{*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} body{{padding:0;max-width:none}} details{{display:block}} details summary{{display:none}} .exports,.export-panel{{display:none}}}}
</style>
<header>
<p class=eyebrow>AI Discoverability Check</p>
<h1>{e(name)}</h1>
<p class=when>Run on {e(human_date(grid['built_at']))}. Site: {e(url or '')}.</p>
<p class=standing>Where it stands. {e(STAGE_WORDS[grid['stage']].capitalize())}.</p>
<div class=glance>
<div class=s-fail><b>{len(blocks)}</b><span>keep machines out</span></div>
<div class=s-risk><b>{len(risks)}</b><span>weaken understanding</span></div>
<div class=s-open><b>{len(opens)}</b><span>still to be checked</span></div>
<div class=s-met><b>{len(met)}</b><span>in order</span></div>
</div>
<p class=exports style="margin-top:14px"><button onclick="exportFile('findings.md','text/markdown')">Download as Markdown</button><button onclick="exportFile('findings.csv','text/csv')">Download as CSV</button><button onclick="exportFile('actions.json','application/json')">Download actions (JSON, for a program)</button><button onclick="window.print()">Print or save as PDF</button></p>
<div id=export-panel class=export-panel hidden><p><b id=export-name></b> <span class=small>If no file appeared, copy the text below.</span></p><p class=exports><button onclick="copyExport()">Copy to clipboard</button><button onclick="document.getElementById('export-panel').hidden=true">Close</button> <span id=export-status class=small></span></p><textarea id=export-text readonly spellcheck=false></textarea></div>
</header>
<textarea id="x-findings.md" hidden>{e(exports['findings.md'])}</textarea>
<textarea id="x-findings.csv" hidden>{e(exports['findings.csv'])}</textarea>
<textarea id="x-actions.json" hidden>{e(exports['actions.json'])}</textarea>
<script>
function exportFile(name, type) {{
  var text = document.getElementById('x-' + name).value, status = document.getElementById('export-status');
  document.getElementById('export-name').textContent = name; status.textContent = '';
  var ta = document.getElementById('export-text'); ta.value = text; document.getElementById('export-panel').hidden = false; ta.focus(); ta.select();
  var plainSave = function () {{ try {{ var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {{type: type + ';charset=utf-8'}})); a.download = name; document.body.appendChild(a); a.click(); a.remove(); }} catch (err) {{}} }};
  if (window.claude && typeof window.claude.use === 'function') {{ window.claude.use('downloads').then(function (dl) {{ if (!dl) {{ plainSave(); return; }} dl.save({{filename: name, data: text}}).then(function () {{ status.textContent = 'Saved.'; }}, function (err) {{ status.textContent = err && err.code === 'declined' ? 'Not saved.' : 'Could not save here; copy the text instead.'; }}); }}, plainSave); }} else plainSave();
}}
function copyExport() {{ var ta = document.getElementById('export-text'); ta.select(); var done = function () {{ document.getElementById('export-status').textContent = 'Copied.'; }}; if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(ta.value).then(done, function () {{ document.execCommand('copy'); done(); }}); else {{ document.execCommand('copy'); done(); }} }}
</script>
{section("1. What keeps machines out", blocks, "s-fail")}
{section("2. What weakens understanding", risks, "s-risk")}
{h2("3. What is still to be checked", "s-open")}
{open_html}
{section("4. Worth knowing", notes, "s-note", numbered=False)}
{h2("5. What the engines did with the questions", "s-obs")}
{obs_html}
<h3>The questions</h3>
{intents_html}
{h2("6. What is in order", "s-met")}
{met_html}
<footer>
<p><b>Method.</b> The site was read the way a crawler reads it: robots policy, sitemap, llms.txt, then a bounded crawl of {(by.get('site.pages') or {}).get('crawled', 0)} pages. The product graph is what the pages declare in structured data, kept apart from what their headings suggest. Questions were derived from that graph. Engines are asked only with keys the operator gives, through documented interfaces, and every answer is stored before it is counted.</p>
<p><b>How we know</b>, on every finding: {e(HOW_WE_KNOW['verified-directly'])} · {e(HOW_WE_KNOW['sub-agent-reported'])} · {e(HOW_WE_KNOW['inferred'])} · {e(HOW_WE_KNOW['needs-engine-access'])} · {e(HOW_WE_KNOW['needs-owner-answer'])}.</p>
<p>This page is generated from the run's data and carries its fingerprint; editing it by hand is detected.</p>
<p class=made><span class=mark aria-hidden=true>{OMTAL_MARK}</span> Made with Omtal, the AI discoverability check by Editerra AB. Open source under the AGPL; Omtal and its mark are trademarks of Editerra AB.</p>
</footer>
"""
    return page


def render(grid_path: Path, out_path: Path, name_hint: str = "") -> None:
    out_path.write_text(render_text(grid_path, name_hint), encoding="utf-8")
    grid = read_json(grid_path)
    for fname, text in export_texts(grid, name_hint or "the product").items():
        (grid_path.parent / fname).write_text(text, encoding="utf-8")


def check_render(grid_path: Path, html_path: Path, name_hint: str = "") -> str | None:
    if not html_path.exists():
        return f"{html_path.name} does not exist; run render"
    if html_path.read_text(encoding="utf-8") != render_text(grid_path, name_hint):
        return f"{html_path.name} is not what render produces from the current {grid_path.name}: run render, do not edit the page"
    return None
