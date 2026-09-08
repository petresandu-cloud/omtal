# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The crawl: a bounded walk of the site, recording what each page says.

Starts from the sitemap when there is one, else from the home page's links.
Stays on the host. Stops at a page budget. Records per page what a crawler and
an answer engine would read: title, description, canonical, headings, JSON-LD
types, word count, links, and the visible text (capped) for the entity pass.
"""

from __future__ import annotations

import urllib.parse

from ..schema import make_probe
from .. import web

DEFAULT_BUDGET = 40
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js", ".xml", ".txt", ".ico", ".json")


def _ok_link(u: str, base: str) -> bool:
    if not u.startswith(base):
        return False
    path = urllib.parse.urlsplit(u).path.lower()
    return not path.endswith(SKIP_EXT)


def probe(url: str, sitemap_pages: list[str] | None = None, budget: int = DEFAULT_BUDGET) -> list[dict]:
    base = web.origin(url)
    section = urllib.parse.urlsplit(url).path.rstrip("/")
    scope = base + section  # a site living under a path (example.com/product/) is crawled within that path
    seeds = [p for p in (sitemap_pages or []) if p.startswith(scope)] or []
    queue = [url] + [s for s in seeds if s.rstrip("/") != url.rstrip("/")]
    seen, pages, errors = set(), [], []
    while queue and len(pages) < budget:
        u = queue.pop(0)
        key = u.split("#", 1)[0].rstrip("/")
        if key in seen or not _ok_link(u, scope):
            continue
        seen.add(key)
        r = web.fetch(u)
        if r["status"] != 200 or "html" not in r["content_type"]:
            errors.append({"url": u, "status": r["status"], "error": r["error"]})
            continue
        pg = web.read_page(r["text"], r["final_url"])
        pg["status"] = r["status"]
        pg["bytes"] = r["bytes"]
        pg["text"] = pg["text"][:6000]
        pages.append(pg)
        for link in pg["internal_links"]:
            if link.split("#", 1)[0].rstrip("/") not in seen and _ok_link(link, scope):
                queue.append(link)
    return [make_probe("site.pages", {"scope": scope, "budget": budget, "crawled": len(pages), "queued_unvisited": len([q for q in queue if q.rstrip("/") not in seen]),
                                      "pages": pages, "errors": errors},
                       source_kind="url", source_ref=scope)]


def self_test() -> None:
    assert _ok_link("https://x/a/b.html", "https://x") and not _ok_link("https://x/a.png", "https://x") and not _ok_link("https://y/", "https://x")
