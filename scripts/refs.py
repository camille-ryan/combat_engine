"""Every ref named in prose resolves to something. The docstrings tell lies.

A row's docstring explains what it waits on and names other rows by ref --
"the same gap `m5941a1` waits on", "`general_s.f3794` has been doing this all
along". Those refs are load-bearing: the next reader follows them instead of
re-reading the card, and a wrong one sends them somewhere real and
irrelevant, which is worse than sending them nowhere.

**Two found the day this was written**, one mine and one three months old:

* `f1411`'s docstring cited `general_s.f3772`. The row is `f3794`. I invented
  it and caught it by hand.
* `m6619a2`'s docstring named disease `x5_34`. Its card says `x5_93` -- a
  different page. That one had sat unnoticed since the row was written, and
  it was found only because the disease work forced a card read. **Nothing
  could have caught it**: a guessed ref in prose reads exactly like a right
  one.

Both are the same failure and neither breaks anything, which is why no
existing instrument looks: the code runs, the row fires, the audit is green,
and the prose is wrong.

**Deliberately narrow.** It checks that a ref-shaped token *resolves*, not
that it is the right one -- `x5_34` resolves and was still wrong, so this
would not have caught the second case above. What it catches is the invented
ref, which is the commoner half. Honest about that rather than claiming the
harder thing.

On probation: Camille asked for it to be monitored, so `--audit` prints what
it flags with enough context to judge each one. The precedent is the
staleness check tried earlier and dropped at 1 real find in 8 flags.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

#: A ref as the tree spells them. Deliberately anchored on the prefixes in
#: use rather than "a letter and digits": `d20`, `1d6`, `a1` and `w3610` are
#: all letter-then-digits and only some of them are refs.
_REF = re.compile(
    r"`(?:[a-z_]+(?:\.[a-z_]+)*\.)?(?P<ref>(?:m\d+a\d+|m\d+|p\d+(?::augment\d+)?|i\d+[px]\d+|i\d+"
    r"|f\d+[b]?|x\d+_\d+|cf:[a-z0-9-]+|rt:[a-z0-9-]+|r\d+|w\d+)"
    r")(?:\(\))?`"
)

#: Prefixes this can actually adjudicate, and what holds each one.
#: Every table holding something prose cites by ref. Listed rather than
#: remembered: the first run flagged 110 refs and most were races, racial
#: traits and item blocks -- tables this did not load, not refs that were
#: wrong. That measurement is what shaped this list.
_TABLES = (
    "monster", "monster_power", "power", "class_feature", "build_option",
    "build_power", "item", "item_block", "item_step", "feat", "race",
    "racial_trait", "companion", "weapon", "armour", "associate", "terrain",
    "trap", "disease",
)


def _known() -> set[str]:
    """Everything a ref in prose could legitimately point at."""
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.db import game
    from combat_engine.engine.dsl import REGISTRY

    out = set(REGISTRY)
    db = game()
    for table in _TABLES:
        try:
            out |= {r[0] for r in db.execute(f"SELECT ref FROM {table}")}
        except Exception:
            continue
    return out


def _prose(path: Path) -> list[tuple[int, str]]:
    """Docstring and comment lines, with their line numbers."""
    lines = path.read_text(errors="replace").splitlines()
    out: list[tuple[int, str]] = []
    in_doc = False
    for n, line in enumerate(lines, 1):
        stripped = line.strip()
        ticks = stripped.count('"""')
        if in_doc or ticks or stripped.startswith("#"):
            out.append((n, line))
        if ticks % 2:
            in_doc = not in_doc
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", action="store_true",
                    help="print every flag with context, to judge the rate")
    ap.add_argument("--placeholders", action="store_true",
                    help="include cf:/rt:/x_ refs for things not yet declared")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    known = _known()
    # **`content/` by default, and only it.** That is where a row's prose
    # cites another row, which is the thing worth checking. `engine/`,
    # `etl/` and `scripts/` docstrings explain the ref *format* -- "`p289`,
    # or `m145a2` for a stat block's ability", "`i601p1` its first Power" --
    # and an example is not a citation. Measured: those two directories
    # contribute five flags and all five are examples, including this file's
    # own docstring citing the bug it was built for. Pass a path to check
    # them anyway.
    roots = [Path(p) for p in args.paths] or [ROOT / "src" / "combat_engine" / "content"]
    # `__init__.py` is skipped: a package docstring explains the ref *format*
    # -- "an item's first Property and `i601p1` its first Power" -- and an
    # example is not a citation. That was the only false positive left in the
    # content tree once armour refs came out of the pattern.
    files = [f for root in roots
             for f in ([root] if root.is_file() else sorted(root.rglob("*.py")))
             if "__pycache__" not in str(f) and f.name != "__init__.py"]

    bad: list[tuple[Path, int, str, str]] = []
    seen = 0
    for path in files:
        for num, line in _prose(path):
            for m in _REF.finditer(line):
                ref = m.group("ref")
                seen += 1
                # **The placeholder families are waived by default**, and
                # that is measured rather than assumed. The content tree
                # names 38 refs that resolve to nothing and every one is a
                # `cf:`, `rt:` or `x<n>_` for something **not yet declared
                # or not yet ingested** -- which is the tree's own
                # convention for saying what is missing, reported properly
                # by `blocked.py`. Flagging them makes this instrument red
                # forever on rows that are correctly marked.
                if not args.placeholders and re.match(r"(cf:|rt:|x\d+_)", ref):
                    continue
                if ref not in known:
                    try:
                        shown = path.resolve().relative_to(ROOT)
                    except ValueError:
                        shown = path
                    bad.append((shown, num, ref, line.strip()))

    if args.audit:
        for rel, num, ref, line in bad:
            print(f"{rel}:{num}  {ref}\n    {line[:110]}")
        print()
    print(f"{seen} refs named in prose, {len(bad)} resolving to nothing")
    if bad and not args.audit:
        for rel, num, ref, _ in bad[:20]:
            print(f"  {rel}:{num}  {ref}")
        if len(bad) > 20:
            print(f"  ... and {len(bad) - 20} more")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
