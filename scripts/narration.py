"""Did the DM narrate the player's own character? Read from a real log.

**A transcript, not a synthetic probe.** A probe with one intent and no
companions could not reproduce the fault at all -- 0 of 8 either side of
the fix -- while a live scene produced it on the first beat. The difference
is everything a real prompt carries: four companions declaring, eight lore
facts, three beats of recall. So the measurement reads the campaign JSONL
that play already writes.

The rule it checks is `_DM`'s: the person at the keyboard decides what
their character does, and the DM decides what the world does back. An NPC
reacting *to* them is wanted; the DM giving them a line or an action is not.

    uv run scripts/narration.py logs/keep.campaign.jsonl
    uv run scripts/narration.py logs/keep.campaign.jsonl --from 9

**The judge is held to two controls first and the run aborts if it fails
them**, because a judge nobody checked is how three earlier attempts at
this produced confident nonsense. Its question names *both* sides: asking
"the Fighter or somebody else" scored 3/4 on a 7B and 3/5 on a 14B, failing
identically, because one option was a name and the other a description and
the model reaches for the name. Naming both took it to 6/6. The model was
never the problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from combat_engine.story import llm

#: 30 and not 10. The enum values are whole names, and a 10-token budget
#: truncates the JSON -- which arrives as `{}` and reads as a wrong answer
#: rather than a cut-off one.
JUDGE = llm.Role(temperature=0.0, max_tokens=30)
ASK = ("Who performs an action or speaks in this passage? "
       "Answer with one of the options.")


def _who(passage: str, player: str, npc: str) -> str:
    schema = {"type": "object",
              "properties": {"who_acts": {"enum": [player, npc, "nobody"]}},
              "required": ["who_acts"]}
    got = llm.structured(JUDGE, [
        {"role": "system", "content": ASK},
        {"role": "user", "content": f"PASSAGE: {passage}"},
    ], schema)
    return str(got.get("who_acts", ""))


def _calibrate(player: str, npc: str) -> None:
    acts = _who(f'{player} stands and says, "No."', player, npc)
    other = _who(f"{npc} sets down a cup and waits.", player, npc)
    print(f"judge: the player acting -> {acts!r}; {npc} acting -> {other!r}")
    if acts != player or other != npc:
        raise SystemExit("the judge fails its own controls; nothing below "
                         "would mean anything")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log")
    ap.add_argument("--from", dest="start", type=int, default=0,
                    help="skip this many scene records (earlier sessions)")
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.log).read_text().splitlines()]
    rows = rows[args.start:]
    beats = [(r["scene"], b) for r in rows for b in (r.get("beats") or [])]
    if not beats:
        print("no beats in that range")
        return 0

    # The player is whoever declared with `played` false.
    # **Refuse a log that cannot say who is who**, rather than guessing.
    # `played` was absent from every record until this was written, and
    # `not i.get("played")` read a missing field as "this is the human" --
    # so the first intent in the file became the player and the whole run
    # judged the wrong character. A silently wrong answer is worse than no
    # answer.
    if any("played" not in i for _, b in beats for i in b.get("intents", ())):
        raise SystemExit(
            "this log predates `played` in the beat record, so the player "
            "cannot be told from a companion. Play a scene with the current "
            "build and read that instead."
        )
    player = next(
        (i["who"] for _, b in beats for i in b.get("intents", ())
         if i["played"] is False), "")
    if not player:
        print("no human intents in that range; nothing to judge")
        return 0
    npc = "the host"
    _calibrate(player, npc)

    hits: list[tuple[str, int, str]] = []
    judged = 0
    for scene, beat in beats:
        said = " ".join((beat.get("reaction") or "").split())
        if not said:
            continue
        judged += 1
        if _who(said, player, npc) == player:
            hits.append((scene, beat.get("n", 0), said))

    print(f"\n{judged} DM replies judged, player {player!r}")
    print(f"  narrated the player: {len(hits)} "
          f"({len(hits) / judged:.0%})" if judged else "")
    for scene, n, said in hits[:6]:
        print(f"\n  {scene} beat {n}:\n    {said[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
