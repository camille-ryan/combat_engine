#!/usr/bin/env python
"""Does each `c.bonus` say the bonus type its card prints?

    uv run scripts/bonuses.py           report every disagreement
    uv run scripts/bonuses.py --fix     write the card's type into the code
    uv run scripts/bonuses.py --quiet   the counts only

4e's stacking rule is entirely about the *type* of a bonus: two of the same
type do not add, untyped ones do. So a bonus written with the wrong type is
not a cosmetic slip -- it is a number that is silently too big or too small
in every fight, and nothing else in this repository can see it. `audit.py`
asks whether a row does something; this asks whether what it does is the
printed amount.

The check is possible at all because **the card says which**. "power bonus"
appears 604 times across the compendium, plus enhancement, shield, racial
and the rest; 225 specs say "bonus" with no type word, and those are the
untyped ones. So the comparison is between the `kind=` in the code and the
word in front of "bonus" in `power.spec`, and neither side is a judgement.

`--fix` is safe for the same reason: where the card names a type and the
code omits one, there is exactly one right answer to write in. It will not
touch a call that already names a type, and it will not guess for a row
with no compendium entry -- a class feature has no card, so those are
listed for a person instead.
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The bonus types 4e prints. `untyped` is not a word any card uses -- it is
#: what the absence of the others means -- but a row may say it explicitly.
TYPES = (
    "power", "feat", "item", "racial", "proficiency",
    "enhancement", "shield", "untyped",
)

#: Types a card names by their mechanic instead of by the word "bonus".
#: `enhancement` is deliberately **not** here. The others are types a
#: card grants by naming the mechanic -- "your allies have cover" is a
#: cover bonus and never calls itself one. An item's enhancement is
#: granted by `engine/equipment.py` off a column, never by a row, so a
#: card mentioning it is always pointing at the number rather than
#: handing one out.
MECHANICS = ("cover", "shield", "proficiency", "concealment")

#: Calls that lay a bonus under **another row's** type on purpose, where
#: the card's own type word is therefore the wrong thing to compare with.
#:
#: The docstring above says neither side of this comparison is a
#: judgement. That is true of the two shapes it was built for and false
#: of a third: a feat whose printed benefit *extends* or *replaces* a
#: bonus some other row already lays. "The bonus from your <racial
#: feature> also applies to ..." and "the bonus to AC ... is equal to
#: the higher of your Constitution or Wisdom modifier" both mean one
#: bonus, not two -- and two of a kind do not stack while the larger
#: wins, so writing the *other* row's kind is what makes the arithmetic
#: come out as printed. Written untyped, both would stack and pay twice.
#:
#: Kept as a list rather than inferred, because deciding that a sentence
#: is talking about somebody else's bonus is exactly the judgement this
#: instrument exists to avoid making. It fails the useful way round: a
#: row that stops needing its waiver is reported, not silently excused.
BORROWED = {
    # `rt:r39-...` was here and race 39 does not exist in the compendium at
    # all -- the feat's own prerequisite says r5. A ref minted from a printed
    # label cannot be checked against anything, which is how a typo in one
    # survived in a comment. #341.
    ("f2095", "racial"),   # extends rt:r5-t0's save bonus
    ("f3163", "racial"),   # replaces rt:r24-t2's +2
    ("f2398", "racial"),   # raises rt:r8-t0' +1 to +2
}

#: Rows where a `c.bonus` call is **not** the card's printed bonus, so
#: the card's type word does not belong on it. Two shapes:
#:
#: `f1766b` — the card prints "+2 power bonus on the attack roll", and
#: that +2 is handed over by `c.grant_attack(attack_bonus=)`, which
#: takes a bare number. The row's one `c.bonus` is the extra radiant
#: die, which the card does not type. Writing "power" into that call
#: would put the word on the wrong number. The type really is lost in
#: play and the row says so with a marker, so this waives the *checker*
#: and not the gap.
#:
#: `f2913` — the card's typed bonus is laid, correctly, as `kind="feat"`.
#: The row's *second* call is the printed "use your Strength modifier in
#: place of your Charisma modifier", written as the difference between
#: the two. That is a substitution, not a bonus, and it is untyped
#: because two of a kind would not stack and it must.
#: `m915a4`, `m970a3` — the same shape a third time, and the first monster
#: rows to need it. Each card prints two numbers in two sentences: "+1 **power**
#: bonus to its next attack roll", then "if the attack hits and deals damage, it
#: deals an extra N damage". The type word belongs to the attack roll and both
#: rows already write `kind="power"` there. The flagged call is the extra damage,
#: which the card types as nothing, and writing "power" onto it would make two
#: untyped dice fail to stack where the card has them stacking. This is the
#: "one card, two numbers, which call is which" limit this file's own notes
#: name -- the checker cannot tell which sentence a call came from, so the
#: judgement is recorded here rather than guessed there.
#:
#: Keyed by ref, as the two above are, which means a waived row's *correct*
#: typed call stops being checked too. That is the cost of the simpler key and
#: is worth saying out loud.
#: `m2079a5` is the same shape a fourth time, two levels up: "+1 **power** bonus
#: to her next attack roll ... it deals an extra 7 damage". Same split, same
#: judgement. Four rows of one card shape is the point at which it is worth saying
#: that this is a *recurring* printed form rather than four oddities -- a typed
#: bonus to the roll and an untyped rider on the damage, in two sentences.
ELSEWHERE = {"f1766b", "f2913", "m915a4", "m970a3", "m2079a5"}

#: A type word is printed as "a **power** bonus" or "+2 **item** bonus".
#: The same word after "the" or "equal to the" is an *amount* being
#: pointed at rather than a type being named.
_AS_TYPE = r"(?:\ba\b|\ban\b|[+-]?\d+)\s+{t}\s+bonus\b"


def _names_type(text: str, t: str) -> bool:
    """Does the card name this as a bonus **type**?

    Only `enhancement` needs the stricter reading, and it needs it badly.
    Every other type word appears on a card only as a type; this one is
    also the name of a number that dozens of magic items point at --
    "deal extra damage equal to the enhancement bonus", "add 5 + the
    enhancement bonus of the orb". Read as a type it advised
    `kind="enhancement"` on two cards that plainly print "item bonus",
    and that kind is the one `engine/equipment.py` uses for the item's
    own plus -- so the two would have eaten each other under the
    same-type rule and the item bonus would have been worth nothing, in
    silence.
    """
    if t != "enhancement":
        return bool(re.search(rf"\b{t}\s+bonus\b", text))
    return bool(re.search(_AS_TYPE.format(t=t), text))


#: Calls are found with `ast`, not a regex. The regex here handled one
#: level of nesting, so a `c.bonus(...)` whose gate is a lambda containing
#: a call was skipped entirely and never checked -- one row in sixty-one
#: was wrong that way and the script reported the file clean.
KIND = re.compile(r"""kind=["']([a-z ]+)["']""")

#: `Mods` is also used as a general keyed store, and those keys are not
#: bonuses any card ever gives a type to -- "automatically a critical hit"
#: is not a +N of any kind. Comparing them against the row's printed text
#: reported a correct row as wrong, because the row had two `c.bonus`
#: calls and only the first was the printed bonus.
INTERNAL = {
    "crit_range", "forced", "forcing", "reach", "concealment",
    "no_advantage", "unflankable", "shift", "initiative",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fix", action="store_true", help="write the card's type in")
    ap.add_argument("--quiet", action="store_true", help="counts only")
    args = ap.parse_args()

    cards = _cards()
    wrong, missing, nocard = [], [], []
    for ref, src, path in _rows():
        card = cards.get(ref)
        for text, key in _calls(src):
            if key in INTERNAL:
                continue
            said = KIND.search(text)
            code = said.group(1) if said else ""
            if card is None:
                nocard.append((ref, code or "(default)", path))
                continue
            typed, plain = card
            if not said:
                # No kind written. Correct if the card types nothing -- and
                # also if it prints an untyped bonus somewhere, since this
                # may be that one. The untyped branch below already made
                # that allowance and this one did not, so a mixed card
                # could never be satisfied from either side.
                if typed and not plain and ref not in ELSEWHERE:
                    missing.append((ref, sorted(typed)[0], path, text))
            elif code == "untyped":
                # A card can print one typed bonus and one plain one, and
                # comparing every call against the whole row's set of type
                # words made that row unpassable -- the untyped call was
                # measured against the *other* bonus's word. Untyped is
                # right whenever the card says "bonus" with no type
                # somewhere, or types nothing at all.
                if typed and not plain:
                    wrong.append((ref, code, sorted(typed), path))
            elif code not in typed and (ref, code) not in BORROWED:
                wrong.append((ref, code, sorted(typed) or ["untyped"], path))

    if args.fix:
        return _fix(missing)

    if not args.quiet:
        for ref, code, card, path in wrong:
            print(f"  WRONG   {ref:9} code says {code!r}, the card says {card} -- {path}")
        for ref, want, path, _ in missing:
            print(f"  add     {ref:9} kind={want!r}, which is what the card prints -- {path}")
    print(
        f"\n  {len(wrong)} disagree with the card, {len(missing)} omit a type the "
        f"card names, {len(nocard)} on refs with no card"
    )
    if nocard and not args.quiet:
        by = Counter(r for r, _, _ in nocard)
        print(f"  (no card: {len(by)} refs -- class features and monster abilities,"
              " which print no bonus type and are a judgement)")
    return 1 if wrong or missing else 0


def _granted(text: str, word: str) -> bool:
    """Does the card *give* this, rather than mention it?

    "your allies have cover" grants a cover bonus. "ignores cover", "no
    cover", "the penalty for cover" and "you must be wielding a shield"
    all mention one without granting it, and matching the bare word made
    five correct rows look wrong -- including one where "shield" appeared
    only in the Requirement line.
    """
    for m in re.finditer(rf"\b{word}\b", text):
        # Back to the start of the sentence, not a fixed window. A
        # negation governs a whole list -- "ignores cover **and
        # concealment**" -- so the word that cancels it can be many
        # tokens away, and four correct rows were flagged because the
        # lookbehind stopped short.
        start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start()))
        before = text[start + 1:m.start()]
        if re.search(
            r"\b(ignore|ignores|ignoring|no|without|not|n't|penalt\w*|must|"
            r"requirement|prerequisite|against creatures that have|"
            # **"while wielding a shield" is a gate and carries no negation.**
            # `must` already caught "you must be wielding a shield", and the
            # commoner phrasing has no such word in it -- so f2630's bonus,
            # which its card leaves untyped, was read as a shield bonus off
            # the clause saying when the feat applies. A type word is never
            # introduced *by* "wielding", so excluding it cannot hide a real
            # one: "a +1 shield bonus while wielding a shield" still grants,
            # because the first `shield` has no `wielding` before it.
            r"wielding|wields|wielded)\b", before
        ):
            continue
        # **"proficiency with that weapon" is a gate, not a grant**, and
        # the negation list above cannot see it: the sentence has no
        # "must" in it, it simply says "you have proficiency with". Every
        # one of the sixty weapon-style feats opens that way, so the day
        # that family was written the checker started advising
        # `kind="proficiency"` on rows whose bonus is plainly untyped.
        #
        # The distinction is the preposition. A type is named *as* a
        # bonus -- "a proficiency bonus" -- and a possession is followed
        # by "with".
        #
        # That preposition test was too literal. The cards also invert
        # it -- "a weapon **with which you have proficiency**" -- where
        # the word is followed by a comma and the "with" is four tokens
        # to its left. So for this one word the positive signal is used
        # instead of the negative: proficiency is a bonus type only when
        # the card says "proficiency bonus", and every other phrasing of
        # it is a possession. The other three mechanics words are
        # genuinely granted without the noun ("your allies have cover"),
        # which is why this is not the rule for all four.
        if word == "proficiency":
            if not re.match(r"\s+bonus\b", text[m.end():]):
                continue
        elif re.match(r"\s+with\b", text[m.end():]):
            continue
        return True
    return False


def _calls(src: str) -> list[tuple[str, str]]:
    """Every `c.bonus(...)` in a row, with the `what` it modifies.

    Found through `ast` rather than by matching brackets, because a gate
    written as a lambda nests arbitrarily deep and a regex that stopped at
    one level skipped such a call without saying so.
    """
    import ast

    try:
        tree = ast.parse(textwrap.dedent(src))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "bonus"):
            continue
        text = ast.get_source_segment(textwrap.dedent(src), node) or ""
        first = node.args[0] if node.args else None
        key = first.value if isinstance(first, ast.Constant) else ""
        if isinstance(first, ast.Attribute):     # `AC`, `Defense.AC`
            key = first.attr.lower()
        elif isinstance(first, ast.Name):
            key = first.id.lower()
        out.append((text, str(key).lower()))
    return out


def _cards() -> dict[str, tuple[set[str], bool]]:
    """What bonus types each row's printed text names, and whether it also
    prints a bonus with no type word at all."""
    sys.argv = sys.argv[:1]
    from combat_engine.etl.build import game

    out: dict[str, tuple[set[str], bool]] = {}
    # **Every table that holds a spec.** A monster ability prints a bonus
    # type as readily as a power does and its text lives in
    # `monster_power`; reading only `power` left 165 calls looking like
    # they had no card when most of them had one in the other table.
    #
    # Items and feats were the same mistake made a second time, and it
    # was worse: the first wave of 80 feats made 63 `c.bonus` calls and
    # this instrument said nothing at all about any of them -- not
    # "disagrees", not "no card", nothing. A checker that is silent about
    # a whole corpus reads exactly like a checker that approves of it.
    for table in ("power", "monster_power", "class_feature",
                  "item", "item_block", "feat"):
        for ref, spec in game().execute(f"select ref, spec from {table}"):
            text = (spec or "").lower()
            typed = {t for t in TYPES if _names_type(text, t)}
            # Some types are named by their mechanic rather than by the
            # word "bonus": a card says "your allies have cover", never
            # "a cover bonus", and cover is exactly a +2 of that type.
            # Without this the correct `kind="cover"` read as a mistake.
            typed |= {t for t in MECHANICS if _granted(text, t)}
            # A "+2 bonus" with no word in front of it. `\w+ bonus` would
            # match "+2 bonus" via the number, so the test is that some
            # mention of a bonus is *not* preceded by a type word.
            plain = (
                any(
                    not any(m.group(0).startswith(t) for t in TYPES)
                    for m in re.finditer(r"[a-z]+\s+bonus\b", text)
                )
                or bool(re.search(r"[+-]\d+\s+bonus\b", text))
                # "deals 1d8 extra damage" is a number the card gives and
                # never calls a bonus, so it is untyped -- and a row that
                # also prints a typed bonus has one call of each.
                or "extra damage" in text
                # **A penalty replaced by a smaller one is untyped.**
                # "a -2 penalty to attack rolls (instead of -5)" is
                # written as the arithmetic difference against the
                # standing penalty, because nothing waives one clause of
                # a condition's rules. That difference is a correction
                # and not a bonus of any type -- but the same card also
                # prints "+2 feat bonus to Dungeoneering", so without
                # this the typed half made the untyped half look wrong.
                or bool(re.search("instead of\\s*[-\u2013]\\s*\\d", text))
                # **A number granted without the word "bonus" is plain.**
                # "It gains +2 to death saving throws and saving throws
                # against the unconscious condition, as well as a +2
                # racial bonus to Stealth" -- the first grant names no
                # type and never calls itself a bonus, the second does
                # both, and comparing the untyped call against the whole
                # card's set made the row unpassable. Written as "+N to
                # X" so it cannot match "a +2 racial bonus to Stealth",
                # where a type word sits between the number and the "to".
                or bool(re.search(r"[+-]\d+\s+to\s", text))
            )
            out[ref] = (typed, plain)
    return out


def _rows() -> list[tuple[str, str, str]]:
    """Every declared row's source, with the file it lives in."""
    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    out = []
    for ref, p in REGISTRY.items():
        try:
            src = inspect.getsource(p.body)
            where = Path(inspect.getfile(p.body)).relative_to(ROOT)
        except (OSError, TypeError, ValueError):
            continue
        out.append((ref, src, str(where)))
    return out


def _fix(missing: list[tuple[str, str, str, str]]) -> int:
    """Write `kind=` into the calls whose card names a type.

    Edits the text of each call rather than the file wholesale, and only
    where the call has no `kind=` already, so a second run is a no-op.
    """
    edits: dict[str, list[tuple[str, str]]] = {}
    for _ref, want, path, call in missing:
        fixed = call[:-1].rstrip()
        if not fixed.endswith(","):
            fixed += ","
        fixed += f' kind="{want}")'
        edits.setdefault(path, []).append((call, fixed))

    touched = 0
    for path, pairs in edits.items():
        file = ROOT / path
        text = file.read_text()
        before = text
        for call, fixed in pairs:
            text = text.replace(call, fixed)
        if text != before:
            file.write_text(text)
            touched += 1
    print(f"  wrote {sum(len(v) for v in edits.values())} kinds across {touched} files")
    print("  re-run without --fix, then `uv run ruff check --fix .` for the wrapping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
