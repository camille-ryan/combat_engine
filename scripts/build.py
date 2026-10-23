#!/usr/bin/env python
"""Rebuild `data/game.db` and `localization/names.json` from the compendium.

    uv run scripts/build.py
    uv run scripts/build.py --force    rebuild from a worktree anyway

**Refuses to run from a git worktree**, because the output is not this
directory's to rewrite. In a worktree both the input and the output are
symlinks into the main checkout:

    compendium.sqlite -> <main>/compendium.sqlite
    data/game.db      -> <main>/data/game.db

That is right for the input -- the compendium is large and git-ignored and
wants one copy -- and a hazard for the output, because `etl.build` opens with
`GAME.unlink(missing_ok=True)` and rebuilds from scratch, by design. So a
rebuild started here deletes and rewrites the database the main checkout
reads, and a worktree is on a branch whose ETL changes are by definition not
merged. After it, `master`'s working tree holds the **old** ETL code while
`data/game.db` holds data built by the **new** one, and every reader there --
`audit.py`, `cards.py`, `bonuses.py`, `keywords.py`, `legs.py`, `spec.py` --
reads the new data through the old code.

**And the 03:07 nightly runs in the main checkout** (#848). It would sweep
21,476 rows against a database their code does not match and report that as a
verdict on `master`: a green run meaningless, a red one sending the next
session after a regression that is not in the commit it is blamed on.

`scripts/CLAUDE.md` already says a rebuild must not race a sweep in the
*same* checkout. This is the same fault across two, and the warning did not
cover it because nobody had both directories at once when it was written.
#857.
"""

from __future__ import annotations

import subprocess
import sys


def _in_worktree() -> str:
    """The main checkout's path if this is a worktree, else "".

    The same question `check.py` asks for #848, by the same means: in a
    worktree `--git-common-dir` resolves into the main checkout while
    `--git-dir` stays local. Fails open -- outside a repository there is no
    worktree to warn about.
    """
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True).stdout.strip()
        here = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
            capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""
    return common.removesuffix("/.git") if common and common != here else ""


if __name__ == "__main__":
    main = _in_worktree()
    if main and "--force" not in sys.argv:
        print(
            f"refusing: this is a git worktree and `data/game.db` is a symlink\n"
            f"into {main}, which is on `master` and holds the old ETL code.\n"
            f"\n"
            f"A rebuild here deletes and rewrites that checkout's database, so\n"
            f"its readers -- and the 03:07 nightly -- would run against data\n"
            f"their code does not match. Do ETL work on `master`, or after this\n"
            f"branch merges.\n"
            f"\n"
            f"`--force` if you mean it. #857.",
            file=sys.stderr)
        raise SystemExit(1)
    from combat_engine.etl.build import build

    print(build().render())
