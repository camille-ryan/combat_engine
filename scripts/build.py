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

**And the nightly runs in the main checkout** (#848). It would sweep
21,476 rows against a database their code does not match and report that as a
verdict on `master`: a green run meaningless, a red one sending the next
session after a regression that is not in the commit it is blamed on.

`scripts/CLAUDE.md` already says a rebuild must not race a sweep in the
*same* checkout. This is the same fault across two, and the warning did not
cover it because nobody had both directories at once when it was written.
#857.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys


def _ancestry() -> set[int]:
    """This process and every parent of it.

    Needed because the check below looks for *other* `scripts/` processes and
    this one is itself `uv run scripts/build.py` -- under `nohup` that is a
    chain of three or four, so excluding `getpid()` and `getppid()` alone
    leaves the build reporting itself and refusing every time. A guard that
    always fires gets `--force`-d by reflex and then protects nothing.
    """
    mine, pid = set(), os.getpid()
    for _ in range(12):
        if pid <= 1 or pid in mine:
            break
        mine.add(pid)
        try:
            got = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            break
        pid = int(got) if got.isdigit() else 0
    return mine


def _live_readers() -> list[str]:
    """Other `scripts/` processes running right now.

    Every one of them resolves rows through `data/game.db`, and this build
    opens by deleting it. Fails open -- if `ps` cannot be read the build
    proceeds, because refusing on a broken probe would be worse than the
    hazard.
    """
    mine = _ancestry()
    try:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True, text=True, check=True).stdout
    except Exception:
        return []
    found = []
    for line in listing.splitlines():
        pid, _, command = line.strip().partition(" ")
        if not pid.isdigit() or int(pid) in mine:
            continue
        if "scripts/" not in command or "ps -axo" in command:
            continue
        # The shell that launched an instrument carries the command in its
        # own argv, so one run shows up as both the wrapper and the
        # interpreter. Counting the wrapper reported "3 processes" for a
        # single `replay.py verify`, and a count that overstates by 50% is
        # the kind of number this project does not leave standing even when
        # the decision it drives ("wait") is unchanged.
        if re.match(r"^(?:/bin/)?(?:z|ba|da|k)?sh\b", command):
            continue
        # **And `uv run`, for the same reason and by the same measurement.**
        # The note above fixed the shell wrapper and left this one: one
        # `replay.py verify` still showed as two, `uv run scripts/...`
        # beside `.venv/bin/python3 scripts/...`, so the refusal read "2
        # other processes are live" for a single reader. The interpreter is
        # the one holding the database open, so the wrapper is what goes --
        # which also keeps the listed pid the one worth waiting on.
        if re.match(r"^\S*uv\b", command) and " run " in f" {command} ":
            continue
        found.append(f"  {pid}  {command[:96]}")
    return found


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
            f"its readers -- and the nightly -- would run against data\n"
            f"their code does not match. Do ETL work on `master`, or after this\n"
            f"branch merges.\n"
            f"\n"
            f"`--force` if you mean it. #857.",
            file=sys.stderr)
        raise SystemExit(1)
    readers = _live_readers()
    if readers and "--force" not in sys.argv:
        listed = "\n".join(readers)
        print(
            f"refusing: {len(readers)} other `scripts/` process(es) are live, "
            f"and they read\n"
            f"`data/game.db` -- which this build opens by deleting.\n"
            f"\n"
            f"{listed}\n"
            f"\n"
            f"Deleting it under a reader does not slow that run, it makes it\n"
            f"*wrong*: `audit.py` reports a raise on a sound row, and a sweep\n"
            f"certifies nothing. Wait for them to finish.\n"
            f"\n"
            f"`--force` if you mean it.",
            file=sys.stderr)
        raise SystemExit(1)
    from combat_engine.etl.build import build

    print(build().render())
