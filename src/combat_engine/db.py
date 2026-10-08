"""Where the built database and the localisation live, and how to read them.

**The smallest module in the package, and it sits below every component.**
Nothing here imports anything else in `combat_engine`, which is what lets ETL,
content, chargen, story and the API all use it without any of them reaching
through another.

It used to live in `etl/build.py`, the module that *writes* `game.db`, and that
was the wrong place in a way with consequences rather than merely untidy:

* **Five components read it and none of them writes.** `chargen` (8 sites),
  `story` (3), `content` (2), `api` (2) and `scripts/` (18). The only writer is
  `scripts/build.py`.
* **Almost every one of those imports was function-local** -- buried inside the
  function that needed it rather than at the top of the file. That is not a
  style choice, it is people avoiding the import, and what they were avoiding
  is 3,828 lines of compendium parsing (`etl.feat`, `etl.html`, `etl.item`,
  `etl.monster`, `etl.power`, `etl.sanitise`, `etl.wields`) pulled in to open a
  read-only sqlite file.
* **`etl/CLAUDE.md` had to carry a warning about it**: that an ETL schema change
  reaches `engine` transitively through `content/loader.py`, so "engine does not
  import etl" is a wrong reading of the seam. With the read path here that
  warning describes a route that no longer exists.
* **And it caused a real bug.** `game()`'s docstring used to justify
  `check_same_thread=False` by reasoning about FastAPI's threadpool -- the
  extraction pipeline deciding connection policy for every reader in the system,
  on an argument about a web framework, somewhere nothing in `api/` could see
  it. Eight concurrent `POST /api/encounter` returned seven 500s. See
  `_connections`.

#334.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

#: The repository root. `parents[2]` from here -- `src/combat_engine/db.py` --
#: where it was `parents[3]` from `src/combat_engine/etl/build.py`. One
#: directory shallower, which is the whole difference and is easy to get wrong.
ROOT = Path(__file__).resolve().parents[2]

#: Your own copy of the compendium. Never committed, and nothing but `etl/`
#: should open it -- the path lives here because the ETL needs to know where to
#: read from and `scripts/leaks.py` needs it to check what came out.
SOURCE = ROOT / "compendium.sqlite"

#: The built database. Recreated from scratch by every build, by design.
GAME = ROOT / "data" / "game.db"

#: Printed names and flavour, git-ignored. The legal boundary: this file is the
#: only place a printed name is allowed to be, and the engine never reads it.
NAMES = ROOT / "localization" / "names.json"


#: One connection per **thread**, not per process.
#:
#: This was `@lru_cache(maxsize=1)` plus `check_same_thread=False`, with a
#: docstring reasoning that "read-only, so sharing it is safe". That is not what
#: `check_same_thread` does: it makes sqlite3 *permit* cross-thread use, it does
#: not serialise it. One `Connection` has shared statement and cursor state, so
#: two threads executing on it interleave -- read-only prevents the *data* being
#: corrupted, not one thread's `fetchone()` being answered from another thread's
#: cursor.
#:
#: Measured. `POST /api/encounter` runs on a FastAPI worker thread, deliberately
#: (`api/app.py:113-118`), and eight concurrent creates returned **seven 500s
#: and one 200**. The tracebacks all landed in `content/loader.load` and
#: `loader.pick`, with `KeyError: 'no monster m1010'` for a ref that exists and
#: `IndexError: tuple index out of range` -- the two classic shapes of a cursor
#: read from the wrong thread. Run sequentially the same eight all returned 200.
#:
#: It also made `scripts/browser.py` -- the entire cover for `web/` --
#: non-deterministic: 5 failures, then 3, then 3, on byte-identical code.
_connections = threading.local()


def _open_game() -> sqlite3.Connection:
    db = getattr(_connections, "game", None)
    if db is None:
        if not GAME.exists():
            raise SystemExit(f"{GAME} is missing. Run: uv run scripts/build.py")
        # `check_same_thread` can go back to its default now: each connection is
        # only ever touched by the thread that opened it, which is the actual
        # invariant.
        db = sqlite3.connect(f"file:{GAME}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        _connections.game = db
    return db


def game() -> sqlite3.Connection:
    """The built database. The engine reads this, never the compendium.

    One connection per thread, opened once and kept. It used to open a fresh one
    on every call, and `loader.spawn` calls it several times per creature -- so
    building an audit board opened six connections, and an audit builds a
    hundred thousand boards. That optimisation is intact; what changed is that
    the cache is per thread rather than per process, because a
    `sqlite3.Connection` cannot be used from two at once. See `_connections`.
    """
    return _open_game()


@lru_cache(maxsize=1)
def localisation() -> dict[str, dict[str, str]]:
    """Printed names, if this machine has them. The engine never calls this.

    Cached: it is seventeen thousand entries, it is read once per name looked
    up, and re-parsing it each time was a quarter of the time taken to draw
    the board. Call `localisation.cache_clear()` after a rebuild.
    """
    if not NAMES.exists():
        return {}
    return json.loads(NAMES.read_text())
