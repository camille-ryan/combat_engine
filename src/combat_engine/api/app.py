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
    actor_id: str | None = None
    power: str | None = None
    square: tuple[int, int] | None = None


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
    """Where a blast or burst would land if pointed at a square.

    Read-only: it changes nothing, it only lets the page shade the squares
    before a player commits. A blast is keyed by the square it is aimed at,
    so for a blast 3 those are the ring two out.
    """
    session = _session(encounter_id)
    out = render.state(session)
    if body.power and body.square:
        from combat_engine.engine import get
        from combat_engine.engine.dsl import area_of

        p = get(body.power)
        actor = session.current
        if p is not None and actor is not None:
            covered = sorted(area_of(session.world, actor, p, tuple(body.square)))
            for option in out.options:
                if option.kind == "power" and option.origin == tuple(body.square):
                    option.affected = covered
    return out


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
    """
    while True:
        if await request.is_disconnected():
            return
        log = session.world.bus.log
        while cursor < len(log):
            event = log[cursor]
            cursor += 1
            payload = render.event_dto(session, event).model_dump()
            yield f"event: log\ndata: {json.dumps(payload)}\n\n"
        yield ": keep-alive\n\n"
        await asyncio.sleep(0.25)


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
