#!/usr/bin/env python3
"""Propose internal links from unlinked keyword mentions already in the copy.

Reads a page inventory (URL, target keywords, body copy, existing outlinks),
builds the current internal link graph, finds pages that mention another page's
target keyword without linking to it, and proposes the links that would do the
most good -- measured by internal PageRank before and after.

Every proposal is anchored to text that already exists on the page. Nothing
here invents copy, and nothing is inserted automatically; the output is a
change list for a human or a CMS job to apply.

Standard library only. Run: python3 link_engine.py
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
PAGES_FILE = ROOT / "data" / "pages.json"
OUTPUT_DIR = ROOT / "out"

# Caps exist because the failure mode of this tool is link stuffing. A page
# that gains twelve new internal links in one pass reads as machine-generated
# and dilutes every link already on it.
MAX_NEW_LINKS_PER_PAGE = 3
MAX_NEW_INLINKS_PER_TARGET = 3

# PageRank settings. Damping is the conventional 0.85; the iteration count is
# generous for graphs this size and converges long before it is reached.
DAMPING = 0.85
ITERATIONS = 100
TOLERANCE = 1e-10

# A page with fewer inlinks than this is treated as under-linked and its
# proposals are prioritised. Orphans (zero inlinks) are the acute case: a page
# nothing links to is a page crawlers reach only via the sitemap, if at all.
UNDER_LINKED_THRESHOLD = 2

ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def visible_text(body):
    """Return body copy with existing anchors and their text removed.

    Text already inside an <a> is unavailable as an anchor for a new link, so
    scanning it would produce proposals that cannot be applied. Removing the
    whole element rather than just the tags is deliberate.
    """
    without_anchors = ANCHOR_RE.sub(" ", body)
    return TAG_RE.sub(" ", without_anchors)


def keyword_positions(text, keyword):
    """Find whole-phrase, case-insensitive occurrences of a keyword."""
    pattern = re.compile(r"\b" + r"\s+".join(re.escape(word) for word in keyword.split()) + r"\b",
                         re.IGNORECASE)
    return [match.span() for match in pattern.finditer(text)]


def build_graph(pages):
    """Return adjacency and reverse-adjacency maps over known URLs only."""
    known = {page["url"] for page in pages}
    outlinks = {}
    inlinks = defaultdict(set)
    for page in pages:
        targets = {link for link in page.get("outlinks", [])
                   if link in known and link != page["url"]}
        outlinks[page["url"]] = targets
        for target in targets:
            inlinks[target].add(page["url"])
    return outlinks, {url: inlinks[url] for url in known}


def pagerank(outlinks, damping=DAMPING, iterations=ITERATIONS, tolerance=TOLERANCE):
    """Internal PageRank over the link graph.

    Dangling pages (no outlinks) have their rank redistributed across the whole
    graph rather than dropped. Dropping it silently leaks rank each iteration
    and makes before/after comparisons meaningless, which is the one thing this
    function exists to support.
    """
    urls = list(outlinks)
    count = len(urls)
    if count == 0:
        return {}
    rank = {url: 1.0 / count for url in urls}

    for _ in range(iterations):
        dangling_mass = sum(rank[url] for url in urls if not outlinks[url])
        updated = {url: (1.0 - damping) / count + damping * dangling_mass / count
                   for url in urls}
        for url in urls:
            targets = outlinks[url]
            if not targets:
                continue
            share = damping * rank[url] / len(targets)
            for target in targets:
                updated[target] += share
        delta = sum(abs(updated[url] - rank[url]) for url in urls)
        rank = updated
        if delta < tolerance:
            break
    return rank


def find_opportunities(pages):
    """Every unlinked mention of another page's keyword, scored."""
    by_url = {page["url"]: page for page in pages}
    outlinks, inlinks = build_graph(pages)

    # Longest keywords first so "elden ring ps5 key" wins over "elden ring"
    # and the more specific anchor is the one proposed.
    keyword_index = []
    for page in pages:
        keywords = [page["target_keyword"]] + list(page.get("secondary_keywords", []))
        for rank_position, keyword in enumerate(keywords):
            keyword_index.append({
                "keyword": keyword,
                "target": page["url"],
                "is_primary": rank_position == 0,
            })
    keyword_index.sort(key=lambda entry: len(entry["keyword"]), reverse=True)

    opportunities = []
    for page in pages:
        source = page["url"]
        text = visible_text(page.get("body", ""))
        claimed = []  # character spans already taken by a longer keyword

        for entry in keyword_index:
            target = entry["target"]
            if target == source:
                continue
            if target in outlinks[source]:
                continue  # already linked, nothing to propose

            for start, end in keyword_positions(text, entry["keyword"]):
                if any(start < c_end and end > c_start for c_start, c_end in claimed):
                    continue
                claimed.append((start, end))
                target_page = by_url[target]
                opportunities.append({
                    "source": source,
                    "target": target,
                    "anchor": text[start:end],
                    "is_primary_keyword": entry["is_primary"],
                    "same_genre": bool(page.get("genre"))
                                  and page.get("genre") == target_page.get("genre"),
                    "target_inlinks": len(inlinks[target]),
                    "target_type": target_page["type"],
                    "reciprocal": source in outlinks[target],
                })
                break  # one link per source/target pair, not per mention

    for opportunity in opportunities:
        opportunity["priority"] = score_opportunity(opportunity)
    opportunities.sort(key=lambda o: o["priority"], reverse=True)
    return opportunities, outlinks, inlinks


def score_opportunity(opportunity):
    """Rank a proposal by how much the link is needed, then how relevant it is.

    Need dominates relevance on purpose. A perfectly relevant link into a page
    that already has eight inlinks changes very little; a decent link into an
    orphan changes whether that page is crawled at all.
    """
    score = 0.0

    if opportunity["target_inlinks"] == 0:
        score += 1.0  # orphan, the acute case
    elif opportunity["target_inlinks"] < UNDER_LINKED_THRESHOLD:
        score += 0.6

    if opportunity["is_primary_keyword"]:
        score += 0.3  # exact target keyword is the strongest relevance signal
    if opportunity["same_genre"]:
        score += 0.2
    if opportunity["target_type"] == "product":
        score += 0.1  # products are what the site is trying to rank and sell
    if opportunity["reciprocal"]:
        score -= 0.15  # a pair linking only to each other traps rank between them

    return round(score, 3)


def apply_caps(opportunities):
    """Keep the highest-priority proposals within the per-page and per-target caps."""
    accepted = []
    rejected = []
    per_source = defaultdict(int)
    per_target = defaultdict(int)

    for opportunity in opportunities:
        source, target = opportunity["source"], opportunity["target"]
        if per_source[source] >= MAX_NEW_LINKS_PER_PAGE:
            opportunity["rejected_because"] = "source page already at its cap of %d new links" % MAX_NEW_LINKS_PER_PAGE
            rejected.append(opportunity)
            continue
        if per_target[target] >= MAX_NEW_INLINKS_PER_TARGET:
            opportunity["rejected_because"] = "target already receiving %d new inlinks this pass" % MAX_NEW_INLINKS_PER_TARGET
            rejected.append(opportunity)
            continue
        per_source[source] += 1
        per_target[target] += 1
        accepted.append(opportunity)

    return accepted, rejected


def orphan_actions(pages, orphans_after, outlinks):
    """Recommend a source for each orphan the copy cannot resolve on its own.

    An orphan survives this pass when no other page mentions its keywords, so
    there is no existing anchor text to attach a link to. That is not a failure
    of the matcher, it is a content gap, and it needs a different fix: a
    deliberate link from the hub that owns the topic. Reporting these as
    "still orphaned" and stopping would leave the useful half unsaid.
    """
    by_url = {page["url"]: page for page in pages}
    hubs = {page.get("genre"): page["url"] for page in pages if page["type"] == "hub"}
    home = next((page["url"] for page in pages if page["type"] == "home"), None)

    actions = []
    for url in sorted(orphans_after):
        page = by_url[url]
        source = hubs.get(page.get("genre")) or home
        if source is None or source == url:
            continue
        actions.append({
            "orphan": url,
            "suggested_source": source,
            "suggested_anchor": page["target_keyword"],
            "reason": "no page mentions this page's keywords, so no anchor exists "
                      "to link from; add one deliberately",
        })
    return actions


def write_outputs(pages, accepted, rejected, outlinks, inlinks, before, after, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    by_url = {page["url"]: page for page in pages}

    lines = ["source,target,anchor,priority,target_inlinks_before"]
    for o in accepted:
        lines.append('"%s","%s","%s",%s,%d' % (
            o["source"], o["target"], o["anchor"].replace('"', '""'),
            o["priority"], o["target_inlinks"]))
    (output_dir / "proposed_links.csv").write_text("\n".join(lines) + "\n")

    (output_dir / "graph.json").write_text(json.dumps({
        "nodes": [
            {
                "url": url,
                "title": by_url[url]["title"],
                "type": by_url[url]["type"],
                "inlinks_before": len(inlinks[url]),
                "pagerank_before": round(before[url], 6),
                "pagerank_after": round(after[url], 6),
                "pagerank_change_pct": round(
                    (after[url] - before[url]) / before[url] * 100, 1) if before[url] else 0.0,
            }
            for url in sorted(outlinks)
        ],
        "edges_existing": [{"source": s, "target": t}
                           for s in sorted(outlinks) for t in sorted(outlinks[s])],
        "edges_proposed": [{"source": o["source"], "target": o["target"],
                            "anchor": o["anchor"]} for o in accepted],
    }, indent=2))

    orphans_before = [url for url in outlinks if not inlinks[url]]
    gained = {o["target"] for o in accepted}
    orphans_after = [url for url in orphans_before if url not in gained]

    movers = sorted(
        outlinks,
        key=lambda url: (after[url] - before[url]) / before[url] if before[url] else 0,
        reverse=True)

    report = [
        "# Internal linking report",
        "",
        "| | Before | After |",
        "| --- | --- | --- |",
        "| Internal links | %d | %d |" % (
            sum(len(t) for t in outlinks.values()),
            sum(len(t) for t in outlinks.values()) + len(accepted)),
        "| Orphan pages | %d | %d |" % (len(orphans_before), len(orphans_after)),
        "",
        "%d proposals accepted, %d held back by the per-page and per-target caps."
        % (len(accepted), len(rejected)),
        "",
        "## Orphan pages before this pass",
        "",
    ]
    if orphans_before:
        for url in sorted(orphans_before):
            status = "resolved" if url in gained else "still orphaned"
            report.append("- `%s` (%s) -- %s" % (url, by_url[url]["type"], status))
    else:
        report.append("None.")

    report += ["", "## Largest PageRank gains", "",
               "| Page | Before | After | Change |", "| --- | --- | --- | --- |"]
    for url in movers[:6]:
        change = (after[url] - before[url]) / before[url] * 100 if before[url] else 0.0
        report.append("| `%s` | %.4f | %.4f | %+.1f%% |" % (
            url, before[url], after[url], change))

    report += ["", "## Proposed links", "",
               "| Source | Anchor | Target | Priority |", "| --- | --- | --- | --- |"]
    for o in accepted:
        report.append("| `%s` | %s | `%s` | %.2f |" % (
            o["source"], o["anchor"], o["target"], o["priority"]))

    actions = orphan_actions(pages, orphans_after, outlinks)
    if actions:
        report += ["", "## Orphans needing a copy change", "",
                   "These cannot be fixed from existing text. Nothing on the site "
                   "mentions their keywords, so there is no anchor to attach a link "
                   "to. Each needs a link added deliberately, from the page that "
                   "owns the topic.", "",
                   "| Orphan | Add a link from | Suggested anchor |",
                   "| --- | --- | --- |"]
        for action in actions:
            report.append("| `%s` | `%s` | %s |" % (
                action["orphan"], action["suggested_source"], action["suggested_anchor"]))
        (output_dir / "orphan_actions.json").write_text(json.dumps(actions, indent=2))

    if rejected:
        report += ["", "## Held back by caps", ""]
        for o in rejected:
            report.append("- `%s` -> `%s` (%s) -- %s" % (
                o["source"], o["target"], o["anchor"], o["rejected_because"]))

    (output_dir / "report.md").write_text("\n".join(report) + "\n")
    return orphans_before, orphans_after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=PAGES_FILE)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    pages = json.loads(args.pages.read_text())
    opportunities, outlinks, inlinks = find_opportunities(pages)
    accepted, rejected = apply_caps(opportunities)

    before = pagerank(outlinks)
    projected = {url: set(targets) for url, targets in outlinks.items()}
    for o in accepted:
        projected[o["source"]].add(o["target"])
    after = pagerank(projected)

    orphans_before, orphans_after = write_outputs(
        pages, accepted, rejected, outlinks, inlinks, before, after, args.out)

    print("Pages:              %d" % len(pages))
    print("Existing links:     %d" % sum(len(t) for t in outlinks.values()))
    print("Opportunities:      %d" % len(opportunities))
    print("Proposed (capped):  %d" % len(accepted))
    print("Orphans:            %d -> %d" % (len(orphans_before), len(orphans_after)))
    print("Written to %s" % args.out)


if __name__ == "__main__":
    main()
