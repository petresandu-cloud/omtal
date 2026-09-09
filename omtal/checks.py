# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The mechanical checks. Each takes the facts and returns (verdict, evidence, provenance).

The one rule of this file: a FAIL or RISK rests on something observed. Input not
given is a gap (UNKNOWN naming what to add); a scan that admits it may miss is a
doubt (RISK at most); only text that was read and is wrong blocks.
"""

from __future__ import annotations

import re
import urllib.parse

from . import web


class Facts:
    def __init__(self, probes: list[dict]):
        self.by = {p["id"]: p for p in probes}

    def val(self, pid: str):
        p = self.by.get(pid)
        return p["value"] if p else None

    def missing(self, *pids: str):
        for pid in pids:
            p = self.by.get(pid)
            if p is None:
                return ("UNKNOWN", f"no fact {pid}: the probe did not run", "verified-directly")
            if p["value"] is None:
                return ("UNKNOWN", f"no fact {pid}: {p.get('error', 'not available')}", p["provenance"])
        return None


# ----------------------------------------------------------------- access

def home_answers(f: Facts):
    if m := f.missing("site.home"):
        return ("FAIL", f"the home page could not be fetched: {m[1]}", "verified-directly")
    h = f.val("site.home")
    pre_deploy = h.get("pre_deploy")
    problems = []
    if h["status"] != 200:
        problems.append(f"HTTP {h['status']}")
    if "html" not in (h["content_type"] or ""):
        problems.append(f"content type {h['content_type'] or 'unknown'}, not HTML")
    https_note = ""
    if not h["https"]:
        if pre_deploy:  # a local build has no TLS; the live host does, so this is not the build's failing
            https_note = "; HTTPS not applicable to this pre-deploy build (the live host serves HTTPS)"
        else:
            problems.append("served over plain HTTP")
    if problems:
        return ("FAIL", "; ".join(problems), "verified-directly")
    how = "as HTML over HTTPS" if h["https"] else "as HTML"
    return ("PASS", f"{h['final_url']} answers 200 {how}" + (" after a redirect" if h["redirected"] else "") + https_note, "verified-directly")


def robots_admits(f: Facts):
    if m := f.missing("site.robots"):
        return m
    r = f.val("site.robots")
    if not r["present"]:
        return ("PASS", "no robots.txt, so every crawler is admitted by default (see the separate rule about stating a policy)", "verified-directly")
    blocked = [b for b, s in r["bots"].items() if s == "blocked"]
    limited = [b for b, s in r["bots"].items() if s == "limited"]
    search_blocked = [b for b in blocked if b in ("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot", "Googlebot", "Bingbot", "ChatGPT-User")]
    if search_blocked:
        return ("FAIL", "robots.txt blocks crawlers that produce answers and citations: " + ", ".join(f"{b} ({web.BOTS[b]})" for b in search_blocked) + "; the product cannot appear on those engines", "verified-directly")
    if blocked:
        return ("NOTE", "robots.txt blocks training crawlers only: " + ", ".join(blocked) + ". Search and answer crawlers are admitted; that is a legitimate choice with no cost to discoverability", "verified-directly")
    if limited:
        return ("PASS", "every crawler is admitted; some paths are held back from " + ", ".join(limited), "verified-directly")
    return ("PASS", "robots.txt admits " + ", ".join(r["bots"]), "verified-directly")


def robots_present(f: Facts):
    if m := f.missing("site.robots"):
        return m
    r = f.val("site.robots")
    if not r["present"]:
        return ("RISK", "no robots.txt: crawlers assume permission, but OpenAI, Google and Bing ask for an explicit policy, and there is nowhere to name the sitemap", "verified-directly")
    if not r["sitemaps"]:
        return ("RISK", "robots.txt exists but names no sitemap", "verified-directly")
    return ("PASS", "robots.txt present, naming " + ", ".join(r["sitemaps"]), "verified-directly")


def sitemap_present(f: Facts):
    if m := f.missing("site.sitemap"):
        return m
    s = f.val("site.sitemap")
    if not s["present"]:
        return ("RISK", "no sitemap at the addresses tried: " + ", ".join(t["url"] for t in s["sitemaps"]), "verified-directly")
    if s["count"] == 0:
        return ("RISK", "a sitemap exists but lists no pages", "verified-directly")
    return ("PASS", f"sitemap lists {s['count']} pages", "verified-directly")


def llms_present(f: Facts):
    if m := f.missing("site.llms"):
        return m
    l = f.val("site.llms")
    if not l["present"]:
        return ("NOTE", "no llms.txt; a short plain-text summary of the product for language models is the cheapest page to add", "verified-directly")
    return ("PASS", f"llms.txt present at {l['url']}, {l['bytes']} bytes", "verified-directly")


def pages_crawlable(f: Facts):
    if m := f.missing("site.pages"):
        return m
    p = f.val("site.pages")
    errs = p["errors"]
    noindex = [pg["url"] for pg in p["pages"] if "noindex" in (pg.get("robots_meta") or "").lower()]
    if p["crawled"] == 0:
        return ("FAIL", "no page could be read within the site", "verified-directly")
    problems = []
    if errs:
        problems.append(f"{len(errs)} linked or listed pages failed: " + "; ".join(f"{e['url']} ({e['error'] or e['status']})" for e in errs[:5]))
    if noindex:
        problems.append(f"{len(noindex)} pages carry a noindex meta tag: " + ", ".join(noindex[:5]))
    if problems:
        return ("RISK", f"{p['crawled']} pages read; " + "; ".join(problems), "verified-directly")
    return ("PASS", f"{p['crawled']} pages read without error" + (f"; {p['queued_unvisited']} more were linked but beyond the crawl budget" if p["queued_unvisited"] else ""), "verified-directly")


def cdn_delivery(f: Facts):
    if m := f.missing("site.home"):
        return m
    h = f.val("site.home")
    cdn = h.get("cdn")
    pages = _pages(f)
    arts = web.cdn_artifacts(pages)
    if not cdn and not arts:
        return ("PASS", "no CDN or edge rewriting detected in front of the origin; the crawler reads what the server sends", "verified-directly")
    lead = f"{cdn} sits in front of the origin, so a crawler reads the edge's version of each page, not the server's" if cdn else "an edge rewrites some pages between the server and the crawler"
    if not arts:
        return ("PASS", lead + "; no rewrites were found that hurt discoverability", "verified-directly")
    detail = "; ".join(f"{a['detail']} Fix: {a['fix']} (seen on {a['where']})" for a in arts)
    return ("NOTE", lead + ". Recognised edge rewrite: " + detail, "verified-directly")


def robots_one_group_per_bot(f: Facts):
    if m := f.missing("site.robots"):
        return m
    r = f.val("site.robots")
    if not r["present"]:
        return ("PASS", "no robots.txt, so there are no groups to conflict", "verified-directly")
    counts = r.get("ua_group_counts") or {}
    watch = {"*"} | {b.lower() for b in web.BOTS}
    dup = sorted(ua for ua, n in counts.items() if n >= 2 and ua in watch)
    if not dup:
        return ("PASS", "each user-agent is named by at most one group; every crawler reads a single set of rules", "verified-directly")
    raw = r.get("raw_groups") or []
    parts = []
    for ua in dup:
        naming = [g for g in raw if ua in g.get("uas", [])]
        missed = [f"{k} {v}" for g in naming[1:] for k, v in g.get("rules", []) if k == "disallow"]
        seg = f"'{ua}' is named by {counts[ua]} separate groups"
        if missed:
            seg += "; a crawler that honours only the first would ignore: " + ", ".join(dict.fromkeys(missed))
        parts.append(seg)
    return ("NOTE", "robots.txt repeats a user-agent across groups (often a CDN prepending its own block). Lenient crawlers merge them; a strict one applies only the first matching group. " + "; ".join(parts), "verified-directly")


# ----------------------------------------------------------------- entity

def organization_declared(f: Facts):
    if m := f.missing("product.graph"):
        return m
    g = f.val("product.graph")
    o = g["declared"]["organization"]
    if not o:
        return ("RISK", "no Organization (or LocalBusiness) node in any page's JSON-LD; the maker is not an entity to the engines", "verified-directly")
    missing = [k for k in ("name", "url") if not o.get(k)]
    if missing:
        return ("RISK", f"Organization declared on {o['declared_on']} without " + ", ".join(missing), "verified-directly")
    return ("PASS", f"Organization '{o['name']}' declared on {o['declared_on']}" + (" with identifier" if o.get("identifier") else "") + (" and sameAs links" if o.get("sameAs") else ""), "verified-directly")


def product_declared(f: Facts):
    if m := f.missing("product.graph"):
        return m
    g = f.val("product.graph")
    ps = g["declared"]["products"]
    if not ps:
        return ("FAIL", "no Product, SoftwareApplication, MobileApplication or Service node in any crawled page's JSON-LD; what the product is has to be guessed from prose", "verified-directly")
    p = ps[0]
    gaps = [k for k in ("name", "description") if not p.get(k)]
    if gaps:
        return ("RISK", f"{p['types'][0]} declared on {p['declared_on']} without " + ", ".join(gaps), "verified-directly")
    return ("PASS", f"{p['types'][0]} '{p['name']}' declared on {p['declared_on']} with a description" + (f", {len(p['features'])} features" if p.get("features") else "") + (", an offer" if p.get("offers") else ""), "verified-directly")


def name_consistent(f: Facts):
    if m := f.missing("product.graph"):
        return m
    g = f.val("product.graph")
    if not g.get("name"):
        return ("UNKNOWN", "no product name could be determined from structured data, og:site_name or titles", "inferred")
    n, total = g["pages_naming_the_product"], g["pages"]
    if total and n / total < 0.6:
        return ("RISK", f"'{g['name']}' appears in the title or description of only {n} of {total} crawled pages", "verified-directly")
    return ("PASS", f"'{g['name']}' appears in the title or description of {n} of {total} crawled pages", "verified-directly")


def _pages(f: Facts):
    return (f.val("site.pages") or {}).get("pages", [])


def canonical_everywhere(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    without = [pg["url"] for pg in pages if not pg.get("canonical")]
    if without:
        return ("RISK", f"{len(without)} of {len(pages)} pages have no canonical link: " + ", ".join(without[:5]), "verified-directly")
    return ("PASS", f"all {len(pages)} crawled pages carry a canonical link", "verified-directly")


def titles_descriptions(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    no_title = [pg["url"] for pg in pages if len((pg.get("title") or "").strip()) < 8]
    no_desc = [pg["url"] for pg in pages if len((pg.get("description") or "").strip()) < 40]
    titles = {}
    for pg in pages:
        titles.setdefault((pg.get("title") or "").strip().lower(), []).append(pg["url"])
    dup = [urls for t, urls in titles.items() if t and len(urls) > 1]
    problems = []
    if no_title:
        problems.append(f"{len(no_title)} pages with no usable title: " + ", ".join(no_title[:4]))
    if no_desc:
        problems.append(f"{len(no_desc)} pages with no description of 40 characters or more: " + ", ".join(no_desc[:4]))
    if dup:
        problems.append(f"{len(dup)} titles shared by several pages, e.g. " + ", ".join(dup[0][:3]))
    if problems:
        return ("RISK", "; ".join(problems), "verified-directly")
    return ("PASS", f"all {len(pages)} crawled pages have a distinct title and a description", "verified-directly")


def one_h1(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    bad = [(pg["url"], len(pg.get("h1") or [])) for pg in pages if len(pg.get("h1") or []) != 1]
    if bad:
        return ("NOTE", f"{len(bad)} of {len(pages)} pages do not have exactly one h1: " + ", ".join(f"{u} ({n})" for u, n in bad[:5]), "verified-directly")
    return ("PASS", f"all {len(pages)} crawled pages have one h1", "verified-directly")


def language_declared(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    bad = [pg["url"] for pg in pages if not pg.get("lang")]
    if bad:
        return ("NOTE", f"{len(bad)} of {len(pages)} pages declare no language: " + ", ".join(bad[:5]), "verified-directly")
    return ("PASS", "every crawled page declares its language: " + ", ".join(sorted({pg['lang'] for pg in pages})), "verified-directly")


def same_as(f: Facts):
    if m := f.missing("product.graph"):
        return m
    o = f.val("product.graph")["declared"]["organization"]
    if not o:
        return ("NOTE", "no Organization node, so no sameAs links", "verified-directly")
    if not o.get("sameAs"):
        return ("NOTE", "the Organization node has no sameAs links to the app stores, GitHub, LinkedIn or Wikidata", "verified-directly")
    return ("PASS", f"sameAs links present: {len(o['sameAs']) if isinstance(o['sameAs'], list) else 1}", "verified-directly")


# ----------------------------------------------------------------- content

def capabilities_have_pages(f: Facts):
    if m := f.missing("product.graph", "site.pages"):
        return m
    g = f.val("product.graph")
    pages = _pages(f)
    caps = []
    for p in g["declared"]["products"]:
        caps += [c for c in (p.get("features") or []) if isinstance(c, str)]
    if not caps:
        return ("UNKNOWN", "no featureList in the product's structured data, so there is no declared list of capabilities to look for; add one, or the check has nothing to compare against", "verified-directly")
    heads = [(pg["url"], t.lower()) for pg in pages for _, t in pg.get("headings", [])]
    texts = [(pg["url"], (pg.get("text") or "").lower()) for pg in pages]
    covered, uncovered = [], []
    for c in caps:
        words = [w for w in re.findall(r"[a-z]{4,}", c.lower())][:3]
        hit = any(all(w in h for w in words) for _, h in heads) if words else False
        weak = any(all(w in t for w in words) for _, t in texts) if words else False
        (covered if hit else uncovered).append((c, weak))
    if uncovered:
        return ("RISK", f"{len(covered)} of {len(caps)} declared capabilities have a heading of their own; without one: " + "; ".join(f"'{c}'" + (" (mentioned in text only)" if w else " (not found in any crawled text)") for c, w in uncovered[:6]), "verified-directly")
    return ("PASS", f"each of the {len(caps)} declared capabilities has a page or a section with a heading", "verified-directly")


def enough_text(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    thin = [(pg["url"], pg.get("words", 0)) for pg in pages if pg.get("words", 0) < 120]
    if len(thin) > len(pages) / 2:
        return ("RISK", f"{len(thin)} of {len(pages)} pages carry fewer than 120 words: " + ", ".join(f"{u} ({w})" for u, w in thin[:5]), "verified-directly")
    if thin:
        return ("NOTE", f"{len(thin)} of {len(pages)} pages are thin (under 120 words): " + ", ".join(f"{u} ({w})" for u, w in thin[:5]), "verified-directly")
    return ("PASS", f"every crawled page carries at least 120 words; {sum(pg.get('words', 0) for pg in pages)} words in all", "verified-directly")


def images_described(f: Facts):
    if m := f.missing("site.pages"):
        return m
    pages = _pages(f)
    total = sum(pg.get("images", 0) for pg in pages)
    bare = sum(pg.get("images_without_alt", 0) for pg in pages)
    if total == 0:
        return ("PASS", "no images on the crawled pages", "verified-directly")
    if bare:
        return ("NOTE", f"{bare} of {total} images have no alt text", "verified-directly")
    return ("PASS", f"all {total} images carry alt text", "verified-directly")


def audience_stated(f: Facts):
    if m := f.missing("product.graph"):
        return m
    a = f.val("product.graph")["apparent"]["audience"]
    if not a:
        return ("NOTE", "no phrase of the form 'for <someone>' was found; the site does not say who the product is for", "inferred")
    return ("PASS", "the site says who it is for: " + ", ".join(a[:4]), "inferred")


# ----------------------------------------------------------------- observation

def _obs(f: Facts):
    s = f.val("observations.summary")
    if not s:
        return None
    return s


def _fraction(f: Facts, key: str, word: str):
    s = _obs(f)
    if s is None:
        p = f.by.get("observations.summary")
        return ("UNKNOWN", "no observations yet: " + ((p or {}).get("error") or "run `omtal observe` with an engine key in the environment"), "needs-engine-access")
    parts, worst = [], 1.0
    for eng, b in s.items():
        asked = b["asked"] - b["failed"]
        if asked == 0:
            parts.append(f"{eng}: every call failed")
            continue
        frac = b[key] / asked
        worst = min(worst, frac)
        parts.append(f"{eng}: {word} in {b[key]} of {asked} answers")
    return frac_verdict(worst, parts, word)


def frac_verdict(worst: float, parts: list[str], word: str):
    ev = "; ".join(parts)
    if worst == 0:
        return ("RISK", f"never {word}: " + ev, "verified-directly")
    if worst < 0.34:
        return ("NOTE", f"rarely {word}: " + ev, "verified-directly")
    return ("PASS", ev, "verified-directly")


def observed_mentioned(f: Facts):
    return _fraction(f, "mentioned", "mentioned")


def observed_cited(f: Facts):
    return _fraction(f, "cited", "cited")


def observed_recommended(f: Facts):
    return _fraction(f, "recommended", "recommended")


def observed_sources(f: Facts):
    s = _obs(f)
    if s is None:
        return ("UNKNOWN", "no observations yet", "needs-engine-access")
    parts = []
    for eng, b in s.items():
        if b["domains"]:
            parts.append(f"{eng} cites most: " + ", ".join(f"{d} ({n})" for d, n in b["domains"][:6]))
        if b["competitors"]:
            parts.append(f"{eng} names: " + ", ".join(f"{c} ({n})" for c, n in b["competitors"]))
    return ("PASS" if parts else "NOTE", "; ".join(parts) or "no citations were returned", "verified-directly")


def self_test() -> None:
    f = Facts([{"id": "site.robots", "value": {"present": True, "bots": {"OAI-SearchBot": "blocked", "Googlebot": "allowed"}, "sitemaps": []}, "provenance": "verified-directly"}])
    assert robots_admits(f)[0] == "FAIL"
    f = Facts([{"id": "site.robots", "value": {"present": True, "bots": {"GPTBot": "blocked", "Googlebot": "allowed"}, "sitemaps": ["x"]}, "provenance": "verified-directly"}])
    assert robots_admits(f)[0] == "NOTE" and robots_present(f)[0] == "PASS"
    f = Facts([])
    assert observed_mentioned(f)[0] == "UNKNOWN" and observed_mentioned(f)[2] == "needs-engine-access"
    f = Facts([{"id": "observations.summary", "value": {"e": {"asked": 3, "failed": 0, "mentioned": 0, "cited": 0, "recommended": 0, "domains": [], "competitors": []}}, "provenance": "verified-directly"}])
    assert observed_mentioned(f)[0] == "RISK"
    f = Facts([{"id": "site.home", "value": {"cdn": None}, "provenance": "verified-directly"},
               {"id": "site.pages", "value": {"pages": []}, "provenance": "verified-directly"}])
    assert cdn_delivery(f)[0] == "PASS"
    f = Facts([{"id": "site.home", "value": {"cdn": "Cloudflare"}, "provenance": "verified-directly"},
               {"id": "site.pages", "value": {"pages": [{"url": "https://x/", "internal_links": ["https://x/cdn-cgi/l/email-protection#a"], "external_links": [], "text": ""}]}, "provenance": "verified-directly"}])
    v = cdn_delivery(f)
    assert v[0] == "NOTE" and "Cloudflare" in v[1] and "email_off" in v[1]
    f = Facts([{"id": "site.robots", "value": {"present": True, "ua_group_counts": {"*": 1}, "raw_groups": [{"uas": ["*"], "rules": [("disallow", "/admin/")]}]}, "provenance": "verified-directly"}])
    assert robots_one_group_per_bot(f)[0] == "PASS"
    f = Facts([{"id": "site.robots", "value": {"present": True, "ua_group_counts": {"*": 2},
                "raw_groups": [{"uas": ["*"], "rules": [("disallow", "")]}, {"uas": ["*"], "rules": [("disallow", "/admin/")]}]}, "provenance": "verified-directly"}])
    v = robots_one_group_per_bot(f)
    assert v[0] == "NOTE" and "/admin/" in v[1]
    live = Facts([{"id": "site.home", "value": {"status": 200, "final_url": "http://x/", "content_type": "text/html", "https": False, "redirected": False, "pre_deploy": False}, "provenance": "verified-directly"}])
    assert home_answers(live)[0] == "FAIL"
    build = Facts([{"id": "site.home", "value": {"status": 200, "final_url": "http://localhost:5055/", "content_type": "text/html", "https": False, "redirected": False, "pre_deploy": True}, "provenance": "verified-directly"}])
    hv = home_answers(build)
    assert hv[0] == "PASS" and "not applicable" in hv[1]
