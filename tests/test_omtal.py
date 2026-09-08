# Copyright (C) 2026 Editerra AB. SPDX-License-Identifier: AGPL-3.0-or-later
import json
import re
import tempfile
import unittest
from pathlib import Path

from omtal import checks, grid, judge, report, web
from omtal.probes import entity, pages, site
from omtal.schema import make_probe, write_json


def probes_for(robots_bots=None, with_product=True, with_obs=False):
    bots = robots_bots or {b: "allowed" for b in web.BOTS}
    pgs = [{"url": "https://x.example/", "title": "Foo — the lending tracker", "description": "Foo remembers who borrowed your books and when they are due back.", "canonical": "https://x.example/",
            "lang": "en", "h1": ["Foo remembers who has your books"], "headings": [("h1", "Foo remembers who has your books"), ("h2", "Lending history"), ("h2", "Annotations")],
            "jsonld": [{"@type": "SoftwareApplication", "name": "Foo", "description": "Tracks lent books", "featureList": ["Lending history", "Annotations"]}] if with_product else [],
            "jsonld_types": ["SoftwareApplication"] if with_product else [], "text": "Foo is built for readers. " * 40, "words": 200, "internal_links": [], "external_links": [], "images": 1, "images_without_alt": 0, "og": {"site_name": "Foo"}}]
    out = [make_probe("site.robots", {"present": True, "bots": bots, "sitemaps": ["https://x.example/sitemap.xml"], "bytes": 40}, source_kind="url", source_ref="r"),
           make_probe("site.sitemap", {"present": True, "sitemaps": [], "pages": ["https://x.example/"], "count": 1}, source_kind="url", source_ref="s"),
           make_probe("site.llms", {"present": False, "url": None, "bytes": 0, "text": ""}, source_kind="url", source_ref="l"),
           make_probe("site.home", {"status": 200, "final_url": "https://x.example/", "content_type": "text/html", "https": True, "redirected": False}, source_kind="url", source_ref="h"),
           make_probe("site.pages", {"scope": "https://x.example", "budget": 10, "crawled": 1, "queued_unvisited": 0, "pages": pgs, "errors": []}, source_kind="url", source_ref="p")]
    out += entity.probe(out[-1]["value"], "https://x.example/")
    if with_obs:
        out.append(make_probe("observations.summary", {"e": {"asked": 3, "failed": 0, "mentioned": 2, "cited": 1, "recommended": 0, "domains": [("reddit.com", 2)], "competitors": []}}, source_kind="file", source_ref="o"))
    else:
        out.append(make_probe("observations.summary", None, source_kind="file", source_ref="o", provenance="needs-engine-access", error="no engine asked"))
    return out


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, g, rid):
        return next(r for r in g["rows"] if r["id"] == rid)

    def test_every_row_has_one_marker_and_a_blocked_search_bot_keeps_machines_out(self):
        bots = {b: "allowed" for b in web.BOTS}
        bots["OAI-SearchBot"] = "blocked"
        g = grid.build(self.out, probes_for(bots))
        grid.validate(g)
        self.assertEqual(self.row(g, "access.robots-admits-ai-crawlers")["verdict"], "FAIL")
        self.assertEqual(g["stage"], "unreachable")

    def test_blocking_only_training_bots_is_a_note(self):
        bots = {b: "allowed" for b in web.BOTS}
        bots["GPTBot"] = "blocked"
        g = grid.build(self.out, probes_for(bots))
        self.assertEqual(self.row(g, "access.robots-admits-ai-crawlers")["verdict"], "NOTE")

    def test_no_engine_key_is_open_not_a_failure(self):
        g = grid.build(self.out, probes_for())
        r = self.row(g, "observation.mentioned")
        self.assertEqual((r["verdict"], r["provenance"]), ("UNKNOWN", "needs-engine-access"))
        self.assertEqual(g["stage"], "understood")

    def test_observations_speak_in_fractions(self):
        g = grid.build(self.out, probes_for(with_obs=True))
        self.assertIn("2 of 3", self.row(g, "observation.mentioned")["evidence"])
        self.assertEqual(self.row(g, "observation.recommended")["verdict"], "NOTE")   # never recommended: a note, for a note-severity rule
        self.assertEqual(g["stage"], "cited")

    def test_no_product_node_keeps_the_site_at_reachable(self):
        g = grid.build(self.out, probes_for(with_product=False))
        self.assertEqual(self.row(g, "entity.product-declared")["verdict"], "FAIL")
        self.assertEqual(g["stage"], "reachable")

    def test_judgement_is_kept_only_while_facts_are_unchanged(self):
        probes = probes_for()
        write_json(self.out / "probes.json", probes)
        judge.add_judgement(self.out, "evidence.positioning-accurate", "PASS", "The description names the function: remembers who borrowed your books.", "a reader")
        g = grid.build(self.out, probes)
        self.assertEqual((self.row(g, "evidence.positioning-accurate")["verdict"], self.row(g, "evidence.positioning-accurate")["provenance"]), ("PASS", "sub-agent-reported"))
        probes[4]["value"]["pages"][0]["description"] = "changed"
        probes[5] = entity.probe(probes[4]["value"], "https://x.example/")[0]
        g = grid.build(self.out, probes)
        self.assertEqual(self.row(g, "evidence.positioning-accurate")["verdict"], "UNKNOWN")
        self.assertIn("discarded", self.row(g, "evidence.positioning-accurate")["evidence"])

    def test_a_judgement_on_a_mechanical_rule_is_refused(self):
        write_json(self.out / "probes.json", probes_for())
        with self.assertRaises(ValueError):
            judge.add_judgement(self.out, "access.sitemap", "PASS", "looks fine to me, honestly it does", "x")


class ReportContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        probes = probes_for()
        write_json(self.out / "probes.json", probes)
        write_json(self.out / "grid.json", grid.build(self.out, probes))
        report.render(self.out / "grid.json", self.out / "report.html", "https://x.example/")
        self.page = (self.out / "report.html").read_text()
        self.text = re.sub(r"<style>.*?</style>", "", self.page, flags=re.S)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sections_in_fixed_order_with_colours_and_words(self):
        heads = ["1. What keeps machines out", "2. What weakens understanding", "3. What is still to be checked", "4. Worth knowing", "5. What the engines did", "6. What is in order"]
        pos = [self.text.find(h) for h in heads]
        self.assertTrue(all(p >= 0 for p in pos) and pos == sorted(pos))
        for cls in ("s-fail", "s-risk", "s-open", "s-met"):
            self.assertIn(f"<div class={cls}>", self.page)
        self.assertIn("<h1>Foo</h1>", self.page)
        self.assertIn("Where it stands.", self.page)

    def test_no_machine_words_and_exports_travel_inside(self):
        for w in report.MACHINE_WORDS:
            self.assertNotRegex(self.text, r"(?<![\w.-])" + re.escape(w) + r"(?![\w-])", w)
        for f in ("findings.md", "findings.csv", "actions.json"):
            self.assertIn(f'id="x-{f}"', self.page)
            self.assertTrue((self.out / f).exists())
        self.assertIn('<meta name="generator" content="Omtal', self.page)
        self.assertIn("trademarks of Editerra AB", self.page)

    def test_hand_edit_is_caught(self):
        self.assertIsNone(report.check_render(self.out / "grid.json", self.out / "report.html", "https://x.example/"))
        p = self.out / "report.html"
        p.write_text(p.read_text().replace("AI Discoverability Check", "AI Discoverability Cheque", 1))
        self.assertIn("run render", report.check_render(self.out / "grid.json", p, "https://x.example/"))


class SelfTests(unittest.TestCase):
    def test_modules(self):
        for m in (web, site, pages, entity, checks, grid):
            m.self_test()
