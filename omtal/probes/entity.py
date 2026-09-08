# Copyright (C) 2026 Editerra AB. Omtal is a trademark of Editerra AB.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The product graph: what the site says the product is, read the way a machine would.

Two sources, kept apart. Declared: what the site states in structured data
(JSON-LD types, names, descriptions, offers, features, sameAs). Apparent: what
its headings, lists and text suggest. The first is a fact about the site; the
second is inferred and labelled so. A model may later refine the apparent half;
it may never overwrite the declared half.
"""

from __future__ import annotations

import re
from collections import Counter

from ..schema import make_probe

ENTITY_TYPES = ("Organization", "Corporation", "LocalBusiness")
PRODUCT_TYPES = ("Product", "SoftwareApplication", "MobileApplication", "WebApplication", "Service", "SoftwareSourceCode")
CLAIM = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?\s?(?:%|percent|x|times|million|thousand|users|customers|apps|downloads|countries|years))\b", re.I)
AUDIENCE = re.compile(r"\b(?:for|built for|designed for|made for)\s+((?:[a-z-]+\s){0,3}(?:developers?|teams?|families|parents|businesses|companies|agencies|publishers|students|doctors|users|people|everyone|anyone|adults|children|kids|seniors|enterprises?))", re.I)


def _nodes(pages: list[dict]) -> list[tuple[str, dict]]:
    out = []
    for pg in pages:
        for it in pg.get("jsonld", []):
            nodes = it.get("@graph") if isinstance(it.get("@graph"), list) else [it]
            for n in nodes:
                if isinstance(n, dict):
                    out.append((pg["url"], n))
    return out


def _types(n: dict) -> list[str]:
    t = n.get("@type")
    return t if isinstance(t, list) else ([t] if t else [])


def build(pages: list[dict], home: dict | None) -> dict:
    nodes = _nodes(pages)
    orgs = [(u, n) for u, n in nodes if any(t in ENTITY_TYPES for t in _types(n))]
    prods = [(u, n) for u, n in nodes if any(t in PRODUCT_TYPES for t in _types(n))]
    declared = {
        "organization": ({"name": orgs[0][1].get("name"), "url": orgs[0][1].get("url"), "sameAs": orgs[0][1].get("sameAs"), "identifier": orgs[0][1].get("identifier"),
                          "email": orgs[0][1].get("email"), "declared_on": orgs[0][0]} if orgs else None),
        "products": [{"name": n.get("name"), "types": _types(n), "description": n.get("description"), "url": n.get("url"), "offers": n.get("offers"),
                      "features": n.get("featureList"), "category": n.get("applicationCategory") or n.get("category"), "os": n.get("operatingSystem"),
                      "declared_on": u} for u, n in prods],
        "jsonld_types": sorted(Counter(t for _, n in nodes for t in _types(n)).items()),
        "pages_with_jsonld": sum(1 for pg in pages if pg.get("jsonld")),
    }
    # apparent: headings and text, from the home page first
    home_pg = next((pg for pg in pages if home and pg["url"].rstrip("/") == home.rstrip("/")), pages[0] if pages else None)
    names = Counter()
    for pg in pages:
        og_site = (pg.get("og") or {}).get("site_name")
        if og_site:
            names[og_site.strip()] += 2
        t = pg.get("title") or ""
        for sep in (" — ", " – ", " | ", " - ", ": "):
            if sep in t:
                names[t.split(sep)[-1].strip()] += 1
                names[t.split(sep)[0].strip()] += 1
    apparent_name = names.most_common(1)[0][0] if names else (home_pg["title"] if home_pg else None)
    h2s = [t for pg in pages for tag, t in pg.get("headings", []) if tag in ("h2", "h3") and 3 <= len(t) <= 80]
    features = [h for h, c in Counter(h2s).most_common(40)]
    text_all = "\n".join(pg.get("text", "") for pg in pages)
    claims = sorted(set(m.group(1).strip() for m in CLAIM.finditer(text_all)))[:40]
    audiences = [m.group(1).strip().lower() for m in AUDIENCE.finditer(text_all)]
    audience = [a for a, _ in Counter(audiences).most_common(6)]
    langs = sorted({pg.get("lang") for pg in pages if pg.get("lang")})
    contact = sorted({m for pg in pages for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", pg.get("text", ""))})[:5]
    apparent = {"name": apparent_name, "tagline": (home_pg["h1"][0] if home_pg and home_pg["h1"] else None), "description": (home_pg or {}).get("description"),
                "features_from_headings": features, "claims_with_numbers": claims, "audience": audience, "languages": langs, "contact": contact,
                "pages": len(pages), "words_total": sum(pg.get("words", 0) for pg in pages)}
    # consistency: does every page name the product?
    name = (declared["products"][0]["name"] if declared["products"] and declared["products"][0].get("name") else None) or (declared["organization"] or {}).get("name") or apparent_name
    named = sum(1 for pg in pages if name and name.lower() in ((pg.get("title") or "") + " " + (pg.get("description") or "")).lower())
    return {"name": name, "declared": declared, "apparent": apparent, "pages_naming_the_product": named, "pages": len(pages)}


def probe(pages_probe: dict, home_url: str) -> list[dict]:
    pages = (pages_probe or {}).get("pages", [])
    if not pages:
        return [make_probe("product.graph", None, source_kind="url", source_ref=home_url, error="no page could be read")]
    g = build(pages, home_url)
    return [make_probe("product.graph", g, source_kind="url", source_ref=home_url, provenance="inferred")]


def self_test() -> None:
    pages = [{"url": "https://x/", "title": "Foo — Acme", "description": "Foo does bar for developers", "og": {"site_name": "Foo"}, "h1": ["Foo does bar"],
              "headings": [("h1", "Foo does bar"), ("h2", "Lending history"), ("h2", "Annotations")], "jsonld": [{"@type": "SoftwareApplication", "name": "Foo", "featureList": ["a"]}],
              "text": "Foo is built for developers. 12,000 users.", "words": 8, "lang": "en"}]
    g = build(pages, "https://x/")
    assert g["name"] == "Foo" and g["declared"]["products"][0]["features"] == ["a"]
    assert "Lending history" in g["apparent"]["features_from_headings"] and g["apparent"]["claims_with_numbers"] == ["12,000 users"]
    assert g["apparent"]["audience"] == ["developers"] and g["pages_naming_the_product"] == 1
