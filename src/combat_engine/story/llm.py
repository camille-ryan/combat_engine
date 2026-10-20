"""Which model does which job, and how to ask it.

`story/dm.py` builds an Anthropic client directly. The story layer needs four
different jobs doing and they do not all want the same model -- so this is the
seam, and it is deliberately small. #802.

## What the local model can and cannot do, measured

`qwen2.5:7b-instruct` on ollama, 32k context, Q4_K_M, about **18 tok/s**.
About 30 seconds cold, then warm. Three findings shape everything above this
file:

* **Structured output is reliable.** Every probe honoured its JSON schema,
  enums included. The wrong answers were *well-formed* wrong answers, which is
  the useful kind -- a caller never has to parse prose or handle a refusal
  shape.
* **Open judgement is not.** Asked to decide which of three declared intents
  needed a skill check it got one right, and the one it got wrong broke an
  instruction that was in the system prompt verbatim. See #801; the answer is
  to hand it a closed list and ask it to match, which it did 3 of 3 across
  three runs at temperature 0.
* **Concurrency is not free, and a first measurement said it was.** Three
  short requests timed 11.7s in series against 2.8s in parallel, which looked
  like 4x. It was a **cold-start artefact**: the serial run paid the model
  load and the parallel one ran warm. Measured properly, warmed first, one
  request takes 4.5s and two concurrent take 8.7s and four take 17.0s --
  **linear**. The server generates one at a time.

  So the beat loop is paced by how many characters the model plays, and the
  mitigations are to keep companion replies short and to **batch the
  matching into one call** rather than one per intent. `fan_out` stays
  because it is correct and costs nothing, and because the two things that
  make it pay -- `OLLAMA_NUM_PARALLEL` on the server, or a role pointed at a
  bigger host -- are both outside this file.

## Roles, and why `base_url` is per role rather than global

A role is a job, not a model: `dm`, `companion`, `match`. Each carries its own
model *and its own endpoint*, because the jobs have genuinely different needs
-- `match` wants temperature 0 and is the one a small model is good at, `dm`
wants the best model available and is where the judgement errors live.

Camille's requirement, and the reason the URL is in the role rather than in a
module constant: **a bigger model on another machine, reachable over
Tailscale, takes the `dm` role by editing one file.** No code change, nothing
else moves, and the local model keeps the cheap roles.

Overridden per campaign from `saves/<id>.roles.json`, which is git-ignored --
an endpoint is somebody's network and does not belong in the tree.

## No new dependency, and no dependency for `check.py`

ollama is spoken to over plain `urllib`, the way `scripts/guides.py` already
talks to the web. The Anthropic path reuses the optional SDK that `dm.py`
already declares.

**Nothing here may become something the suite needs.** `check.py` runs the
story layer with a scripted answerer and no model at all; `reachable()` is
what lets a second, model-using instrument report an honest *skip* rather than
failing when nobody is serving.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from combat_engine.db import ROOT

#: Where a campaign's role overrides live, beside its save. Git-ignored.
SAVES = ROOT / "saves"

#: Long enough for a cold load of a 7B on a laptop, which is about 30 seconds,
#: plus the generation. Short enough that an unreachable host fails rather
#: than hanging a game.
TIMEOUT = 180


class NoModel(RuntimeError):
    """Nothing is serving, or the request was refused. The caller falls back."""


@dataclass(frozen=True)
class Role:
    """One job, and what answers it."""

    model: str = "qwen2.5:7b-instruct"
    #: An ollama host, or `"anthropic"` for the API path. A Tailscale address
    #: goes here verbatim -- `http://desktop.tailnet.ts.net:11434`.
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.7
    #: ollama's own default is small and the prompts here are not. A scene
    #: brief, a cast of personas and a beat's history do not fit in 2k.
    num_ctx: int = 8192
    #: Set for a repeatable answer. Not a reproducibility guarantee -- a model
    #: version change moves it, and narration is outside what `replay.py`
    #: pins either way.
    seed: int | None = None
    #: Cap on one reply. A beat wants three sentences, not an essay.
    max_tokens: int = 700

    @property
    def local(self) -> bool:
        return self.base_url.startswith("http")


#: The jobs. `match` is temperature 0 because the measurement that justifies
#: the whole affordance design was taken there and was stable across runs;
#: moving it is moving the thing that makes a small model usable.
ROLES: dict[str, Role] = {
    # 200, not 500. Three sentences is about 60 tokens and the extra room was
    # being spent on scene-setting the prompt forbids -- a cap is a cheaper
    # instruction than a sentence asking for brevity.
    "dm": Role(temperature=0.6, max_tokens=200),
    "companion": Role(temperature=0.9, max_tokens=250),
    "match": Role(temperature=0.0, max_tokens=200),
}


def roles_for(campaign_id: str = "") -> dict[str, Role]:
    """The roles, with any per-campaign override laid on top.

    The file names only what it changes:

        {"dm": {"base_url": "http://desktop.tailnet.ts.net:11434",
                "model": "qwen2.5:32b-instruct"}}

    An unknown role name or field is **reported by raising**, not ignored. A
    typo'd key in a config that silently does nothing is the same failure as a
    gate on a word no board carries -- it reads exactly like it worked.
    """
    out = dict(ROLES)
    if not campaign_id:
        return out
    where = SAVES / f"{Path(campaign_id).name}.roles.json"
    if not where.exists():
        return out
    raw = json.loads(where.read_text())
    known = set(Role.__dataclass_fields__)
    for name, over in raw.items():
        if name not in out:
            raise SystemExit(
                f"{where}: no role {name!r}. Known: {', '.join(sorted(out))}"
            )
        unknown = set(over) - known
        if unknown:
            raise SystemExit(
                f"{where}: role {name!r} sets {', '.join(sorted(unknown))}, "
                f"which is not a Role field. Known: {', '.join(sorted(known))}"
            )
        out[name] = replace(out[name], **over)
    return out


# -- the backends -----------------------------------------------------------


def _ollama(role: Role, messages: list[dict], schema: dict | None) -> str:
    """One turn against an ollama host.

    `format` takes a JSON Schema outright, which is what makes a small model
    usable here: the enum is the guarantee rather than a thing to validate
    afterwards and retry.
    """
    options: dict[str, Any] = {
        "num_ctx": role.num_ctx,
        "temperature": role.temperature,
        "num_predict": role.max_tokens,
    }
    if role.seed is not None:
        options["seed"] = role.seed
    body: dict[str, Any] = {
        "model": role.model,
        "stream": False,
        "options": options,
        "messages": messages,
    }
    if schema is not None:
        body["format"] = schema
    request = urllib.request.Request(
        f"{role.base_url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as fh:
            got = json.loads(fh.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise NoModel(
            f"{role.base_url} refused the request ({exc.code}): {detail}\n"
            f"Is {role.model!r} pulled? `ollama pull {role.model}`"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NoModel(
            f"nothing answered at {role.base_url}: {exc}\n"
            "Start it with `ollama serve`, or play with --no-llm, which needs "
            "no model at all."
        ) from exc
    return str((got.get("message") or {}).get("content", ""))


def _anthropic(role: Role, messages: list[dict], schema: dict | None) -> str:
    """The same turn against the API, for the role somebody upgrades."""
    try:
        import anthropic
    except ImportError:
        raise NoModel(
            "the anthropic backend needs its SDK: uv sync --extra dm"
        ) from None
    system = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    output: dict[str, Any] = {}
    if schema is not None:
        output["format"] = {"type": "json_schema", "schema": schema}
    try:
        got = anthropic.Anthropic().messages.create(
            model=role.model,
            max_tokens=role.max_tokens,
            system="\n\n".join(system) or anthropic.NOT_GIVEN,
            output_config=output or anthropic.NOT_GIVEN,
            messages=rest,
        )
    except Exception as exc:  # several SDK error shapes
        raise NoModel(f"the API refused: {type(exc).__name__}: {exc}") from exc
    if got.stop_reason == "refusal":
        raise NoModel("the model declined this one")
    return next((b.text for b in got.content if b.type == "text"), "")


def chat(role: Role, messages: list[dict], schema: dict | None = None) -> str:
    """One turn, against whichever backend the role names."""
    return (_ollama if role.local else _anthropic)(role, messages, schema)


def structured(role: Role, messages: list[dict], schema: dict) -> dict:
    """One turn that must come back as an object. `{}` when it does not.

    A small model occasionally returns an empty string rather than JSON -- on
    a cold load, or when `num_predict` cuts it off mid-object. The caller is
    expected to have a fallback, because **the alternative is a retry loop
    that hides the failure**: the whole point of the affordance design is that
    a wrong answer is cheap, so a missing one should be too.
    """
    text = chat(role, messages, schema).strip()
    if not text:
        return {}
    try:
        got = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return got if isinstance(got, dict) else {}


# -- running several at once ------------------------------------------------


def fan_out(jobs: list[Callable[[], Any]], *, limit: int = 8) -> list[Any]:
    """Run them together and keep the order. A job that raises yields `None`.

    **This buys nothing against a default ollama and is kept anyway.** Warmed
    and measured: 1 request 4.5s, 2 concurrent 8.7s, 4 concurrent 17.0s. That
    is linear -- the server generates one at a time, so the round costs N
    times one companion and not one.

    It stays for three reasons. It is correct either way; the ordering and
    error handling below are wanted regardless; and the two levers that make
    it pay are both outside this file -- `OLLAMA_NUM_PARALLEL` on the server,
    and a role pointed at a host with room to batch. A caller written against
    `fan_out` gets that for free the day either changes, where a caller
    written as a `for` loop would have to be found and rewritten.

    Exceptions are swallowed into `None` deliberately. One companion failing
    to answer should cost that character their turn, not end the session, and
    the caller can see which by the `None`.
    """
    if not jobs:
        return []

    def guarded(job: Callable[[], Any]) -> Any:
        try:
            return job()
        except Exception:  # a dead backend must not take the table with it
            return None

    with ThreadPoolExecutor(max_workers=min(limit, len(jobs))) as pool:
        return list(pool.map(guarded, jobs))


# -- is anybody there -------------------------------------------------------


def reachable(role: Role) -> str:
    """`""` if that role can answer, else why not.

    Cheap -- a tag list, no generation -- so an instrument can decide between
    running and reporting a skip without paying for a turn. It does **not**
    check that the model is pulled, because `ollama pull` on a missing model
    is the error the first real call reports with the fix in it.
    """
    if not role.local:
        from . import dm

        return dm.available()
    try:
        with urllib.request.urlopen(
            f"{role.base_url.rstrip('/')}/api/tags", timeout=5
        ) as fh:
            tags = json.loads(fh.read())
    except Exception as exc:  # any failure here means "not reachable"
        return f"nothing answered at {role.base_url}: {exc}"
    have = {str(m.get("model", "")) for m in tags.get("models", ())}
    if role.model not in have:
        return (
            f"{role.base_url} is up but has no {role.model!r}.\n"
            f"Run: ollama pull {role.model}"
        )
    return ""


@dataclass
class Spend:
    """What a session asked of the models, so a run can say."""

    calls: int = 0
    by_role: dict[str, int] = field(default_factory=dict)
    empty: int = 0

    def note(self, role: str, *, ok: bool = True) -> None:
        self.calls += 1
        self.by_role[role] = self.by_role.get(role, 0) + 1
        if not ok:
            self.empty += 1

    def __str__(self) -> str:
        if not self.calls:
            return "no model calls"
        each = ", ".join(f"{k} {v}" for k, v in sorted(self.by_role.items()))
        tail = f", {self.empty} gave nothing" if self.empty else ""
        return f"{self.calls} model calls ({each}){tail}"
