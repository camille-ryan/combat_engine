# Working on this

## The one rule

**Nobody writing a power is shown what it is called.** Specs come out of
`scripts/spec.py` with the names and flavour text stripped; the engine holds
ids and mechanics, and the prose lives in a git-ignored `localization/`
built from your own copy of the compendium. `scripts/leaks.py` checks that
nothing has crept in, and it runs as part of `check.py`.

A row that cannot be expressed is **left out**, and the missing `Cast`
method reported. Never stubbed, never faked: `scripts/coverage.py` counts
what is absent and a count cannot go stale, where a half-written row looks
finished.

## Checking your work

```
uv run scripts/check.py            # all seven instruments, ~47s
uv run scripts/check.py --fast     # skip the two that start a server, ~3s
uv run scripts/check.py --all      # audit every row, not just changed ones
uv run scripts/check.py --history  # what each has cost, and what it has caught
```

These are instruments rather than tests — each plays the real thing and
reports what it saw. **There are no unit tests and none should be written.**

`--history` exists because the previous attempt at this project grew a check
suite nobody could afford to run, and the reason it got that way is that
nothing measured it. If an instrument has never caught anything in dozens of
runs, it should have to justify its seconds.

`audit` runs only the rows in changed content files by default, and widens back
to everything the moment anything under `engine/` is touched — an engine
change moves every row at once, so a narrowed run there would not be narrow,
it would be wrong.

## Git

Work is tracked in **GitHub Issues**. Open one before starting unplanned
work; close it from the commit rather than by hand:

```
Closes #12
```

Repeat the keyword for each one. `Closes #12, #13` closes **only #12** — the
rest is read as prose, and six issues once stayed open after the commit that
finished them:

```
Closes #12, closes #13, closes #14
```

`scripts/issues.py` closes the content issues from coverage, so those need no
keyword at all. Engine issues are closed by hand, with what landed and how it
was verified — a closing comment that only says "done" is worth nothing to
the next reader.

Commits Claude writes are authored `Claude (Camille)` with Camille as
committer, so `git log` shows who wrote what while the account stays
Camille's. There is an alias for it:

```
git cc -m "..."     # author: Claude (Camille), committer: Camille
git commit -m "..." # author: Camille — for commits you write yourself
```

If you clone fresh, the alias is local config and needs setting again:

```
git config alias.cc "!git -c author.name='Claude (Camille)' \
    -c author.email='rdbrady@gmail.com' commit"
```

Messages are prose: a subject that is a sentence, then what was actually
wrong and why it mattered. The history is meant to be readable.

## What is not in the repo

`compendium.sqlite` (the source data — supply your own), `data/` (derived
from it), `localization/` (names and flavour), and `logs/` (transcripts and
the instrument ledger). None of them has ever been committed.

`scripts/fixtures/` **is** tracked, deliberately: combat holds no randomness
beyond a seeded generator, so a divergence from a recorded log is always a
code change, and a fresh clone with no fixtures would have nothing to verify
against.
