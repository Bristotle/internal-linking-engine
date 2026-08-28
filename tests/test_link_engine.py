"""Tests for link_engine. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from link_engine import (  # noqa: E402
    MAX_NEW_INLINKS_PER_TARGET, MAX_NEW_LINKS_PER_PAGE, apply_caps, build_graph,
    find_opportunities, keyword_positions, orphan_actions, pagerank, visible_text,
)


def page(url, keyword, body, page_type="product", genre="rpg",
         outlinks=None, secondary=None):
    return {
        "url": url,
        "title": url,
        "type": page_type,
        "genre": genre,
        "target_keyword": keyword,
        "secondary_keywords": secondary or [],
        "outlinks": outlinks or [],
        "body": body,
    }


class TestVisibleText(unittest.TestCase):
    def test_removes_existing_anchors_including_their_text(self):
        # Text inside an <a> cannot host a second link, so proposing it would
        # produce a change nobody can apply.
        cleaned = visible_text('Buy an <a href="/x">elden ring ps5 key</a> today.')
        self.assertNotIn("elden ring ps5 key", cleaned)
        self.assertIn("today", cleaned)

    def test_strips_other_tags_but_keeps_their_text(self):
        self.assertIn("elden ring", visible_text("<p><strong>elden ring</strong></p>"))

    def test_plain_text_is_left_alone(self):
        self.assertIn("elden ring ps5 key", visible_text("An elden ring ps5 key."))


class TestKeywordPositions(unittest.TestCase):
    def test_matches_are_case_insensitive(self):
        self.assertEqual(len(keyword_positions("An Elden Ring PS5 Key here", "elden ring ps5 key")), 1)

    def test_respects_word_boundaries(self):
        self.assertEqual(keyword_positions("supercyberpunkgame", "cyberpunk"), [])

    def test_tolerates_irregular_whitespace_between_words(self):
        self.assertEqual(len(keyword_positions("an elden  ring key", "elden ring")), 1)


class TestBuildGraph(unittest.TestCase):
    def test_ignores_links_to_urls_outside_the_inventory(self):
        pages = [page("/a", "a", "", outlinks=["/b", "https://external.example.com"]),
                 page("/b", "b", "")]
        outlinks, _ = build_graph(pages)
        self.assertEqual(outlinks["/a"], {"/b"})

    def test_drops_self_links(self):
        pages = [page("/a", "a", "", outlinks=["/a"])]
        outlinks, _ = build_graph(pages)
        self.assertEqual(outlinks["/a"], set())

    def test_records_the_reverse_edges(self):
        pages = [page("/a", "a", "", outlinks=["/b"]), page("/b", "b", "")]
        _, inlinks = build_graph(pages)
        self.assertEqual(inlinks["/b"], {"/a"})
        self.assertEqual(inlinks["/a"], set())


class TestPageRank(unittest.TestCase):
    def test_ranks_sum_to_one(self):
        outlinks = {"/a": {"/b"}, "/b": {"/c"}, "/c": {"/a"}}
        self.assertAlmostEqual(sum(pagerank(outlinks).values()), 1.0, places=6)

    def test_dangling_pages_do_not_leak_rank(self):
        # /c has no outlinks. If its mass were dropped rather than
        # redistributed, the total would fall below 1 and before/after
        # comparisons would be meaningless.
        outlinks = {"/a": {"/b"}, "/b": {"/c"}, "/c": set()}
        self.assertAlmostEqual(sum(pagerank(outlinks).values()), 1.0, places=6)

    def test_a_page_with_more_inlinks_ranks_higher(self):
        outlinks = {"/a": {"/c"}, "/b": {"/c"}, "/c": set(), "/d": set()}
        rank = pagerank(outlinks)
        self.assertGreater(rank["/c"], rank["/d"])

    def test_an_empty_graph_returns_no_ranks(self):
        self.assertEqual(pagerank({}), {})


class TestFindOpportunities(unittest.TestCase):
    def test_finds_an_unlinked_keyword_mention(self):
        pages = [page("/a", "game a", "Compare it with an elden ring ps5 key."),
                 page("/b", "elden ring ps5 key", "Elden Ring.")]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual([(o["source"], o["target"]) for o in opportunities], [("/a", "/b")])

    def test_skips_a_pair_that_is_already_linked(self):
        pages = [page("/a", "game a", "An elden ring ps5 key.", outlinks=["/b"]),
                 page("/b", "elden ring ps5 key", "Elden Ring.")]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual(opportunities, [])

    def test_never_proposes_a_self_link(self):
        pages = [page("/a", "elden ring ps5 key", "An elden ring ps5 key.")]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual(opportunities, [])

    def test_proposes_one_link_per_pair_not_per_mention(self):
        pages = [page("/a", "game a", "An elden ring ps5 key, and another elden ring ps5 key."),
                 page("/b", "elden ring ps5 key", "Elden Ring.")]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual(len(opportunities), 1)

    def test_prefers_the_longer_more_specific_anchor(self):
        # Both keywords match the same span of text. The specific one wins, so
        # the anchor describes the product rather than the franchise.
        pages = [page("/a", "game a", "Looking at an elden ring ps5 key here."),
                 page("/b", "elden ring ps5 key", "Specific."),
                 page("/c", "elden ring", "Broad.")]
        opportunities, _, _ = find_opportunities(pages)
        targets = {o["target"] for o in opportunities}
        self.assertIn("/b", targets)
        self.assertNotIn("/c", targets)

    def test_an_orphan_target_outranks_a_well_linked_one(self):
        pages = [
            page("/a", "game a", "See the elden ring ps5 key and the witcher 3 xbox key."),
            page("/b", "elden ring ps5 key", "Linked already.", outlinks=[]),
            page("/c", "witcher 3 xbox key", "Orphan.", outlinks=[]),
            page("/d", "game d", "Filler.", outlinks=["/b"]),
        ]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual(opportunities[0]["target"], "/c")

    def test_does_not_propose_a_link_from_inside_an_existing_anchor(self):
        pages = [page("/a", "game a", 'Buy an <a href="/b">elden ring ps5 key</a>.'),
                 page("/b", "elden ring ps5 key", "Elden Ring.")]
        opportunities, _, _ = find_opportunities(pages)
        self.assertEqual(opportunities, [])


class TestCaps(unittest.TestCase):
    def _opportunity(self, source, target):
        return {"source": source, "target": target, "anchor": "x", "priority": 1.0}

    def test_a_source_page_cannot_exceed_its_new_link_cap(self):
        opportunities = [self._opportunity("/a", "/t%d" % i)
                         for i in range(MAX_NEW_LINKS_PER_PAGE + 2)]
        accepted, rejected = apply_caps(opportunities)
        self.assertEqual(len(accepted), MAX_NEW_LINKS_PER_PAGE)
        self.assertEqual(len(rejected), 2)

    def test_a_target_cannot_exceed_its_new_inlink_cap(self):
        opportunities = [self._opportunity("/s%d" % i, "/t")
                         for i in range(MAX_NEW_INLINKS_PER_TARGET + 1)]
        accepted, _ = apply_caps(opportunities)
        self.assertEqual(len(accepted), MAX_NEW_INLINKS_PER_TARGET)

    def test_rejections_explain_which_cap_was_hit(self):
        opportunities = [self._opportunity("/a", "/t%d" % i)
                         for i in range(MAX_NEW_LINKS_PER_PAGE + 1)]
        _, rejected = apply_caps(opportunities)
        self.assertIn("cap", rejected[0]["rejected_because"])


class TestOrphanActions(unittest.TestCase):
    def test_recommends_the_matching_genre_hub(self):
        pages = [page("/guide", "redeem steam key", "Guide.", page_type="guide", genre="rpg"),
                 page("/genres/rpg.html", "rpg games", "Hub.", page_type="hub", genre="rpg")]
        actions = orphan_actions(pages, ["/guide"], {})
        self.assertEqual(actions[0]["suggested_source"], "/genres/rpg.html")

    def test_falls_back_to_the_homepage_when_no_hub_owns_the_topic(self):
        pages = [page("/guide", "redeem steam key", "Guide.", page_type="guide", genre=""),
                 page("/index.html", "game keys", "Home.", page_type="home", genre="")]
        actions = orphan_actions(pages, ["/guide"], {})
        self.assertEqual(actions[0]["suggested_source"], "/index.html")

    def test_returns_nothing_when_there_are_no_orphans(self):
        self.assertEqual(orphan_actions([], [], {}), [])


if __name__ == "__main__":
    unittest.main()
