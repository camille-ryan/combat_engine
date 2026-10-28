"""Build a story graph out of a module's pages, locally and for nothing.

    uv run scripts/ingest.py keep                 every page
    uv run scripts/ingest.py keep --pages 10-14   a chapter, to look first
    uv run scripts/ingest.py keep --dry           extract, report, write nothing

`docs/STORY_GRAPH.md` is the design. This is the stage that turns an
adventure's prose into entities with facts, each fact carrying a verbatim
quote and the page it came from, so the DM can be asked "who is this" and
answer out of the book or honestly say nobody knows (#830).

**Local and free, which is a design constraint rather than a convenience.**
The project this borrows from spent $256 on cloud OCR and extraction, and
hit a spending limit by surprise. Two things make the local version
possible:

* **no OCR stage.** 134 of the 154 pages of the module in hand carry a text
  layer, median 2,730 characters. The books that needed GPT-4o vision were
  scans; a digital PDF needs `pypdf` and nothing else.
* **structured output is free** through ollama's `format`, which takes a
  JSON Schema outright. The schema is a guarantee rather than something to
  validate and retry, which is the same mechanism the affordance matcher
  already rests on.

Measured on three real pages: 20, 15 and 14 entities, schema honoured every
time.

## The quote is the point, and it is checked

A fact without a verbatim quote cannot be audited later, so every one is
matched back against the page by **climbing fuzzy match** -- exact first,
then one edit at a time to a hard cap. On a hit the **document's span
replaces the model's text**, so what is stored is what the page says,
hyphenation and all.

    max edits   recovered     wrong page
            0    33/49  67%    0/98   0%
            2    46/49  94%    0/98   0%
            4    47/49  96%    0/98   0%

The knee is at two edits and the negative control is flat zero throughout:
98 attempts to match a quote against a page it did not come from, not one
false hit, even at eight edits. The 4% that never recovers is paraphrase
rather than hallucination -- a third-person restatement of a line the page
prints as dialogue -- and dropping it is right.

Climbing from exact also matters for cost. An error budget set as a
fraction of the quote's length gives a 200-character quote 40 edits, and
one pass at that width over a page does not finish.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from combat_engine.db import ROOT
from combat_engine.story import graph as gr
from combat_engine.story import llm

MODULES = ROOT / "modules"

#: Hard ceiling on the edits a quote may need. Ten is Camille's number and
#: the curve above says the useful range ends around four.
CAP = 10

#: What the extractor is asked for. `kind` is an enum so it cannot invent a
#: taxonomy, which is the one thing `format` makes free.
SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"enum": list(gr.KINDS)},
                    "quote": {"type": "string"},
                },
                "required": ["name", "kind", "quote"],
            },
        }
    },
    "required": ["entities"],
}

#: **The quote is the fact.** The first version asked for a one-sentence
#: gloss as well, and the model filled it with the entity's own name --
#: the entity's name where a description belonged -- in **38 of 38**
#: cases, while putting the real
#: sentence in the quote. Rather than argue with it, the gloss was deleted:
#: the page's own sentence is better than a paraphrase of it, is already
#: validated against the source, and removes the only place in this stage
#: where the model could write something the adventure does not say.
#:
#: What is left is extraction and not generation. The model's whole job is
#: to point at a span and say who it is about.
SYSTEM = """\
You read one page of a tabletop adventure and list what it names.

For each person, place, thing, group, creature or idea the page names,
give its name exactly as the page spells it, what kind of thing it is, and
**one sentence copied from the page** that says something about it.

Copy the sentence word for word. Do not tidy it, do not shorten it, do not
join two sentences, do not write your own. If there is no sentence on the
page you can copy, leave that entity out.

Skip page furniture: headings, chapter titles, page numbers, product
names, and the labels of rules tables.

Write in English."""


#: Curly punctuation the page uses and a model does not. Written as escapes
#: rather than literals because `ruff` reads a bare curly quote in source as
#: an ambiguous character, which it is.
CURLY = {"\u2019": "'", "\u2018": "'", "\u201c": '"',
         "\u201d": '"', "\u2014": "-", "\u2013": "-"}


def _fold(text: str) -> str:
    """Normalise the two sides so only real differences survive.

    The page is typeset and the model types ASCII, so a quote that is
    word-for-word right still fails a strict match on punctuation alone.
    Folding both sides first is what makes the edit budget below mean
    edits rather than apostrophes.
    """
    text = unicodedata.normalize("NFKC", text)
    for curly, plain in CURLY.items():
        text = text.replace(curly, plain)
    return " ".join(text.split())


def ground(quote: str, page: str) -> tuple[str, int] | None:
    """The page's own words for this quote, and the edits it took.

    `None` when the page does not contain it at any budget, which is the
    honest answer for a paraphrase and the reason the check exists.
    """
    try:
        import regex
    except ImportError:
        # The stdlib `re` has no fuzzy matching, and without it every quote
        # the page punctuates differently is dropped -- which would report
        # a 67% keep rate as if it were the model's fault.
        raise SystemExit(
            "the fuzzy quote check needs the `regex` package.\n"
            "Run: uv sync --extra modules"
        ) from None

    want, hay = _fold(quote), _fold(page)
    if len(want) < 12:
        return None
    if want in hay:
        return want, 0
    for budget in range(1, CAP + 1):
        hit = regex.search(f"(?:{regex.escape(want)}){{e<={budget}}}", hay)
        if hit:
            return hit.group(0), budget
    return None


#: Names that are page furniture rather than things in the world. The
#: prompt asks the model to skip these and it mostly does not: one run
#: offered a chapter heading, a product title, a rules-table label and a
#: four-digit code off a page footer.
FURNITURE = re.compile(
    r"^(chapter|part|appendix|encounter|session|table|sidebar)\b"
    r"|^[a-z]?\d{2,}$"
    r"|\blevel \d+ \(", re.I)


def _furniture(name: str) -> bool:
    return bool(FURNITURE.search(name.strip()))


#: Kinds that can be rules vocabulary rather than something in the world.
#:
#: A `thing` or an `idea` named by the rules -- "cold damage", "close blast
#: 3", "action points" -- is mechanical vocabulary the extractor picked off
#: a stat block, and an entity for it only adds noise to a prompt. A
#: `creature`, `person`, `place` or `group` is **not** filtered even when
#: the rules name it: a monster that has a stat block is still a monster in
#: this adventure, and dropping it would lose a real opponent.
#:
#: Measured on chapter 1: nine of 134 names are rules phrases, and the
#: split is exactly along this line -- eight `thing`s that are vocabulary,
#: and one `creature` that is an actual opponent.
MECHANICAL = ("thing", "idea")


def _rules_vocabulary() -> set[str]:
    """Two- and three-word phrases the rules themselves use."""
    from combat_engine.db import game

    out: set[str] = set()
    try:
        db = game()
    except Exception:
        return out
    for table in ("power", "monster_power", "class_feature", "item"):
        cols = [r[1] for r in db.execute(f"pragma table_info({table})")]
        if "spec" not in cols:
            continue
        for (spec,) in db.execute(f"select spec from {table}"):
            words = re.findall(r"[a-z]+", (spec or "").lower())
            out |= {
                " ".join(words[i:i + n])
                for n in (2, 3)
                for i in range(len(words) - n + 1)
            }
    return out


def _pages(spec: str, total: int) -> list[int]:
    if not spec:
        return list(range(total))
    lo, _, hi = spec.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def read_page(folder: Path, n: int) -> str:
    where = folder / "pages" / f"{n:04d}.txt"
    return where.read_text() if where.exists() else ""


def harvest(folder: Path, pages: list[int], role: llm.Role,
            *, say: bool = True) -> tuple[gr.Graph, dict]:
    """Every page through the extractor, every quote checked, into a graph."""
    graph = gr.Graph()
    vocabulary = _rules_vocabulary()
    tally = {"pages": 0, "offered": 0, "kept": 0, "unquotable": 0,
             "mended": 0, "mechanical": 0, "seconds": 0.0}
    for n in pages:
        text = read_page(folder, n)
        if len(text.strip()) < 200:
            continue
        tally["pages"] += 1
        started = time.monotonic()
        got = llm.structured(role, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"THE PAGE:\n\n{text}"},
        ], SCHEMA)
        tally["seconds"] += time.monotonic() - started
        for item in got.get("entities") or []:
            tally["offered"] += 1
            name = str(item.get("name", "")).strip()
            if not name or _furniture(name):
                continue
            kind = str(item.get("kind", "person"))
            if kind in MECHANICAL and " ".join(
                    re.findall(r"[a-z]+", name.lower())) in vocabulary:
                tally["mechanical"] += 1
                continue
            found = ground(str(item.get("quote", "")), text)
            if found is None:
                # **Dropped, not stored unverified.** A fact that cannot be
                # pointed at a page is exactly what this layer exists to
                # keep out; storing it as canon would launder the model's
                # paraphrase into the adventure's voice.
                tally["unquotable"] += 1
                continue
            span, edits = found
            tally["mended"] += bool(edits)
            tally["kept"] += 1
            graph.add(gr.Entity(
                id=gr._slug(name), name=name,
                kind=kind,
                facts=[gr.Fact(text=span, source="page", where=f"p{n}",
                               quote=span)]))
        if say:
            print(f"  p{n:<4} {tally['kept']:4} kept  "
                  f"{tally['unquotable']:3} unquotable  "
                  f"{tally['seconds']:5.0f}s", flush=True)
    return graph, tally


# **Names are reconciled, with a tail rule rather than a model.** One run
# produced a banker under his surname and his full name, and a keep under
# its short and full name. `graph.reconcile` folds a one-word name into
# the long name it is the *last* word of, when the kinds agree -- the
# surname and head-noun pattern -- and keeps the short form as an alias,
# so nothing is lost if the rule is ever wrong.
#
# A model verifier is the thing to add when a second source arrives, not
# now: across twenty-seven books two deities one letter apart are
# different people, and inside one adventure the tail rule is exact. #903.


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("module", help="a folder under modules/")
    ap.add_argument("--pages", default="", help="e.g. 10-14. Default: all")
    ap.add_argument("--model", default="deepseek-r1:14b")
    ap.add_argument("--host", default="")
    ap.add_argument("--dry", action="store_true",
                    help="extract and report, write nothing")
    args = ap.parse_args()

    folder = MODULES / args.module
    if not (folder / "pages").is_dir():
        raise SystemExit(
            f"no pages under {folder}. Import the module first:\n"
            f"  uv run scripts/play.py --import <pdf> --id {args.module}")

    # A reasoning model spends its budget thinking before it answers; 200
    # tokens bought 906 characters of thought and an empty string. 4,000
    # covers a page's worth of entities as well as the thinking.
    role = llm.Role(model=args.model, temperature=0.0, num_ctx=16384,
                    max_tokens=4000, timeout=900,
                    **({"base_url": args.host} if args.host else {}))
    why = llm.reachable(role)
    if why:
        raise SystemExit(why)

    # Pay the cold load here, where it is a line on the screen, rather than
    # inside the first page where it is indistinguishable from a hang. The
    # 9 GB model took 3m26s to load and 5s a call after that.
    print(f"warming {role.model}...", end="", flush=True)
    print(f" {llm.warm(role):.0f}s")

    total = len(list((folder / "pages").glob("*.txt")))
    pages = _pages(args.pages, total)
    print(f"{args.module}: {len(pages)} of {total} pages, {role.model} "
          f"at {role.base_url.split('//')[-1]}\n")

    graph, tally = harvest(folder, pages, role)

    print(f"\n{tally['pages']} pages with text")
    print(f"  {tally['offered']:5} entities offered")
    print(f"  {tally['kept']:5} kept, with a quote found on the page")
    print(f"  {tally['mended']:5} of those needed a fuzzy match to find")
    print(f"  {tally['unquotable']:5} dropped: no such words on the page")
    print(f"  {tally['mechanical']:5} dropped: rules vocabulary, not this "
          f"adventure's")
    folded = gr.reconcile(graph)
    for short, long in folded:
        print(f"      folded {short!r} into {long!r}")
    print(f"  {len(graph.entities):5} distinct entities after merging")
    if tally["offered"]:
        print(f"  {tally['kept'] / tally['offered']:.0%} of what the model "
              f"offered could be pointed at the page")
    print(f"  {tally['seconds']:.0f}s")

    if args.dry:
        print("\n--dry: nothing written")
        return 0
    where = folder / "graph.json"
    gr.save(graph, where)
    print(f"\nwrote {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
