"""Reading the compendium's HTML.

Every row in the source database is a whole standalone HTML document with a
`<div id="detail">` holding the only part anyone wants. These are the shared
helpers; the dialect-specific work is in `monster.py` and `power.py`.
"""

from __future__ import annotations

import re
from html import unescape

_DETAIL = re.compile(r'<div id="detail">(.*?)</div>\s*</form>', re.S)
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile("[ \t\u00a0]+")  # the source is full of non-breaking spaces


def detail(document: str) -> str:
    """The body of a compendium page, without the page furniture."""
    found = _DETAIL.search(document)
    if found:
        return found.group(1)
    # A few rows close the div differently. Falling back to everything after
    # the opening tag is better than dropping the row.
    start = document.find('<div id="detail">')
    return document[start + len('<div id="detail">') :] if start >= 0 else document


def text(fragment: str) -> str:
    """Tags out, entities decoded, runs of space collapsed.

    A tag becomes a **space**, not nothing. Deleting them outright runs the
    last word of one cell into the first of the next -- `Initiative +2` then
    `<b>AC</b> 13` reads as `+2AC 13`, and every regex looking for a word
    boundary before `AC` quietly finds nothing. That cost every defence in
    half the corpus until it was noticed.
    """
    out = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    out = _TAGS.sub(" ", out)
    out = unescape(out)
    out = _SPACE.sub(" ", out)
    return "\n".join(line.strip() for line in out.split("\n")).strip()


def paragraphs(fragment: str) -> list[tuple[str, str]]:
    """Every `<p>` as `(class, inner html)`, in document order."""
    out = []
    for m in re.finditer(r'<p\b([^>]*)>(.*?)(?=<p\b|<h[12]\b|$)', fragment, re.S):
        attrs, body = m.group(1), m.group(2)
        cls = re.search(r'class="([^"]*)"', attrs)
        out.append((cls.group(1) if cls else "", body))
    return out


def headings(fragment: str) -> list[tuple[int, str, int]]:
    """Every `<h1>`/`<h2>` as `(level, text, offset)`."""
    return [
        (int(m.group(1)), text(m.group(2)), m.start())
        for m in re.finditer(r"<h([12])[^>]*>(.*?)</h\1>", fragment, re.S)
    ]


def first_int(s: str, default: int = 0) -> int:
    m = re.search(r"[+-]?\d+", s)
    return int(m.group()) if m else default


def labelled(body: str, tags: tuple[str, ...] = ("b",)) -> tuple[str, str] | None:
    """Split `<b>Label</b>: rest` into its two halves.

    A mechanical line always carries one of these; a flavour line never does,
    which is the whole basis of the sanitiser.

    **The item dialect labels with `<i>`.** A power card writes
    `<b>Effect</b>`, a magic item's power block writes `<i>Effect:</i>` --
    so an item read with the default would come out as one unlabelled blob
    and `power_spec` would drop the whole of it as flavour. That is the same
    failure that once cost about a hundred clauses on power cards.

    `tags` is not widened by default, and must not be: the *power* dialect
    uses `<i>` for the flavour line under the title, so accepting it
    everywhere would push a publisher's prose into twelve thousand specs.
    An `<i>` label is therefore only honoured **with its colon inside the
    tag** -- which is how the item dialect always writes one, and which
    italic flavour never does.
    """
    inner = "|".join(tags)
    m = re.match(rf"\s*(?:&nbsp;|\s)*<({inner})>(.*?)</\1>\s*:?\s*(.*)", body, re.S)
    if not m:
        return None
    label = text(m.group(2))
    if m.group(1) != "b" and not label.rstrip().endswith(":"):
        return None
    return label.rstrip(":"), text(m.group(3))
