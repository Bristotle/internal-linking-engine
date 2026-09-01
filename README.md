# internal-linking-engine

Finds the internal links a site should already have, by looking for places where
one page mentions another page's target keyword and does not link to it.

**Live output:** https://bristotle.github.io/internal-linking-engine/

Third in a series of SEO automation tools built around a game marketplace use
case, after [eneba-01-programmatic-seo](https://github.com/Bristotle/eneba-01-programmatic-seo)
(generate the pages) and [crawl-redirect-mapper](https://github.com/Bristotle/crawl-redirect-mapper)
(migrate the old site onto them).

[llm-metadata-qa-pipeline](https://github.com/Bristotle/llm-metadata-qa-pipeline)
closes the set: it writes the metadata those pages render, with quality gates
between the model and anything that publishes.

## The problem it solves

Programmatic SEO produces pages faster than anyone links to them. A generator
can publish 50,000 product pages in a build step, but internal linking is
usually left to a template rule, breadcrumbs plus related products, and that
rule links by category rather than by relevance. The result is a catalogue where
authority pools in the hubs, the long tail sits on one or two template links,
and pages nobody linked to at all are discoverable only through the sitemap.

Meanwhile the copy on those pages is already full of the right anchors. A
product description that mentions a rival title, a guide that names three games
it applies to, a hub that lists its own products in prose. Every one of those is
a link that was written and never made.

This engine finds them.

## What it does

1. **Builds the current link graph** from existing outlinks, ignoring self links
   and links to URLs outside the inventory.
2. **Scans visible copy for unlinked keyword mentions.** Existing anchors are
   removed before scanning, elements and all. Text already inside an `<a>`
   cannot host a second link, so proposing it would generate a change nobody can
   apply.
3. **Prefers the most specific anchor.** Where "elden ring ps5 key" and "elden
   ring" both match the same span, the specific one wins and the broader page
   does not get a claim on that text.
4. **Scores each proposal by need first, relevance second.** A perfect link into
   a page with eight inlinks changes very little. A decent link into an orphan
   changes whether that page gets crawled. Orphans are weighted accordingly,
   with genre match, primary keyword match and page type as tiebreakers, and a
   penalty for reciprocal pairs that would trap rank between two pages.
5. **Caps the result.** No more than 3 new links out of any page and 3 new
   inlinks into any target per pass. The failure mode of a tool like this is
   link stuffing, and a page that gains a dozen internal links in one run reads
   as machine generated.
6. **Models the effect** with internal PageRank before and after, so the value
   of the change set is a number rather than an assertion.

## The part it cannot fix, and says so

Some orphans have no inbound opportunity at all. Nothing on the site mentions
their keywords, so there is no anchor text to attach a link to. On the bundled
fixture that is all three guide pages.

The tool reports these separately, naming the hub that should own each topic and
a suggested anchor, rather than filing them under "still orphaned" and stopping.
That is a content gap, not a matching failure, and it needs a person to write a
sentence rather than a script to find one.

## Output

```
out/proposed_links.csv     source, target, anchor, priority
out/report.md              before and after summary, PageRank movers, change list
out/graph.json             every node with inlinks and PageRank before and after,
                           existing edges and proposed edges
out/orphan_actions.json    orphans that need a copy change, with a suggested source
docs/index.html            the report as a published page
```

Nothing is inserted automatically. The output is a change list for a person or a
CMS job to apply, which is deliberate. Anchor text is copy, and copy gets
reviewed.

## Running it

```bash
python3 link_engine.py
python3 publish.py
python3 -m unittest discover -s tests
```

Standard library only, no install step, 42 tests. Point `--pages` at a real
inventory export to run it against a live site.

## Result on the bundled fixture

12 pages, 15 existing internal links. The engine finds 13 unlinked mentions and
proposes all 13, taking the graph to 28 links.

The two most under linked product pages gain the most. Witcher 3 gains 113
percent internal PageRank and Elden Ring 107 percent, funded largely by the RPG
hub's share falling 11 percent. That redistribution is the point. Hub pages
accumulate rank by default and have the least need for it.
