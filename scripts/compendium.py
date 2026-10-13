#!/usr/bin/env python
"""Regex search over the compendium source, in a browser.

    uv run scripts/compendium.py                 start it, print the URL
    uv run scripts/compendium.py --port 8700     on a port you can bookmark
    uv run scripts/compendium.py --open          and open a browser at it

The third-party viewer this replaces searches a porter-stemmed full-text index
with Google-ish operators, so an exact question cannot be asked of it at all --
`ongoing \\d+ fire`, or `shift \\d+ squares` without `as a free action`, or which
rows still reference `symbol/\\d+a\\.gif`. The source database here is the same
one that viewer serves, down to the column names, so the only missing piece was
a regex box.

**Stdlib `http.server`, which no other instrument here uses.** Two reasons, and
the second is the real one:

* It keeps `fastapi`/`uvicorn` -- the `api` extra -- out of a tool that wants a
  regex and a socket.
* The compendium is the **copyrighted source**. Putting this behind
  `api/app.py`, the server that draws the game, would make 140MB of prose
  reachable from the process that serves the page to a browser. A separate
  process on a separate port, bound to loopback, is the boundary -- and it is
  the same reason `db.py` says only `etl/` and `scripts/leaks.py` open `SOURCE`.

**Not registered in `check.py`.** It is a viewer. It has nothing to assert and
no regression to catch, so it would cost seconds and buy none.

What it shows that the replaced viewer cannot: a **repo** column, per row.

    m15                the ETL built it, and this is its ref
    m32 dropped=       built, and a content row under it carries a marker
    (not built)        the ETL did not build it -- 2,196 monsters, 5,155 powers
    (blank)            no table in `game.db`: this category was never meant to be

The last two have to read differently. Collapsing them would invent a backlog
out of the nine categories nothing was ever going to build.

#552.
"""

from __future__ import annotations

import argparse
import functools
import html
import json
import re
import socket
import sqlite3
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from combat_engine.db import GAME, SOURCE
from combat_engine.etl.html import detail

WEB = Path(__file__).resolve().parent / "compendium_web"

#: Rows per page. The replaced viewer's own default, and the number the
#: pagination buttons were sized for.
PER_PAGE = 100

#: How many `<mark>`-ed snippets a row carries, and how much either side.
#: Three is enough to see whether a match is the clause you meant; a fourth
#: pushes the next row off the screen.
SNIPPETS = 3
AROUND = 60


@dataclass(frozen=True)
class Category:
    """One source table, and where this repo put it.

    `built` is the `game.db` tables to look in, **in order** -- `Item` splits
    three ways and the first hit wins. `marked` captures the source ID out of a
    content row's ref.
    """

    name: str
    built: tuple[str, ...] = ()
    marked: str = ""


#: The twenty source tables. Built ones first, because the repo column is the
#: reason this exists; the rest alphabetical.
#:
#: **Every `marked` pattern is anchored and consumes the digits.** A monster
#: keeps its markers on its ability rows, and `m150a0` and `m1513a0` both start
#: with `m15` -- `startswith` here silently hands one creature another's
#: markers, which is the first thing this was written wrong as.
#:
#: `Item`'s rows are blocks under an item (`i399p12`, `i402x1`), not the item
#: itself, so it reads like `Monster` rather than like `Power`.
#:
#: `Class` has no pattern on purpose: its content rows key on a class slug
#: (`cf:<slug>-f0`), not on a source ID, so there is no honest way to reach them
#: from here. The ref still shows -- `game.db` has it -- the markers do not.
CATEGORIES: tuple[Category, ...] = (
    Category("Monster", ("monster",), r"^m(\d+)a\d+$"),
    Category("Power", ("power",), r"^p(\d+)[a-z]?$"),
    Category("Item", ("item", "weapon", "armour"), r"^i(\d+)[px]\d+$"),
    Category("Feat", ("feat",), r"^f(\d+)[a-z]?$"),
    Category("Race", ("race",), r"^rt:r(\d+)-"),
    Category("Class", ("class",)),
    Category("Trap", ("trap",)),
    Category("Terrain", ("terrain",)),
    Category("Disease", ("disease",)),
    Category("Associate", ("associate",)),
    Category("Companion", ("companion",)),
    Category("Background"),
    Category("Deity"),
    Category("EpicDestiny"),
    Category("Glossary"),
    Category("ParagonPath"),
    Category("Poison"),
    Category("Ritual"),
    Category("Skill"),
    Category("Theme"),
)

BY_NAME = {c.name: c for c in CATEGORIES}

#: Shown as columns: everything but the key and the two text blobs. `Teaser` is
#: the source's own "is this a preview row" flag and means nothing here.
HIDDEN = {"ID", "Txt", "PlainTxt", "Teaser"}

#: The markers a content row can carry. `content/CLAUDE.md` owns the meanings;
#: this only reports which are present.
MARKERS = ("todo", "dropped", "defect", "narrative", "obsolete")

_TAGS = re.compile(r"<[^>]+>")


# ------- reading

_local = threading.local()


def _open(path: Path, hint: str) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"{path} is missing.\n{hint}")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def source() -> sqlite3.Connection:
    """The compendium, read-only, one connection per **thread**.

    Per-thread and not cached once, for the reason `db.py:_connections` records
    at length: one `sqlite3.Connection` has shared cursor state, so two threads
    executing on it answer each other's `fetchone()`. This server is threaded.
    """
    db: sqlite3.Connection | None = getattr(_local, "source", None)
    if db is None:
        db = _open(
            SOURCE,
            "It is ~140MB of copyrighted content and is not distributed with "
            "this repository. Put your own copy at the project root.",
        )
        _local.source = db
    return db


def built() -> sqlite3.Connection | None:
    """The built database, or `None` if there is not one yet.

    Missing is not fatal here. Without it the repo column has nothing to say,
    and a search over the source still answers -- so it degrades to a note in
    the header rather than refusing to start.
    """
    if getattr(_local, "built_missing", False):
        return None
    db: sqlite3.Connection | None = getattr(_local, "built", None)
    if db is None:
        if not GAME.exists():
            _local.built_missing = True
            return None
        db = _open(GAME, "Run: uv run scripts/build.py")
        _local.built = db
    return db


@functools.cache
def columns(cat: str) -> tuple[str, ...]:
    rows = source().execute(f'SELECT name FROM pragma_table_info("{cat}")').fetchall()
    return tuple(r["name"] for r in rows if r["name"] not in HIDDEN)


@functools.cache
def total(cat: str) -> int:
    return int(source().execute(f'SELECT count(*) FROM "{cat}"').fetchone()[0])


@functools.cache
def refs(cat: str) -> dict[int, str]:
    """`{source ID: ref}` for one category, read out of `game.db`.

    **Looked up, never computed.** `monster.id=15` is `m15` and it is tempting
    to stop there, but `trap` is `t:5`, `terrain` ID 3 is `x2_4`, and
    `companion` has no `id` column at all -- its ref is `comp:<id>` and the ID
    has to come back out of it. A formula would be wrong for four of the eleven
    built categories and look right for the other seven.
    """
    db = built()
    if db is None:
        return {}
    out: dict[int, str] = {}
    for table in BY_NAME[cat].built:
        names = {r["name"] for r in db.execute(f'SELECT name FROM pragma_table_info("{table}")')}
        if not names:
            continue
        if "id" in names:
            for row in db.execute(f'SELECT id, ref FROM "{table}"'):
                out.setdefault(int(row["id"]), row["ref"])
            continue
        for row in db.execute(f'SELECT ref FROM "{table}"'):
            found = re.search(r"(\d+)", row["ref"] or "")
            if found:
                out.setdefault(int(found.group(1)), row["ref"])
    return out


@functools.lru_cache(maxsize=1)
def markers() -> dict[str, dict[int, tuple[str, ...]]]:
    """`{category: {source ID: markers present}}`, derived from the content rows.

    **The import has to be `content.loader`.** `from combat_engine.engine.dsl
    import REGISTRY` on its own yields *three* rows -- importing the content
    tree is what fills it, which `content/__init__.py` already warns about. It
    costs about 0.6s, once, on the first search of a run.

    A monster's markers are the union of the markers on its ability rows, which
    is the shape `loader.defective` reads for the same reason: the row is the
    one place the fact lives, so a second list cannot go stale against it.
    """
    import combat_engine.content.loader  # noqa: F401  -- the import is what fills REGISTRY
    from combat_engine.engine.dsl import REGISTRY

    patterns = [(c.name, re.compile(c.marked)) for c in CATEGORIES if c.marked]
    found: dict[str, dict[int, set[str]]] = {name: {} for name, _ in patterns}
    for ref, row in REGISTRY.items():
        present = tuple(m for m in MARKERS if getattr(row, m, None))
        if not present:
            continue
        for name, pattern in patterns:
            hit = pattern.match(ref)
            if hit:
                found[name].setdefault(int(hit.group(1)), set()).update(present)
                break
    return {
        name: {ident: tuple(m for m in MARKERS if m in got) for ident, got in table.items()}
        for name, table in found.items()
    }


def repo(cat: str, ident: int) -> dict[str, Any]:
    """What this repo made of one source row. See the module docstring."""
    if not BY_NAME[cat].built:
        return {"state": "absent"}
    ref = refs(cat).get(ident)
    if not ref:
        return {"state": "unbuilt"}
    return {"state": "built", "ref": ref, "markers": markers().get(cat, {}).get(ident, ())}


def plain(row: sqlite3.Row) -> str:
    """The card as text. `PlainTxt`, falling back to stripping the markup."""
    return row["PlainTxt"] or _TAGS.sub(" ", row["Txt"] or "")


# ------- searching


def _compile(pattern: str, fold: bool) -> re.Pattern[str] | None:
    """`None` for an empty pattern, which means "every row"."""
    if not pattern:
        return None
    return re.compile(pattern, re.IGNORECASE if fold else 0)


def _snippets(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Escaped HTML, with each match wrapped in a `<mark>`.

    Escaping happens per fragment and the `<mark>` goes in after, so a card that
    contains a `<` cannot close the tag we just opened.
    """
    out: list[str] = []
    for hit in list(pattern.finditer(text))[:SNIPPETS]:
        start, end = hit.span()
        if start == end:  # a zero-width pattern matches everywhere; a snippet of it says nothing
            continue
        lead = text[max(0, start - AROUND) : start]
        tail = text[end : end + AROUND]
        piece = (
            ("…" if start - AROUND > 0 else "")
            + html.escape(lead)
            + "<mark>"
            + html.escape(text[start:end])
            + "</mark>"
            + html.escape(tail)
            + ("…" if end + AROUND < len(text) else "")
        )
        out.append(" ".join(piece.split()))
    return out


def search(
    cat: str,
    pattern: str,
    *,
    targets: set[str],
    fold: bool,
    filters: dict[str, str],
    sort: str,
    descending: bool,
    page: int,
) -> dict[str, Any]:
    """Rows of one category matching a regex, and what matched.

    The main pattern is OR-ed across the chosen targets; the per-column filters
    are AND-ed on top. An empty main pattern lists the category.
    """
    main = _compile(pattern, fold)
    columns_ = columns(cat)
    column_filters = [
        (name, _compile(expr, fold))
        for name, expr in filters.items()
        if name in columns_ and expr
    ]

    wanted = ", ".join(f'"{c}"' for c in columns_)
    needs_text = bool(main) and ("text" in targets or "html" in targets)
    select = f'SELECT ID, {wanted}' + (", Txt, PlainTxt" if needs_text else "") + f' FROM "{cat}"'

    rows: list[dict[str, Any]] = []
    for row in source().execute(select):
        if any(f and not f.search(str(row[name] or "")) for name, f in column_filters):
            continue
        snippets: list[str] = []
        if main:
            hit = False
            if "name" in targets and main.search(row["Name"] or ""):
                hit = True
            if "text" in targets:
                text = plain(row)
                if main.search(text):
                    hit = True
                    snippets = _snippets(text, main)
            if "html" in targets and not snippets:
                raw = row["Txt"] or ""
                if main.search(raw):
                    hit = True
                    snippets = _snippets(raw, main)
            if not hit:
                continue
        ident = int(row["ID"])
        rows.append(
            {
                "id": ident,
                "cells": {c: row[c] for c in columns_},
                "snippets": snippets,
                "repo": repo(cat, ident),
            }
        )

    key = sort if sort in columns_ else "Name"
    rows.sort(key=lambda r: _sortable(r["cells"][key]), reverse=descending)

    pages = max(1, -(-len(rows) // PER_PAGE))
    page = min(max(1, page), pages)
    start = (page - 1) * PER_PAGE
    return {
        "category": cat,
        "columns": list(columns_),
        "total": total(cat),
        "matched": len(rows),
        "page": page,
        "pages": pages,
        "sort": key,
        "descending": descending,
        "rows": rows[start : start + PER_PAGE],
    }


def _sortable(value: Any) -> tuple[int, float, str]:
    """Sort numbers as numbers, blanks last, everything else as folded text.

    The source stores `Level` as TEXT on some tables and INTEGER on others, and
    a few levels are ranges, so a plain string sort puts 10 before 2.
    """
    if value is None or value == "":
        return (2, 0.0, "")
    found = re.match(r"\s*-?\d+", str(value))
    if found:
        return (0, float(found.group()), str(value).lower())
    return (1, 0.0, str(value).lower())


# ------- one card

#: Every image the source references, as a glyph -- **all seventeen**, counted
#: over all 26,601 rows. A 40-row-per-category sample found nine and missed the
#: `\da.gif` recharge faces entirely, which is most of what a monster's usage
#: line is about.
#:
#: The numbered ones are die faces: `etl/monster.py:577-581` reads
#: `/symbol/(\d)` as "recharge when the die shows that", so a die face is what
#: they are and a die face is what they get.
#:
#: The `title` keeps the filename. A glyph that reads wrong can then be traced
#: to what it stood for, rather than quietly meaning something else -- which
#: matters because these are the only reading of attack type and recharge a card
#: has, and guessing one wrong would be a silently false card.
GLYPHS = {
    "images/bullet.gif": "✦",
    "images/symbol/x.gif": "✖",
    "images/symbol/1a.gif": "⚀",
    "images/symbol/2a.gif": "⚁",
    "images/symbol/3a.gif": "⚂",
    "images/symbol/4a.gif": "⚃",
    "images/symbol/5a.gif": "⚄",
    "images/symbol/6a.gif": "⚅",
    "images/symbol/S2.gif": "⚔",
    "images/symbol/S3.gif": "➹",
    "images/symbol/Z1.gif": "◣",
    "images/symbol/Z1a.gif": "◣",
    "images/symbol/Z2a.gif": "◎",
    "images/symbol/Z3a.gif": "◈",
    "images/symbol/Z4.gif": "◆",
    "images/symbol/Z4a.gif": "◆",
    "images/symbol/aura.png": "◉",
}

_SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)
_DROP = re.compile(r"<(?:link|meta)\b[^>]*>", re.I)
#: `src\s*=\s*` and either quote, because the source writes `<img src = "..."`
#: 5,268 times and a tighter pattern left those images on the page.
_IMG = re.compile(r"""<img\b[^>]*?src\s*=\s*["']([^"']*)["'][^>]*>""", re.I)
_LINK = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_INTERNAL = re.compile(r"item\.php\?fid=(\d+)", re.I)


def clean(fragment: str) -> str:
    """The card body, with everything that would reach off this machine removed.

    The source rows are whole standalone HTML documents written for a web
    application that no longer exists: a `<script>` per row, a stylesheet and
    images we do not have, and outbound links through a referer-stripping
    redirector. None of it can be left in.
    """
    out = _SCRIPT.sub("", fragment)
    out = _DROP.sub("", out)

    def image(hit: re.Match[str]) -> str:
        src = hit.group(1)
        glyph = GLYPHS.get(src, "▫")
        return f'<span class="sym" title="{html.escape(src)}">{glyph}</span>'

    out = _IMG.sub(image, out)

    def link(hit: re.Match[str]) -> str:
        attrs, label = hit.group(1), hit.group(2)
        found = _INTERNAL.search(attrs)
        if found:
            return f'<a href="?view=Item.{found.group(1)}">{label}</a>'
        # Everything else points at a dead site through a redirector. Keep the
        # words, drop the hop.
        return f'<span class="deadlink">{label}</span>'

    return _LINK.sub(link, out)


def entry(cat: str, ident: int) -> dict[str, Any]:
    wanted = ", ".join(f'"{c}"' for c in columns(cat))
    row = source().execute(
        f'SELECT ID, {wanted}, Txt FROM "{cat}" WHERE ID = ?', (ident,)
    ).fetchone()
    if row is None:
        raise KeyError(f"{cat} {ident}")
    return {
        "category": cat,
        "id": ident,
        "cells": {c: row[c] for c in columns(cat)},
        "html": clean(detail(row["Txt"] or "")),
        "repo": repo(cat, ident),
    }


def catalogue() -> dict[str, Any]:
    return {
        "built": built() is not None,
        "categories": [
            {
                "name": c.name,
                "count": total(c.name),
                "columns": list(columns(c.name)),
                "cross": bool(c.built),
                "markers": bool(c.marked),
            }
            for c in CATEGORIES
        ],
    }


# ------- serving


class Handler(BaseHTTPRequestHandler):
    server_version = "compendium"

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet. A request per keystroke would bury the one line that matters.

        The parameter has to keep the stdlib's name, shadowed builtin and all:
        `scripts/types.py` checks override compatibility and renaming it to
        something tidier is an invalid override.
        """

    def _send(self, code: int, kind: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        self._send(code, "application/json; charset=utf-8", json.dumps(payload).encode())

    def _static(self, name: str) -> None:
        path = WEB / name
        if not path.is_file():
            self._send(404, "text/plain; charset=utf-8", b"no such file")
            return
        kinds = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
        kind = kinds.get(path.suffix, "application/octet-stream")
        self._send(200, f"{kind}; charset=utf-8", path.read_bytes())

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        route = url.path

        try:
            if route in ("/", "/index.html"):
                self._static("index.html")
            elif route in ("/style.css", "/app.js"):
                self._static(route.lstrip("/"))
            elif route == "/api/categories":
                self._json(200, catalogue())
            elif route == "/api/search":
                self._json(200, self._search(query))
            elif route == "/api/entry":
                self._json(200, self._entry(query))
            else:
                self._send(404, "text/plain; charset=utf-8", b"no such route")
        except re.error as bad:
            # A typo must read as a typo. Returning zero rows here would make a
            # broken pattern indistinguishable from a true negative, which is
            # the one failure this whole tool exists to avoid.
            self._json(400, {"error": f"bad pattern: {bad}"})
        except KeyError as missing:
            self._json(404, {"error": f"no such row: {missing}"})
        except Exception as wrong:
            self._json(500, {"error": f"{type(wrong).__name__}: {wrong}"})

    def _search(self, query: dict[str, str]) -> dict[str, Any]:
        cat = query.get("cat", CATEGORIES[0].name)
        if cat not in BY_NAME:
            raise KeyError(cat)
        targets = {t for t in query.get("in", "name,text").split(",") if t}
        filters = {k[4:]: v for k, v in query.items() if k.startswith("col.")}
        return search(
            cat,
            query.get("q", ""),
            targets=targets,
            fold=query.get("fold", "1") != "0",
            filters=filters,
            sort=query.get("sort", "Name"),
            descending=query.get("dir", "asc") == "desc",
            page=int(query.get("page", "1") or 1),
        )

    def _entry(self, query: dict[str, str]) -> dict[str, Any]:
        cat = query.get("cat", "")
        if cat not in BY_NAME:
            raise KeyError(cat)
        return entry(cat, int(query.get("id", "0") or 0))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=0, help="pin the port (default: any free one)")
    ap.add_argument("--open", action="store_true", help="open a browser at it")
    args = ap.parse_args()

    source()  # fail now, with the reason, rather than on the first request
    port = args.port or free_port()
    # Loopback only. This serves 140MB of content that is nobody else's.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"compendium search on {url}")
    if built() is None:
        print(f"  {GAME} is missing, so the repo column will be empty.")
    print("  ctrl-c to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
