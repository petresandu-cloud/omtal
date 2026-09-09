# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Facts about the site as a whole: can machines reach it, and what map did it publish?

Facts only. The robots verdict per bot, the sitemap and what it lists, llms.txt,
the home page's response. Each is a probe with its own provenance.
"""

from __future__ import annotations

import urllib.parse

from ..schema import make_probe
from .. import web


def probe(url: str, pre_deploy: bool = False) -> list[dict]:
    base = web.origin(url)
    out = []

    r = web.fetch(base + "/robots.txt")
    if r["status"] == 200 and r["text"].strip():
        parsed = web.parse_robots(r["text"])
        bots = {b: web.bot_access(parsed, b) for b in web.BOTS}
        out.append(make_probe("site.robots", {"present": True, "bots": bots, "sitemaps": parsed["sitemaps"], "bytes": r["bytes"],
                                              "ua_group_counts": parsed["ua_group_counts"], "raw_groups": parsed["raw_groups"]},
                              source_kind="url", source_ref=base + "/robots.txt"))
    elif r["status"] == 404:
        out.append(make_probe("site.robots", {"present": False, "bots": {b: "allowed" for b in web.BOTS}, "sitemaps": [], "bytes": 0},
                              source_kind="url", source_ref=base + "/robots.txt"))
    else:
        out.append(make_probe("site.robots", None, source_kind="url", source_ref=base + "/robots.txt", error=r["error"] or f"HTTP {r['status']}"))

    sm_urls = list((out[-1]["value"] or {}).get("sitemaps") or []) or [base + "/sitemap.xml"]
    if pre_deploy:  # the Sitemap: line names the production host; follow it against the build being audited
        sm_urls = [web.remap_to_base(u, base) for u in sm_urls]
    pages, seen, tried = [], set(), []
    queue = list(sm_urls)
    while queue and len(tried) < 20:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        s = web.fetch(u)
        tried.append({"url": u, "status": s["status"]})
        if s["status"] == 200 and ("<urlset" in s["text"] or "<sitemapindex" in s["text"]):
            p, kids = web.sitemap_urls(s["text"])
            if pre_deploy:  # entries name the production host; the build serves them at the local base
                p = [web.remap_to_base(x, base) for x in p]
                kids = [web.remap_to_base(x, base) for x in kids]
            pages += p
            queue += kids
    if pages or any(t["status"] == 200 for t in tried):
        out.append(make_probe("site.sitemap", {"present": True, "sitemaps": tried, "pages": sorted(set(pages))[:2000], "count": len(set(pages))},
                              source_kind="url", source_ref=", ".join(t["url"] for t in tried)))
    else:
        out.append(make_probe("site.sitemap", {"present": False, "sitemaps": tried, "pages": [], "count": 0},
                              source_kind="url", source_ref=", ".join(t["url"] for t in tried) or base + "/sitemap.xml"))

    for path in (urllib.parse.urlsplit(url).path.rstrip("/") + "/llms.txt", "/llms.txt"):
        l = web.fetch(base + path)
        if l["status"] == 200 and l["text"].lstrip().startswith("#"):
            out.append(make_probe("site.llms", {"present": True, "url": base + path, "bytes": l["bytes"], "text": l["text"][:8000]},
                                  source_kind="url", source_ref=base + path))
            break
    else:
        out.append(make_probe("site.llms", {"present": False, "url": None, "bytes": 0, "text": ""}, source_kind="url", source_ref=base + "/llms.txt"))

    h = web.fetch(url)
    out.append(make_probe("site.home", {"status": h["status"], "final_url": h["final_url"], "content_type": h["content_type"], "https": h["final_url"].startswith("https://"),
                                        "redirected": h["final_url"].rstrip("/") != url.rstrip("/"),
                                        "cdn": web.detect_cdn(h.get("headers") or {}), "headers": h.get("headers") or {},
                                        "pre_deploy": pre_deploy, "local": web.is_local_host(url)},
                          source_kind="url", source_ref=url, error=h["error"]) if h["status"] else
               make_probe("site.home", None, source_kind="url", source_ref=url, error=h["error"] or "no response"))
    return out


def self_test() -> None:
    assert web.bot_access(web.parse_robots(""), "Bingbot") == "allowed"
