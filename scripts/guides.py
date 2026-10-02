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
import itertools
import json
import pathlib
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

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


@lru_cache(maxsize=1)
def weapon_groups() -> frozenset[str]:
    """The printed weapon groups, normalised, read off the `weapon` table.

    **Not options, and one of them resolves.** Guides discuss groups constantly --
    "take a light blade", "any heavy blade works" -- and bold or colour them exactly
    as they do an option, because to the author they *are* one. 13 of the 17 then
    resolve to a ref: twelve to a monster's ability, which `RATEABLE` already
    refuses, and **`light blade` to `p1225`, a power printed "Light"**, which it does
    not. So that power carried ratings from nine classes and most of them never
    mention it.

    Derived rather than typed, like `LEGEND_WORDS` is derived from each guide's own
    key: a group that moved underneath a hand-written list would go unnoticed, and
    this is the same vocabulary `Weapon.grp` already is. #290.

    A rating *on a group* is the better answer eventually -- "this class likes light
    blades" is real doctrine -- but `chargen.choices.wield_options` scores weapons by
    ref and has nowhere to put it, so dropping these loses nothing that is read
    today.
    """
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
        from combat_engine.etl.build import game

        bare = [norm(r[0]) for r in game().execute(
            "SELECT DISTINCT grp FROM weapon") if r[0]]
        # **Plurals too, because guides write them.** "Light Blades" resolves to
        # `p1225` exactly as "Light Blade" does -- the resolver's own normalisation
        # takes the suffix off -- so a singular-only set caught the paladin guide and
        # missed the psion one. Both spellings, rather than reimplementing the
        # resolver's stemming out here where it could drift from it.
        return frozenset(bare) | {f"{g}s" for g in bare} | {f"{g}es" for g in bare}
    except Exception:
        # An instrument that cannot reach the database should still read guides.
        return frozenset()

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


#: The palette most EnWorld guides share, as a floor under the derived key.
#:
#: **Needed because deriving the key silently fails on some guides.** A guide
#: that states its legend in an image, or in a table, or in words this code does
#: not recognise, yields no map at all -- and then every coloured rating is
#: dropped as unmapped and only the uncoloured blacks survive. That took 14 of
#: 36 guides to 95-100% black, which is what a broken reader looks like rather
#: than what a guide looks like.
#:
#: These six are read off the guides that *do* state a key, and agree across
#: them. Anything outside this and the derived key is still reported unmapped
#: rather than guessed.
CANON: dict[str, str] = {
    "#000000": "black",
    "#ff0000": "red",
    "#800080": "purple",
    "#0000ff": "blue",
    "#00ccff": "sky",
    "#33cccc": "sky",
    "#ff9900": "gold",
    "#339966": OUT_OF_COMBAT,
}


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
    #: Which posts hold the guide proper, as an override. Empty means **every
    #: post by whoever started the thread**, which is the right default: a long
    #: guide runs over several posts, and several start at post 2 behind a short
    #: introduction and a table of contents. Reading post 0 alone found nothing
    #: at all on 51 of 96 candidates.
    posts: tuple[int, ...] = ()
    note: str = ""


def host_of(url: str) -> str:
    """Which parser a URL wants. Four hosts carry these guides."""
    if "docs.google.com" in url:
        return "gdocs"
    if "web.archive.org" in url:
        return "archive"
    if "sites.google.com" in url:
        return "gsites"
    return "enworld"

#: (slug, class, url, overrides, note). One line per guide, because the colour
#: key derives itself now and the only thing left to record by hand is which
#: class a guide is about -- and even that is *checked* rather than trusted, by
#: `agreement()`. The host follows from the URL.
#:
#: The class comes from `--discover`, which reads every candidate and reports
#: whichever class owns most of the powers it rates. The index thread mislabels
#: at least one guide, so detecting beats believing.
REGISTRY: tuple[tuple[str, str, str, dict[str, str], str], ...] = (
    ("ardent", "ardent",
     "http://www.enworld.org/forum/showthread.php?468822",
     {}, "279 options, 79 powers, 96% ardent"),
    ("artificer", "artificer",
     "http://www.enworld.org/forum/showthread.php?468924",
     {}, "class stated, not detected"),
    ("assassin", "assassin",
     "http://www.enworld.org/forum/showthread.php?469376",
     {}, "220 options, 90 powers, 84% assassin"),
    ("barbarian", "barbarian",
     "http://www.enworld.org/forum/showthread.php?469384",
     {}, "330 options, 143 powers, 99% barbarian"),
    ("avenger", "avenger",
     "https://sites.google.com/view/avengershandbook/",
     {}, "a Google Site of 51 sub-pages, crawled and joined"),
    ("bard", "bard",
     "http://www.enworld.org/forum/showthread.php?468955",
     {}, "161 options, 51 powers, 88% bard"),
    ("battlemind", "battlemind",
     "http://www.enworld.org/forum/showthread.php?469129",
     {}, "351 options, 159 powers, 97% battlemind"),
    ("cleric", "cleric",
     "http://www.enworld.org/forum/showthread.php?471418",
     {}, "424 options, 102 powers, 96% cleric"),
    ("cleric2", "cleric",
     "http://www.enworld.org/forum/showthread.php?469235",
     {}, "64 options, 18 powers, 100% cleric"),
    ("druid", "druid",
     "http://www.enworld.org/forum/showthread.php?469148",
     {}, "151 options, 74 powers, 96% druid"),
    ("fighter", "fighter",
     "http://www.enworld.org/forum/showthread.php?469122",
     {}, "570 options, 278 powers, 88% fighter"),
    ("fighter2", "fighter",
     "http://www.enworld.org/forum/showthread.php?517231",
     {}, "398 options, 113 powers, 95% fighter"),
    ("fighter3", "fighter",
     "http://www.enworld.org/forum/showthread.php?469139",
     {}, "377 options, 112 powers, 95% fighter"),
    ("invoker", "invoker",
     "http://www.enworld.org/forum/showthread.php?469150",
     {}, "436 options, 143 powers, 99% invoker"),
    ("monk", "monk",
     "https://web.archive.org/web/20150916220419/http://community.wi"
     "zards.com/content/forum-topic/3735276",
     {}, "195 options, 67 powers, 93% monk"),
    ("monk2", "monk",
     "http://www.enworld.org/forum/showthread.php?468782",
     {}, "168 options, 68 powers, 93% monk"),
    ("paladin", "paladin",
     "http://www.enworld.org/forum/showthread.php?471429",
     {}, "692 options, 226 powers, 91% paladin"),
    ("paladin2", "paladin",
     "http://www.enworld.org/forum/showthread.php?469141",
     {}, "437 options, 161 powers, 84% paladin"),
    ("paladin3", "paladin",
     "http://www.enworld.org/forum/showthread.php?469135",
     {}, "343 options, 112 powers, 92% paladin"),
    ("psion", "psion",
     "http://www.enworld.org/forum/showthread.php?471677",
     {}, "327 options, 82 powers, 94% psion"),
    ("ranger", "ranger",
     "http://www.enworld.org/forum/showthread.php?517233",
     {}, "377 options, 114 powers, 89% ranger"),
    ("ranger2", "ranger",
     "http://www.enworld.org/forum/showthread.php?468963",
     {}, "166 options, 63 powers, 97% ranger"),
    ("rogue", "rogue",
     "http://www.enworld.org/forum/showthread.php?469717",
     {}, "385 options, 155 powers, 95% rogue"),
    ("runepriest", "runepriest",
     "http://www.enworld.org/forum/showthread.php?469230",
     {}, "140 options, 42 powers, 98% runepriest"),
    ("seeker", "seeker",
     "http://www.enworld.org/forum/showthread.php?469092",
     {}, "296 options, 122 powers, 96% seeker"),
    ("seeker2", "seeker",
     "https://www.enworld.org/threads/713594/",
     {}, "272 options, 73 powers, 93% seeker"),
    ("shaman", "shaman",
     "http://www.enworld.org/forum/showthread.php?469231",
     {}, "95 options, 23 powers, 96% shaman"),
    ("sorcerer", "sorcerer",
     "http://www.enworld.org/forum/showthread.php?469385",
     {}, "149 options, 120 powers, 99% sorcerer"),
    ("swordmage", "swordmage",
     "http://www.enworld.org/forum/showthread.php?469143",
     {}, "404 options, 120 powers, 89% swordmage"),
    ("warden", "warden",
     "http://www.enworld.org/forum/showthread.php?469144",
     {}, "class stated, not detected"),
    ("warlock", "warlock",
     "http://www.enworld.org/forum/showthread.php?469339",
     {}, "374 options, 143 powers, 94% warlock"),
    ("warlock2", "warlock",
     "https://docs.google.com/document/d/117rZcbx32PrhfHVcWMqm4Ucgfk"
     "iLdWNqRzwH8Sg7hXk/edit?tab=t.0#heading=h.xr28oblc61hn",
     {}, "335 options, 183 powers, 99% warlock"),
    ("warlock3", "warlock",
     "http://www.enworld.org/forum/showthread.php?471621",
     {}, "283 options, 179 powers, 83% warlock"),
    ("warlord", "warlord",
     "http://www.enworld.org/forum/showthread.php?469232",
     {}, "73 options, 15 powers, 100% warlord"),
    ("wizard", "wizard",
     "http://www.enworld.org/forum/showthread.php?471408",
     {}, "360 options, 179 powers, 99% wizard"),
    ("wizard2", "wizard",
     "http://www.enworld.org/forum/showthread.php?471672",
     {}, "264 options, 158 powers, 86% wizard"),
    ("wizard3", "wizard",
     "https://www.enworld.org/threads/469147/",
     {}, "165 options, 79 powers, 100% wizard"),
)

#: The wizard handbook writes "Sky Blue" in one teal and rates with another, so
#: the derived key cannot see the one it actually uses. The only override any
#: guide has needed so far.
OVERRIDES: dict[str, dict[str, str]] = {
    "wizard": {"#33cccc": "sky"},
}

GUIDES: dict[str, Guide] = {
    slug: Guide(url=url, cls=cls,
                colours={**over, **OVERRIDES.get(slug, {})},
                host=host_of(url), note=note)
    for slug, cls, url, over, note in REGISTRY
}

#: Set by `main`/`discover` once the name index exists. `options` needs to ask
#: "does this text name something" to spot a name split across two colours, and
#: threading the index through every call site for one predicate is worse.
def _RESOLVES(_text: str) -> bool:
    return False

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


def _crawl_gsites(url: str) -> bytes:
    """A Google Site is many pages; fetch them all and join them.

    The avenger handbook is 51 sub-pages under one site, with the colour key on
    the landing page and the ratings spread across the rest. One document is what
    the parser wants, so they are concatenated -- the `<article>` shape the forum
    parser looks for is absent either way, so the whole thing is one scope.
    """
    import time
    import urllib.parse

    head = {"User-Agent": "combat_engine research (ratings)"}
    root = url.rstrip("/")
    base = urllib.parse.urlsplit(root)
    prefix = base.path.rstrip("/")
    with urllib.request.urlopen(
            urllib.request.Request(root, headers=head), timeout=90) as fh:
        first = fh.read()
    page = first.decode("utf-8", "replace")
    subs = sorted({m for m in re.findall(
        rf'href="({re.escape(prefix)}/[^"#?]*)"', page)})
    parts = [first]
    for sub in subs:
        u = f"{base.scheme}://{base.netloc}{sub}"
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(u, headers=head), timeout=90) as fh:
                parts.append(fh.read())
        except Exception:
            pass                                        # one dead sub-page is fine
        time.sleep(0.8)
    return b"<html><body>" + b"".join(parts) + b"</body></html>"


def fetch(guide: Guide, name: str = "") -> str:
    """The page, from `.cache/` if it is there. One fetch per URL, ever.

    Keyed on the **URL**, not on the guide's slug, so `--discover` and a run over
    the registry share the same cache. Keyed on the slug they did not, and a
    registry run refetched all 36 pages -- which is both rude and how a transient
    502 killed the whole pass.
    """
    import hashlib

    CACHE.mkdir(parents=True, exist_ok=True)
    src = source_url(guide)
    at = CACHE / f"{hashlib.sha1(src.encode()).hexdigest()[:16]}.html"
    if not at.exists():
        if guide.host == "gsites":
            at.write_bytes(_crawl_gsites(src))
        else:
            req = urllib.request.Request(
                src, headers={"User-Agent": "combat_engine research (ratings)"})
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


_COL = re.compile(r"(?<!background-)color:\s*(#[0-9a-f]{3,6}|[a-z]{3,24})\b")

#: CSS colour *names*, folded onto the canonical hex of the tier they mean.
#:
#: **Over five thousand ratings were being discarded** because `_COL` matched only
#: hex. One guide writes its sky blue as `DarkTurquoise` and its blue as
#: `MediumBlue`, and every one of its 436 options fell through to black -- which
#: is why it looked like a guide whose colour had been lost in a migration. It had
#: not; the reader could not see it.
#:
#: Folded onto the canon rather than kept as names so there is one code path, and
#: so a guide's own stated key still wins: a legend written in `DeepSkyBlue`
#: arrives here as `#00ccff` and is read the same way as a legend written in hex.
NAMED: dict[str, str] = {
    "red": "#ff0000", "crimson": "#ff0000", "firebrick": "#ff0000",
    "purple": "#800080", "violet": "#800080", "darkviolet": "#800080",
    "blue": "#0000ff", "mediumblue": "#0000ff", "navy": "#0000ff",
    "deepskyblue": "#00ccff", "darkturquoise": "#00ccff",
    "skyblue": "#00ccff", "lightskyblue": "#00ccff",
    "mediumturquoise": "#00ccff", "aqua": "#00ccff", "cyan": "#00ccff",
    "goldenrod": "#ff9900", "darkgoldenrod": "#ff9900",
    "gold": "#ff9900", "orange": "#ff9900",
    "green": "#339966", "darkgreen": "#339966", "seagreen": "#339966",
    "black": "#000000",
}

#: Names that are page furniture rather than a rating.
CHROME = frozenset({"white", "inherit", "rgba", "rgb", "hsl", "hsla",
                    "transparent", "currentcolor", "initial", "unset"})


def _hex(token: str) -> str | None:
    """A colour token as a canonical hex, or None when it is not a rating."""
    t = token.strip().lower()
    if t.startswith("#"):
        return t
    if t in CHROME:
        return None
    return NAMED.get(t)
#: Grey and near-black are body text, not a rating.
NEUTRAL = ("#000000", "#434343", "#666666", "#333333", "#222222", "#111111")


def gdoc_styles(body: str) -> dict[str, tuple[str | None, bool]]:
    """Google Docs puts bold and colour in class definitions, not on elements."""
    out: dict[str, tuple[str | None, bool]] = {}
    for name, decls in re.findall(r"\.(c\d+)\s*\{([^}]*)\}", body):
        flat = decls.replace(" ", "")
        m = re.search(r"(?<!background-)color:(#[0-9a-f]{6}|[a-z]{3,24})", flat)
        out[name] = (_hex(m.group(1)) if m else None,
                     "font-weight:700" in flat)
    return out


def legend(doc, colour_of) -> dict[str, str]:  # noqa: ANN001
    """The guide's own key, read off the colour words it wrote in colour.

    Takes the first colour each word appears in, so a later mention of the word
    in ordinary prose cannot overwrite the swatch.
    """
    found: dict[str, str] = {}
    # Only elements that *carry* a colour can be a swatch, and walking every
    # element instead took the run over 36 guides past ten minutes.
    cands = doc.xpath("//*[contains(@style,'color')] | //span[@class] | "
                      "//font[@color]")
    for el in cands:
        txt = " ".join((el.text_content() or "").split()).strip().lower()
        txt = txt.rstrip(":").strip()
        if txt in LEGEND_WORDS and len(txt) <= 12:
            c = colour_of(el)
            if c and c not in NEUTRAL:
                found.setdefault(c, LEGEND_WORDS[txt])
    return found


def tint(el) -> str | None:  # noqa: ANN001
    """The colour this element is rated in -- looking up, then down.

    **Both directions, because guides nest it both ways.** The wizard handbook
    writes `<span style="color:..."><b>name</b></span>`, so the colour is on an
    ancestor. The fighter handbook writes `<b><span style="color:...">name</span>
    </b>`, so it is on a descendant. Reading ancestors alone found the colour on
    42 of its bold elements and missed 583, which left 14 of 36 guides reporting
    95-100% black -- what a broken reader looks like, not what a guide looks like.

    Ancestors win, because an explicitly wrapped rating is the more deliberate of
    the two.
    """
    cur = el
    while cur is not None:
        m = _COL.search((cur.get("style") or "").lower())
        if m and (got := _hex(m.group(1))):
            return got
        cur = cur.getparent()
    for kid in el.xpath(".//*[contains(@style,'color')]"):
        m = _COL.search((kid.get("style") or "").lower())
        if m and (got := _hex(m.group(1))):
            return got
    return None


def _joined(els, colour_of, resolves):  # noqa: ANN001, ANN202
    """Names an author split across two coloured spans, and both their colours.

    **A word cut in half is two ratings, not a broken one.** One guide colours the
    first half of a name for its Wisdom build and the second half for its
    Constitution build, so neither half resolves and the option is lost entirely.
    11 refs in that guide are written this way, with the halves in genuinely
    different colours -- red/purple, purple/red, blue/sky.

    Detected rather than guessed: the two must be adjacent siblings with nothing
    between them, the concatenation must resolve to a ref, and the first half
    alone must *not*. That last condition is what stops two ordinary adjacent
    ratings being welded together.

    Yields (tier-bearing colour, joined text) twice, once per half, so the
    caller's "rated twice at different tiers" path keeps the better and counts it.
    """
    for a, b in itertools.pairwise(els):
        if a.getparent() is not b.getparent() or (a.tail or "").strip():
            continue
        ta = " ".join((a.text_content() or "").split())
        tb = " ".join((b.text_content() or "").split())
        if not ta or not tb or resolves(ta) or not resolves(ta + tb):
            continue
        ca, cb = colour_of(a), colour_of(b)
        if ca:
            yield ca, ta + tb
        if cb and cb != ca:
            yield cb, ta + tb


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
            """Bold **or** coloured. Guides use one, the other, or both.

            A third convention, and the one that made four classes look almost
            unrated: the name is wrapped in a colour and is *not* bold --
            `<span style="color:#0000ff">name</span> (PP): commentary`. Accepting
            only bold candidates meant such a guide never offered a single one.
            """
            if el.tag in ("b", "strong"):
                return True
            style = (el.get("style") or "").replace(" ", "")
            return ("font-weight:bold" in style or "font-weight:700" in style
                    or _COL.search(style.lower()) is not None)

        roots = doc.xpath("//article[contains(@class,'message--post')]")
        if roots and not guide.posts:
            # **The author's own posts, not the first post.** A reply is somebody
            # else's opinion and must not be read as the guide's rating, but the
            # guide itself often runs over five or six posts. The thread starter
            # wrote post 0, so that is who to keep.
            starter = roots[0].get("data-author")
            if starter:
                roots = [r for r in roots if r.get("data-author") == starter]
        if not roots:
            # Not a forum thread. An archived WotC page or a Google Site is one
            # document, so the whole of it is the guide.
            roots = [doc]
        holders = None

    # Canonical floor, then whatever the guide states for itself, then the hand
    # overrides. A guide that contradicts the canon wins, which is the point of
    # reading its own key at all.
    key = dict(CANON)
    key.update(legend(doc, colour_of))
    key.update(guide.colours)

    out: list[tuple[str, str, int]] = []
    unmapped: Counter[str] = Counter()
    scopes = [(0, doc)] if holders is not None else [
        (i, r) for i, r in enumerate(roots) if not guide.posts or i in guide.posts]
    for i, scope in scopes:
        cands = scope.xpath(".//span[@class]") if holders is not None \
            else scope.xpath(".//b | .//strong | "
                             ".//*[contains(@style,'font-weight')] | "
                             ".//*[contains(@style,'color')]")
        # The xpath union can offer one element twice -- a bold wrapping a
        # coloured span matches both arms. Deliberately not deduplicated: lxml
        # builds element proxies on demand, so `id()` is reused after collection
        # and deduplicating on it silently dropped ~500 refs. A repeat offer is
        # harmless, because the "rated twice" path keeps the better tier, which
        # is exactly right when the bold says black and the span inside says blue.
        for el in cands:
            if not is_name(el):
                continue
            text = " ".join((el.text_content() or "").split())
            if not text:
                continue
            # **The key's own swatches are not options.** A guide writes its
            # legend in the colours it is defining, so every swatch is a
            # coloured bold run and offers itself as a candidate -- and one of
            # them resolves: `"Light Blue"` matches a real power's printed name
            # and was being rated sky by every guide whose key spells sky that
            # way. `legend` already knows these words; this is the same test it
            # makes, so the two cannot drift apart.
            bare = text.strip(" .:,;-\u2013\u2014").strip().lower()
            if bare in LEGEND_WORDS:
                continue
            # **A weapon group is not an option.** Same shape as the legend swatch
            # above -- a coloured bold run that resolves to something the author did
            # not mean. See `weapon_groups`. #290.
            if norm(bare) in weapon_groups():
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
        # Names split across two coloured spans, which neither half resolves.
        from_split = _joined(
            scope.xpath(".//*[contains(@style,'color')]"), colour_of,
            lambda t: _RESOLVES(t))
        for hex_, text in from_split:
            tier = key.get(hex_)
            if tier is not None:
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
    contested: set[str] = set()
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
            # **Which refs, not just how many.** #256: one class can hold two
            # answers -- 23 of 25 classes have build legs differing on an
            # ability, and one guide writes a name split across two coloured
            # spans *because* its two builds rate it differently. Keeping the
            # better of the two loses exactly the distinction the author took
            # trouble to express, and the key cannot hold which build is which
            # because the split-colour form never says.
            #
            # So the disagreement is recorded rather than resolved, and
            # `rating()` declines to answer for a contested pair the same way it
            # declines when only other classes have an opinion.
            contested.add(ref)
            want = max(want, rated[ref])
        rated[ref] = want
    return {
        "runs": len(runs), "rated": rated, "aside": aside,
        "why": why, "unresolved": unresolved, "clash": clash,
        "contested": contested,
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


def discover() -> int:
    """Fetch every candidate URL and work out which class each guide is about.

    **The class is detected, not trusted.** The index thread mislabels at least
    one guide, and the check that caught it -- do the resolved powers belong to
    the class claimed -- works just as well with nothing claimed at all: whichever
    class owns most of the powers a guide rates is the class it is about.

    Writes a candidate registry to git-ignored `notes/`, because the titles that
    make it readable are the authors' words.
    """
    import time

    index = Index.load()
    globals()["_RESOLVES"] = lambda t: index.find(t)[1] == "ok"
    urls = [u for u in (CACHE / "_urls.txt").read_text().split() if u.strip()]
    print(f"{len(urls)} candidate URLs\n")
    print(f"{'#':>3} {'host':<8} {'rated':>6} {'powers':>6} {'class':<12} "
          f"{'share':>6}  url")
    found: list[dict] = []
    for i, url in enumerate(urls):
        host = host_of(url)
        slug = f"_d{i:03d}"
        g = Guide(url=url, cls="", host=host)
        try:
            html = fetch(g, slug)
        except Exception as exc:
            print(f"{i:>3} {host:<8} {'--':>6} {'fetch failed':<12} "
                  f"{type(exc).__name__:>6}  {url[:64]}")
            continue
        time.sleep(1.2)
        try:
            runs, _key, _un = options(html, g)
        except Exception as exc:
            print(f"{i:>3} {host:<8} {'--':>6} {'parse failed':<12} "
                  f"{type(exc).__name__:>6}  {url[:64]}")
            continue
        owner = _power_owners()
        who: Counter[str] = Counter()
        n = 0
        for tier, text, _p in runs:
            if tier in (OUT_OF_COMBAT, TABLE_DEPENDENT):
                continue
            ref, why_ = index.find(text)
            if ref is None or why_ != "ok" or Index._pre(ref) not in RATEABLE:
                continue
            n += 1
            if ref.startswith("p") and owner.get(ref):
                who[owner[ref]] += 1
        top, share = ("", 0.0)
        if who:
            top, cnt = who.most_common(1)[0]
            share = cnt / sum(who.values())
        # **The share is over powers, so the power count has to be reported too.**
        # An items compendium that happens to resolve two wizard powers otherwise
        # reads as a wizard guide at 100%.
        print(f"{i:>3} {host:<8} {n:>6} {sum(who.values()):>6} "
              f"{top or '(none)':<12} {share:>5.0%}  {url[:60]}")
        found.append({"url": url, "host": host, "rated": n,
                      "powers": sum(who.values()), "cls": top, "share": share})
    NOTES.mkdir(exist_ok=True)
    keep = [f for f in found
            if f["rated"] >= 60 and f["powers"] >= 10 and f["share"] >= 0.8]
    lines = ["# Candidate class guides", "",
             f"{len(keep)} of {len(urls)} URLs look like a class guide: at least",
             "60 resolvable options, at least 10 of them powers, and 80% of those",
             "powers owned by a single class.",
             ""]
    for f in sorted(keep, key=lambda x: (x["cls"], -x["rated"])):
        lines.append(f'* `{f["cls"]}` {f["rated"]} rated ({f["powers"]} powers, '
                     f'{f["share"]:.0%} that class) -- `{f["host"]}` -- {f["url"]}')
    (NOTES / "candidates.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(keep)} look like class guides; written to notes/candidates.md")
    print(f"classes covered: "
          f"{sorted({f['cls'] for f in keep if f['cls']})}")
    return 0


def _power_owners() -> dict[str, str]:
    from combat_engine.etl.build import game

    if not hasattr(_power_owners, "_c"):
        _power_owners._c = {
            r["ref"]: (r["class"] or "").lower()
            for r in game().execute('SELECT ref, "class" FROM power')}
    return _power_owners._c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--discover", action="store_true",
                    help="fetch every candidate URL and detect its class")
    ap.add_argument("--guide", default="", help="just this one")
    ap.add_argument("--emit", action="store_true",
                    help="write src/combat_engine/ratings.py and notes/")
    args = ap.parse_args()
    if args.discover:
        return discover()

    index = Index.load()
    globals()["_RESOLVES"] = lambda t: index.find(t)[1] == "ok"
    chosen = {k: v for k, v in GUIDES.items()
              if not args.guide or k == args.guide}
    if not chosen:
        print(f"no such guide: {args.guide}", file=sys.stderr)
        return 2

    failed: list[str] = []
    refused: list[str] = []
    every: dict[str, dict[str, float]] = {}
    sources: dict[str, list[str]] = {}
    spread: dict[str, list[float]] = {}
    #: ref -> the classes for which the guides give more than one answer. #256.
    contested: dict[str, set[str]] = {}
    #: class -> ref -> the rating the last guide for that class gave, so two
    #: guides disagreeing about one class is detectable as well as one guide
    #: disagreeing with itself.
    seen_for: dict[str, dict[str, float]] = {}
    skipped: dict[str, str] = {}
    print(f"{'guide':<10} {'runs':>6} {'rated':>6} {'aside':>6} {'unres':>6} "
          f"{'own class':>10} {'stray':>6}")
    for name, guide in chosen.items():
        try:
            got = read(name, guide, index)
        except Exception as exc:
            # One unreachable page must not cost the other thirty-five.
            print(f"{name:<12} {'--':>6} {type(exc).__name__}: "
                  f"{str(exc)[:48]}")
            failed.append(name)
            continue
        # **A guide with no colours has no ratings.** Everything falls through to
        # black, and a few hundred false averages are worse than nothing: they
        # look like verdicts. One guide in the set does not colour-code at all.
        tiers = Counter(got["rated"].values())
        n_rated = sum(tiers.values())
        if n_rated and tiers.get(TIERS["black"], 0) / n_rated > 0.9:
            print(f"{name:<12} {got['runs']:>6} {'--':>6}   refused: "
                  f"{tiers.get(TIERS['black'], 0)}/{n_rated} black, so no colour "
                  f"key was found and nothing here is a rating")
            refused.append(name)
            continue
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
            # Contested *within one class*, which is the #256 case: either this
            # guide rated it twice at different tiers, or two guides for the same
            # class disagree. Both mean "one class, two answers", and the second
            # is caught here because the first is caught in `read`.
            if ref in got["contested"]:
                contested.setdefault(ref, set()).add(guide.cls or "any")
        for ref in got["rated"]:
            if ref in seen_for.get(guide.cls or "any", ()) and \
                    seen_for[guide.cls or "any"][ref] != got["rated"][ref]:
                contested.setdefault(ref, set()).add(guide.cls or "any")
        for ref, v in got["rated"].items():
            seen_for.setdefault(guide.cls or "any", {})[ref] = v
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

    if failed:
        print(f"\n{len(failed)} guide(s) could not be read: {', '.join(failed)}")
    if refused:
        print(f"{len(refused)} guide(s) refused for having no colour key: "
              f"{', '.join(refused)}")
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
        write_table(every, sources, skipped, contested)
        print(f"\nwrote src/combat_engine/ratings.py and {NOTES}/")
    return 0


def write_table(rated: dict[str, dict[str, float]],
                sources: dict[str, list[str]],
                skipped: dict[str, str],
                contested: dict[str, set[str]] | None = None) -> None:
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
        pairs = [f'"{c}": {v}' for c, v in sorted(rated[ref].items())]
        one = f'    "{ref}": {{{", ".join(pairs)}}},'
        if len(one) <= 96:
            lines.append(one)
            continue
        # A ref a dozen guides rated does not fit on a line. Wrapped rather than
        # left long, so the emitted file passes the same lint as everything else.
        lines.append(f'    "{ref}": {{')
        row = "       "
        for pair in pairs:
            if len(row) + len(pair) + 2 > 94:
                lines.append(row)
                row = "       "
            row += f" {pair},"
        if row.strip():
            lines.append(row)
        lines.append("    },")
    lines += [
        "}",
        "",
        "#: ref -> the classes for which the guides give **more than one answer**.",
        "#:",
        "#: One class can hold two answers and this key cannot: 23 of 25 classes",
        "#: have build legs differing on an ability, and one guide writes a name",
        "#: split across two coloured spans precisely because its two builds rate",
        "#: it differently -- red/purple, purple/red, blue/sky. Keeping the better",
        "#: of the two throws away the distinction the author took trouble over.",
        "#:",
        "#: Which build each half belongs to is **not** recoverable: the",
        "#: split-colour form never says, and a guide that discusses one build in",
        "#: prose says it nowhere a parser can read. So the disagreement is",
        "#: recorded instead of resolved, and `rating()` declines to answer for a",
        "#: contested pair -- the same thing it does when only other classes have",
        "#: an opinion, and for the same reason: absent evidence beats a number",
        "#: that is wrong for both builds. #256.",
        "CONTESTED: dict[str, tuple[str, ...]] = {",
    ]
    for ref in sorted(contested or {}):
        names = sorted(contested[ref])
        one = f'    "{ref}": ({", ".join(chr(34) + c + chr(34) for c in names)},),'
        if len(one) <= 96:
            lines.append(one)
            continue
        # Wrapped the way `SOURCES` below is: a race contested by twenty classes
        # runs to 171 characters on one line and `ruff` refuses the file.
        lines.append(f'    "{ref}": (')
        row = "       "
        for c in names:
            piece = f'"{c}",'
            if len(row) + len(piece) + 1 > 94:
                lines.append(row)
                row = "       "
            row += f" {piece}"
        if row.strip():
            lines.append(row)
        lines.append("    ),")
    lines += [
        "}",
        "",
        "#: ref -> the guides that rated it. Provenance, so a number can be",
        "#: argued with rather than trusted.",
        "SOURCES: dict[str, tuple[str, ...]] = {",
    ]
    for ref in sorted(sources):
        names = sorted(set(sources[ref]))
        one = f'    "{ref}": ({", ".join(chr(34) + g + chr(34) for g in names)},),'
        if len(one) <= 96:
            lines.append(one)
            continue
        lines.append(f'    "{ref}": (')
        row = "       "
        for g in names:
            piece = f'"{g}",'
            if len(row) + len(piece) + 1 > 94:
                lines.append(row)
                row = "       "
            row += f" {piece}"
        if row.strip():
            lines.append(row)
        lines.append("    ),")
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
        "",
        "    And None for a **contested** pair -- see `CONTESTED`. One class can",
        "    hold two answers, the key cannot, and which build each belongs to is",
        "    not recoverable, so no number here would be right for both builds.",
        '    """',
        "    per = RATINGS.get(ref)",
        "    if not per:",
        "        return None",
        "    if cls and cls in CONTESTED.get(ref, ()):",
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
