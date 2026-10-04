#!/usr/bin/env python
"""Does a monster ability's header say the numbers its stat block prints?

    uv run scripts/cards.py              report every disagreement
    uv run scripts/cards.py --quiet      the counts only
    uv run scripts/cards.py m264a0 ...   just these refs
    uv run scripts/cards.py --level 3    every declared ability at a level
    uv run scripts/cards.py --silent-ok  do not exit non-zero

`audit.py` asks whether a row does *something*. `bonuses.py` asks whether one
property -- the type of a bonus -- is the printed one. Nothing asks whether a
monster's attack bonus, damage, range or usage are the printed ones, and those
four are almost the whole of a monster ability: the modal row's body is two
lines (`if c.strike(): c.hit()`) and everything that could be wrong with it is
in the header.

So this is the check that makes a wave of monster rows trustworthy, and it is
cheap for one reason: **the stat block states the answer**, in the most regular
text in the database --

    (standard, at-will) Weapon +4 vs AC; 1d4+4 damage.
    At-Will / Attack: Melee 1 (one creature); +13 vs. AC / Hit: 1d8 + 8 damage.

-- against a header that holds the same four facts as data:

    Attack(vs=AC, printed=4)   Damage("1d4", 4)   reach=Melee(1)   usage=AT_WILL

Neither side is a judgement, which is the same ground `bonuses.py` stands on.

## Why there is no `ast` here, unlike `bonuses.py`

`bonuses.py` walks the source because `c.bonus(...)` is a call in the *body*,
and a body is code. A monster's numbers are in the **decorator**, which `@power`
has already evaluated into a frozen `Power` -- so the comparison reads
`REGISTRY[ref].attack.printed`, an int, and there is nothing to parse and
nothing to miss. (`bonuses.py` records what parsing the easy way costs: its
regex handled one level of nesting and silently skipped a call whose gate was a
lambda, and one row in sixty-one was wrong that way while the script reported
the file clean.)

## Running it during a concurrent wave

`--level N` reads **every** declared ability at that level, including rows a
sibling agent is still writing. During a round of 3-4 concurrent waves that
makes the output move between runs -- one agent reported this as the
instrument being non-deterministic, which it is not: five runs on a settled
level are byte-identical and there is no randomness in this file at all. What
moved was the tree.

So while siblings are writing, **pass your own refs** rather than `--level`.
The disagreement that agent saw had been fixed by its owner four minutes
later.

## Only where both sides speak

A card that states nothing is not a disagreement. Three real shapes where the
stat block gives no number of its own, all of which must stay quiet:

* a row whose whole text is *"makes three sling attacks"* -- the numbers belong
  to the row it names, and the header copies them so the policy can forecast;
* the earlier dialect omits `Melee 1` and lets it default, so an absent range
  is an absent range and not a wrong one;
* a trait or an effect-only row, which prints no attack and no damage at all.

That rule is what keeps this instrument from needing the pile of
natural-language disambiguation `bonuses.py` accumulated. It reports a
**disagreement**, never an omission on the card's side.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

from combat_engine.content import declared
from combat_engine.engine.dsl import REGISTRY
from combat_engine.etl.build import game

#: A monster ability's ref. Nothing else is in scope: a character power's card
#: names an ability rather than a finished total, so `printed` is None there and
#: there is nothing to compare.
_ABILITY = re.compile(r"m\d+a\d+")

#: `+13 vs. AC`, `+6 vs Reflex`. The defence word is spelled out in full on
#: both dialects, and `vs.` loses its stop on the earlier one.
#:
#: `Armor Class` written out is the long form of `AC` and three cards use it.
#: Three of 7,812 is not worth a regex on its own -- it is worth one because
#: without it those three have no card value and this check is **silent** about
#: them, which reads exactly like approval.
_ATTACK = re.compile(
    r"([+-]\s*\d+)\s+vs\.?\s+(Armor Class|AC|Fortitude|Reflex|Will)\b", re.I
)

#: `1d8 + 8`, `1d4+4`, `2d6 + 5`. **The word `damage` is not required to
#: follow it**, and requiring it was wrong: one card prints
#: `1d8+5 plus 1d10 cold damage`, where the row's damage is the first
#: expression and the only `damage` in the sentence trails the second. Asking
#: for the word made the check read the rider as the row.
_DAMAGE = re.compile(r"\b(\d+)d(\d+)\b\s*(?:\+\s*(\d+))?", re.I)

#: The faces a die actually has. **A card can be corrupt**, and one is: it
#: prints `1d81+ damage` where the digits of `1d8+1` have been transposed, so
#: the face reads as 81. Three specs in 13,432 carry an implausible face, and
#: without this the check reports the *row* as wrong about a number the card
#: never stated properly. A malformed card has nothing to compare against.
_FACES = frozenset({2, 3, 4, 6, 8, 10, 12, 20, 100})

#: An **ongoing** number is a rider, not the row's damage, and it is written in
#: the same shape -- "plus ongoing 5 fire damage". 320 undeclared rows print one.
#: Matching it as the damage would report a disagreement on every single one.
_ONGOING = re.compile(r"\bongoing\b", re.I)

#: The range shapes. **Taken by position in the text, never by the order of
#: this tuple** -- testing in a fixed order said `close burst` for a card
#: printing `Close blast 5`, because a burst appeared later in the same
#: sentence. Four rows reported that way and all four headers were right.
_RANGES = (
    ("area_burst", re.compile(r"\barea burst\s+(\d+)", re.I)),
    ("close_burst", re.compile(r"\bclose burst\s+(\d+)", re.I)),
    ("close_blast", re.compile(r"\bclose blast\s+(\d+)", re.I)),
    ("ranged", re.compile(r"\branged\s+(\d+)", re.I)),
    ("melee", re.compile(r"\bmelee\s+(\d+)", re.I)),
    ("melee", re.compile(r"\breach\s+(\d+)", re.I)),
)

#: `(standard, recharge )` -- the earlier dialect prints the word with the
#: number sometimes missing, which is why the digit is optional and an absent
#: one means "the card said recharge and did not say when".
_USAGES = (
    ("recharge", re.compile(r"\brecharge\b\s*(\d)?", re.I)),
    ("at-will", re.compile(r"\bat-?will\b", re.I)),
    ("encounter", re.compile(r"\bencounter\b", re.I)),
    ("daily", re.compile(r"\bdaily\b", re.I)),
)

#: Where the usage is allowed to be read from: the leading parenthetical, or
#: the standalone word the later dialect opens with. **Not the body**, and that
#: distinction was worth thirteen false reports: the commonest shapes are
#: `until the end of the encounter` -- a duration -- and a body that enumerates
#: `an at-will, encounter, or recharge attack power`, which is the row talking
#: about other rows. Both read as a usage when the whole spec was searched.
_BODY_STARTS = re.compile(r"\b(?:Attack|Hit|Miss|Effect|Trigger|Requirement)\s*:")

#: `Melee or Ranged 10` -- two shapes on one line, the first with no number of
#: its own because it means "as far as the weapon in hand reaches".
#: **The number may sit between the two words.** This required them adjacent, so
#: `Ranged 10 or melee`, `Melee 1 or Ranged` and `Ranged 5/10 or melee` did not
#: match -- 14 cards against the 83 that print the words together -- and
#: `_card_range` read each as a plain ranged line, then reported a correct
#: `MeleeOrRanged` header as "reach melee but the card says ranged". Found by a
#: level-6 wave that checked its header was right and said so instead of changing
#: it, which is the only reason it surfaced rather than becoming a wrong row.
#:
#: The gap is deliberately small -- up to a range band and nothing more -- so a
#: sentence that merely mentions both words cannot match across a clause.
_EITHER = re.compile(
    r"\b(?:melee|ranged)\b(?:\s+\d+(?:/\d+)?)?\s+or\s+(?:melee|ranged)\b", re.I
)

#: `encounter` in this phrase is a duration and never a usage.
_DURATION = re.compile(r"\bend of (?:the|its|his|her)\b[^.;]{0,24}$", re.I)

#: A determiner in front of the word means it is a **noun in a sentence**, never
#: a printed label. `Encounter` and `At-Will` are printed standing alone or in a
#: parenthetical; nothing on a card prints "the Encounter" as its usage.
#:
#: This is the `_DURATION` guard's family, and that guard only knew one member of
#: it -- "until the end of the encounter". The rest got through:
#:
#:     At the start of an encounter, ...        -> read as usage=encounter
#:     The first time it is hit during an encounter, ...
#:     Before the encounter begins, ...
#:
#: 22 cards across the tree, every one a trait the column records correctly as
#: `at-will` or as no usage at all. **Eight written rows had already followed the
#: wrong advice**, which is the part that matters: this instrument is what an
#: author checks a header against, so a false positive here does not just fail to
#: catch an error, it causes one. Same shape as `bonuses.py`'s `_AS_TYPE`, where a
#: type word after "the" is an amount being pointed at rather than a type named.
#: **`per` is deliberately not in this list.** "twice per encounter" is a real
#: usage printed as a limit rather than as a label, and three cards state it that
#: way with the column agreeing. Excluding `per` suppressed all three and bought
#: nothing -- none of the 22 false positives used it.
_AS_PROSE = re.compile(r"\b(?:an?|the|each|this|every)\s+$", re.I)

_DEFENCES = {"ac": "AC", "armor class": "AC",
             "fortitude": "FORT", "reflex": "REF", "will": "WILL"}

#: Rows whose header disagrees with its card for a reason a person has looked
#: at. Four of 2,630, every one found by this check on its first run, and
#: **three of them are one family**: a usage the card states conditionally.
#:
#: Kept as a list rather than inferred, for the reason `bonuses.py` keeps
#: `BORROWED` as one: deciding that a conditional recharge is "really" an
#: at-will is exactly the judgement this instrument exists to avoid making. They
#: fail the useful way round -- a row that stops needing its waiver is reported.
#:
#: These are not excused, they are **queued**: #358.
KNOWN = {
    # **At-will with a cap, which one `usage` value cannot say.** The card prints
    # `At-Will (N/encounter)`; the row writes `usage=ENCOUNTER, uses=N` because
    # `dsl.usable` only consults `uses` when the usage is *not* at-will
    # (`dsl.py:1611`), so declaring the printed word would make the cap
    # decoration. Both rows already do this -- the waiver is for the label
    # disagreeing, not for anything left undone. An earlier version of this entry
    # read "wants `uses=3`", which sounded like a gap when the row had it.
    #
    # Exactly two cards in 13,432 print this shape, so it is a pair of waivers
    # rather than a feature; `Usage.AT_WILL` plus a respected `uses` would be the
    # real fix and is not worth it for two.
    "m302a2": "the card prints At-Will (3/encounter); the row says "
              "`usage=ENCOUNTER, uses=3` so the cap is enforced",
    "m6011a1": "the card prints At-Will (6/encounter); the row says "
               "`usage=ENCOUNTER, uses=6` so the cap is enforced",
    "m476a2": "the card's parenthetical says at-will and the header says "
              "encounter; the row is a standing modifier, so at-will looks right",
    "m4950a3": "the card prints `Melee 0` -- the square the creature is moving "
               "through -- and the header rounds it to 1",
    "m4962a3": "`Recharge when no enemy is dominated by this power` is a "
               "condition rather than a die roll, so the header chose at-will",
    # Not a missing value like #360's 88 -- a **contradictory** one. The card
    # prints `Melee 10/20`: a range band on a melee line, which cannot be both.
    # One row in 13,432. The header takes the normal half of the band and says so
    # in its docstring; this is waived rather than taught to the reader, because
    # a reader that accepts `Melee N/M` would stop checking the shape at all.
    "m6277a3": "the card prints `Melee 10/20` -- a range band on a melee line, "
               "which is contradictory rather than missing; see #360",
    # **`m2777a8` was here and is gone, because the row solved it.** The card
    # states two usages in one parenthetical -- `recharge 5, or at-will while
    # bloodied` -- and I waived it ahead of the row being written so whoever
    # wrote it would not be told to "fix" a correct header. The level-7 wave did
    # better than the waiver assumed: it declares `usage=RECHARGE, recharge=5`,
    # which is what the prose says, and pays the bloodied half out in the body by
    # restoring the use the moment it fires. Nothing disagrees, so the waiver was
    # dead weight and the stale-waiver guard said so on the first run after the
    # row landed. That guard earning its keep is worth more than the entry was.
}


def _card_attack(spec: str) -> tuple[int, str] | None:
    """The printed attack bonus and defence, or None if the card prints none."""
    found = _ATTACK.search(spec)
    if not found:
        return None
    bonus = int(found.group(1).replace(" ", ""))
    return bonus, _DEFENCES[found.group(2).lower()]


def _card_damage(spec: str) -> tuple[str, int] | None:
    """The printed dice and flat bonus, skipping any ongoing rider.

    Takes the **first** expression that is not ongoing. A row printing a Hit
    and a Miss states the Hit first, and a header's `Damage` is the Hit line --
    `half_on_miss` carries the other half rather than a second expression.

    **Read after the attack line, because a target count is dice too.** One card
    prints `targets 1d4 random creatures in the burst; +5 vs AC; 1d10+1 damage`:
    the first dice expression on the line is how many creatures it hits, not how
    hard. Damage always follows the attack clause on a monster card, in both
    dialects, so starting there settles it without having to tell a count from a
    die by looking at it.

    An earlier version required the word `damage` to follow the dice, which
    fixed this case and broke another -- `1d8+5 plus 1d10 cold damage`, where
    the row's own damage is the expression the word does *not* follow. Anchoring
    on the attack line fixes both.
    """
    attack = _ATTACK.search(spec)
    if attack:
        spec = spec[attack.end():]
    for found in _DAMAGE.finditer(spec):
        lead = spec[max(0, found.start() - 24): found.start()]
        if _ONGOING.search(lead):
            continue
        if int(found.group(2)) not in _FACES:
            return None
        return f"{found.group(1)}d{found.group(2)}", int(found.group(3) or 0)
    return None


def _earliest(spec: str, patterns: tuple) -> tuple[str, re.Match] | None:
    """The match that appears first in the text, not first in `patterns`."""
    best: tuple[int, str, re.Match] | None = None
    for kind, pattern in patterns:
        found = pattern.search(spec)
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), kind, found)
    return (best[1], best[2]) if best else None


def _card_range(spec: str) -> tuple[str, int] | None:
    """The printed range, or None when the card states two.

    A card printing `Close blast 3 or area burst 3 within 10` offers a choice,
    and a header holding one of them is not wrong -- so two shapes in one
    sentence means this has no single answer to compare against.
    """
    # **A secondary attack's range is not this row's.** One card prints no range
    # for its primary and `Secondary Attack Reach 2` for the follow-up; reading
    # the whole text took the second and reported the header wrong about the
    # first.
    cut = re.search(r"\bSecondary\b", spec, re.I)
    spec = spec[: cut.start()] if cut else spec
    # **A two-kind line where one kind carries no number.** The books print
    # `Melee or Ranged 10`: the melee half is the wielded weapon's reach and has
    # no digit, so `_RANGES` cannot see it and the check saw only `ranged 10` --
    # reporting a correct `MeleeOrRanged(1, 10)` header as wrong. The bail below
    # only caught the case where *both* kinds carry a digit.
    #
    # Found by a content agent, which then declined to add it to `KNOWN`: the
    # row was right and the instrument was not, and `KNOWN` is for the other
    # way round. That is the correct call and worth recording.
    if _EITHER.search(spec):
        return None
    hits = [
        (pattern.search(spec).start(), kind, pattern.search(spec))
        for kind, pattern in _RANGES
        if pattern.search(spec)
    ]
    if not hits:
        return None
    kinds = {kind for _at, kind, _m in hits}
    if len(kinds) > 1 and " or " in spec[: max(at for at, _k, _m in hits) + 24]:
        return None
    _at, kind, found = min(hits, key=lambda h: h[0])
    return kind, int(found.group(1))


def _card_usage(spec: str) -> tuple[str, int | None] | None:
    """The printed usage, read only from the head of the card. See `_BODY_STARTS`."""
    body = _BODY_STARTS.search(spec)
    head = spec[: body.start()] if body else spec
    # A long head with no label is a card whose whole text is one sentence; the
    # usage is in its opening clause, not three lines down.
    head = head[:90]
    found = _earliest(head, _USAGES)
    if not found:
        return None
    kind, match = found
    before = head[: match.start()]
    if _DURATION.search(before) or _AS_PROSE.search(before):
        return None
    if kind == "recharge":
        digit = match.group(1)
        return kind, int(digit) if digit else None
    return kind, None


def _check(ref: str, power: object, spec: str) -> list[str]:
    """Every disagreement between one header and one stat block."""
    out: list[str] = []
    flat = " ".join((spec or "").split())
    if not flat:
        return out

    card = _card_attack(flat)
    attack = getattr(power, "attack", None)
    if card and attack is not None and attack.printed is not None:
        want, defence = card
        if attack.printed != want:
            out.append(f"attack +{attack.printed} but the card prints +{want}")
        if attack.vs.name != defence:
            out.append(f"attack vs {attack.vs.name} but the card says {defence}")

    card_dmg = _card_damage(flat)
    damage = getattr(power, "damage", None)
    if card_dmg and damage is not None and damage.dice:
        dice, bonus = card_dmg
        if damage.dice.replace(" ", "") != dice:
            out.append(f"damage {damage.dice} but the card prints {dice}")
        # A character's bonus is an ability name resolved at use; only a
        # monster's is a number, and only a number is comparable.
        if isinstance(damage.bonus, int) and damage.bonus != bonus:
            out.append(f"damage +{damage.bonus} but the card prints +{bonus}")

    card_range = _card_range(flat)
    reach = getattr(power, "reach", None)
    if card_range and reach is not None and reach.kind != "personal":
        kind, size = card_range
        if reach.kind != kind:
            out.append(f"reach {reach.kind} but the card says {kind}")
        elif reach.size != size:
            out.append(f"reach {reach.kind} {reach.size} but the card says {size}")

    card_usage = _card_usage(flat)
    usage = getattr(power, "usage", None)
    if card_usage and usage is not None:
        kind, digit = card_usage
        if usage.value != kind:
            out.append(f"usage {usage.value} but the card says {kind}")
        elif digit is not None and getattr(power, "recharge", 0) != digit:
            out.append(
                f"recharge {getattr(power, 'recharge', 0)} but the card says {digit}"
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("refs", nargs="*", help="only these refs")
    ap.add_argument("--level", type=int, help="every declared ability at a level")
    ap.add_argument("--quiet", action="store_true", help="the counts only")
    ap.add_argument("--silent-ok", action="store_true",
                    help="report, but do not exit non-zero")
    args = ap.parse_args()

    db = game()
    specs = {
        r["ref"]: r["spec"]
        for r in db.execute("SELECT ref, spec FROM monster_power")
    }
    if args.level is not None:
        wanted = {
            r["ref"]
            for r in db.execute(
                "SELECT a.ref FROM monster_power a JOIN monster m "
                "ON m.ref = a.monster_ref WHERE m.level = ?", (args.level,)
            )
        }
    else:
        wanted = set(args.refs) if args.refs else None

    rows = declared()
    refs = [r for r in sorted(REGISTRY) if _ABILITY.fullmatch(r)]
    if wanted is not None:
        refs = [r for r in refs if r in wanted]
        # **Refuse rather than report nothing.** `0 of 0 agree` is
        # success-shaped: it exits 0, says no row disagreed, and is exactly what
        # a run that checked nothing looks like. An agent reported this as the
        # instrument failing above some argument count; the real cause was the
        # shell -- **zsh does not word-split an unquoted `$VAR`**, so a ref list
        # held in a variable arrives as one argument full of spaces and matches
        # no ref. `${=VAR}` splits it, and `$(cat file)` splits too.
        #
        # Either way the lesson is the instrument's: say so loudly.
        if not refs:
            given = sorted(wanted)[:4]
            print(f"  none of the {len(wanted)} ref(s) given is a declared "
                  f"monster ability: {', '.join(given)}"
                  + (" ..." if len(wanted) > 4 else ""))
            print("  (in zsh an unquoted $VAR is one argument -- use ${=VAR})")
            return 1

    faults: dict[str, list[str]] = {}
    nocard = checked = skipped = 0
    for ref in refs:
        power = REGISTRY[ref]
        # A `todo=` row is refused in play and its header is a placeholder; a
        # comparison against it would report the marker, not a mistake.
        if rows.get(ref) is not None and getattr(rows[ref], "todo", None):
            skipped += 1
            continue
        spec = specs.get(ref)
        if not spec:
            nocard += 1
            continue
        checked += 1
        bad = _check(ref, power, spec)
        if bad:
            faults[ref] = bad

    fresh = {r: v for r, v in faults.items() if r not in KNOWN}
    waived = {r: v for r, v in faults.items() if r in KNOWN}

    if not args.quiet:
        for ref in sorted(fresh):
            for line in fresh[ref]:
                print(f"  WRONG   {ref:<12} {line}")
        for ref in sorted(waived):
            print(f"  known   {ref:<12} {KNOWN[ref]}")

    kinds = Counter(line.split()[0] for lines in fresh.values() for line in lines)
    print(f"\n  {checked - len(faults)} of {checked} monster abilities "
          f"agree with their stat block")
    if fresh:
        print(f"  {len(fresh)} disagree: "
              + ", ".join(f"{n} {k}" for k, n in kinds.most_common()))
    if waived:
        print(f"  {len(waived)} disagree for a reason somebody looked at -- "
              f"see KNOWN and #358")
    # A waiver for a ref that no longer disagrees is the quietest failure here:
    # the row it was written for could regress and this would stay quiet. Same
    # argument `audit.py` makes about a stale `KNOWN_SILENT` key.
    # Parenthesised for the reader, not to fix a bug: `-` binds tighter than
    # `&`, so the unparenthesised form already grouped as `(KNOWN - faults) &
    # refs`, which is what is wanted. Written out because getting that wrong is
    # half of what #216 was, and a reader should not have to recall the table.
    stale = sorted((set(KNOWN) & set(refs)) - set(faults))
    if stale:
        print(f"  {len(stale)} waiver(s) no longer needed, remove from KNOWN: "
              + ", ".join(stale))
    if nocard:
        print(f"  {nocard} have no stat-block text to compare against")
    if skipped:
        print(f"  {skipped} skipped as `todo=`, whose header is a placeholder")
    # **Never a bare percentage**: say what was counted.
    scope = (f"level {args.level}" if args.level is not None
             else "the refs given" if args.refs else "every declared ability")
    print(f"  counting {scope}; a card that states nothing is never a fault")
    return 1 if (fresh or stale) and not args.silent_ok else 0


if __name__ == "__main__":
    sys.exit(main())
