#!/opt/alt/python311/bin/python3
# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The front door: a URL in, a report out. Runs as a CGI script on the Omtal site.

The report is returned inline, in the response to the visitor who asked for it.
Nothing is written to a public folder, so one visitor's report is never a page
another visitor can open, browse, or guess. A private cache keyed by the checked
site keeps a repeat check of the same public site fast; a "Run it again" link
(fresh=1) skips the cache.

Bounded on purpose: a small crawl budget, a wall-clock limit, a private cache per
site for an hour, and one run at a time per visitor address. No engine keys on
this host, so the observation layer stays open; the report says so. The report
body is exactly what the command line renders, wrapped only in a controls bar.
"""

import hashlib
import html
import os
import re
import signal
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = Path(os.environ.get("OMTAL_APP", str(Path.home() / "omtal-app")))
CACHE = Path(os.environ.get("OMTAL_CACHE", str(Path.home() / "omtal-cache")))
SITE = "https://editerra.se/omtal"
BUDGET = 12
SECONDS = 50
TTL = 3600
sys.path.insert(0, str(APP))


def out(status: str, body: str, ctype="text/html; charset=utf-8", extra=""):
    sys.stdout.write(f"Status: {status}\r\nContent-Type: {ctype}\r\n{extra}\r\n\r\n{body}")
    sys.stdout.flush()


def page(title, inner):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="robots" content="noindex"><style>body{{font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#141414;max-width:720px;margin:0 auto;padding:48px 24px}}
a{{color:#3A2E7A}} pre{{background:#f4f4f4;border:1px solid #cfcfcf;padding:12px}} .cta{{display:inline-block;background:#3A2E7A;color:#fff;padding:10px 16px;text-decoration:none;font-weight:600}}</style></head>
<body><p><a href="{SITE}/">← Omtal</a></p>{inner}</body></html>"""


def self_action() -> str:
    """This script's own address, for the form and the run-again link."""
    return os.environ.get("SCRIPT_URI") or ("https://" + os.environ.get("HTTP_HOST", "editerra.se") + os.environ.get("SCRIPT_NAME", "/cgi-bin/omtal-check.py"))


def controls(url: str) -> str:
    """A bar wrapped around the report: check another site, or run this one again."""
    action = self_action()
    again = action + "?url=" + urllib.parse.quote(url, safe="") + "&fresh=1"
    return (
        '<div style="font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:900px;margin:0 auto;padding:14px 24px;border-bottom:1px solid #cfcfcf;'
        'display:flex;gap:12px;flex-wrap:wrap;align-items:center;background:#fafafa">'
        f'<form action="{html.escape(action)}" method="get" style="display:flex;gap:8px;flex:1;min-width:260px;margin:0">'
        '<input name="url" type="url" inputmode="url" placeholder="https://another-site.example" required autocomplete="url" '
        'style="flex:1;min-width:200px;font:inherit;padding:8px 10px;border:1px solid #141414">'
        '<button type="submit" style="font:inherit;font-weight:600;background:#3A2E7A;color:#fff;border:0;padding:8px 14px;cursor:pointer">Check another site</button>'
        '</form>'
        f'<span style="font-size:14px;color:#5a5a5a"><a href="{html.escape(again)}" style="color:#3A2E7A">Run this one again</a> · '
        f'<a href="{SITE}/" style="color:#3A2E7A">Omtal</a></span></div>'
    )


def clean_url(raw: str) -> str | None:
    u = (raw or "").strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urllib.parse.urlsplit(u)
    host = p.hostname or ""
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", host, re.I) or host in ("localhost",) or re.match(r"^(\d+\.){3}\d+$", host):
        return None
    if host.endswith((".local", ".internal")) or host.startswith(("10.", "192.168.", "127.", "169.254.")) or host.startswith("172.") and 16 <= int(host.split(".")[1] or 0) <= 31:
        return None
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", "", ""))


def main():
    qs = urllib.parse.parse_qs(os.environ.get("QUERY_STRING", ""))
    url = clean_url((qs.get("url") or [""])[0])
    if not url:
        return out("400 Bad Request", page("Omtal", "<h1>That is not an address we can read</h1><p>Give a public web address such as <code>https://example.com</code>.</p>"))
    fresh = (qs.get("fresh") or [""])[0] in ("1", "true", "yes")
    slug = re.sub(r"[^a-z0-9.-]+", "_", (urllib.parse.urlsplit(url).netloc + urllib.parse.urlsplit(url).path.rstrip("/")).lower()).strip("_")[:120]
    work = CACHE / slug
    report = work / "report.html"          # private: under CACHE, never served as a file
    stamp = CACHE / f"{slug}.at"
    if not fresh and report.exists() and stamp.exists() and time.time() - float(stamp.read_text() or 0) < TTL:
        return out("200 OK", controls(url) + report.read_text(encoding="utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    ip = os.environ.get("REMOTE_ADDR", "0")
    lock = CACHE / ("lock-" + hashlib.sha256(ip.encode()).hexdigest()[:16])
    if lock.exists() and time.time() - lock.stat().st_mtime < SECONDS + 10:
        return out("429 Too Many Requests", page("Omtal", "<h1>One at a time</h1><p>A check from your address is still running. Give it a minute, then try again.</p>"))
    lock.write_text(str(time.time()))
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
        signal.alarm(SECONDS)
        from omtal import grid as grid_mod, intents as intents_mod, observe, report as report_mod
        from omtal.probes import entity, pages, site
        from omtal.schema import make_probe, write_json
        work.mkdir(parents=True, exist_ok=True)
        probes = site.probe(url)
        sm = next((p["value"] for p in probes if p["id"] == "site.sitemap"), None) or {}
        probes += pages.probe(url, sm.get("pages"), budget=BUDGET)
        pg = next(p["value"] for p in probes if p["id"] == "site.pages")
        probes += entity.probe(pg, url)
        g = next(p["value"] for p in probes if p["id"] == "product.graph")
        probes.append(make_probe("observations.summary", None, source_kind="file", source_ref="none", provenance="needs-engine-access",
                                 error="the hosted check asks no engine; run Omtal yourself with a key to fill this section"))
        write_json(work / "probes.json", probes)
        write_json(work / "intents.json", intents_mod.generate(g) if g else [])
        gd = grid_mod.build(work, probes)
        write_json(work / "grid.json", gd)
        report_mod.render(work / "grid.json", report, url)  # into the private work dir only
        signal.alarm(0)
        stamp.write_text(str(time.time()))
        return out("200 OK", controls(url) + report.read_text(encoding="utf-8"))
    except TimeoutError:
        return out("504 Gateway Timeout", page("Omtal", f"<h1>The site took too long to read</h1><p>{html.escape(url)} did not finish within {SECONDS} seconds at a {BUDGET}-page budget. Run Omtal yourself for a full crawl:</p><pre>pip install git+https://github.com/petresandu-cloud/omtal\nomtal audit {html.escape(url)}</pre>"))
    except Exception as e:  # noqa: BLE001
        return out("500 Internal Server Error", page("Omtal", f"<h1>The check failed</h1><p>{html.escape(type(e).__name__)}: {html.escape(str(e)[:300])}</p><p>Run Omtal yourself for the full trace: <code>omtal audit {html.escape(url)}</code>.</p>"))
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
