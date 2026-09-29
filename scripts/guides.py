#!/usr/bin/env python
"""Read community option ratings out of the optimisation guides.

    uv run scripts/guides.py                 report what resolves, and how well
    uv run scripts/guides.py --emit          write ratings.py and notes/
    uv run scripts/guides.py --guide NAME    just one

The community has rated 4e's options on a six-colour scale for fifteen years,
and this project cannot currently rank any of them: every weight in
`chargen/choices.py` is a number somebody invented, and #213 asks for a scorer
that is "doctrine based". A guide's colour is doctrine, written down by somebody
who played the class.

**What crosses into the repository, and what does not.** The output is
`(ref, class) -> number` and a source URL. Keyed by the *guide's* class, because
a race or feat is class-agnostic and gets rated in a class context: gold for an
Intelligence class is red for a Charisma one, which is two correct answers rather
than a disagreement. No prose, ever: the guides are authored text
and the names in them are the thing this whole project is arranged to keep out.
So the fetched HTML lands in git-ignored `.cache/`, the reasoning lands in
git-ignored `notes/`, and `scripts/leaks.py` is what proves nothing slipped.

Resolution is an exact match on a normalised name, and that is enough because of
a measurement rather than a hope:

    powers   4,243 refs -> 4,243 distinct names   0 collisions
    items    1,883 refs -> 1,882                  1 collision
    feats    3,501 refs -> 3,368                  133 names shared by two refs

So no fuzzy matching, no confidence threshold, no reject list. A power name
identifies a power. Only feats can be ambiguous, and those are reported rather
than guessed at.

**Every guide needs its own colour map.** The scale is conventional but the
hexes are not -- the wizard handbook's author says outright that the shades were
picked to suit photosensitive eyes, and uses a teal for sky blue where another
guide uses a pale blue. Each guide states its key in its own words, so the map
is read off that and recorded here by hand. Guessing a tier from a hue is how
a red gets scored as a gold.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CACHE = ROOT / ".cache" / "guides"
NOTES = ROOT / "notes"
NAMES = ROOT / "localization" / "names.json"

#: The six tiers, and what a colour is worth. `black` is the rated average;
#: an option no guide mentions scores `UNRATED`, just below it -- a guide's
#: silence is weaker evidence than a guide's "average", and not evidence of
#: badness.
TIERS: dict[str, float] = {
    "red": 0.0,        # do not take this
    "purple": 1.5,     # outclassed, or only good situationally
    "black": 3.0,      # middle of the road
    "blue": 4.0,       # good
    "sky": 5.0,        # cream of the crop
    "gold": 6.0,       # mandatory, or a tax on the character
}
UNRATED = 2.5

#: Not a tier. Several guides use green for "a different kind of useful", and
#: the wizard handbook's key says so outright: *a lot of non-combat options fall
#: here*. That is this project's `narrative=` and `out_of_combat=True` category,
#: so green is recorded and **excluded from the combat score** rather than
#: ranked against things it is not comparable to.
OUT_OF_COMBAT = "green"

#: Also not a tier. One guide adds an "Expected Table Variation" code for
#: options that are "either unclear or won't be allowed at every table" -- a
#: judgement about the group rather than about the option. Recorded and kept out
#: of the score, the same way green is.
TABLE_DEPENDENT = "pink"

#: Ref prefixes a rating is kept for. Everything else in `names.json` is
#: indexed anyway, so a coloured run naming it is reported as **out of scope**
#: rather than as a failure to resolve -- which is the difference between "this
#: instrument is not working" and "this project does not implement paragon
#: paths". `x` alone is 4,876 entries with no table in `game.db` at all.
RATEABLE = ("p", "f", "i", "r")

#: Indexed for classification only, so a miss can be named.
KINDS = {"p": "power", "f": "feat", "i": "item", "r": "race",
         "m": "monster", "x": "not imported", "t": "trap", "q": "prereq",
         "cf": "class feature", "comp": "companion"}


#: The words a guide writes its own key in. Nearly every guide states the key
#: near the top and writes each colour word *in that colour*, which is what makes
#: the map derivable instead of hand-entered -- 50 guides would otherwise be 50
#: manual steps. Verified on two hosts: the derived map agreed with the
#: hand-recorded one on 6 of 6 entries.
LEGEND_WORDS = {
    "red": "red", "purple": "purple", "black": "black", "blue": "blue",
    "sky blue": "sky", "skyblue": "sky", "light blue": "sky", "cyan": "sky",
    "teal": "sky", "gold": "gold", "orange": "gold", "yellow": "gold",
    "green": OUT_OF_COMBAT, "pink": TABLE_DEPENDENT,
}
# Deliberately not guessed: "magenta" and "violet" were mapped to purple here on
# the assumption that a purple-ish word means the purple tier. The second guide
# read uses that exact colour for "GM/Table dependent", which is not a tier at
# all. Inferring a tier from a colour *word* is the same mistake as inferring one
# from a hue, and this is where it would have gone wrong.


@dataclass
class Guide:
    """One guide, and the colour key it states for itself."""

    url: str
    #: The class it is about, or "" for a cross-cutting guide. Used as a
    #: correctness check rather than a filter: a wizard guide resolving to a
    #: fighter power is a false positive, and that is measurable without anybody
    #: reading a name.
    cls: str
    #: Hex -> tier **overrides**, on top of what `legend()` derives from the
    #: guide's own stated key. Only needed where the legend's swatch differs
    #: from what the body actually uses -- the wizard handbook writes "Sky Blue"
    #: in one teal and rates with another.
    colours: dict[str, str] = field(default_factory=dict)
    #: Where the text is. `enworld` reads inline styles and `<b>`; `gdocs` has
    #: to go through the export endpoint and read CSS classes, because the
    #: /edit URL serves 1.7MB of editor JavaScript and no content at all.
    host: str = "enworld"
    #: Which posts hold the guide proper. Replies are other people's opinions.
    posts: tuple[int, ...] = (0,)
    note: str = ""


GUIDES: dict[str, Guide] = {
    # States its key in full, and explains the green: "Something not easily
    # compared to others, or of a different kind of useful. A lot of non-combat
    # options fall here."
    "wizard": Guide(
        url="https://www.enworld.org/threads/"
            "archmages-ascension-the-4e-wizards-handbook-ruinsfate.471408/",
        cls="wizard",
        note="shades chosen for photosensitive eyes; teal is this guide's sky blue",
        # The legend writes "Sky Blue" in #00ccff and then rates with #33cccc.
        # The derived key cannot see that, so it is the one override needed.
        colours={"#33cccc": "sky"},
    ),
    # Labelled a seeker guide in the index; it is a warlock guide. The
    # class-agreement check caught it at once -- 180 of 182 "strays" were warlock
    # rows -- which is the whole reason that check exists.
    "warlock": Guide(
        url="https://docs.google.com/document/d/"
            "117rZcbx32PrhfHVcWMqm4UcgfkiLdWNqRzwH8Sg7hXk/edit",
        cls="warlock",
        host="gdocs",
        note="adds a seventh code, pink, for table-dependent options",
    ),
}

_WORD = re.compile(r"[^a-z0-9 ]+")


def norm(s: str) -> str:
    """A name reduced to what two spellings of it have in common."""
    s = s.lower().replace("&amp;", "&").replace("\u2019", "'")
    s = s.replace("'", "").replace("-", " ").replace("/", " ")
    return " ".join(_WORD.sub(" ", s).split())


def source_url(guide: Guide) -> str:
    """Where the text actually is.

    A Google Docs `/edit` link serves the editor: 1.7MB of application
    JavaScript, no `<b>` elements and no document content. The export endpoint
    serves the real thing.
    """
    if guide.host != "gdocs":
        return guide.url
    m = re.search(r"/document/d/([A-Za-z0-9_-]+)", guide.url)
    if m is None:
        return guide.url
    return f"https://docs.google.com/document/d/{m.group(1)}/export?format=html"


def fetch(guide: Guide, name: str) -> str:
    """The page, from `.cache/` if it is there. One fetch per guide, ever."""
    CACHE.mkdir(parents=True, exist_ok=True)
    at = CACHE / f"{name}.html"
    if not at.exists():
        req = urllib.request.Request(
            source_url(guide),
            headers={"User-Agent": "combat_engine research (ratings)"})
        with urllib.request.urlopen(req, timeout=90) as fh:
            at.write_bytes(fh.read())
    return at.read_text(errors="replace")


@dataclass
class Index:
    """Normalised printed name -> ref, built from the git-ignored names file.

    **The only thing here that sees a name.** It is held in memory, never
    written anywhere, and nothing downstream carries more than a ref.
    """

    by_name: dict[str, list[str]] = field(default_factory=dict)
    kind_of: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Index:
        if not NAMES.exists():
            raise SystemExit(
                "localization/names.json is missing, so no rating can be "
                "attached to a ref. Build it from your own compendium first.")
        raw = json.loads(NAMES.read_text())
        by_name: dict[str, list[str]] = defaultdict(list)
        kind: dict[str, str] = {}
        for ref, v in raw.items():
            printed = v.get("name") if isinstance(v, dict) else None
            if not printed:
                continue
            by_name[norm(printed)].append(ref)
            pre = "cf" if ref.startswith("cf") else (
                "comp" if ref.startswith("comp") else ref[0])
            kind[ref] = KINDS.get(pre, pre)
        return cls(dict(by_name), kind)

    def find(self, text: str) -> tuple[str | None, str]:
        """The ref a coloured run names, and why it failed when it does.

        A coloured span is usually the name and then some prose, so the leading
        word-runs are tried longest first. Longest first matters: a short name
        that is also the start of a longer one would otherwise win.
        """
        words = norm(text).split()
        if not words:
            return None, "empty"
        for n in range(min(len(words), 9), 0, -1):
            got = self.by_name.get(" ".join(words[:n]))
            if not got:
                continue
            if len(got) == 1:
                return got[0], "ok"
            # **A collision is usually not one.** Widening the index to every
            # prefix so a miss could be named also made a power that shares a
            # monster's name ambiguous, which took the figure from 6 to 63. A
            # guide rates options, so a rateable prefix wins outright.
            prefer = [r for r in got if self._pre(r) in RATEABLE]
            if len(prefer) == 1:
                return prefer[0], "ok"
            if not prefer:
                return got[0], "ok"          # all out of scope; caller reports
            return None, "ambiguous"
        return None, "no match"

    @staticmethod
    def _pre(ref: str) -> str:
        if ref.startswith("cf"):
            return "cf"
        return "comp" if ref.startswith("comp") else ref[0]


_COL = re.compile(r"(?<!background-)color:\s*(#[0-9a-f]{3,6})")
#: Grey and near-black are body text, not a rating.
NEUTRAL = ("#000000", "#434343", "#666666", "#333333", "#222222", "#111111")


def gdoc_styles(body: str) -> dict[str, tuple[str | None, bool]]:
    """Google Docs puts bold and colour in class definitions, not on elements."""
    out: dict[str, tuple[str | None, bool]] = {}
    for name, decls in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", body):
        flat = decls.replace(" ", "")
        m = re.search(r"(?<!background-)color:(#[0-9a-f]{6})", flat)
        out[name] = (m.group(1) if m else None, "font-weight:700" in flat)
    return out


def legend(doc, colour_of) -> dict[str, str]:  # noqa: ANN001
    """The guide's own key, read off the colour words it wrote in colour.

    Takes the first colour each word appears in, so a later mention of the word
    in ordinary prose cannot overwrite the swatch.
    """
    found: dict[str, str] = {}
    for el in doc.xpath("//*"):
        txt = " ".join((el.text_content() or "").split()).strip().lower()
        txt = txt.rstrip(":").strip()
        if txt in LEGEND_WORDS and len(txt) <= 12:
            c = colour_of(el)
            if c and c not in NEUTRAL:
                found.setdefault(c, LEGEND_WORDS[txt])
    return found


def tint(el) -> str | None:  # noqa: ANN001
    """The nearest colour this element or an ancestor sets.

    Ancestors matter: the colour is on a wrapping span and the name is in a
    `<b>` inside it, so reading the bold element's own style finds nothing.
    """
    cur = el
    while cur is not None:
        m = _COL.search((cur.get("style") or "").lower())
        if m:
            return m.group(1)
        cur = cur.getparent()
    return None


def options(html: str, guide: Guide) -> tuple[list[tuple[str, str, int]],
                                              dict[str, str], Counter]:
    """(tier, text, post) for every option the guide names, plus its key.

    **Bold is the anchor, not colour.** An option's name is bold; a colour is
    wrapped around it only when the author is rating it away from average. So
    walking the colours alone finds every rating except the commonest -- black,
    the default, which carries no colour and which the first version of this
    missed entirely. Measured on the wizard handbook: 419 bold names sit inside a
    colour and 152 do not, and those 152 are the blacks.

    Bold is the cleaner anchor for a second reason: a coloured span often runs on
    into the prose after the name, where the bold element is the name and stops.

    The two hosts express both differently. EnWorld uses `<b>` and inline
    `style="color:"`; Google Docs uses `<span class="c12">` with the weight and
    the colour in a stylesheet, so neither can be read off the element.
    """
    from lxml import html as LH

    doc = LH.fromstring(html)
    if guide.host == "gdocs":
        styles = gdoc_styles(html)

        def colour_of(el):  # noqa: ANN001, ANN202
            for c in (el.get("class") or "").split():
                got = styles.get(c, (None, False))[0]
                if got:
                    return got
            return None

        def is_name(el):  # noqa: ANN001, ANN202
            return any(styles.get(c, (None, False))[1]
                       for c in (el.get("class") or "").split())

        holders = doc.xpath("//span[@class]")
        roots = [doc]
    else:
        colour_of = tint

        def is_name(el):  # noqa: ANN001, ANN202
            return el.tag == "b"

        roots = doc.xpath("//article[contains(@class,'message--post')]")
        holders = None

    key = dict(legend(doc, colour_of))
    key.update(guide.colours)               # hand overrides win

    out: list[tuple[str, str, int]] = []
    unmapped: Counter[str] = Counter()
    scopes = [(0, doc)] if holders is not None else [
        (i, r) for i, r in enumerate(roots) if not guide.posts or i in guide.posts]
    for i, scope in scopes:
        cands = scope.xpath(".//span[@class]") if holders is not None \
            else scope.xpath(".//b")
        for el in cands:
            if not is_name(el):
                continue
            text = " ".join((el.text_content() or "").split())
            if not text:
                continue
            hex_ = colour_of(el)
            if hex_ is None or hex_ in NEUTRAL:
                tier = "black"
            else:
                tier = key.get(hex_)
                if tier is None:
                    unmapped[hex_] += 1
                    continue
            out.append((tier, text, i))
    return out, key, unmapped


def read(name: str, guide: Guide, index: Index) -> dict:
    """Everything one guide yields, with no name in the result."""
    runs, key, unmapped = options(fetch(guide, name), guide)
    rated: dict[str, float] = {}
    aside: dict[str, list[str]] = {}
    why: Counter[str] = Counter()
    unresolved: list[tuple[str, str]] = []      # (tier, text) -- notes only
    clash = 0
    for tier, text, _post in runs:
        ref, reason = index.find(text)
        if ref is None:
            why[reason] += 1
            unresolved.append((tier, text))
            continue
        pre = index._pre(ref)
        if pre not in RATEABLE:
            # Real, named, and nothing this project can score. Counted so the
            # coverage figure is not flattered by calling it a miss.
            why[f"out of scope: {index.kind_of.get(ref, pre)}"] += 1
            continue
        why["ok"] += 1
        if tier in (OUT_OF_COMBAT, TABLE_DEPENDENT):
            aside.setdefault(tier, []).append(ref)
            continue
        want = TIERS[tier]
        if ref in rated and rated[ref] != want:
            # An author who rates the same option twice at different tiers is
            # usually rating it for two builds. The better reading is kept, to
            # match the "best case" the doctrine already asks for elsewhere, and
            # the count is reported rather than buried.
            clash += 1
            want = max(want, rated[ref])
        rated[ref] = want
    return {
        "runs": len(runs), "rated": rated, "aside": aside,
        "why": why, "unresolved": unresolved, "clash": clash,
        "key": key, "unmapped": unmapped,
    }


def agreement(rated: dict[str, float], guide: Guide) -> tuple[int, int, Counter]:
    """Do the powers it resolved actually belong to the class it is about?

    The accuracy check that needs no human and no name. A wizard guide naming a
    fighter power has mis-resolved, and this counts it.
    """
    from combat_engine.etl.build import game

    g = game()
    owner = {r["ref"]: (r["class"] or "").lower()
             for r in g.execute('SELECT ref, "class" FROM power')}
    ok = bad = 0
    strays: Counter[str] = Counter()
    for ref in rated:
        if not ref.startswith("p"):
            continue                      # a feat or item belongs to nobody
        who = owner.get(ref, "")
        if not who or not guide.cls:
            continue
        if who == guide.cls:
            ok += 1
        else:
            bad += 1
            strays[who] += 1
    return ok, bad, strays


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", default="", help="just this one")
    ap.add_argument("--emit", action="store_true",
                    help="write src/combat_engine/ratings.py and notes/")
    args = ap.parse_args()

    index = Index.load()
    chosen = {k: v for k, v in GUIDES.items()
              if not args.guide or k == args.guide}
    if not chosen:
        print(f"no such guide: {args.guide}", file=sys.stderr)
        return 2

    every: dict[str, dict[str, float]] = {}
    sources: dict[str, list[str]] = {}
    spread: dict[str, list[float]] = {}
    skipped: dict[str, str] = {}
    print(f"{'guide':<10} {'runs':>6} {'rated':>6} {'aside':>6} {'unres':>6} "
          f"{'own class':>10} {'stray':>6}")
    for name, guide in chosen.items():
        got = read(name, guide, index)
        ok, bad, strays = agreement(got["rated"], guide)
        print(f"{name:<10} {got['runs']:>6} {len(got['rated']):>6} "
              f"{sum(len(v) for v in got['aside'].values()):>6} "
              f"{len(got['unresolved']):>6} "
              f"{ok:>10} {bad:>6}")
        if bad:
            print(f"{'':<10}   strays by class: {dict(strays)}")
        if got["clash"]:
            print(f"{'':<10}   {got['clash']} refs rated twice at different tiers")
        print(f"{'':<10}   why: {dict(got['why'])}")
        print(f"{'':<10}   key: {got['key']}")
        if got["unmapped"]:
            print(f"{'':<10}   UNMAPPED colours (add an override): "
                  f"{dict(got['unmapped'].most_common(6))}")
        for ref, v in got["rated"].items():
            # **Keyed by the guide's class, not by ref alone.** A race or a feat
            # is class-agnostic and gets rated in a class context: one that is
            # gold for an Intelligence class is red for a Charisma one, and that
            # is two correct answers to different questions rather than a
            # disagreement. Averaging them produced a mid-tier number that was
            # wrong for both, on 33 of the 35 overlaps.
            per = every.setdefault(ref, {})
            if guide.cls in per and per[guide.cls] != v:
                spread.setdefault(ref, []).append(v)
            per[guide.cls or "any"] = v
            sources.setdefault(ref, []).append(name)
        for tier, refs in got["aside"].items():
            for ref in refs:
                skipped[ref] = f"{name} ({tier})"
        if args.emit:
            NOTES.mkdir(exist_ok=True)
            body = [f"# {name}", "", guide.url, "",
                    f"{len(got['unresolved'])} coloured runs did not resolve to "
                    "a ref. Kept here because this directory is git-ignored.", ""]
            body += [f"* [{t}] {x}" for t, x in got["unresolved"]]
            (NOTES / f"{name}-unresolved.md").write_text("\n".join(body) + "\n")

    multi = {r: v for r, v in every.items() if len(v) > 1}
    print(f"\n{len(every)} refs rated, {len(skipped)} set aside")
    print(f"  rated for more than one class: {len(multi)}")
    if multi:
        gaps = [max(v.values()) - min(v.values()) for v in multi.values()]
        wide = sum(1 for g2 in gaps if g2 >= 2.0)
        print(f"    widest spread across classes {max(gaps):.1f} of 6; "
              f"{wide} differ by two tiers or more, which is why these are not "
              f"averaged")
    if spread:
        print(f"  {len(spread)} rated twice for the SAME class at different "
              f"tiers (genuine disagreement); the later guide wins")
    kinds = Counter(index.kind_of.get(r, "?") for r in every)
    print(f"  by kind: {dict(kinds)}")
    flat = [v for per in every.values() for v in per.values()]
    print(f"  tiers:   {dict(sorted(Counter(flat).items()))}")

    if args.emit:
        write_table(every, sources, skipped)
        print(f"\nwrote src/combat_engine/ratings.py and {NOTES}/")
    return 0


def write_table(rated: dict[str, dict[str, float]],
                sources: dict[str, list[str]],
                skipped: dict[str, str]) -> None:
    """The tracked output. Refs, class names and numbers, and nothing else."""
    lines = [
        '"""Community ratings for player options, as `(ref, class) -> score`.',
        "",
        "Generated by `scripts/guides.py`. **Do not hand-edit**: re-run the",
        "instrument, which is also what records where each rating came from.",
        "",
        "The scale is the community's six colours -- gold 6, sky blue 5, blue 4,",
        "black 3, purple 1.5, red 0. An option no guide mentions scores",
        "`UNRATED`, at 2.5, just below rated-average: a guide's silence is weaker",
        'evidence than a guide\'s "average" and is not evidence of badness.',
        "",
        "**Keyed by class, and that is not a detail.** A race or a feat is",
        "class-agnostic and gets rated in a class context. One that is gold for",
        "an Intelligence class is red for a Charisma one -- two correct answers to",
        "different questions, not a disagreement. Averaging them gave a mid-tier",
        "number that was wrong for both, on 33 of the first 35 overlaps. So",
        "`rating(ref, cls)` wants the class, and returns `UNRATED` when the only",
        "opinions on file belong to other classes rather than guessing from them.",
        "",
        "A power is already class-specific, so its entry has one class and the",
        "key is redundant there -- except where a guide rates another class's row",
        "as worth poaching, which is a real and separate judgement.",
        "",
        "`OUT_OF_COMBAT` holds the ratings that are not tiers at all: green for",
        '"a different kind of useful", mostly non-combat, and pink for',
        '"GM/table dependent". Recorded because they are real, and kept out of the',
        "combat score because they are not comparable to it.",
        "",
        "No printed name appears here and none ever should: the names live in",
        "git-ignored `localization/`, and `scripts/leaks.py` is what proves it.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f"UNRATED = {UNRATED}",
        "",
        "#: ref -> {class: score}. The class is the guide's, not the option's.",
        "RATINGS: dict[str, dict[str, float]] = {",
    ]
    for ref in sorted(rated):
        per = ", ".join(f'"{c}": {v}' for c, v in sorted(rated[ref].items()))
        lines.append(f'    "{ref}": {{{per}}},')
    lines += [
        "}",
        "",
        "#: ref -> the guides that rated it. Provenance, so a number can be",
        "#: argued with rather than trusted.",
        "SOURCES: dict[str, tuple[str, ...]] = {",
    ]
    for ref in sorted(sources):
        got = ", ".join(f'"{g}"' for g in sorted(set(sources[ref])))
        lines.append(f'    "{ref}": ({got},),')
    lines += [
        "}",
        "",
        "#: Rated green or pink: real, and not comparable on a combat axis.",
        "OUT_OF_COMBAT: dict[str, str] = {",
    ]
    for ref in sorted(skipped):
        lines.append(f'    "{ref}": "{skipped[ref]}",')
    lines += [
        "}",
        "",
        "#: The classes a guide has actually been read for. Everything else is",
        "#: unrated for the plainest possible reason: nobody has written it down",
        "#: here yet.",
        "GUIDED_CLASSES: frozenset[str] = frozenset({",
    ]
    for c in sorted({c for per in rated.values() for c in per}):
        lines.append(f'    "{c}",')
    lines += [
        "})",
        "",
        "",
        'def rating(ref: str, cls: str = "") -> float | None:',
        '    """What a guide thinks of this option for this class, or None.',
        "",
        "    **None means unrated, and unrated is not a low score.** It is absent",
        "    evidence. Returned rather than a number so a caller cannot read a",
        "    placeholder as a measurement by accident -- use `score()` if a float",
        "    is genuinely needed.",
        "",
        "    Also None when the only opinions on file belong to other classes: a",
        "    wizard guide's view of a race says nothing about that race for a",
        "    fighter, and borrowing it is worse than admitting ignorance.",
        '    """',
        "    per = RATINGS.get(ref)",
        "    if not per:",
        "        return None",
        "    if cls and cls in per:",
        "        return per[cls]",
        "    if len(per) == 1 and not cls:",
        "        return next(iter(per.values()))",
        "    return None",
        "",
        "",
        'def rated(ref: str, cls: str = "") -> bool:',
        '    """Did a guide actually say something about this, for this class."""',
        "    return rating(ref, cls) is not None",
        "",
        "",
        'def score(ref: str, cls: str = "") -> float:',
        '    """A number for callers that must have one. `UNRATED` when unrated.',
        "",
        "    The placeholder sits just below rated-average because a guide's",
        "    silence is weaker evidence than a guide's \"average\". It is **not** a",
        "    verdict, and a scorer that can omit a term instead should prefer to:",
        "    ask `rated()` first and leave the feature absent.",
        '    """',
        "    got = rating(ref, cls)",
        "    return UNRATED if got is None else got",
        "",
        "",
        'def why(ref: str, cls: str = "") -> str:',
        '    """Why this is unrated, in words, so a false signal can be spotted.',
        "",
        '    * `"rated"` -- a guide for this class rated it.',
        '    * `"no guide for this class"` -- much the commonest, and carries no',
        "      information whatever about the option.",
        '    * `"rated for another class only"` -- an opinion exists and does not',
        "      transfer.",
        '    * `"unmentioned"` -- a guide for this class exists and did not name it.',
        "      **Still not a negative.** The first guide read rated 136 of 3,501",
        "      feats; it did not consider and reject the other 3,365. Silence means",
        "      the author wrote about something else, or the option postdates the",
        "      guide, or their table bans the source.",
        '    """',
        "    if rated(ref, cls):",
        '        return "rated"',
        "    if cls and cls not in GUIDED_CLASSES:",
        '        return "no guide for this class"',
        "    if RATINGS.get(ref):",
        '        return "rated for another class only"',
        '    return "unmentioned"',
        "",
        "",
        "def spread(ref: str) -> float:",
        '    """How far apart the classes are on this option. 0 when they agree.',
        "",
        "    Worth reading rather than smoothing away: an option two experienced",
        "    players put two tiers apart is genuinely situational, and that is",
        "    information a single number loses.",
        '    """',
        "    per = RATINGS.get(ref) or {}",
        "    return max(per.values()) - min(per.values()) if len(per) > 1 else 0.0",
        "",
    ]
    (ROOT / "src" / "combat_engine" / "ratings.py").write_text(
        "\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
