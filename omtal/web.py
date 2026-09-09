# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading the web the way a crawler does: fetch, robots, sitemaps, and what a page says.

Standard library only. Every function returns plain data; nothing here decides.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (compatible; omtal/0.1; +https://editerra.se/omtal)"
MAX_BYTES = 1_500_000

# The crawlers behind AI answers and search. A site that blocks one is invisible there.
BOTS = {
    "OAI-SearchBot": "ChatGPT search results and citations",
    "GPTBot": "OpenAI model training (blocking it does not affect search)",
    "ChatGPT-User": "pages ChatGPT opens on a user's behalf",
    "PerplexityBot": "Perplexity answers",
    "ClaudeBot": "Anthropic crawling",
    "Claude-SearchBot": "Claude search results",
    "Googlebot": "Google search, AI Overviews and AI Mode",
    "Google-Extended": "Gemini training and grounding",
    "Bingbot": "Bing, Copilot and the engines built on Bing",
}


def fetch(url: str, timeout: int = 30, max_bytes: int = MAX_BYTES) -> dict:
    """One fetch, recorded: status, final address, content type, body text, and the error if any."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(max_bytes)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            ctype = r.headers.get("Content-Type", "")
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype)
            if m:
                charset = m.group(1)
            try:
                text = raw.decode(charset, "replace")
            except LookupError:
                text = raw.decode("utf-8", "replace")
            return {"url": url, "status": r.status, "final_url": r.geturl(), "content_type": ctype, "text": text, "bytes": len(raw), "headers": _header_subset(r.headers), "error": None}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "final_url": url, "content_type": "", "text": "", "bytes": 0, "headers": _header_subset(getattr(e, "headers", None)), "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": 0, "final_url": url, "content_type": "", "text": "", "bytes": 0, "headers": {}, "error": str(e)[:200]}


# The few response headers that reveal a CDN or edge in front of the origin.
_CDN_HEADERS = ("server", "via", "cf-ray", "cf-cache-status", "x-served-by", "x-cache", "x-vercel-id", "x-nf-request-id", "x-powered-by", "x-amz-cf-id")


def _header_subset(headers) -> dict:
    if not headers:
        return {}
    out = {}
    for k in _CDN_HEADERS:
        v = headers.get(k)
        if v:
            out[k] = v
    return out


# Signatures that name the edge sitting in front of the origin. Header key -> substring (or "" for present-at-all) -> name.
_CDN_SIGNS = (
    ("cf-ray", "", "Cloudflare"),
    ("server", "cloudflare", "Cloudflare"),
    ("x-amz-cf-id", "", "Amazon CloudFront"),
    ("server", "cloudfront", "Amazon CloudFront"),
    ("x-vercel-id", "", "Vercel"),
    ("x-nf-request-id", "", "Netlify"),
    ("server", "netlify", "Netlify"),
    ("x-served-by", "fastly", "Fastly"),
    ("via", "fastly", "Fastly"),
    ("server", "akamai", "Akamai"),
    ("x-cache", "akamai", "Akamai"),
)


def detect_cdn(headers: dict) -> str | None:
    """The name of the CDN or edge in front, from response headers, or None."""
    if not headers:
        return None
    low = {k.lower(): (v or "").lower() for k, v in headers.items()}
    for key, needle, name in _CDN_SIGNS:
        v = low.get(key)
        if v is None:
            continue
        if needle == "" or needle in v:
            return name
    return None


# Rewrites a CDN performs on the delivered HTML that a crawler sees but the origin did not send.
def cdn_artifacts(pages: list[dict]) -> list[dict]:
    """Recognised edge rewrites found in the crawled pages: what it is, why it appears, and what to do."""
    found = []
    hit_email = False
    for pg in pages:
        links = list(pg.get("internal_links") or []) + list(pg.get("external_links") or [])
        if not hit_email and (any("/cdn-cgi/l/email-protection" in u for u in links) or "/cdn-cgi/l/email-protection" in (pg.get("text") or "")):
            hit_email = True
            found.append({
                "kind": "email-obfuscation",
                "cdn": "Cloudflare",
                "detail": "Cloudflare Email Address Obfuscation rewrote a plain email address into a link to /cdn-cgi/l/email-protection, which returns 404 when fetched without its script. The origin HTML has the address in plain text.",
                "fix": "wrap the address in Cloudflare's <!--email_off--> ... <!--/email_off--> markers to keep it plain, or turn the feature off; the link is otherwise a dead end a crawler follows.",
                "where": next((pg["url"] for pg in pages if any("/cdn-cgi/l/email-protection" in u for u in (pg.get("internal_links") or []) + (pg.get("external_links") or []))), pages[0]["url"] if pages else ""),
            })
    return found


def origin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def remap_to_base(url: str, base: str) -> str:
    """Point a URL at a different host, keeping its path and query. Used in pre-deploy mode,
    where a local build's absolute URLs (sitemap entries, the Sitemap: line) name the
    production host, but must be followed against the local server actually being audited."""
    p = urllib.parse.urlsplit(url)
    b = urllib.parse.urlsplit(base)
    return urllib.parse.urlunsplit((b.scheme, b.netloc, p.path, p.query, p.fragment))


def is_local_host(url: str) -> bool:
    """A host that only exists on this machine or a private network — a build being tested, not the live site."""
    host = urllib.parse.urlsplit(url).netloc.split(":", 1)[0].lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local") or host.startswith(("192.168.", "10.", "127."))


# ----------------------------------------------------------------- robots.txt

def parse_robots(text: str) -> dict:
    """Groups by user agent, the rules in each, and the sitemaps named. Case-insensitive, comments stripped.

    `groups` merges every rule for a user-agent, which is how lenient crawlers read
    the file. `raw_groups` keeps each block separately, so a caller can see when the
    same agent is named by more than one group — which a strict crawler does not merge.
    """
    groups: dict[str, list[tuple[str, str]]] = {}
    raw_groups: list[dict] = []
    current: list[str] = []
    current_raw: dict | None = None
    last_was_ua = False
    sitemaps = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if not last_was_ua:
                current = []
                current_raw = {"uas": [], "rules": []}
                raw_groups.append(current_raw)
            current.append(v.lower())
            current_raw["uas"].append(v.lower())
            groups.setdefault(v.lower(), [])
            last_was_ua = True
            continue
        last_was_ua = False
        if k == "sitemap":
            sitemaps.append(v)
        elif k in ("allow", "disallow"):
            for ua in current:
                groups[ua].append((k, v))
            if current_raw is not None:
                current_raw["rules"].append((k, v))
    counts: dict[str, int] = {}
    for grp in raw_groups:
        for ua in set(grp["uas"]):
            counts[ua] = counts.get(ua, 0) + 1
    return {"groups": groups, "raw_groups": raw_groups, "ua_group_counts": counts, "sitemaps": sitemaps}


def bot_access(robots: dict, bot: str, path: str = "/") -> str:
    """'allowed', 'blocked' or 'limited' for one bot and one path, by the longest matching rule."""
    rules = robots["groups"].get(bot.lower())
    if rules is None:
        rules = robots["groups"].get("*", [])
    best = None
    for kind, pat in rules:
        if not pat:
            continue
        rx = "^" + re.escape(pat).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(rx, path):
            if best is None or len(pat) > len(best[1]):
                best = (kind, pat)
    if best is None:
        return "allowed"
    if best[0] == "allow":
        return "allowed"
    return "blocked" if best[1] == "/" else "limited"


# ----------------------------------------------------------------- sitemaps

def sitemap_urls(xml: str) -> tuple[list[str], list[str]]:
    """(page urls, child sitemap urls) from a sitemap or a sitemap index."""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    if "<sitemapindex" in xml:
        return [], locs
    return locs, []


# ----------------------------------------------------------------- pages

class _Page(HTMLParser):
    """What a page says, structurally: title, metas, links, headings, JSON-LD, visible text."""

    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas: list[dict] = []
        self.links: list[dict] = []
        self.anchors: list[tuple[str, str]] = []
        self.headings: list[tuple[str, str]] = []
        self.jsonld: list[str] = []
        self.lang = None
        self.text_parts: list[str] = []
        self.images_without_alt = 0
        self.images = 0
        self._stack: list[str] = []
        self._in_title = False
        self._heading: tuple[str, list[str]] | None = None
        self._jsonld = False
        self._anchor: list[str] | None = None
        self._anchor_href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "a":
            self._anchor = []
            self._anchor_href = a.get("href", "")
        elif tag in ("h1", "h2", "h3"):
            self._heading = (tag, [])
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._jsonld = True
        elif tag == "img":
            self.images += 1
            if not (a.get("alt") or "").strip():
                self.images_without_alt += 1
        if tag in self.SKIP:
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self.anchors.append((self._anchor_href, " ".join(self._anchor).strip()))
            self._anchor = None
        elif tag in ("h1", "h2", "h3") and self._heading:
            self.headings.append((tag, " ".join(self._heading[1]).strip()))
            self._heading = None
        elif tag == "script":
            self._jsonld = False
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag in ("p", "li", "div", "section", "article", "br", "tr", "h1", "h2", "h3", "h4"):
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._jsonld:
            self.jsonld.append(data)
            return
        if self._stack:
            return
        if self._in_title:
            self.title += data
        if self._heading:
            self._heading[1].append(data.strip())
        if self._anchor is not None:
            self._anchor.append(data.strip())
        self.text_parts.append(data)


def read_page(html_text: str, url: str) -> dict:
    p = _Page()
    try:
        p.feed(html_text)
    except Exception:  # noqa: BLE001
        pass
    metas = {}
    for m in p.metas:
        key = (m.get("name") or m.get("property") or "").lower()
        if key and "content" in m:
            metas.setdefault(key, m["content"])
    canonical = next((l.get("href") for l in p.links if (l.get("rel") or "").lower() == "canonical"), None)
    lds, ld_types = [], []
    for raw in p.jsonld:
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            ld_types.append("INVALID")
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if not isinstance(it, dict):
                continue
            lds.append(it)
            nodes = it.get("@graph") if isinstance(it.get("@graph"), list) else [it]
            for n in nodes:
                t = n.get("@type") if isinstance(n, dict) else None
                ld_types += t if isinstance(t, list) else ([t] if t else [])
    text = re.sub(r"[ \t]+", " ", "".join(p.text_parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    base = origin(url)
    internal, external = [], []
    for href, label in p.anchors:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urllib.parse.urljoin(url, href.split("#", 1)[0])
        (internal if full.startswith(base) else external).append((full, label))
    return {
        "url": url, "title": html.unescape(p.title.strip()), "lang": p.lang, "description": metas.get("description"),
        "canonical": canonical, "robots_meta": metas.get("robots"), "og": {k[3:]: v for k, v in metas.items() if k.startswith("og:")},
        "headings": p.headings, "h1": [t for tag, t in p.headings if tag == "h1"], "jsonld": lds, "jsonld_types": ld_types,
        "text": text[:20000], "words": len(text.split()), "internal_links": sorted({u for u, _ in internal}), "external_links": sorted({u for u, _ in external}),
        "images": p.images, "images_without_alt": p.images_without_alt,
    }


def self_test() -> None:
    r = parse_robots("User-agent: *\nDisallow: /private/\n\nUser-agent: GPTBot\nDisallow: /\n\nSitemap: https://x/s.xml\n")
    assert bot_access(r, "OAI-SearchBot") == "allowed" and bot_access(r, "GPTBot") == "blocked"
    assert bot_access(r, "Googlebot", "/private/x") == "limited" and r["sitemaps"] == ["https://x/s.xml"]
    assert r["ua_group_counts"] == {"*": 1, "gptbot": 1}
    dupe = parse_robots("User-agent: *\nDisallow:\n\nUser-agent: *\nDisallow: /admin/\n")
    assert dupe["ua_group_counts"]["*"] == 2 and len(dupe["raw_groups"]) == 2
    assert remap_to_base("https://pompedozare.ro/sitemap.xml", "http://localhost:5055") == "http://localhost:5055/sitemap.xml"
    assert is_local_host("http://localhost:5055/") and not is_local_host("https://pompedozare.ro/")
    pages, kids = sitemap_urls("<sitemapindex><sitemap><loc>https://x/a.xml</loc></sitemap></sitemapindex>")
    assert kids == ["https://x/a.xml"] and pages == []
    pg = read_page('<html lang="en"><head><title>T &amp; U</title><meta name="description" content="d"><link rel="canonical" href="https://x/"><script type="application/ld+json">{"@type":"Organization","name":"X"}</script></head><body><h1>Hi</h1><p>Hello <a href="/a">A</a> <a href="https://y/b">B</a></p><script>ignored()</script></body></html>', "https://x/")
    assert pg["title"] == "T & U" and pg["jsonld_types"] == ["Organization"] and pg["h1"] == ["Hi"] and "ignored" not in pg["text"]
    assert pg["internal_links"] == ["https://x/a"] and pg["external_links"] == ["https://y/b"]
    assert detect_cdn({"cf-ray": "abc"}) == "Cloudflare" and detect_cdn({"Server": "cloudflare"}) == "Cloudflare"
    assert detect_cdn({"x-served-by": "cache-fra fastly"}) == "Fastly" and detect_cdn({"server": "nginx"}) is None and detect_cdn({}) is None
    arts = cdn_artifacts([{"url": "https://x/", "internal_links": ["https://x/cdn-cgi/l/email-protection#abc"], "external_links": [], "text": ""}])
    assert len(arts) == 1 and arts[0]["kind"] == "email-obfuscation" and arts[0]["cdn"] == "Cloudflare"
    assert cdn_artifacts([{"url": "https://x/", "internal_links": ["https://x/a"], "external_links": [], "text": "hello"}]) == []
