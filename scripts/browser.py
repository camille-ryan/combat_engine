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
import os
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
        )
        import urllib.request

        for _ in range(80):
            with contextlib.suppress(Exception):
                urllib.request.urlopen(f"{self.base}/api/health", timeout=3)
                return self
            time.sleep(0.25)
        raise SystemExit("the server did not come up")

    def __exit__(self, *_: object) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.passed = 0

    def that(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  ok    {what}")
        else:
            self.failed.append(what)
            print(f"  FAIL  {what}" + (f"\n          {detail}" if detail else ""))


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

        page.goto(server.base, wait_until="networkidle")
        page.evaluate(f"localStorage.setItem('dnd4e.speed', '{args.speed}')")
        # Clicking the board is gated behind "freeform targeting", which is
        # off by default -- so a click lands on nothing and says nothing.
        # Turned on here because clicking the board is what is being tested.
        page.evaluate("localStorage.setItem('dnd4e.freeform', 'on')")
        page.reload(wait_until="networkidle")

        check.that(not problems, "the page loads with no script errors", "; ".join(problems[:3]))
        _play(page, check, problems, served)

        if args.shot:
            page.screenshot(path=args.shot, full_page=True)
            print(f"\n  screenshot: {args.shot}")
        browser.close()

    print(f"\n{check.passed} checks passed, {len(check.failed)} failed")
    return 1 if check.failed else 0


def _play(page, check: Checks, problems: list[str], served: list[dict]) -> None:  # noqa: ANN001
    page.wait_for_selector("#board .token", timeout=15000)
    tokens = page.locator("#board .token")
    check.that(tokens.count() >= 8, f"the board drew {tokens.count()} tokens")

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

    # The action list, and a move by clicking the board.
    before = _positions(page)
    highlights = page.locator("#movement .mv")
    check.that(highlights.count() > 0, f"movement is highlighted ({highlights.count()} squares)")

    moved = _click_a_move_square(page)
    check.that(moved is not None, "a highlighted square accepted a click")
    if moved:
        page.wait_for_timeout(900)
        after = _positions(page)
        check.that(after != before, "the board moved somebody",
                   f"{before} vs {after}")

    # An area power must highlight where it can be *centred*, not the
    # footprint it would cover from where the caster stands.
    _check_area_aiming(check, served[-1] if served else None)

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

    check.that(not problems, "still no script errors after playing",
               "; ".join(problems[:3]))


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
        answers = page.locator("#actions button.pending-answer")
        if answers.count():
            answers.first.click()  # a power asked something mid-resolution
            continue
        buttons = page.locator("#actions button:not([disabled])")
        if not buttons.count():
            return
        labels = [buttons.nth(i).inner_text().lower() for i in range(buttons.count())]
        pick = _first(labels, lambda t: "->" in t and "second wind" not in t)
        if pick is None:
            pick = _first(labels, lambda t: t.startswith("move to"))
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


def _positions(page) -> dict:  # noqa: ANN001
    return page.evaluate(
        "() => Object.fromEntries([...document.querySelectorAll('#board .token')]"
        ".map(t => [t.dataset.actor, t.style.left + ',' + t.style.top]))"
    )


def _click_a_move_square(page):  # noqa: ANN001, ANN202
    """Click a highlighted movement square, as a player would.

    The click has to go to the board, which is what carries the handler. The
    highlight overlay sits on top of it and is only there to be looked at.
    """
    squares = page.locator("#movement .mv")
    if not squares.count():
        return None
    box = squares.nth(min(3, squares.count() - 1)).bounding_box()
    if not box:
        return None
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    return box


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


if __name__ == "__main__":
    raise SystemExit(main())
