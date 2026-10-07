#!/usr/bin/env python
"""Play the real page in a real browser, headless.

    uv run scripts/browser.py
    uv run scripts/browser.py --show          watch it happen
    uv run scripts/browser.py --shot out.png  and keep a picture

The other instruments talk to the API. This one loads `web/index.html` in
Chromium, clicks the board, and reads the DOM back -- which is the only way
to catch the half of the contract that is not JSON: an event stream under the
wrong frame name, an animation keyed to a spelling nothing emits, a square
the page will not let you click.

Every one of those was invisible to `api_smoke.py`, because the JSON was
perfectly correct and the page ignored it.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from combat_engine.engine.grid import distance

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self) -> None:
        self.port = free_port()
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> Server:
        self.proc = subprocess.Popen(
            ["uv", "run", "uvicorn", "combat_engine.api.app:app",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=ROOT, env={**os.environ},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # **Its own process group, so teardown can reach the server.**
            # `self.proc` is the `uv` wrapper, not uvicorn -- terminating it
            # left the real server running, reparented to PID 1. 69 of them
            # had accumulated over three and a half days, holding 328 MB and
            # contending for the cores the audit is trying to use.
            start_new_session=True,
        )
        import urllib.request

        for _ in range(80):
            with contextlib.suppress(Exception):
                urllib.request.urlopen(f"{self.base}/api/health", timeout=3)
                return self
            time.sleep(0.25)
        raise SystemExit("the server did not come up")

    def __exit__(self, *_: object) -> None:
        """Signal the whole process group, not just the wrapper.

        `self.proc` is the `uv run ...` handle; the uvicorn is its child.
        `terminate()` killed `uv` and left the server running, reparented to
        PID 1 -- **69 of them had accumulated over three and a half days**,
        holding 328 MB and contending for the cores the audit needs. That is
        what `start_new_session=True` above is for: `killpg` reaches both.

        Killed rather than asked politely if it dawdles. A uvicorn holding
        an event stream open can outlast a polite terminate, and the wait
        raising turned a clean run into a failure *after* every check had
        passed -- the instrument reporting on its own teardown.
        """
        if not self.proc:
            return
        import signal

        try:
            group = os.getpgid(self.proc.pid)
        except (ProcessLookupError, PermissionError):
            group = None
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                if group is not None:
                    os.killpg(group, sig)
                elif sig == signal.SIGTERM:
                    self.proc.terminate()
                else:
                    self.proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=10)
                return

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.skipped: list[str] = []
        self.passed = 0

    def that(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  ok    {what}")
        else:
            self.failed.append(what)
            print(f"  FAIL  {what}" + (f"\n          {detail}" if detail else ""))

    def skip(self, what: str, why: str) -> None:
        """This board could not pose the question. Said out loud, never passed.

        `scripts/CLAUDE.md`: *"An instrument must not skip itself quietly. A
        check that runs on half its runs is not a check. Pin the seed, and
        report a skip as a skip rather than passing."* The seed here **is**
        pinned and it is still not enough -- which is the honest finding: a
        dealt board sometimes cannot pose a question, and counting that as a
        pass is the loosening the rule is about.

        Not counted in `passed`, so the headline figure moves when a run skips
        something and a reader can see it did. #402.
        """
        self.skipped.append(what)
        print(f"  skip  {what}\n          {why}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--show", action="store_true", help="a visible browser")
    ap.add_argument("--shot", help="save a screenshot here")
    ap.add_argument("--speed", default="instant", help="animation speed to play at")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed. Run: uv sync --all-extras", file=sys.stderr)
        return 1

    check = Checks()
    with Server() as server, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.show)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})

        problems: list[str] = []
        page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(str(e)))

        def failed_request(response) -> None:  # noqa: ANN001
            """A 4xx says which call and with what, not merely that one broke.

            "Failed to load resource: 400" is what the console gives, and it
            names neither the endpoint nor the body -- so a real wire bug
            reads exactly like noise.
            """
            if response.status < 400:
                return
            with contextlib.suppress(Exception):
                problems.append(
                    f"HTTP {response.status} {response.url.split('/api/')[-1]} "
                    f"<- {response.request.post_data} :: {response.text()[:120]}"
                )

        page.on("response", failed_request)

        # The page keeps its state to itself, so the last snapshot it was
        # served is read off the wire rather than out of the DOM.
        served: list[dict] = []

        def remember(response) -> None:  # noqa: ANN001
            if "/api/encounter" in response.url and response.request.method in ("POST", "GET"):
                with contextlib.suppress(Exception):
                    body = response.json()
                    if isinstance(body, dict) and "board" in body:
                        served.append(body)

        page.on("response", remember)

        # Every call the page makes, in order. A click that does not move the
        # board could be a click that never reached the handler or a move the
        # server refused, and the DOM alone cannot say which.
        calls: list[str] = []

        def note(response) -> None:  # noqa: ANN001
            if "/api/" in response.url:
                calls.append(
                    f"{response.status} {response.request.method} "
                    f"{response.url.split('/api/')[-1]} <- {response.request.post_data}"
                )

        page.on("response", note)

        page.goto(server.base, wait_until="networkidle")
        page.evaluate(f"localStorage.setItem('dnd4e.speed', '{args.speed}')")
        # Clicking the board is gated behind "freeform targeting", which is
        # off by default -- so a click lands on nothing and says nothing.
        # Turned on here because clicking the board is what is being tested.
        page.evaluate("localStorage.setItem('dnd4e.freeform', 'on')")
        page.reload(wait_until="networkidle")

        check.that(not problems, "the page loads with no script errors", "; ".join(problems[:3]))
        # On a known seed, for the same reason `_check_footprint` already
        # restarts on one: the fight the page opens with is drawn fresh, so
        # who is acting and what they carry was a coin toss and the run
        # counted anywhere from 40 to 48 checks. A count that moves hides
        # both a skip and a failure -- one run in five failed here and the
        # next one passed, which is worse than either answer.
        _restart(page, START_SEED, served)
        _play(page, check, problems, served, calls)

        _check_chargen(page, check, problems)

        if args.shot:
            page.screenshot(path=args.shot, full_page=True)
            print(f"\n  screenshot: {args.shot}")
        browser.close()

    print(f"\n{check.passed} checks passed, {len(check.failed)} failed"
          + (f", {len(check.skipped)} skipped" if check.skipped else ""))
    return 1 if check.failed else 0


def _texts(page, selector: str) -> list[str]:  # noqa: ANN001
    """Every matching element's text, read in **one** call.

    The shape this replaces was `[loc.nth(i).inner_text() for i in
    range(loc.count())]`, which is one round trip per element with the page
    free to re-render between any two of them. When it did, `nth(i)` waited
    30 seconds for an index that no longer existed and the run failed on a
    locator timeout rather than on anything about the page -- `nth(63)` of
    `#actions button` was the one that showed up. #355.

    One `evaluate` cannot tear: the list is read inside the page, in a single
    task, so there is no window to re-render through.
    """
    return [
        " ".join(t.split())
        for t in page.eval_on_selector_all(
            selector, "els => els.map(e => e.innerText || '')"
        )
    ]


#: How many tokens a board always has before it is worth acting on. Eight is
#: what `_play` has asserted since #355 -- five characters and at least three
#: enemies, which is the smallest encounter the dealer builds -- so the other
#: waits use the same number rather than inventing one each.
#:
#: **The point is that `wait_for_selector("#board .token")` returns on token
#: one.** #355 fixed the one site where that was followed by a length
#: assertion, and recommended auditing the rest. This is that audit: three more
#: sites waited for the first token and then acted as though the board were
#: drawn -- a monsters' turn watched, a restart issued, a stream polled. None
#: asserted a count, which is why none of them failed loudly; they failed by
#: being a race nobody could see. #402.
TOKENS_DRAWN = 8


def _settled(page, selector: str, least: int, timeout: int = 15000) -> int:  # noqa: ANN001
    """Wait until `selector` has at least `least` matches; return the count.

    **Waiting for the first of a list and then asserting the length is the
    bug this exists to remove.** `wait_for_selector("#board .token")` returns
    on token one, and the board draws them one at a time, so a run that got
    in between saw 6 and reported "the board drew 6 tokens" -- about half of
    them did. The wait now belongs to the condition actually being asserted.

    Returns the count so a caller can report the real number, and returns
    whatever it reached on timeout rather than raising: the check is then the
    thing that fails, with its own message, instead of a locator timeout that
    says nothing about what was wrong.
    """
    deadline = time.monotonic() + timeout / 1000
    count = page.locator(selector).count()
    while count < least and time.monotonic() < deadline:
        page.wait_for_timeout(100)
        count = page.locator(selector).count()
    return count


def _check_chargen(page, check: Checks, problems: list[str]) -> None:  # noqa: ANN001
    """The advisor page: ranked, explained, and choosing nothing by itself.

    Its own page and its own class names, so none of this touches the
    encounter page's selectors. Run last, because it navigates away.
    """
    before = len(problems)
    page.goto(page.url.split("/index.html")[0].rstrip("/") + "/chargen.html")
    page.wait_for_selector(".choice", timeout=20000)

    # Both lists, each waited for in its own right. Waiting for `.choice` only
    # returns on the first one drawn anywhere on the page. #355.
    n_races = _settled(page, "#races .choice", 21, timeout=20000)
    n_feats = _settled(page, "#feats .choice", 101, timeout=20000)
    races = page.locator("#races .choice")
    check.that(n_races > 20 and n_feats > 100,
               f"chargen lists {n_races} races and {n_feats} feats")

    # **Sorted by score is the feature**, so it is asserted rather than assumed:
    # the page is for reading down the score column and an unsorted list of 400
    # rows is not an advisor.
    scores = [
        float(races.nth(i).locator(".choice-score").inner_text())
        for i in range(min(6, races.count()))
    ]
    check.that(scores == sorted(scores, reverse=True),
               "chargen ranks best first", str(scores))

    # Hovering gives the reasons. Asserting a *term name* and not merely that
    # a card appeared: an empty card and an explained one look the same to a
    # check that only asks whether the panel is visible.
    races.nth(0).hover()
    page.wait_for_selector("#card:not([hidden])", timeout=5000)
    card = page.inner_text("#card")
    check.that("primary_bonus" in card or "traits_written" in card,
               "hovering a choice names the terms behind its score",
               card.replace("\n", " ")[:80])

    # Nothing is chosen until a human clicks, which is the whole difference
    # between this page and the dealer.
    check.that("race —" in page.inner_text("#picked"),
               "chargen chooses nothing on its own")
    races.nth(0).click()
    check.that("taken" in (races.nth(0).get_attribute("class") or ""),
               "clicking a choice keeps it")

    # Switching class re-ranks rather than re-sorting what was already there.
    page.select_option("#cls", "wizard")
    page.wait_for_function(
        "() => document.getElementById('leg').textContent.includes('wizard')",
        timeout=20000)
    check.that("implements only" in page.inner_text("#leg"),
               "switching to an implement class says so")
    check.that(len(problems) == before, "no script errors on the chargen page",
               "; ".join(problems[before:][:3]))


def _play(page, check: Checks, problems: list[str], served: list[dict],  # noqa: ANN001
          calls: list[str]) -> None:
    drawn = _settled(page, "#board .token", TOKENS_DRAWN)
    check.that(drawn >= TOKENS_DRAWN, f"the board drew {drawn} tokens")

    # The log. This is the one that was silently empty: the stream was fine
    # and the frames were named something the page does not listen for.
    page.wait_for_timeout(1200)
    # `.narration` is what a player reads; `.logline` is the raw stream and
    # is hidden behind a checkbox. Checking the raw lines only is how an
    # empty log panel passed for a working one.
    read = page.locator("#log .narration")
    raw = page.locator("#log .logline")
    check.that(raw.count() > 0, f"the raw stream arrived ({raw.count()} events)",
               "nothing arrived -- check the SSE frame name")
    check.that(read.count() > 0, f"the log reads as prose ({read.count()} lines)",
               "raw events arrived but no narration frames did")
    for i in range(min(4, read.count())):
        print(f"        {read.nth(i).inner_text()[:78]}")

    _check_usage_bars(page, check)

    # The action list, and a move by clicking the board. The range is no
    # longer painted on every render -- `Move` is a thing you press and the
    # squares are the answer to having pressed it -- so the check presses it.
    before = _positions(page)
    check.that(
        page.locator("#movement .mv").count() == 0,
        "the movement range is not drawn until it is asked for",
    )
    check.that(_press_move(page), "the action list offers Move")
    highlights = page.locator("#movement .mv")
    check.that(highlights.count() > 0,
               f"pressing Move highlights where you can go ({highlights.count()} squares)")

    # **A bare board click must not move anybody (#139).** Moving is now
    # selected before it is aimed, in both modes, so the reachable square that
    # walks with Move pressed must do nothing with Move unpressed. Measured on
    # a square known to be reachable and known not to provoke -- the same one
    # the click further down uses -- because "nothing moved" is only evidence
    # if the square would otherwise have moved somebody. And on the calls the
    # page made, because a board that did not move could also be a board that
    # asked the server and was refused.
    spot = _move_square_box(page, 3)
    if spot is None:
        # **The gate for everything below that walks somewhere.** A character
        # boxed in by enemies has no square that provokes nothing, which is a
        # legal board rather than a broken page -- and five checks depend on
        # one existing: this, the hover, the route, the click, and the free
        # square in the default mode. Measured by forcing the locator to miss:
        # one failure became five. The dependents are already guarded by
        # `if spot:` below; this is the one that used to fail instead of
        # saying so. #402.
        check.skip(
            "a reachable free square is on the board",
            f"every lit square provokes on this board "
            f"({page.locator('#movement .mv').count()} lit), so the hover, "
            f"route and click checks below have nowhere safe to aim",
        )
    else:
        check.that(True, "a reachable free square is on the board")
    _press_move(page)  # the row is a toggle; press it again to unpick it
    # Off the action list first. Hovering the Move row is a *preview* of
    # pressing it and paints the same squares, so with the pointer parked on
    # the row the range is legitimately lit whether or not it is picked --
    # which is why the state being tested is the picked class, and the range
    # is only read once nothing is being pointed at.
    page.mouse.move(4, 4)
    page.wait_for_timeout(200)
    check.that(
        page.locator("#board.aiming").count() == 0
        and page.locator("#actions button.aiming").count() == 0,
        "unpicking Move leaves nothing picked",
    )
    check.that(
        page.locator("#movement .mv").count() == 0,
        "and puts the range away again",
    )
    if spot:
        sent = len(calls)
        parked = _positions(page)
        _click_box(page, spot)
        page.wait_for_timeout(600)
        after_bare = _positions(page)
        moves = [c for c in calls[sent:] if "/aim" in c or "/act" in c]
        status = page.eval_on_selector("#status", "el => el.innerText.trim()")
        check.that(
            after_bare == parked and not moves,
            "a bare board click with nothing picked moves nobody",
            f"{parked} vs {after_bare} | calls: {moves or None} | status: {status!r}",
        )
        check.that(bool(status), "and says why instead of moving", f"status: {status!r}")
    _press_move(page)  # back to picked, for the walk the rest of this checks
    check.that(
        page.locator("#movement .mv").count() > 0,
        "pressing Move again brings the range back",
    )

    # Pointing at one of those squares draws the route the walk would take.
    # Only askable where a free square exists -- see the skip above.
    box = _hover_a_move_square(page) if spot else None
    if spot is None:
        check.skip("a movement square accepted a hover", "no free square to point at")
        check.skip("hovering a square draws its route", "nothing safe to hover")
        route = None
    else:
        check.that(box is not None, "a movement square accepted a hover")
        route = page.locator("#highlights .hl-path")
        check.that(route.count() > 0,
                   f"hovering a square draws its route ({route.count()} steps)",
                   "the server sends every route with the squares; nothing drew one")

    sent = len(calls)
    seen = len(served)
    moved = _click_a_move_square(page) if spot else None
    if spot is None:
        check.skip("a highlighted square accepted a click", "no free square to click")
    else:
        check.that(moved is not None, "a highlighted square accepted a click")
    if moved:
        # Wait for the board to change, not for a fixed 900ms. The token
        # animates and the server has to answer, and 900ms was about even
        # odds. A flaky instrument is worse than a slow one: it teaches you
        # to re-run rather than to read.
        #
        # It was flaky for a second reason for a long time, blamed on
        # `check.py` and on the click not registering, and it was neither:
        # the square being clicked was one that provokes. See
        # `_click_a_move_square`. **No retry** here -- a retry would have
        # hidden that instead of making it measurable.
        after = before
        for _ in range(40):
            after = _positions(page)
            if after != before:
                break
            page.wait_for_timeout(100)
        # Say *why* when it does not move. This failed intermittently under
        # load and the message was two position dicts, which cannot tell a
        # slow animation from a parked question from a click that missed --
        # so it got read as a regression twice before anyone measured it.
        pending = page.locator("#question, .pending, [data-pending]").count()
        # `.token.current` and `.unit.current` are the classes the page
        # actually sets. `.actor.current` was asked for and matches nothing,
        # so this line reported "0" on every run, pass or fail.
        acting = page.locator("#board .token.current").count()
        # The board refuses a click three ways and only one of them is loud:
        # `busy` and a turn that is not yours return in silence, an
        # unreachable square says so in `#status`. Reading the status line
        # tells those apart, which two position dicts never could.
        status = page.eval_on_selector("#status", "el => el.innerText.trim()")
        still = page.locator("#movement .mv").count()
        # The square under the pointer, in the page's own words, and where
        # the reply to the click says the actor is standing. A board that did
        # not move because the server said it did not is a different fault
        # from a board that was sent a move and did not draw it.
        at = page.eval_on_selector("#hover", "el => el.innerText.trim()")
        reply = served[-1] if len(served) > seen else None
        where = None
        if reply:
            where = next(
                (a["square"] for a in reply["actors"] if a["id"] == reply.get("current")), None
            )
        check.that(
            after != before,
            "the board moved somebody",
            f"{before} vs {after}"
            f" | pending questions: {pending} | current actor drawn: {acting}"
            f" | squares still lit: {still} | status line: {status!r}"
            f" | calls after the click: {calls[sent:] or None}"
            f" | clicked {at} | the reply puts the actor at {where}",
        )

    # An area power must highlight where it can be *centred*, not the
    # footprint it would cover from where the caster stands.
    _check_area_aiming(check, served[-1] if served else None)
    # And pointing at one of those centres must show what it would catch.
    # Started again on a fixed seed first, because whether the creature whose
    # turn it is happens to carry an area power is otherwise a coin toss, and
    # a check that skips itself on half its runs is not a check.
    _restart(page, BLAST_SEED, served)
    _check_footprint(page, check, served[-1] if served else None)

    # A burst that takes no aim must still show what it covers, and must fire
    # when pressed rather than waiting for a square nobody can give it.
    _restart(page, AIMLESS_SEED, served)
    _check_aimless_area(page, check, served[-1] if served else None, calls)

    # A trap the party has spotted must be on the board and hoverable.
    _restart(page, TRAP_SEED, served)
    _check_things(page, check, served[-1] if served else None)

    # Play on, so attacks happen and the log has a fight in it rather than a
    # first turn. Clicking real buttons, because that is what is being tested.
    before_lines = page.locator("#log .narration").count()
    _play_on(page, rounds=args_turns())
    read = page.locator("#log .narration")
    check.that(
        read.count() > before_lines + 3,
        f"playing on wrote more log ({before_lines} -> {read.count()} lines)",
    )
    print("        ...")
    for i in range(max(0, read.count() - 4), read.count()):
        print(f"        {read.nth(i).inner_text()[:78]}")

    _check_animation(page, check)
    _check_enemies_animate(page, check)
    _check_initiative(page, check, served)

    _check_enumerated_move(page, check)

    check.that(not problems, "still no script errors after playing",
               "; ".join(problems[:3]))


#: What `style.css` paints each band. Read back as the browser computes it,
#: because the class landing on the element is not the same claim as the
#: colour arriving: #164 was a tone name nothing matched, so the rule that
#: applied was the neutral default and the class list looked fine.
BANDS = {
    "at-will": "rgb(63, 156, 83)",
    "encounter": "rgb(156, 59, 50)",
    "daily": "rgb(125, 132, 143)",
}


def _check_usage_bars(page, check: Checks) -> None:  # noqa: ANN001
    """Is an at-will's band green on the page, and an encounter's red?

    Matched on the usage the row prints beside the name, so this is the same
    reading a player makes: the words say "at-will", the rule under them must
    be green.
    """
    rows = page.evaluate(
        "() => [...document.querySelectorAll('#actions .option')].map(b => {"
        "  const u = b.querySelector('.option-usage'), bar = b.querySelector('.usage-bar');"
        "  if (!u || !bar) return null;"
        "  return [u.innerText.trim().toLowerCase(),"
        "          getComputedStyle(bar).backgroundColor]; }).filter(Boolean)"
    )
    check.that(bool(rows), f"powers print a usage band ({len(rows)} rows)")
    for word, want in BANDS.items():
        seen = {c for u, c in rows if u.replace("-", " ").startswith(word.replace("-", " "))}
        if not seen:
            print(f"        no {word} power in this turn's kit (skipped)")
            continue
        check.that(seen == {want}, f"{word} powers show the {word} colour", f"got {sorted(seen)}")


_TURNS = 14


def args_turns() -> int:
    return _TURNS


def _play_on(page, rounds: int) -> None:  # noqa: ANN001
    """Take some turns by clicking what the action list offers.

    Barely a policy: attack if anything is in reach, otherwise close, and end
    the turn if neither. It only has to make a fight happen -- what is being
    tested is that the buttons do what they say.

    The first version preferred "anything that is not a move", which meant it
    found `second wind` and pressed it every single turn. Four rounds of a
    party healing itself and nothing else looked exactly like a stalled loop.
    """
    for _ in range(rounds):
        page.wait_for_timeout(120)
        # The action list is disabled while the board is still playing the
        # events behind the snapshot it is showing -- acting then would send
        # an option index the server has already moved past. So wait for it
        # rather than treating a settling board as an empty one.
        # Suppressed rather than asserted: a finished fight has no enabled
        # buttons and never will, and that is not this helper's business.
        with contextlib.suppress(Exception):
            page.wait_for_function(
                "() => document.querySelectorAll"
                "('#actions button:not([disabled])').length > 0",
                timeout=6000,
            )
        answers = page.locator("#actions button.pending-answer")
        if answers.count():
            answers.first.click()  # a power asked something mid-resolution
            continue
        buttons = page.locator("#actions button:not([disabled])")
        if not buttons.count():
            return
        labels = [t.lower() for t in _texts(page, "#actions button:not([disabled])")]
        pick = _first(labels, lambda t: "->" in t and "second wind" not in t)
        if pick is None:
            pick = _first(labels, lambda t: t.startswith("move to"))
        # Ending the turn by its name rather than by its place in the list.
        # It used to be the last button and is now the first, and a policy
        # that presses whatever is at the bottom was pressing a power it
        # cannot fire without a square -- so nobody's turn ever ended.
        if pick is None:
            pick = _first(labels, lambda t: t.startswith("end turn"))
        buttons.nth(pick if pick is not None else len(labels) - 1).click()


def _first(labels: list[str], want) -> int | None:  # noqa: ANN001
    return next((i for i, t in enumerate(labels) if want(t)), None)


#: The three event kinds `anim.js` will actually play. Everything else is
#: logged and not shown, which is a silence rather than an error -- so this
#: is checked by name.
ANIMATED = {"moved", "attack_rolled", "attack_hit"}


def _check_animation(page, check: Checks) -> None:  # noqa: ANN001
    """Did the events the board can play actually arrive, and in the shape it wants?

    `anim.js` reads three kinds and three kinds only, and a `moved` without
    `data.from` and `data.to` is dropped on the floor. Nothing errors when
    this is wrong; the board simply snaps instead of moving, which is exactly
    how it went unnoticed.
    """
    kinds = page.evaluate(
        "() => [...document.querySelectorAll('#log .logline')]"
        ".map(n => (n.className.match(/kind-(\\S+)/) || [])[1]).filter(Boolean)"
    )
    seen = set(kinds)
    check.that(bool(seen & ANIMATED), f"the board got something to play ({len(kinds)} events)",
               f"kinds seen: {sorted(seen)}")
    for kind in sorted(ANIMATED & seen):
        check.that(True, f"  {kind} arrived")
    missing = sorted(ANIMATED - seen)
    if missing:
        print(f"        not seen this run (may simply not have happened): {missing}")


ANIM_SEED = 4


def _set_speed(page, name: str) -> None:  # noqa: ANN001
    """Change the board speed the way a player would, without needing to see it."""
    page.eval_on_selector(
        "#speed",
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('change')); }",
        name,
    )


def _check_enemies_animate(page, check: Checks) -> None:  # noqa: ANN001
    """Do the monsters slide, or do they teleport?

    Watched rather than inferred: every frame, note which tokens are holding
    a transform. A monster round is four creatures and a couple of dozen
    steps, and the snapshot that ends it used to be forced through after a
    second and a half no matter what -- so the enemies animated for that long
    and then jumped to wherever they had got to.

    Two things had to be true before this could measure anything. The suite
    plays at `--speed instant` so it finishes quickly, and at zero
    milliseconds `anim.enqueue` returns without queueing -- so the animator
    was switched off for every run of it. And the fight has to be started
    again, because by the time this runs the earlier checks have played it
    out, and a finished encounter has no turns left to animate.
    """
    # Through the page's own control, not localStorage: `anim.js` reads the
    # stored speed once when the module loads, so writing the key afterwards
    # changes nothing until a reload.
    # Driven by dispatching the control's own change event: the picker lives
    # in a panel that may be folded away, so `select_option` waits forever for
    # something that is never going to be visible.
    was = page.eval_on_selector("#speed", "el => el.value")
    _set_speed(page, "normal")
    # A fresh page rather than the restart button: `_restart` leaves the
    # board mid-settle often enough that the action list is empty when this
    # starts clicking, and an empty list measures nothing.
    # `load` and then the board, rather than `networkidle`. Idle means "no
    # request for 500ms", which a page holding an event stream open reaches
    # only by luck -- and waiting for the token is the thing actually being
    # waited for.
    page.reload(wait_until="load")
    _settled(page, "#board .token", TOKENS_DRAWN)
    _set_speed(page, "normal")
    page.wait_for_timeout(600)
    page.evaluate(
        "() => { window.__slid = new Set();"
        " const tick = () => { for (const t of document.querySelectorAll('#board .token'))"
        "   if (t.style.transform && t.style.transform !== 'none')"
        "     window.__slid.add(t.dataset.actor);"
        " requestAnimationFrame(tick); }; tick(); }"
    )
    # Ending turns directly rather than through `_play_on`, which prefers an
    # attack when one is offered and so advances the round slowly. What is
    # being watched is the monsters' turn, and the way to reach it is to
    # stop taking your own. The pause after each is the point: every render
    # clears the transforms, so a watcher that looks only between clicks
    # sees a board at rest and concludes nothing moved.
    for _ in range(8):
        # **Found by text, never by index.** This read the labels, found the
        # position of "end turn" in that list, and then clicked `.nth(i)` of a
        # *freshly evaluated* locator -- so a redraw between the two reads made
        # `i` point at a different button, and the click landed on an attack
        # instead. The round then did not advance, the monsters never acted, and
        # the check below read `0 of them slid`. **Reproduced 2 runs in 6**, and
        # it was the only failing check in both.
        #
        # #355 fixed a sibling of this by swapping a stale ElementHandle for a
        # locator, and recorded that a locator is re-evaluated on use. True, and
        # not enough: re-evaluating the *selector* does not re-evaluate the
        # *index*. Playwright filters by text, so the index goes away. #402.
        end = page.locator(
            "#actions button:not([disabled])"
        ).filter(has_text=re.compile("end turn", re.I))
        with contextlib.suppress(Exception):
            end.first.click(timeout=5000)
        # Every render clears the transforms, so a watcher looking only between
        # clicks sees a board at rest and concludes nothing moved.
        page.wait_for_timeout(2200)
    slid = set(page.evaluate("Array.from(window.__slid)"))
    enemies = {a for a in slid if a.startswith("npc")}
    check.that(bool(enemies), f"enemy tokens animate ({len(enemies)} of them slid)",
               f"tokens that moved at all: {sorted(slid)}")
    _set_speed(page, was or "instant")


def _positions(page) -> dict:  # noqa: ANN001
    return page.evaluate(
        "() => Object.fromEntries([...document.querySelectorAll('#board .token')]"
        ".map(t => [t.dataset.actor, t.style.left + ',' + t.style.top]))"
    )


def _press_move(page) -> bool:  # noqa: ANN001
    """Press the Move row in the action list, the way a player would.

    **A locator, not an `ElementHandle`.** `query_selector_all` hands back
    snapshots of the elements as they were; the action list re-renders on
    every state change, which detaches them, and the click then dies with
    "Element is not attached to the DOM". A locator re-resolves the selector
    at click time, so a re-render between finding the row and pressing it is
    survivable rather than fatal.

    This failed about half of all runs, and it only started being *visible*
    when the per-element label loops nearby were replaced by one `evaluate`:
    those sixty round trips had been acting as an accidental sleep, holding
    the instrument back until the page had settled. Removing the delay did
    not cause the bug -- it stopped hiding it. #355.
    """
    labels = [t.lower() for t in _texts(page, "#actions button")]
    for i, label in enumerate(labels):
        if label.startswith("move") and "move to" not in label:
            page.locator("#actions button").nth(i).click(force=True)
            page.wait_for_timeout(200)
            return True
    return False


def _move_square_box(page, nth: int):  # noqa: ANN001, ANN202
    """The screen rect of one highlighted movement square.

    **`.mv-free`, not `.mv`.** The overlay draws the provoking squares first
    and there are usually ten times as many of them, so "the fourth square"
    was reliably one that provokes -- and a walk that provokes can be stopped
    by the attack it draws, sometimes on the very first step. The server
    answers 200 and the creature has not moved, which is correct play and
    looks exactly like a click that missed. That is the whole of this
    instrument's intermittent failure. A free square provokes nothing and so
    cannot be interrupted.
    """
    squares = page.locator("#movement .mv-free")
    if not squares.count():
        return None
    return squares.nth(min(nth, squares.count() - 1)).bounding_box()


def _hover_a_move_square(page):  # noqa: ANN001, ANN202
    """Point at a highlighted square. The route is drawn on `mousemove`."""
    box = _move_square_box(page, 5)
    if not box:
        return None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)
    return box


def _click_a_move_square(page):  # noqa: ANN001, ANN202
    """Click a highlighted movement square, as a player would.

    The click has to go to the board, which is what carries the handler. The
    highlight overlay sits on top of it and is only there to be looked at.
    """
    box = _move_square_box(page, 3)
    if not box:
        return None
    _click_box(page, box)
    return box


def _click_box(page, box: dict) -> None:  # noqa: ANN001
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _check_area_aiming(check: Checks, state: dict | None) -> None:
    """An area power must offer the squares it can be *centred* on.

    Taken from the last state the page was actually served, because the page
    highlights exactly what it is given -- if these are wrong the highlight is
    wrong in the same way, and the DOM would only agree with itself.

    A burst that offered the squares it *covers* rather than the squares it
    may be centred on is why one could not be aimed: the page lit up the area
    the burst would fill if cast on the caster's own head, and clicking
    anywhere else did nothing at all.
    """
    if not state or not state.get("roster"):
        check.that(True, "nobody with a kit is acting just now (skipped)")
        return
    areas = [
        p
        for p in state["roster"]
        if "burst" in p["range_text"].lower() or "blast" in p["range_text"].lower()
    ]
    if not areas:
        check.that(True, "the acting creature has no area power (skipped)")
        return
    here = next(a["square"] for a in state["actors"] if a["id"] == state["current"])
    for p in areas:
        if not p["squares"]:
            check.that(False, f"{p['name']} offers nowhere to aim")
            continue
        far = max(distance(tuple(sq), tuple(here)) for sq in p["squares"])
        check.that(
            len(p["squares"]) > 1,
            f"{p['name']} offers {len(p['squares'])} squares to aim at, furthest {far} away",
        )
        if "within" in p["range_text"]:
            limit = int(p["range_text"].rsplit(" ", 1)[-1])
            check.that(far <= limit, f"{p['name']} aims no further than {limit}", f"got {far}")


def _check_aimless_area(page, check: Checks, state: dict | None,  # noqa: ANN001
                        calls: list[str]) -> None:
    """A non-attack burst covers an area and has nothing to aim at.

    263 of the 1441 burst and blast rows roll no attack, so `_clickable`
    hands back no squares -- correctly, there is nothing to click -- and the
    board therefore drew **nothing at all** for them. Worse in freeform: the
    row was greyed for having no squares, and the plain-button fallback skips
    anything a roster row has claimed, so it could not be used at all.

    Three things, and the third is the one that was broken: it lights, it
    does not ask for an aim, and pressing it **acts**.
    """
    if not state or not state.get("roster"):
        check.that(True, "nobody with a kit is acting just now (skipped)")
        return
    row = next(
        (p for p in state["roster"]
         if p.get("available") and not p.get("squares") and p.get("shows")),
        None,
    )
    if row is None:
        check.that(True, "the acting creature has no aimless area power (skipped)")
        return
    check.that(
        len(row["shows"]) > 1,
        f"{row['name']} covers {len(row['shows'])} squares with nothing to aim at",
    )
    buttons = page.locator("#actions .option")
    mine = None
    for i in range(buttons.count()):
        if row["name"] and row["name"] in buttons.nth(i).inner_text():
            mine = buttons.nth(i)
            break
    if mine is None:
        check.that(False, f"{row['name']} has a row in freeform",
                   "greyed or missing -- the 263 rows this check exists for")
        return
    check.that(True, f"{row['name']} is offered rather than greyed")
    mine.hover()
    page.wait_for_timeout(300)
    check.that(
        page.locator("#highlights .hl-affected").count() > 0,
        f"hovering it lights the {len(row['shows'])} squares it covers",
        "the board drew nothing, which is the bug",
    )
    # Asked before clicking, because a greyed row makes Playwright retry for
    # thirty seconds and then raise -- so the regression this check exists to
    # catch reported itself as a timeout in the harness rather than as a
    # failure in the page. Which is true, and useless to read.
    if not mine.is_enabled():
        check.that(False, "pressing it acts",
                   "the row is disabled, so it cannot be pressed at all")
        return
    sent = len(calls)
    mine.click()
    page.wait_for_timeout(900)
    after = calls[sent:]
    check.that(
        any("/act" in c for c in after),
        "pressing it acts",
        f"calls: {after or None}",
    )
    check.that(
        not any("/aim" in c for c in after),
        "and never asks for an aim square",
        f"calls: {after or None}",
    )


def _check_things(page, check: Checks, state: dict | None) -> None:  # noqa: ANN001
    """A trap, a piece of scenery or a conjuration must reach the board.

    None of the three has `Health`, so none arrives through `ActorDTO` and
    the page could draw none of them. A player walked onto an invisible
    hazard; worse, scenery and conjurations own their squares through
    `grid.place`, so they were already blocking movement with nothing drawn
    to explain it.

    A trap is only shipped once it is sprung or somebody has noticed it, so
    finding one here is also a check on the Perception gate: the board this
    seed draws has one the party can see.
    """
    things = ((state or {}).get("board") or {}).get("things") or []
    if not things:
        check.that(False, "the board's non-creatures reached the page",
                   "no trap, scenery or conjuration was served at all")
        return
    check.that(True, f"{len(things)} non-creature(s) served: "
                     f"{sorted({t['kind'] for t in things})}")
    drawn = page.locator("#board .thing")
    check.that(
        drawn.count() >= sum(len(t["squares"]) for t in things),
        f"and the board drew {drawn.count()} of their squares",
        "served but not drawn -- renderBoard is not reading board.things",
    )
    trap = next((t for t in things if t["kind"] == "trap"), None)
    if trap is None:
        check.that(True, "no trap on this board (skipped)")
        return
    # An unsprung trap being visible at all means a character noticed it,
    # which is the whole of the information decision in #224.
    check.that(
        not trap["sprung"],
        "the trap is one the party spotted rather than one that has fired",
        "this seed's trap has already gone off -- the gate is untested here",
    )
    spot = page.locator("#board .thing-trap").first
    spot.hover()
    page.wait_for_timeout(300)
    card = page.locator("#card")
    check.that(
        "trap" in card.inner_text().lower(),
        "hovering it says what it is",
        f"card read: {card.inner_text()[:60]!r}",
    )


def _check_enumerated_move(page, check: Checks) -> None:  # noqa: ANN001
    """The mode with the checkbox off must play the same two-step gesture.

    Everything above runs with "freeform targeting" on, which is *not* what a
    fresh visitor gets. The default list used to print one button per reachable
    square -- around ninety "move to (x, y)" rows and a hundred and twenty "run
    to" ones -- and its board was not clickable at all. So the same complaint as
    #139 arrived from the other end: the destination was over-specified and the
    kind of movement was the thing nobody could see. Both modes now offer Move,
    Run and Shift and take the square off the board.
    """
    page.evaluate("localStorage.setItem('dnd4e.freeform', 'off')")
    page.reload(wait_until="networkidle")
    _settled(page, "#board .token", TOKENS_DRAWN)
    # A known seed, because whether the first turn belongs to a character with a
    # move left is otherwise a coin toss.
    _restart(page, BLAST_SEED)

    labels = [t.lower() for t in _texts(page, "#actions button")]
    per_square = [text for text in labels if "move to" in text or "run to" in text]
    check.that(
        not per_square,
        f"the default list has no per-square movement rows ({len(labels)} rows in all)",
        f"still there: {per_square[:3]}",
    )
    check.that(
        any(text.startswith("run") for text in labels),
        "and offers Run, which only the enumerated squares used to carry",
        f"rows: {labels[:12]}",
    )
    check.that(
        page.locator("#movement .mv").count() == 0,
        "the default board draws no range until Move is pressed",
    )

    before = _positions(page)
    check.that(_press_move(page), "the default list offers Move")
    check.that(
        page.locator("#movement .mv").count() > 0,
        "pressing it lights where you can go",
    )
    # **A board where every reachable square provokes is a real board**, and
    # this check used to call it a failure. `.mv-free` is the squares that
    # provoke nothing; a character boxed in by enemies has none, and the seed
    # being pinned does not prevent it -- measured, 1 run in 8. The check's
    # *definition* was wrong rather than the page, so it says skip. #402.
    box = _move_square_box(page, 3)
    if box is None:
        lit = page.locator("#movement .mv").count()
        check.skip(
            "a free square is lit in the default mode",
            f"every one of the {lit} lit squares provokes on this board, so "
            f"there is no free square to click -- which is legal play",
        )
    else:
        check.that(True, "a free square is lit in the default mode")
    if not box:
        return
    _click_box(page, box)
    after = before
    for _ in range(40):
        after = _positions(page)
        if after != before:
            break
        page.wait_for_timeout(100)
    status = page.eval_on_selector("#status", "el => el.innerText.trim()")
    check.that(
        after != before,
        "and clicking a lit square walks there with the checkbox off",
        f"{before} vs {after} | status: {status!r}",
    )


#: A fight whose first turn belongs to somebody holding an area power. The
#: form's own fields, so this is the fight a player typing this seed gets.
BLAST_SEED = 2

#: A fight whose first actor carries a burst that takes no aim -- a close
#: burst 5 covering 88 squares with nothing to point at. Pinned for the same
#: reason every other seed here is: whether such a row is in the kit is
#: otherwise a coin toss, and a check that skips itself is not a check.
AIMLESS_SEED = 1

#: A fight whose board carries a trap the party's passive Perception is good
#: enough to spot, and which has not gone off. Pinned because whether a trap
#: is laid at all is a coin toss and whether it is *noticed* depends on the
#: party's Wisdom -- two draws deep, so an unpinned run would check this on
#: maybe one board in six.
TRAP_SEED = 22

#: The fight the whole run opens on. Picked because every check has its
#: precondition met under it -- somebody with a kit is acting, there is a
#: free square to walk to, and the turn carries a power of each usage band.
START_SEED = 2


def _restart(page, seed: int, served: list[dict] | None = None) -> None:  # noqa: ANN001
    """Start a fresh fight from the page's own form, on a known seed.

    **Waits for the new snapshot to arrive, not merely for a token to exist.**
    Every caller then reads `served[-1]`, and the old wait -- first token plus
    600ms -- did not guarantee the restart's own response had been recorded.
    So `served[-1]` was sometimes the *previous* seed's board, and a check
    written against this seed silently ran against the last one: that is how
    "no trap, scenery or conjuration was served at all" appeared on a seed
    whose board the server returns a trap for 8 times out of 8. The server was
    deterministic the whole time; the instrument was reading the wrong board.
    #355.
    """
    mark = len(served) if served is not None else 0
    page.fill("#seed", str(seed))
    page.click("#restart")
    _settled(page, "#board .token", TOKENS_DRAWN)
    if served is not None:
        deadline = time.monotonic() + 15
        while len(served) <= mark and time.monotonic() < deadline:
            page.wait_for_timeout(100)
    page.wait_for_timeout(600)


def _check_footprint(page, check: Checks, state: dict | None) -> None:  # noqa: ANN001
    """Pointing at an aim square must show the squares that aim point hits.

    The two are not the same list and for a blast they barely overlap: the
    ring you may point at is not the nine squares that burn. So a player
    placing a blast 3 could not see what it would cover until after using it.
    `footprints` is the server's answer, keyed by aim square, and this walks
    the whole way round -- pick the power, point at one of its squares, count
    what lit up -- because the wire being right is the half that was never
    the problem.
    """
    if not state or not state.get("roster"):
        check.that(True, "nobody with a kit is acting just now (skipped)")
        return
    power = next((p for p in state["roster"] if p.get("footprints")), None)
    if power is None:
        check.that(True, "the acting creature has no blast or burst (skipped)")
        return

    name = power["name"].lower()
    buttons = page.locator("#actions button")
    pick = _first(
        [t.lower() for t in _texts(page, "#actions button")],
        lambda t: t.startswith(name),
    )
    if pick is None:
        check.that(False, f"{power['name']} is offered in the action list")
        return
    buttons.nth(pick).click()  # aim it; the square comes next

    # The aim point that catches the most, because a footprint of one square
    # would pass this test by accident.
    at = max(power["footprints"], key=lambda k: len(power["footprints"][k]))
    covered = power["footprints"][at]
    x, y = (int(n) for n in at.split(","))
    tile = page.locator("#board .tile").nth(y * state["board"]["width"] + x)
    box = tile.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    lit = page.evaluate(
        "() => [...document.querySelectorAll('#highlights .hl-hit')]"
        ".map(n => n.style.left + ',' + n.style.top)"
    )
    want = page.evaluate(
        "(spec) => spec.squares.map(([x, y]) => {"
        "  const t = document.querySelectorAll('#board .tile')[y * spec.width + x];"
        "  return t.style.left + ',' + t.style.top; })",
        {"squares": covered, "width": state["board"]["width"]},
    )
    check.that(
        sorted(lit) == sorted(want),
        f"{power['name']} aimed at {x},{y} lights the {len(covered)} squares it hits",
        f"{len(lit)} squares lit, {len(want)} expected",
    )
    # The point of the colour: what it hits is not what you may click.
    aims = {f"{sq[0]},{sq[1]}" for sq in power["squares"]}
    check.that(
        {f"{sq[0]},{sq[1]}" for sq in covered} != aims,
        "the squares it hits are a different set from the squares it aims at",
    )
    buttons.nth(pick).click()  # put the power back down


def _check_initiative(page, check: Checks, served: list[dict]) -> None:  # noqa: ANN001
    """The strip along the top must be the initiative order.

    Two halves, because the bug could be in either. `actors` used to arrive in
    the order the world spawned creatures -- the whole party, then all the
    monsters -- which reads exactly like an order and is not one; the page
    draws the array as it comes. So: the strip is what the server sent, and
    what the server sent is the order the turns happen in. Within one round
    each creature that acts must sit further down the strip than the last one;
    a round is what the wrap back to the top is called.
    """
    if not served:
        check.that(False, "the page was served a state to draw")
        return
    # This encounter's states only. The page starts a fight on load and another
    # on the reload that turns freeform on, and two fights have two initiative
    # orders -- reading both as one is a creature acting out of turn.
    served = [s for s in served if s.get("id") == served[-1].get("id")]
    order = [a["id"] for a in served[-1]["actors"]]
    strip = page.evaluate(
        "() => [...document.querySelectorAll('#order .unit')].map(n => n.dataset.actor)"
    )
    check.that(strip == order, "the strip is drawn in the order the server sent",
               f"{strip}\n          vs {order}")

    spot = {a: i for i, a in enumerate(order)}
    turns: list[tuple[int, str]] = []
    for s in served:
        who = s.get("current")
        if who and s.get("round") and (not turns or turns[-1][1] != who):
            turns.append((s["round"], who))
    backwards = [
        (a, b)
        for (ra, a), (rb, b) in itertools.pairwise(turns)
        if ra == rb and spot.get(b, -1) <= spot.get(a, -1)
    ]
    check.that(
        len(turns) > 1 and not backwards,
        f"turns run down the strip ({len(turns)} turns seen)",
        f"went backwards inside a round: {backwards}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
