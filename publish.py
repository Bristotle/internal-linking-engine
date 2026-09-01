#!/usr/bin/env python3
"""Render the generated markdown report as a GitHub Pages page.

The tool in this repo is a command line pipeline, so its result is a file on
someone's disk. This turns that same report into a page anyone can open, which
is the difference between "here is a repo" and "here is the output".

The report is the single source: this converts it rather than restating it, so
the page cannot drift from what the tool actually produced.

Standard library only. Run: python3 publish.py
"""

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).parent
REPORT_FILE = ROOT / "out" / "report.md"
DOCS_DIR = ROOT / "docs"

PROJECT_TITLE = "Internal linking engine"
PROJECT_TAGLINE = "Finds the internal links a site should already have, by looking for places where one page mentions another page's target keyword and does not link to it."
REPO_URL = "https://github.com/Bristotle/internal-linking-engine"
RUN_COMMAND = "python3 link_engine.py"

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")


def render_inline(text):
    """Escape a line, then apply the inline markdown this report set uses."""
    escaped = html.escape(text)
    escaped = INLINE_CODE.sub(lambda m: "<code>%s</code>" % m.group(1), escaped)
    escaped = BOLD.sub(lambda m: "<strong>%s</strong>" % m.group(1), escaped)
    return escaped


def split_row(line):
    """Split a markdown table row into its cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_divider(line):
    """True for the |---|---| line that separates a table head from its body."""
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells)


def render_markdown(source):
    """Convert the subset of markdown these reports use into HTML.

    Deliberately not a general markdown parser. It handles headings, tables,
    unordered lists, paragraphs, inline code and bold, which is everything the
    generated reports contain. Anything wider would be untested surface area.
    """
    lines = source.splitlines()
    output = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            output.append("<h%d>%s</h%d>" % (level, render_inline(heading.group(2)), level))
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and is_divider(lines[index + 1]):
            headers = split_row(stripped)
            index += 2
            body = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                body.append(split_row(lines[index].strip()))
                index += 1
            output.append('<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s'
                          "</tbody></table></div>" % (
                              "".join("<th>%s</th>" % render_inline(cell) for cell in headers),
                              "".join("<tr>%s</tr>" % "".join(
                                  "<td>%s</td>" % render_inline(cell) for cell in row)
                                  for row in body)))
            continue

        if stripped.startswith("- "):
            items = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(lines[index].strip()[2:])
                index += 1
            output.append("<ul>%s</ul>" % "".join(
                "<li>%s</li>" % render_inline(item) for item in items))
            continue

        paragraph = []
        while index < len(lines) and lines[index].strip() and not re.match(
                r"^(#{1,4}\s|\||- )", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        output.append("<p>%s</p>" % render_inline(" ".join(paragraph)))

    return "\n".join(output)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{tagline}">
<style>
:root {{
  --bg: #ffffff; --panel: #f7f5fb; --ink: #1A1033; --muted: #5c5470;
  --line: #e3ddf0; --accent: #6B2FD9; --accent-soft: #f0e9fd;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #14101f; --panel: #1c1730; --ink: #ede9f7; --muted: #a79fc0;
    --line: #2e2745; --accent: #8B52E8; --accent-soft: #241d3c;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 860px; margin: 0 auto; padding: 0 24px 80px; }}
header {{ border-bottom: 1px solid var(--line); margin-bottom: 40px; padding: 56px 0 32px; }}
.eyebrow {{
  color: var(--accent); font-size: 12px; font-weight: 600;
  letter-spacing: .09em; text-transform: uppercase; margin: 0 0 12px;
}}
h1 {{ font-size: clamp(28px, 5vw, 40px); line-height: 1.15; margin: 0 0 12px; letter-spacing: -.02em; }}
.tagline {{ color: var(--muted); font-size: 18px; margin: 0 0 24px; max-width: 60ch; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
.btn {{
  display: inline-block; padding: 9px 16px; border-radius: 8px; font-size: 14px;
  font-weight: 600; text-decoration: none; background: var(--accent); color: #fff;
}}
.btn.ghost {{ background: transparent; color: var(--accent); border: 1px solid var(--line); }}
h2 {{
  font-size: 13px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
  color: var(--muted); margin: 44px 0 14px; padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}}
h3 {{ font-size: 18px; margin: 28px 0 10px; }}
p {{ margin: 0 0 16px; max-width: 68ch; }}
ul {{ margin: 0 0 16px; padding-left: 20px; max-width: 68ch; }}
li {{ margin-bottom: 8px; }}
code {{
  background: var(--accent-soft); color: var(--accent); padding: 2px 6px;
  border-radius: 4px; font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
.scroll {{ overflow-x: auto; margin: 0 0 20px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; min-width: 460px; }}
th, td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line); }}
th {{
  font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; background: var(--panel);
}}
tbody tr:last-child td {{ border-bottom: none; }}
td code {{ font-size: 12px; }}
footer {{
  margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 14px;
}}
footer code {{ font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="eyebrow">SEO automation</p>
  <h1>{title}</h1>
  <p class="tagline">{tagline}</p>
  <div class="actions">
    <a class="btn" href="{repo}">View the source</a>
    <a class="btn ghost" href="{repo}#readme">How it works</a>
  </div>
</header>
<main>
{body}
</main>
<footer>
  <p>This page is generated from the tool's own output. Reproduce it with
  <code>{command}</code> in the repository, then <code>python3 publish.py</code>.</p>
</footer>
</div>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT_FILE)
    parser.add_argument("--docs", type=Path, default=DOCS_DIR)
    args = parser.parse_args()

    if not args.report.exists():
        raise SystemExit("No report at %s. Run the tool first." % args.report)

    # Drop the report's own H1. The page header already states the title, and
    # two H1s on a page generated by an SEO tool would be an odd advert.
    source = re.sub(r"\A#\s+[^\n]*\n", "", args.report.read_text())
    body = render_markdown(source)
    args.docs.mkdir(parents=True, exist_ok=True)
    (args.docs / "index.html").write_text(PAGE.format(
        title=html.escape(PROJECT_TITLE), tagline=html.escape(PROJECT_TAGLINE),
        repo=REPO_URL, command=html.escape(RUN_COMMAND), body=body))
    # GitHub Pages runs a folder through Jekyll unless told not to.
    (args.docs / ".nojekyll").write_text("")
    print("Published %s" % (args.docs / "index.html"))


if __name__ == "__main__":
    main()
