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
from functools import cache
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
    # The same trait, raised by a second feat, and the same reading. Measured
    # rather than argued, because `kind=` is load-bearing here: beside the
    # trait's racial +1, a second *racial* 2 totals 2 -- the card's "increases
    # to +2" -- while a *power* 2 would add and total 3. Probed both ways on a
    # board; they differ by exactly 1.
    #
    # The card does print "power", once, for its *other* clause -- a +2 power
    # bonus to damage, which the row lays with `kind="power"` and which is not
    # what was flagged. So this is the by-ref cost the note above owns: the
    # checker pools both clauses of one card and cannot see which sentence a
    # call came from.
    ("f1863", "racial"),   # raises rt:r8-t0's +1 to +2, as f2398 does
    # Two more feats raising that same trait, found by this check the moment
    # they were written. Four cards now, one trait, one reading: `Mods.total`
    # takes the max within a `kind` bucket, so a second *racial* bonus is the
    # raise and an untyped one would add. `f2129b` and `f2300` are the same
    # raise as each other -- two symbols over one need, noted on both rows.
    #
    # **Four instances is the point at which the by-ref list is the wrong
    # shape here too**, exactly as the `ELSEWHERE` note above concluded for
    # its own six: the rule is "a call that raises another row's typed bonus
    # takes that row's type", and the checker would have to follow the
    # reference to know. Recorded rather than inferred, again.
    ("f2129b", "racial"),  # raises rt:r8-t0, as f1863/f2398/f2300 do
    ("f2300", "racial"),   # the same raise as f2129b, different card
    # **A feat granting two *other feats'* benefits wholesale.** "You gain
    # the benefits of <f233> and <f1032> with all weapons you are proficient
    # with" prints no type word of its own -- correctly, because it hands out
    # somebody else's bonuses and both of those cards print "feat bonus". So
    # the type belongs to the borrowed benefit, exactly as the note above
    # describes, and untyped is the one reading that is definitely wrong: it
    # would stack with `f233` itself and pay +2 where the rules pay +1.
    #
    # Two entries because the row lays two calls, attack and damage, and the
    # key is per (ref, kind).
    ("f2149", "feat"),     # borrows f233's and f1032's feat bonuses
    # **The third shape is parsed now, so neither waiver is needed.** A
    # card can name an object's own bonus with no article -- "add the
    # enhancement bonus of this implement to your will defence" -- and
    # `_ADDED_TO` reads it, gated on the verb and on the destination being a
    # roll or a defence. `i2842x1` and `i1468x1` were waived here when the
    # parse could not; removing the waivers is the tightening, and the
    # instrument stays clean without them. #523.
    # **A fourth of the extends-another-row shape**, the first three being
    # the racials above. "You gain **additional** temporary hit points
    # from your rt:r36-t1 racial trait equal to your Constitution
    # modifier" is one pool, not two: written untyped it would stack with
    # the trait's own and pay twice, so the trait's kind is what makes the
    # arithmetic come out as printed.
    ("f1855", "racial"),
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
#:
#: `m2354a4` is the **fifth**, from level 12: "+1 **power** bonus to its next
#: attack roll ... If the attack hits and deals damage, it deals extra 5 damage".
#: Identical split. Five instances is enough to say the by-ref list is the wrong
#: shape for this: the card names the type in the sentence about the *roll*, and
#: the rider is a separate sentence with no type word in it. Read per sentence
#: rather than per row and all five pass without being named -- and the cost of
#: naming them, recorded above, is that each waived row's *correct* typed call
#: stops being checked too. Filed rather than changed here, because narrowing a
#: natural-language reader is how this file grew its false positives in the first
#: place and it wants its own measurement.
#:
#: `i3382p1` is the **sixth**, and a variant worth distinguishing: its untyped
#: call is not a rider on damage but a *substitution*. The card prints "+4
#: power bonus to AC and Reflex" -- written, typed, correct -- and separately
#: "you can use the attack result as your defense", which the row implements as
#: the difference between the roll and the live defence. That delta is not a
#: printed bonus at all, and typing it `power` would be actively wrong: two
#: bonuses of one type do not stack, so it would collide with the +4 and the
#: larger would win.
#:
#: So six instances, two shapes, one conclusion -- the per-sentence read this
#: comment has wanted since the fifth is still the right fix, and the delta
#: case says something the first five did not: the question is not only "which
#: sentence names the type" but "is this call a printed bonus at all".
#:
ELSEWHERE = {"f1766b", "f2913", "m915a4", "m970a3", "m2079a5", "m2354a4",
             "i3382p1"}

#: A type word is printed as "a **power** bonus" or "+2 **item** bonus".
#: The same word after "the" or "equal to the" is an *amount* being
#: pointed at rather than a type being named.
_AS_TYPE = r"(?:\ba\b|\ban\b|[+-]?\d+)\s+{t}\s+bonus\b"

#: **The third phrasing, and the word that tells it from the second.** A card
#: can name an object's own bonus with no article, and whether that is a
#: *type* or a *magnitude* turns entirely on the verb:
#:
#:   add the enhancement bonus of this implement **to** your will defence
#:       -> applied as itself, so it carries the type
#:   a penalty to your AC **equal to** the enhancement bonus of this armor
#:       -> a number the card points at, so it carries no type
#:
#: `_AS_TYPE` refuses both, deliberately -- reading them loosely put
#: `kind="enhancement"` on two cards that plainly print "item bonus", which
#: would have made the real item bonus worth nothing under the same-type
#: rule. So this does not widen that gate; it adds the narrower question
#: beside it, requiring the **verb** and a **destination**.
#:
#: Measured before being written, which is what #523 asked for: 4 cards in
#: the corpus print `the <type> bonus ... of <object>` with no article, and
#: they split 2 and 2 -- two apply it (`i1964x1`, `i2842x1`) and two are
#: "equal to" magnitudes, one of them a *distance in squares*. So the
#: discriminator is not "a type word with no article"; it is this. #523.
#: **A bonus type only means something on a roll or a defence**, because the
#: same-type rule is what the type is *for*. The destinations in the corpus
#: split exactly there, and measuring them is what caught two cards this
#: branch had wrong:
#:
#:   to your attack roll / your grab attack / your will defence  -> a type
#:   to the range                                                -> a distance
#:   to the hit points regained                                  -> healing
#:
#: The last two are magnitudes with no stacking question, so typing them
#: would be the same error as reading "equal to the enhancement bonus" as a
#: type. `i2771x1` and `i2784p1` are those two and both read True until the
#: destination was constrained. #523.
#: Braces doubled: this is spliced into `_ADDED_TO`, which goes through
#: `.format(t=...)`, and a bare `{0,40}` reads as a field name there.
_DESTINATION = (r"[^.,;]{{0,40}}?"
                r"\b(?:attacks?|rolls?|defen[cs]e|ac|will|fortitude|reflex)\b")

#: Four phrasings of the same clause, measured rather than guessed:
#:
#:   add the enhancement bonus **of** this implement to your will defence
#:   add the proficiency bonus and enhancement bonus of this weapon to ...
#:   add the symbol**'s** enhancement bonus to your attack roll
#:   add**ing** the weapon's enhancement bonus to your grab attack
#:
#: so the verb takes `-s`/`-ing` and the object comes either before the type
#: as a possessive or after it with `of`. Anything reached this way is still
#: put past `_RETYPED` -- three of the matches say "as a power bonus" or
#: "as an item bonus", which names a different type and is the whole reason
#: this gate was tight to begin with.
_ADDED_TO = (r"\badd(?:s|ing)?\s+(?:the\s+)?(?:"
             # **Both apostrophes.** The imported text carries a straight
             # `'` on one card and a typographic U+2019 on another, so a
             # pattern with either alone silently misses half the
             # possessives -- which is how this one was missed first time.
             r"[a-z]+['\u2019]s\s+{t}\s+bonus"
             r"|(?:[a-z]+\s+bonus\s+and\s+)?{t}\s+bonus\s+of\b"
             r")[^.]*?\b(?:to|against)\s+" + _DESTINATION)


#: `as a[n] <word> bonus` inside an applied clause -- the card naming the
#: type the figure is handed out as, which is then **that** type and not the
#: one the magnitude came from.
_RETYPED = re.compile(r"\bas\s+an?\s+[a-z]+\s+bonus\b")


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
    if re.search(_AS_TYPE.format(t=t), text):
        return True
    applied = re.search(_ADDED_TO.format(t=t), text)
    # **"as an item bonus" names the type, and it is not this one.** Both
    # cards on record as false positives say so outright -- "add the
    # enhancement bonus of this weapon **as an item bonus** to all your
    # defences" -- so the enhancement figure is the *magnitude* and `item`
    # is the type. Reading the verb alone put `kind="enhancement"` back on
    # both of them, which is the loosening this gate exists to prevent.
    return bool(applied) and not _RETYPED.search(applied.group(0))


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
    "crit_range", "forced", "forcing", "concealment",
    "no_advantage", "unflankable", "shift", "initiative",
    # **`dsl._stretched`'s three keys, and only one of them was here.**
    # `reach`, `range` and `blast_size` are the melee, ranged and burst
    # halves of one mechanism -- that function reads exactly these three --
    # and a *distance* is not a bonus a card types. `reach` was listed and
    # its two siblings were not, so a row growing a burst or a ranged range
    # was measured against the card's typed bonuses and asked to label a
    # radius "power".
    #
    # It surfaced on `f1010`, whose card prints one typed bonus ("+2 power
    # bonus to weapon damage rolls") and one *replacement* ("becomes a close
    # burst 5 + your Charisma modifier"). The replacement is expressed with
    # a `blast_size` modifier because that is the mechanism available, and
    # the check asked for `kind='power'` on it -- which would have mislabeled
    # a radius as a typed bonus and put it in the same stacking bucket as
    # the damage one.
    #
    # Four rows already used the two missing keys and passed, but only
    # incidentally: their cards print an untyped bonus somewhere, which the
    # `not said` branch allows. So this is the check's definition being
    # short, not a row being wrong -- `scripts/CLAUDE.md`'s first rule, and
    # the direction it points here is "fix the check".
    "reach", "range", "blast_size",
    # **Two permissions, not bonuses.** `shares_space` and `may_enter` are
    # the occupant's and the mover's halves of "may stand where you stand"
    # (#626). Each is a 1 under a key, because `Mods` with a `when=` gate is
    # how a scoped property is held -- there is no number on any card to
    # type. `shares_space` passed before this only incidentally, through the
    # `not said` branch, which is the same shortfall the note above
    # describes for `range` and `blast_size`.
    "shares_space", "may_enter",
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
        for text, key, gating in _calls(src):
            if key in INTERNAL:
                continue
            said = KIND.search(text)
            code = said.group(1) if said else ""
            # **#550: the clause belongs to the feat's card, not this
            # row's.** Checked against that card rather than waived, so a
            # migrated clause whose `kind=` is wrong is still caught -- and
            # per *clause*, since a feat names a different bonus in each
            # power it lists.
            if code and gating:
                theirs = _feat_clauses().get((gating, ref))
                if theirs and code in theirs:
                    continue
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


#: A feat ref written as a string anywhere in an `if` test.
_FEAT_IN_GATE = re.compile(r"\bf\d+\b")


def _calls(src: str) -> list[tuple[str, str, str]]:
    """Every `c.bonus(...)` in a row: its text, the `what`, and the feat
    whose clause it belongs to if it sits inside one.

    Found through `ast` rather than by matching brackets, because a gate
    written as a lambda nests arbitrarily deep and a regex that stopped at
    one level skipped such a call without saying so.

    **The third value exists because #550 broke this check's premise.**
    That migration writes a feat's clause into the power the feat names,
    so a power's body lays bonuses the *power's* card never prints -- and
    comparing them against the power's card reported the migration working
    as two faults. The clause is always gated on the declared feat,
    `if arena == "f992":` or `if c.feat("f1298"):`, so the ref that says
    which card to read is right there in the test.
    """
    import ast

    body = textwrap.dedent(src)
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return []

    # Which feat gates each statement, by walking `if` tests downward.
    gate: dict[int, str] = {}

    def mark(stmts: list, ref: str) -> None:
        for st in stmts:
            for node in ast.walk(st):
                gate.setdefault(id(node), ref)

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.get_source_segment(body, node.test) or ""
        found = _FEAT_IN_GATE.findall(test)
        if len(found) == 1:
            # One feat named, so the branch is unambiguously its clause.
            # Two or more is a compound condition this must not guess at.
            mark(node.body, found[0])

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "bonus"):
            continue
        text = ast.get_source_segment(body, node) or ""
        first = node.args[0] if node.args else None
        key = first.value if isinstance(first, ast.Constant) else ""
        if isinstance(first, ast.Attribute):     # `AC`, `Defense.AC`
            key = first.attr.lower()
        elif isinstance(first, ast.Name):
            key = first.id.lower()
        out.append((text, str(key).lower(), gate.get(id(node), "")))
    return out


@cache
def _feat_clauses() -> dict[tuple[str, str], set[str]]:
    """Types each feat's card names, per power it names, keyed `(feat, power)`.

    A feat's spec lists its associated powers one per line, prefixed by the
    power's ref -- `p1758 : If you are wielding a shield ... you gain a +1
    feat bonus to AC ...`. That line is the card for a migrated clause, and
    it is the one to compare a `kind=` against once #550 has moved it into
    the power's body.

    Read per clause rather than per feat on purpose: a feat with four
    associated powers names a different bonus in each, so the union of its
    types would waive a wrong one.
    """
    sys.argv = sys.argv[:1]
    from combat_engine.db import game

    out: dict[tuple[str, str], set[str]] = {}
    for ref, spec in game().execute("select ref, spec from feat"):
        for line in (spec or "").split("\n"):
            head = re.match(r"\s*(p\d+[a-z0-9:]*)\s*:\s*(.*)", line, re.I)
            if not head:
                continue
            text = head.group(2).lower()
            types = {t for t in TYPES if _names_type(text, t)}
            types |= {t for t in MECHANICS if _granted(text, t)}
            out[(ref, head.group(1).lower())] = types
    return out


def _cards() -> dict[str, tuple[set[str], bool]]:
    """What bonus types each row's printed text names, and whether it also
    prints a bonus with no type word at all."""
    sys.argv = sys.argv[:1]
    from combat_engine.db import game

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
