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
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Killed rather than asked twice. A uvicorn holding an event
                # stream open can outlast a polite terminate, and the wait
                # raising turned a clean run into a failure *after* every
                # check had passed -- the instrument reporting on its own
                # teardown rather than on the page.
                self.proc.kill()
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

    # Pointing at one of those squares draws the route the walk would take.
    box = _hover_a_move_square(page)
    check.that(box is not None, "a movement square accepted a hover")
    route = page.locator("#highlights .hl-path")
    check.that(route.count() > 0, f"hovering a square draws its route ({route.count()} steps)",
               "the server sends every route with the squares; nothing drew one")

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
    # And pointing at one of those centres must show what it would catch.
    # Started again on a fixed seed first, because whether the creature whose
    # turn it is happens to carry an area power is otherwise a coin toss, and
    # a check that skips itself on half its runs is not a check.
    _restart(page, BLAST_SEED)
    _check_footprint(page, check, served[-1] if served else None)

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
        labels = [buttons.nth(i).inner_text().lower() for i in range(buttons.count())]
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
    page.wait_for_selector("#board .token", timeout=15000)
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
        for btn in page.query_selector_all("#actions button:not([disabled])"):
            if "end turn" in (btn.inner_text() or "").lower():
                btn.click()
                break
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
    """Press the Move row in the action list, the way a player would."""
    for b in page.query_selector_all("#actions button"):
        label = (b.inner_text() or "").strip().lower()
        if label.startswith("move") and "move to" not in label:
            b.click(force=True)
            page.wait_for_timeout(200)
            return True
    return False


def _hover_a_move_square(page):  # noqa: ANN001, ANN202
    """Point at a highlighted square. The route is drawn on `mousemove`."""
    squares = page.locator("#movement .mv")
    if not squares.count():
        return None
    box = squares.nth(min(5, squares.count() - 1)).bounding_box()
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


#: A fight whose first turn belongs to somebody holding an area power. The
#: form's own fields, so this is the fight a player typing this seed gets.
BLAST_SEED = 2


def _restart(page, seed: int) -> None:  # noqa: ANN001
    """Start a fresh fight from the page's own form, on a known seed."""
    page.fill("#seed", str(seed))
    page.click("#restart")
    page.wait_for_selector("#board .token", timeout=15000)
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
        [buttons.nth(i).inner_text().lower() for i in range(buttons.count())],
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
