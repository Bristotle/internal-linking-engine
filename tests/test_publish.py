"""Tests for publish. Run: python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publish import is_divider, render_inline, render_markdown, split_row  # noqa: E402


class TestInline(unittest.TestCase):
    def test_escapes_html_in_report_text(self):
        # Report text is generated from crawled URLs and page copy, so it can
        # contain anything. Escaping before applying markdown is the order that
        # matters.
        self.assertIn("&lt;script&gt;", render_inline("<script>"))

    def test_renders_inline_code(self):
        self.assertEqual(render_inline("a `/path/x.html` b"),
                         "a <code>/path/x.html</code> b")

    def test_renders_bold(self):
        self.assertEqual(render_inline("**Total**"), "<strong>Total</strong>")

    def test_a_url_in_a_code_span_is_still_escaped(self):
        self.assertNotIn("<b>", render_inline("`<b>`"))


class TestTableParsing(unittest.TestCase):
    def test_splits_a_row_into_cells(self):
        self.assertEqual(split_row("| a | b | c |"), ["a", "b", "c"])

    def test_recognises_a_divider_row(self):
        self.assertTrue(is_divider("| --- | --- |"))
        self.assertTrue(is_divider("| :--- | ---: |"))

    def test_a_content_row_is_not_a_divider(self):
        self.assertFalse(is_divider("| Metric | Now |"))


class TestRenderMarkdown(unittest.TestCase):
    def test_renders_headings_at_the_right_level(self):
        html = render_markdown("# One\n\n## Two\n")
        self.assertIn("<h1>One</h1>", html)
        self.assertIn("<h2>Two</h2>", html)

    def test_renders_a_table_with_a_head_and_body(self):
        html = render_markdown("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertIn("<th>A</th>", html)
        self.assertIn("<td>1</td>", html)
        self.assertEqual(html.count("<tr>"), 2)

    def test_wraps_tables_so_they_scroll_rather_than_break_the_page(self):
        html = render_markdown("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertIn('<div class="scroll">', html)

    def test_renders_a_list(self):
        html = render_markdown("- first\n- second\n")
        self.assertIn("<ul>", html)
        self.assertEqual(html.count("<li>"), 2)

    def test_joins_a_wrapped_paragraph_into_one_block(self):
        # The generated reports hard-wrap prose, which must not become two
        # paragraphs on the page.
        html = render_markdown("one line\nand its continuation\n")
        self.assertEqual(html, "<p>one line and its continuation</p>")

    def test_a_list_directly_after_a_paragraph_is_not_swallowed(self):
        html = render_markdown("Intro text\n- item\n")
        self.assertIn("<p>Intro text</p>", html)
        self.assertIn("<li>item</li>", html)

    def test_blank_lines_do_not_produce_empty_paragraphs(self):
        self.assertNotIn("<p></p>", render_markdown("# A\n\n\n\nbody\n"))

    def test_an_empty_report_renders_nothing(self):
        self.assertEqual(render_markdown(""), "")

    def test_a_table_at_the_end_of_the_report_closes_properly(self):
        html = render_markdown("| A |\n| --- |\n| 1 |")
        self.assertTrue(html.rstrip().endswith("</table></div>"))
