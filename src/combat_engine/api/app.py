"""The web surface.

    uv run uvicorn combat_engine.api.app:app --port 8765

Then open http://127.0.0.1:8765 and play.

`CE_NAMES=off` serves the same game with every printed name replaced by its
id, which is how a hosted deployment runs -- the engine never held a name in
the first place, so nothing has to be stripped, only not looked up.

REST for state and actions, server-sent events for the log. Both are what the
page already speaks: it came over from the first attempt unchanged, and the
consumer defines the contract.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import dto, render
from .session import SESSIONS, Session
from .wire import names_enabled

WEB = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="combat-engine")


class NewEncounter(BaseModel):
    """Every field is blank-means-default, and the defaults live here.

    A client that filled them in would be a second copy of the defaults, and
    it would write the composition of the default party into a static asset.
    """

    level: int = 1
    seed: int | None = None
    pcs: list[str] | None = None
    enemies: list[str] | None = None
    scaling: str = "full"
    scale: float | None = None  # accepted and ignored; the page sends it


class ActRequest(BaseModel):
    actor_id: str | None = None
    action_index: int


class DecideRequest(BaseModel):
    actor_id: str | None = None
    answer_index: int


class AimRequest(BaseModel):
    """A click on the board.

    With no `power_index` it is a move: walk to the square, or shift to it
    when `mode` says so. With one, it is that entry of the roster aimed at
    the square -- at whatever is standing there, or at that square as the
    origin of a burst or a blast.
    """

    actor_id: str | None = None
    square: tuple[int, int]
    power_index: int | None = None
    mode: str | None = None


def _session(encounter_id: str) -> Session:
    found = SESSIONS.get(encounter_id)
    if found is None:
        raise HTTPException(404, f"no encounter {encounter_id}")
    return found


@app.get("/api/health")
async def health() -> dict[str, bool | str]:
    return {"ok": True, "names": names_enabled()}


@app.post("/api/encounter")
async def create_encounter(body: NewEncounter | None = None) -> dto.EncounterStateDTO:
    body = body or NewEncounter()
    seed = body.seed if body.seed is not None else _draw()
    try:
        session = Session.create(
            seed=seed,
            level=body.level,
            scaling=body.scaling,
            pcs=body.pcs,
            enemies=body.enemies,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    SESSIONS[session.id] = session
    return render.state(session)


@app.get("/api/encounter/{encounter_id}")
async def read_encounter(encounter_id: str) -> dto.EncounterStateDTO:
    return render.state(_session(encounter_id))


@app.post("/api/encounter/{encounter_id}/act")
async def act(encounter_id: str, body: ActRequest) -> dto.EncounterStateDTO:
    session = _session(encounter_id)
    if not session.awaiting:
        raise HTTPException(409, "not waiting for a decision")
    try:
        session.act(body.action_index)
    except IndexError as exc:
        raise HTTPException(400, str(exc)) from exc
    return render.state(session)


@app.post("/api/encounter/{encounter_id}/decide")
async def decide(encounter_id: str, body: DecideRequest) -> dto.EncounterStateDTO:
    """Answer a question a power asked while it was resolving."""
    session = _session(encounter_id)
    if session.gate.question is None:
        raise HTTPException(409, "nothing to decide")
    session.answer(body.answer_index)
    return render.state(session)


@app.post("/api/encounter/{encounter_id}/aim")
async def aim(encounter_id: str, body: AimRequest) -> dto.EncounterStateDTO:
    """Point at a square and do the thing that means.

    This **acts**. It is how the board is played -- clicking a square is the
    ordinary way to move and to attack, and the enumerated action list beside
    it is the same set of choices written out. So it resolves the click to
    one of those options and takes it, rather than being a preview: the two
    modes differ in what a player is shown, never in what the engine accepts.
    """
    session = _session(encounter_id)
    if not session.awaiting:
        raise HTTPException(409, "not waiting for a decision")
    square = tuple(body.square)
    try:
        if body.power_index is None:
            session.walk_to(square, shift=body.mode == "shift")
        else:
            session.aim(body.power_index, square)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    return render.state(session)


@app.post("/api/encounter/{encounter_id}/end")
async def end_turn(encounter_id: str) -> dto.EncounterStateDTO:
    session = _session(encounter_id)
    session.end_turn()
    return render.state(session)


@app.get("/api/encounter/{encounter_id}/events")
async def events(encounter_id: str, request: Request, from_: int = 0) -> StreamingResponse:
    session = _session(encounter_id)
    cursor = int(request.query_params.get("from", from_))
    return StreamingResponse(_stream(session, cursor, request), media_type="text/event-stream")


async def _stream(session: Session, cursor: int, request: Request) -> AsyncIterator[str]:
    """Replay from `cursor`, then follow.

    Replaying from the start is what a reconnect does, so every event has to
    arrive exactly once whether the client has been listening or not.

    The frame is named `encounter_event` because that is the name the page
    listens for. Calling it anything else does not error anywhere -- the
    events simply arrive and are dropped on the floor, and the log stays
    empty with nothing to say why.

    `id:` carries the seq so a browser's own `Last-Event-ID` reconnect
    resumes where it left off rather than replaying the fight.
    """
    span: list = []

    def sentence() -> str | None:
        """Close the open span and turn it into one readable line."""
        if not span:
            return None
        text = render.narrate_span(session, span)
        last = span[-1]
        span.clear()
        if not text:
            return None
        payload = {
            "round": getattr(last, "round", session.world.round),
            "seq": last.seq + 1,
            "text": text,
        }
        return f"event: narration\ndata: {json.dumps(payload)}\n\n"

    while True:
        if await request.is_disconnected():
            return
        log = session.world.bus.log
        if cursor >= len(log):
            # Caught up. Close whatever sentence is open, so the last thing
            # that happened is on screen rather than waiting for the next.
            frame = sentence()
            if frame:
                yield frame
            yield ": keep-alive\n\n"
            # Short: this is how long the board lags a click, and a quarter
            # of a second of it is plainly visible.
            await asyncio.sleep(0.02)
            continue
        while cursor < len(log):
            event = log[cursor]
            cursor += 1
            if span and render.starts_span(event):
                frame = sentence()
                if frame:
                    yield frame
            span.append(event)
            payload = render.event_dto(session, event).model_dump()
            yield (
                f"id: {payload['seq']}\n"
                f"event: encounter_event\n"
                f"data: {json.dumps(payload)}\n\n"
            )


@app.get("/api/day")
@app.post("/api/day")
async def day() -> dict[str, str]:
    """The adventuring day is not built yet.

    The page has a day mode -- several fights with a rest between -- and it
    is past what a combat engine is for, so it comes later. Answering plainly
    is better than a 404 the page would read as a bug.
    """
    raise HTTPException(501, "the adventuring day is not implemented yet")


def _draw() -> int:
    """A seed, when the client did not pick one. Kept, so a fight repeats."""
    import secrets

    return secrets.randbelow(1 << 31)


if WEB.exists():
    # Mounted at the root, with `html=True` so `/` serves index.html. The
    # page asks for `./app.js` and `./style.css` relative to itself, so a
    # prefix here would break both. Registered last: the API routes above
    # are matched first.
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
