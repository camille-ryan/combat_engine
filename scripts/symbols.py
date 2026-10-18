#!/usr/bin/env python
"""The authoring vocabulary, sorted into categories and written to docs/.

    uv run scripts/symbols.py              verify the committed files
    uv run scripts/symbols.py --write      regenerate them
    uv run scripts/symbols.py --quiet      one line, for `check.py`

`vocab.py` answers "does this exist" by searching docstrings. This answers the
question before it: **"what are my options for this kind of thing"** -- and it
answers it as one small committed file per category, so somebody who knows
they need a movement verb reads 30 lines instead of 392 members.

## Why this is generated and gated rather than written

`Cast` has 392 public members over 12,000 lines. `vocab.py`'s nine `GROUPS`
prefixes matched 80 of them and the other ~274 fell through to a flat
alphabetical "everything else" dump -- which is exactly where the expensive
mistake lives. `vocab.py`'s own `_context` note records the cost:

    the document every author is told to grep before marking a row quietly
    became a third of itself. Six verbs that exist were marked missing by
    four different agents in one afternoon.

A hand-written hierarchy would answer that for a fortnight. So this one is
generated from `Cast` and **gated three ways**, the middle one being the
point:

* a committed file that no longer matches what the code generates is red;
* **a member in no category is red**, so growing `Cast` without placing the
  new verb fails the suite. That is what keeps the taxonomy honest, and it is
  the whole reason this is a check and not a document;
* a category file on disk that the taxonomy no longer names is red.

Same `record`/`verify` shape as `replay.py`, for the same reason: a tracked
artifact nobody verifies is a document that is wrong by the second week.

## What the categories are not

**They are not a model of the rules.** They are where a person looks. Several
members could sit in two of them and the split was made by "what would
somebody with this card in hand search for", not by taxonomy -- `c.conceal`
is under `modifiers` because its whole effect is -2 to attacks, even though
concealment is a state. Arguing the edges is cheaper than the flat list.

**Two levels, and only where the split changes what you write.** `movement`
separates voluntary from forced because the squares are read off a different
creature in each. `conditions` separates writers from readers because ten
condition names are writers, two are readers and one of those is a property.
Nothing else is nested, because nothing else has a split the code insists on.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DOCS = ROOT / "docs" / "symbols"

#: One entry per file. `title` heads the page, `blurb` says what belongs here
#: so the next person placing a verb has a rule to follow, and `sections` is
#: an ordered list of `(heading, [member names])`. A heading of `""` prints no
#: sub-heading, which is the ordinary case.
CATEGORIES: dict[str, dict] = {
    "attacking": {
        "title": "Attacking",
        "blurb": "Making an attack, and what the attack turns out to be.",
        "sections": [
            ("", [
                "add_target", "also_hits", "as_basic", "as_implement",
                "as_ranged", "as_though_hit_by", "as_weapon", "attack",
                "attack_with", "attacks_defence", "autohit", "basic",
                "cast_from", "coup_de_grace", "crit", "disarm",
                "flurry_of_blows", "grant_attack", "hit", "landed",
                "provoke", "redirect", "retarget_defence", "strike",
                "target",
            ]),
            ("aiding somebody else's", [
                "aid_another", "aid_attack", "aid_defence",
            ]),
        ],
    },
    "damage": {
        "title": "Damage and healing",
        "blurb": "Points off and points back on, and the dice behind them.",
        "sections": [
            ("dealing it", [
                "absorb", "apply_poison", "b", "burns", "cushion", "damage",
                "deals", "flat", "half_damage", "halve", "maximise",
                "no_miss_damage", "ongoing", "quarry_damage", "reduce",
                "sneak_damage", "w",
            ]),
            ("undoing it", [
                "half_healing", "heal", "regen_suppressed",
                "regeneration", "resume_regeneration", "temp_hp",
            ]),
        ],
    },
    "movement": {
        "title": "Movement",
        "blurb": (
            "Verbs that move a creature. The **mode** it travels in -- fly, "
            "swim, burrow -- is not a verb; see the modes section."
        ),
        "sections": [
            # **`c.shifted` was in here, beside `c.shift`, and means
            # shapechanged** -- "Has the creature taken a shape that is not
            # its own?". It is the reader for `c.form`, which is in
            # `effects`, so the writer and its reader were two files apart
            # while the reader sat under a verb it has nothing to do with.
            # The worst false friend found while placing all 397, because
            # `c.shift` is on the line above and `if c.shifted():` after a
            # shift reads exactly right. #592 is the same shape on `c.held`.
            #
            # `c.hide`/`c.unhide` went to `modifiers` for a duller reason:
            # both docstrings are about being seen, not about moving.
            ("voluntary -- the creature spends its own movement", [
                "charge", "charge_at", "flee", "hover", "jump", "move",
                "moving_as", "overrun", "ride", "rise", "run_at", "shift",
                "shift_as", "teleport", "walk_toward",
            ]),
            ("forced -- somebody else moves it", [
                "bull_rush", "pull", "push", "slide",
            ]),
            # Neither voluntary nor forced by a creature, so it had no honest
            # home in either. `falling.AIRBORNE` in the modes section below
            # is what decides whether a mode falls at all.
            ("falling", [
                "fall",
            ]),
            ("how far, and what stops it", [
                "any_size_manoeuvre", "blocks_entry", "extend_every",
                "extend_move", "forces", "ignores_difficult",
                "ignores_difficult_in", "immovable", "no_walk", "phasing",
                "may_enter", "resist_forced", "shares_space",
                "speed_of", "squares_for",
            ]),
            ("modes and mounts", [
                "lose_mode", "mode", "mount", "move_companion",
            ]),
        ],
    },
    "conditions": {
        "title": "Conditions, saves and dying",
        "blurb": (
            "The 24 `Condition` members and the states next to them. Every "
            "writer takes a duration from `When`."
        ),
        "sections": [
            ("writers -- a condition named after itself", [
                "blinded", "cannot_shift", "dazed", "immobilized",
                "insubstantial", "prone", "slowed", "stunned", "unconscious",
                "weakened",
            ]),
            ("writers -- a condition under another name, or the generic", [
                "bind", "command", "condition", "control", "dominate", "grab",
                "grab_attempt", "latch", "leash", "link", "mark", "unlatch",
                "worsen",
            ]),
            ("readers", [
                "dying", "grabbed_by", "grabbing", "latched", "marked",
                "suffering",
            ]),
            ("getting out, and not getting out", [
                "cure", "escape", "immune", "ignore_condition", "save",
                "unsave",
            ]),
            ("dying and after", [
                "decay", "destroy", "kill", "reanimate", "revives_unless",
            ]),
            ("riders that behave like conditions", [
                "curse", "cursed", "rattled", "rattling", "shroud", "shrouds",
            ]),
            # Its own track, not a condition and not a modifier: a disease
            # has stages and a saving throw at the end of the encounter
            # rather than a duration from `When`. Filed under cover and
            # concealment in `modifiers` until the cross-references printed
            # the docstring next to the heading.
            ("disease", [
                "expose", "exposed",
            ]),
        ],
    },
    "effects": {
        "title": "Effects, zones and watchers",
        "blurb": (
            "Things that persist on the board or on a creature, and the "
            "windows that fire while they last."
        ),
        "sections": [
            ("laid on the board", [
                "area", "aura", "barrier", "conjure", "douse", "hazard",
                "light", "line", "move_zone", "origin", "resize_aura",
                # Beside `resize_aura` because it is the same question about
                # another row's area: that one changes a size, this one
                # changes the shape. #614.
                "reshape_area",
                "floor", "scenery", "set_origin", "terraform", "terrain",
                "unlit",
                "wall", "zone",
            ]),
            # `shifted` is the third reader of the shape mechanism and was
            # in `movement`, under `shift`. It has nothing to do with
            # shifting. See the note in `movement`'s sections.
            ("laid on a creature", [
                "effect", "form", "in_form", "merge", "shifted", "stance",
                "transfer",
            ]),
            ("summoning and companions", [
                "beast_independent", "call_beast", "call_companion",
                "dismiss_companion", "summon", "summon_inline",
            ]),
            ("size", ["contract", "grow", "resize"]),
            ("ending, suspending, watching", [
                "aftereffect", "arm_trigger", "cancel", "dispel", "end_effect",
                "endable", "lingers_label", "on_attack", "on_sustain",
                "suspend_when", "watch",
            ]),
        ],
    },
    "modifiers": {
        "title": "Modifiers and refusals",
        "blurb": (
            "Numbers added to or taken off a roll, and permissions withdrawn. "
            "A modifier nothing reads is this component's commonest bug -- if "
            "you add a key, add its reader in the same commit."
        ),
        "sections": [
            ("the numbers", [
                "amount_for", "attack_mod", "bonus", "boost_check",
                "boost_roll", "change_amount", "change_dice", "dice_for",
                "enhancement", "grants_in", "penalty", "rolls_with",
                "shield_bonus", "treat_roll_as", "widen_areas",
            ]),
            ("rerolls", [
                "reroll_attack", "reroll_check", "reroll_damage",
                "reroll_initiative", "reroll_ones", "reroll_save",
            ]),
            ("resistance and vulnerability", [
                "ignore_resistance", "resist", "resist_in", "resistances",
                "vulnerabilities", "vulnerable", "vulnerable_in",
            ]),
            # **`expose`/`exposed` were in here and are about disease**, which
            # is how the cross-reference work found them: writing "look in
            # modifiers for combat advantage" printed `c.exposed` beside
            # "Has this creature caught a disease", under a heading saying
            # cover and concealment. They are in `conditions` now. The other
            # eleven were read one by one and every one is genuinely about
            # advantage, cover or concealment.
            ("advantage, cover and concealment", [
                "conceal", "conceal_in", "cover", "cover_in",
                "damage_disadvantage",
                "gains_advantage", "grants_advantage", "had_advantage",
                "hide", "ignore_cover", "ignores_long_range", "invisible",
                "no_advantage", "no_cover", "unhide",
            ]),
            # Not cover either: a relation between two creatures, where one
            # is answering for the other. Beside cover only because both end
            # up changing what an attack does.
            ("taking another creature under protection", [
                "guard", "guarding", "is_guarded",
            ]),
            ("refusals", [
                "cannot_attack", "cannot_be_flanked", "counts_as",
                "counts_as_keyword", "forbid", "gains_property", "no_basic",
                "no_healing", "no_provoke", "no_surges", "waive",
            ]),
        ],
    },
    "asking": {
        "title": "Asking the board and the caster",
        "blurb": (
            "Readers. None of these change anything, so a row whose whole "
            "body is one of them does nothing."
        ),
        "sections": [
            # **`c.fallen` belongs beside `c.within` and not under a
            # category of its own**, which is the point of putting it here:
            # it is the one reader in this section that answers about the
            # dead, and three rows were marked unwritable because the
            # author looked at the live finders, found them all ending in
            # `alive(...)`, and concluded the board could not name a
            # corpse. A reader nobody can find is the failure this file
            # exists to stop.
            #
            # `c.level_of` is here rather than under "the caster's own
            # numbers" because it reads *somebody else's* level, which is
            # the same split `c.size_of` already sits on -- `c.level` is
            # the caster's and is in that section.
            ("who and where", [
                "adjacent", "adjacent_to", "allies", "beast", "can_flank",
                "can_see", "carrying", "companion", "companions",
                "conjurations", "distance", "enemies", "fallen", "familiar",
                "familiar_active", "familiar_mode", "first", "height",
                "held", "here",
                "in_my_aura", "in_squares", "last", "level_of", "living",
                "master", "my_aura", "my_weapon", "my_zones", "servants",
                "size_of", "there", "threatens", "within",
            ]),
            ("the caster's own numbers", [
                "ability_for", "b_mod", "cha_", "cha_mod", "con_", "con_mod",
                "dex_", "dex_mod", "int_", "int_mod", "level", "mod",
                "primary", "primary_mod", "score", "stats", "str_", "str_mod",
                "total", "total_defence", "weapon_dice", "weapon_of",
                "weapon_range", "wielding", "wis_", "wis_mod",
            ]),
            ("state and identity", [
                "bloodied", "build", "element", "feat", "granted_by",
                "granted_via", "healed_by", "index", "instinctive", "is_",
                "is_hidden", "is_kind", "is_minion", "is_quarry", "is_trap",
                "keywords_of", "kinds_of", "knows", "made_by", "missing",
                "passive", "quarry", "race_of", "reach", "result", "turn_of",
                "wounded",
            ]),
            ("senses", [
                "blindsight", "darkvision", "has_sense", "low_light",
                "see_invisible", "see_unseen", "sight_range", "tremorsense",
                "truesight",
            ]),
            ("what the call already knows -- state, not calls", [
                "declared_feats", "me", "ref", "targets", "world",
            ]),
            ("rolling and the trigger", [
                "ability_check", "check", "opportunity", "ranged", "roll",
                "struck_by", "struck_by_property", "struck_with", "trigger",
            ]),
        ],
    },
    "resources": {
        "title": "Resources, actions and turns",
        "blurb": "Things a creature spends, and the budget it spends them from.",
        "sections": [
            ("surges and hit points", [
                "regain_surge", "second_wind", "spend_surge",
                "surge", "surge_value",
            ]),
            ("power points and augments", [
                "augment", "augmented", "lend_augment", "points",
                "points_spent", "regain_points", "spend_points",
                "spend_shrouds", "transfer_points",
            ]),
            ("charges and per-day uses", [
                "ammunition", "charge_left", "per_day_left", "restore_charge",
                "restore_use", "spend_charge", "spend_per_day",
            ]),
            ("actions and turns", [
                "action_point", "action_points", "end_turn", "extra_action",
                "extra_turn", "grant_action", "grant_action_point",
                "initiative", "payment_window", "swap_initiative",
            ]),
            ("cards and carried things", [
                "draw", "draws_free", "give", "stow",
            ]),
        ],
    },
    "rows": {
        "title": "Other rows, and choices",
        "blurb": (
            "Handing a row over, taking one away, replacing a clause, and "
            "asking somebody to pick."
        ),
        "sections": [
            ("granting and spending a row", [
                "borrow_row", "borrowed_rows", "expend_row", "expended",
                "grant_row", "recast", "spellbook", "use_power", "used",
            ]),
            ("changing what a row does", [
                "branch", "instead_of", "instead_of_now", "pass_on",
                "pre_empt", "prepare", "rider", "substitutions", "swap",
                "variant",
            ]),
            ("asking", ["choose", "declare", "may", "note"]),
        ],
    },
    "gates": {
        "title": "Gates -- the `when=` context",
        "blurb": (
            "Almost every modifier takes `when=lambda ctx: ...`. This is the "
            "whole vocabulary a gate may read."
        ),
        "sections": [],
    },
}

#: Every key a `when=` gate may read, and where it comes from.
#:
#: **A ctx is a plain dict, so an unknown key is not an error** -- the gate
#: is just never true, the row lays its effect, and `audit` credits it with
#: having done something. That is the "silently false" shape the engine
#: component file names, and `m5788a0` is the live case: its whole card is
#: "ignores all other effects" of a Will attack, it reads `ctx["vs"]`, and
#: nothing writes that key, so the immunity has never applied once (#591).
#:
#: So this is a **deny-by-default list**, the discipline `c.bonus(once=)`
#: already uses after five keys were silently mis-spent. Adding a key here
#: is one line; mis-spelling one in a row is a failure.
#:
#: Only the read direction is gated. The engine writes ~147 dict keys and
#: most of those dicts are not ctxs, so gating "written but unlisted" would
#: be noise -- and it is the read that goes wrong.
CTX_KEYS: dict[str, str] = {
    "ability": "which ability scored the roll.",
    "action_point": "was an action point spent on this.",
    "actor": "whoever is acting, on a ctx built from a non-attack event.",
    "advantage": "did the attack have combat advantage.",
    "ammo": "the ammunition used.",
    "among": "the set a choice was made from.",
    "as_": "the action it is being taken as.",
    "attacker": "who is swinging. `target` is who it lands on.",
    "branch": "which half of a melee-or-ranged row is in use.",
    "charge": "is this use a charge.",
    "conditions": "the conditions in play for this read.",
    "crit": "was it a critical hit.",
    "dtype": "the damage type of this blow.",
    "dtypes": "every type of a blow that is several at once.",
    "effect": "the effect being asked about.",
    "from_attack": "did this come out of an attack.",
    "granted_by": "who handed this creature the attack, or -1.",
    "granted_via": "the ref of the row that handed it over.",
    "hand": "which hand the weapon is in.",
    "how": "the kind of forced movement -- push, pull, slide.",
    "keywords": "the keywords of the row or effect being asked about.",
    "kind": "the kind of action or roll. See `Cast.does_not_provoke`.",
    "label": "the label of the effect being asked about.",
    "mode": "the movement mode in use.",
    "mover": "who is trying to enter a square. `movement.may_enter`.",
    "occupant": "who is standing in it. The other half of `mover`.",
    "ongoing": "is this ongoing damage rather than a blow.",
    "opportunity": "is this an opportunity attack.",
    "power": "the ref of the row doing this. The commonest gate.",
    "ranged": "was it a ranged attack.",
    "reach": "the shape of the attack -- `Range.kind` verbatim.",
    "reroll_by": "the ref of whatever asked for the reroll.",
    "skill": "the skill being checked, lowercased.",
    "source": "who laid the effect.",
    "target": "who it lands on. The commonest key in the tree.",
    "why": "the reason recorded for this.",
}

#: Gates reading a key that is not in `CTX_KEYS`, named with the issue that
#: covers each. **A stale entry is a failure**, the discipline `DEFERRED` and
#: `todo.py` both apply: if the row is fixed, the entry is dead weight.
#:
#: These are not waivers. Each one is a row that does nothing, left named
#: rather than quietly fixed because the repair is a judgement about the row
#: and this is a lookup change.
#: **Empty, and that is the point.** It held one entry for the whole of its
#: life -- `m5788a0`'s immunity, gated on a key nothing writes, so the
#: immunity never applied once. #591 is closed: the row asks the power the
#: context *does* name, and the staleness check below is what made the
#: allowance expire rather than outlive the repair.
KNOWN_DEAD: dict[tuple[str, str], str] = {}

#: Vocabularies that are not `Cast` members but that a row reaches for in the
#: same breath, printed at the foot of the category they belong to.
ENUMS = {
    "conditions": [("Condition", "combat_engine.engine.types"),
                   ("When", "combat_engine.engine.durations")],
    "damage": [("DamageType", "combat_engine.engine.types")],
    "attacking": [("Defense", "combat_engine.engine.types")],
}


#: **The other half of what a row calls, and it was not here.**
#:
#: `CATEGORIES` above covers `Cast` -- every verb a body invokes. It covers
#: nothing else, and `query.py` is the second half: 75 public functions, 432
#: content files importing from it, 51 distinct names imported. An author
#: asking "does a reader for this exist" got a complete answer for `Cast`
#: and no answer at all for the readers.
#:
#: That cost three families in one session (#648):
#:
#: * `f1296` was marked *"nothing asks what cover a creature has"*;
#:   `query.cover_between` had been that reader the whole time, and the
#:   symbol it shared stood over five rows wanting two opposite things.
#: * `query.moved_this_turn` was filed as a missing reader when
#:   `query.since_turn_began` already bounds exactly that window -- and that
#:   function's own docstring says 21 content helpers were consolidated into
#:   it, so the facility was not merely present but advertised.
#: * `c.save_order()`'s keyword halves were already writable off the context
#:   `Durations.save` builds, and nothing said so.
#:
#: Same shape as `CATEGORIES`, rendered as `query.name(...)` rather than
#: `c.name(...)`, and under the same two gates: a function in no section
#: fails the check, and a section naming a function `query.py` no longer has
#: fails it too.
READERS: dict[str, list[str]] = {
    "who, and whose side": [
        "active", "alive", "allies", "combatants", "conscious", "creatures",
        "enemies", "is_", "is_conjuration", "is_trap", "kinds_of",
        "level_term", "living", "printed_kinds", "race_of", "scenery",
        "stat_block", "targetable", "team",
    ],
    "where, and how far": [
        "adjacent", "distance_between", "leash_of", "line_of_effect",
        "moving_as", "on_the_ground", "prefers_range", "range_profile",
        "sealed", "speed", "squares",
    ],
    "seeing and being seen": [
        "blinded", "concealment_of", "cover_between", "cover_granters",
        "cover_waived", "has_sense", "hidden_from", "light_concealment",
        "light_level", "sees_in", "sees_invisible", "sees_through",
        "sheltered_from", "sight_capped", "unseen_by",
    ],
    "attacking and defending": [
        "attack_penalty", "can_flank", "deals_half", "defence", "flanked_by",
        "flankers", "grants_ca", "has_combat_advantage", "shield_bonus",
        "takes_half",
    ],
    "what a creature may do": [
        "can_act", "can_move", "can_react", "can_shift", "can_walk",
        "granted_actions", "held_by", "holding", "holds_somebody",
        "immune_to",
    ],
    "what has already happened": [
        "hit_me_this_turn", "in_form", "granted_amount", "lingers",
        "my_hits_this_turn", "my_misses_this_turn", "shifted",
        "since_turn_began", "surge_value", "taking_ongoing",
    ],
    "the companion": [
        "acting_independently", "familiar_active", "familiar_echoes",
        "familiar_of",
    ],
}

READING_BLURB = (
    "Readers in `combat_engine.engine.query`, which is the other half of "
    "what a row calls. Nothing here changes anything.\n\n"
    "**Check here before marking a row.** Three families in one session "
    "were marked as engine gaps when the reader already existed -- see "
    "#648. `since_turn_began` in particular bounds \"this creature's own "
    "turn so far\" and 21 content files had hand-rolled it."
)


def _readers() -> dict[str, Callable[..., object]]:
    """Every public function in `query.py`, by name.

    `o.__module__` is the filter that matters: `query.py` imports plenty of
    functions from its siblings, and re-exporting `movement.shares_space`
    here would claim it as a reader this document governs when
    `movement.py` owns it. Only what is defined in `query.py` is listed.
    """
    from combat_engine.engine import query as q

    # Typed `Callable`, not `object`. `_shape`'s note records `types.py`
    # being right to fail an `inspect.signature` call on an `object`, and
    # this function hit the same wall -- but here the answer is the honest
    # type rather than a `callable()` guard, because `isfunction` below has
    # already established it.
    # **A cached reader is not `inspect.isfunction`.**
    # `functools.lru_cache` returns a `_lru_cache_wrapper`, so
    # `query.printed_kinds` was invisible to this walk -- and therefore to
    # *both* gates below it, the orphan one and the stale one. It arrived
    # documented, was rendered nowhere, and `check.py` stayed green. The
    # gates were right; this function was not showing them the reader.
    out: dict[str, Callable[..., object]] = {}
    for n, o in vars(q).items():
        if n.startswith("_"):
            continue
        fn = inspect.unwrap(o) if hasattr(o, "__wrapped__") else o
        if inspect.isfunction(fn) and fn.__module__ == "combat_engine.engine.query":
            # The wrapper, not the unwrapped function: the signature a row
            # calls is the wrapper's, and `functools.wraps` makes the two
            # agree anyway.
            out[n] = o
    return out


def _render_reading(readers: dict[str, Callable[..., object]]) -> str:
    out = ["# Reading the board", "", READING_BLURB, ""]
    out += [
        "> Generated by `scripts/symbols.py`. Do not edit: `check.py` fails",
        "> when a committed file and the code disagree. `--write` rewrites it.",
        "",
    ]
    for heading, names in READERS.items():
        present = [n for n in names if n in readers]
        if not present:
            continue
        out += [f"## {heading}", ""]
        for name in sorted(present):
            fn = readers[name]
            try:
                sig = str(inspect.signature(fn))
            except (TypeError, ValueError):
                sig = "(...)"
            out.append(f"- `query.{name}{sig}`")
            out.append(f"  - {_one_line(fn)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _members() -> dict[str, object]:
    """Every public member of `Cast`, by name.

    **Three kinds, and they must not be rendered alike.** `Cast` is a
    dataclass, so a field's *default value* sits in `vars(Cast)` beside the
    methods -- `charge: bool = False` arrives here as the bool `False`. The
    first draft of this file ran `inspect.getdoc` over that and published
    "c.charge -- Returns True when the argument is true", which is Python's
    docstring for `bool` and is worse than saying nothing.

    So fields are detected from `dataclasses.fields` and described from
    `vocab.CONTEXT`, which already documents them and is already guarded:
    `vocab._context` complains when `Cast` grows a field that `CONTEXT` does
    not name. The five fields with no default never appear in `vars` at all,
    which is the other half of why this cannot just read `vars`.
    """
    import dataclasses

    from combat_engine.engine.cast import Cast

    out: dict[str, object] = {
        n: m for n, m in vars(Cast).items() if not n.startswith("_")
    }
    for field in dataclasses.fields(Cast):
        if not field.name.startswith("_"):
            out[field.name] = _Field(field.name, field.type)
    return out


class _Field:
    """A dataclass field on `Cast`: state a body reads, never calls."""

    def __init__(self, name: str, annotation: object) -> None:
        self.name = name
        self.annotation = annotation


def _one_line(member: object) -> str:
    """The first line of a docstring, or a field's own description."""
    if isinstance(member, _Field):
        from vocab import CONTEXT

        return CONTEXT.get(member.name, "(not described in vocab.CONTEXT)")
    doc = inspect.getdoc(member) or ""
    first = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
    return first or "(no docstring)"


def _shape(name: str, member: object) -> str:
    """`c.name(signature)` for a verb; the bare name for state.

    A reader has to be able to tell at a glance whether to call it, so a
    field is printed with its type and a property without parentheses.
    """
    if isinstance(member, _Field):
        return f"c.{name}: {member.annotation}"
    if isinstance(member, property):
        return f"c.{name}"
    # `callable` rather than a bare `try`, which `types.py` was right to
    # fail: `member` is `object` here, and `inspect.signature` wants
    # something callable. The `except` stays for a callable with no
    # readable signature -- a builtin, or a C slot wrapper.
    if not callable(member):
        return f"c.{name}"
    try:
        return f"c.{name}{inspect.signature(member)}"
    except (TypeError, ValueError):
        return f"c.{name}"


def _render(slug: str, spec: dict, members: dict[str, object]) -> str:
    out = [f"# {spec['title']}", "", spec["blurb"], ""]
    out += [
        "> Generated by `scripts/symbols.py`. Do not edit: `check.py` fails",
        "> when a committed file and the code disagree. `--write` rewrites it.",
        "",
    ]
    for heading, names in spec["sections"]:
        present = [n for n in names if n in members]
        if not present:
            continue
        if heading:
            out += [f"## {heading}", ""]
        for name in sorted(present):
            out.append(f"- `{_shape(name, members[name])}`")
            out.append(f"  - {_one_line(members[name])}")
        out.append("")
    for enum_name, module in ENUMS.get(slug, []):
        mod = __import__(module, fromlist=[enum_name])
        enum = getattr(mod, enum_name)
        out += [f"## `{enum_name}` ({len(list(enum))} members)", ""]
        out.append("  " + ", ".join(f"`{m.value}`" for m in enum))
        out.append("")
    out += EXTRA.get(slug, lambda: [])()
    out += _elsewhere(slug, members)
    return "\n".join(out).rstrip() + "\n"


#: **The near-misses, because getting the category right is not enough.**
#: Two of the four verbs this whole document was built to make findable
#: landed in a file the plan predicted wrong -- `c.grants_advantage` in
#: `modifiers` where Camille's own sketch puts combat advantage under
#: *conditions*, and `c.reroll_ones` in `modifiers` where an author writing
#: a damage clause looks in *attacking*.
#:
#: Moving either is the wrong fix: `grants_advantage` sits with
#: `gains_advantage`, `had_advantage` and `no_advantage`, which belong
#: together, and splitting that cluster trades one wrong guess for four. So
#: the first guess is made to cost **one line instead of a filed gap**.
#:
#: Keyed by the file an author *opens*; each entry is the verb and the file
#: it is really in. `main()` fails if a name here is not on `Cast` or is not
#: in the category it claims, so a later recategorisation turns this red
#: rather than leaving a pointer into nowhere.
SEE_ALSO: dict[str, list[tuple[str, str]]] = {
    "conditions": [
        ("grants_advantage", "modifiers"),
        ("gains_advantage", "modifiers"),
        ("invisible", "modifiers"),
        ("curse", "conditions"),
    ],
    "attacking": [
        ("reroll_ones", "modifiers"),
        ("reroll_attack", "modifiers"),
        ("reroll_damage", "modifiers"),
        ("ignore_resistance", "modifiers"),
        ("resist", "modifiers"),
        ("vulnerable", "modifiers"),
        ("attack_mod", "modifiers"),
    ],
    "movement": [
        ("extend_every", "movement"),
        ("cannot_shift", "conditions"),
        ("immobilized", "conditions"),
        ("slowed", "conditions"),
        # The pointer exists to say "this is not what you think": an author
        # who has just written `c.shift` and wants to ask whether it
        # happened will look here, and `c.shifted` is about shapechanging.
        ("shifted", "effects"),
        ("hide", "modifiers"),
    ],
    "damage": [
        ("reroll_damage", "modifiers"),
        ("reroll_ones", "modifiers"),
        ("change_dice", "modifiers"),
        ("resist", "modifiers"),
        ("vulnerable", "modifiers"),
    ],
    "modifiers": [
        ("save", "conditions"),
        ("immune", "conditions"),
        ("ignore_condition", "conditions"),
    ],
}


def _elsewhere(slug: str, members: dict[str, object]) -> list[str]:
    """"You probably meant one of these, and it is in another file."""
    here = _placed_in(slug)
    # `members` rather than `here` decides what is printed: a pointer at a
    # verb `Cast` does not have is `main`'s failure to report, not a
    # `KeyError` here. `knock_prone` was exactly that -- invented while
    # writing the list, and the first run died rendering it instead of
    # naming it.
    away = [(n, f) for n, f in SEE_ALSO.get(slug, [])
            if n not in here and n in members]
    if not away:
        return []
    out = ["## not here -- look in another file", ""]
    for name, where in sorted(away):
        out.append(f"- `c.{name}` is in [`{where}.md`]({where}.md)"
                   f" -- {_one_line(members[name])}")
    out.append("")
    return out


def _modes() -> list[str]:
    """The movement **modes**, which are strings and not verbs.

    The distinction this section exists for: there is no `c.fly`. A mode is
    a key in `Speed.modes` with its own speed -- `{"fly": 8, "climb": 3}` --
    granted by `c.mode(name, speed)` and travelled with `c.move(at="fly")`.
    Read off the constants so the list cannot drift from the code that
    decides what falling and difficult terrain do about each one.
    """
    from combat_engine.engine.falling import AIRBORNE
    from combat_engine.engine.movement import OVERHEAD

    every = sorted(set(AIRBORNE) | set(OVERHEAD))
    return [
        "## movement modes -- strings, not verbs",
        "",
        "There is no `c.fly`. A mode is a key in `Speed.modes` with its own",
        "speed, granted by `c.mode(name, speed)` and travelled with",
        "`c.move(at=...)`. `c.moving_as(mode)` asks which one is in use.",
        "",
        "  " + ", ".join(f"`{m}`" for m in every),
        "",
        "- **leaves the ground, so it passes over whoever is standing in",
        "  the way** (`movement.OVERHEAD`): "
        + ", ".join(f"`{m}`" for m in sorted(OVERHEAD))
        + ". Teleport is not one of these -- it has no path to pass along,",
        "  so it has to arrive somewhere it fits.",
        "- **does not fall** (`falling.AIRBORNE`): "
        + ", ".join(f"`{m}`" for m in sorted(AIRBORNE))
        + ". Climbing counts: a creature on a wall is holding on, which is",
        "  the state an arrested fall leaves it in.",
        "",
        "The two sets are **not** nested and neither is 'airborne' in the",
        "English sense -- `burrow` leaves the ground and still falls;",
        "`climb` does not leave it and does not fall.",
        "",
    ]


def _ctx_keys() -> list[str]:
    """The `when=` context keys, and where each is written."""
    out = [
        "## `when=` context keys",
        "",
        "A gate is `when=lambda ctx: ...`. The ctx is a plain dict, so a key",
        "that is not written is not an error -- the gate is simply never",
        "true, and the row lays its effect and does nothing. `m5788a0` reads",
        "`ctx[\"vs\"]`, which nothing writes, so its immunity has never",
        "applied (#591). `symbols.py` refuses a key that is not listed here.",
        "",
    ]
    for key, note in sorted(CTX_KEYS.items()):
        out.append(f"- `ctx[{key!r}]` -- {note}")
    out.append("")
    return out


EXTRA = {"movement": _modes, "gates": _ctx_keys}


def _without_prose(text: str) -> str:
    """The same text with docstrings and comments blanked, length preserved.

    **A row that explains a retired key kept its own allowance alive.**
    `_gate_reads` is a text scan, so a docstring describing a dead gate
    counted as a live read of the key it named -- which meant
    `KNOWN_DEAD`'s staleness check could never fire for the one row it was
    written for. The repair landed and the entry stayed, reporting a dead
    gate that was no longer there.

    Same family as `leaks.py`'s quoted-position problem, and the same
    lesson: a check that reads prose as code is measuring the wrong file.

    Lengths are preserved -- blanks for the removed span rather than a
    deletion -- because the caller finds the owning `@power` by comparing
    offsets, and shifting them would mis-attribute every gate after the
    first docstring.
    """
    import re as _re

    def blank(m: _re.Match[str]) -> str:
        return "".join(ch if ch == "\n" else " " for ch in m.group(0))

    # Triple-quoted strings first, then line comments in what is left, so a
    # hash inside a docstring is already gone and a triple quote inside a
    # comment cannot open one.
    for quote in ('"' * 3, "'" * 3):
        text = _re.sub(f"(?s){quote}.*?{quote}", blank, text)
    return _re.sub(r"(?m)#[^\n]*", blank, text)


def _gate_reads() -> list[tuple[str, str, str]]:
    """Every `ctx.get("…")` in `content/`, as (ref, key, file).

    The ref is the nearest `@power("…")` above the gate, which is what makes
    a failure actionable: the author needs the row, not the line.
    """
    import re

    out: list[tuple[str, str, str]] = []
    decorator = re.compile(r'@power\(\s*\n?\s*"([A-Za-z0-9_:+-]+)"')
    getter = re.compile(r'ctx\.get\(\s*"([a-z_]+)"')
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        text = _without_prose(path.read_text(errors="replace"))
        marks = [(m.start(), m.group(1)) for m in decorator.finditer(text)]
        for hit in getter.finditer(text):
            owner = ""
            for at, ref in marks:
                if at < hit.start():
                    owner = ref
                else:
                    break
            rel = path.relative_to(ROOT).as_posix()
            out.append((owner, hit.group(1), rel))
    return out


def _placed() -> dict[str, str]:
    """name -> category, and a complaint if two categories claim one name."""
    seen: dict[str, str] = {}
    for slug, spec in CATEGORIES.items():
        for _heading, names in spec["sections"]:
            for name in names:
                if name in seen:
                    raise SystemExit(
                        f"{name!r} is in both {seen[name]!r} and {slug!r};"
                        f" a member belongs to exactly one category"
                    )
                seen[name] = slug
    return seen


def _placed_in(slug: str) -> set[str]:
    """Every name one category claims. `{}` for a category that is gone."""
    spec = CATEGORIES.get(slug)
    if spec is None:
        return set()
    return {n for _heading, names in spec["sections"] for n in names}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="rewrite docs/symbols")
    ap.add_argument("--quiet", action="store_true", help="one line of summary")
    args = ap.parse_args()

    members = _members()
    placed = _placed()
    readers = _readers()
    reader_placed = {n for names in READERS.values() for n in names}

    # The same two gates the `Cast` side has, for the same reason: a reader
    # nobody can find is a reader somebody files a gap for, and three
    # families in one session proved it. #648.
    reader_orphans = sorted(set(readers) - reader_placed)
    reader_stale = sorted(reader_placed - set(readers))

    # A member in no category, which is the failure that keeps this current.
    orphans = sorted(set(members) - set(placed))
    # A name in the taxonomy that `Cast` no longer has.
    stale = sorted(set(placed) - set(members))

    # A gate reading a key no ctx carries. Named rows are allowed through and
    # a named row that stops reading it is itself a failure.
    unknown = [(ref, key, where) for ref, key, where in _gate_reads()
               if key not in CTX_KEYS and (ref, key) not in KNOWN_DEAD]
    still_dead = {(ref, key) for ref, key, _w in _gate_reads()}
    cured = sorted(k for k in KNOWN_DEAD if k not in still_dead)

    # A cross-reference pointing at a verb that moved, or was never there.
    # Without this the pointers are the one hand-written part of the document
    # and would be the one part that goes stale.
    misdirected: list[str] = []
    for slug, pairs in SEE_ALSO.items():
        for name, where in pairs:
            if name not in members:
                misdirected.append(
                    f"{slug}.md points at `c.{name}`, which Cast does not have")
            elif name not in _placed_in(where):
                real = [s for s in CATEGORIES if name in _placed_in(s)]
                misdirected.append(
                    f"{slug}.md sends `c.{name}` to {where}.md; it is in "
                    f"{', '.join(f'{s}.md' for s in real) or 'no category'}")

    want = {slug: _render(slug, spec, members)
            for slug, spec in CATEGORIES.items()}
    want["reading"] = _render_reading(readers)

    if args.write:
        DOCS.mkdir(parents=True, exist_ok=True)
        for slug, text in want.items():
            (DOCS / f"{slug}.md").write_text(text)
        for path in DOCS.glob("*.md"):
            if path.stem not in want:
                path.unlink()
        print(f"wrote {len(want)} files to {DOCS.relative_to(ROOT)}")
        if orphans:
            print(f"\n{len(orphans)} member(s) in NO category -- place them:")
            for name in orphans:
                print(f"  c.{name:28} {_one_line(members[name])[:60]}")
            return 1
        if reader_orphans:
            print(f"\n{len(reader_orphans)} query reader(s) in NO section:")
            for name in reader_orphans:
                print(f"  query.{name:24} {_one_line(readers[name])[:60]}")
            return 1
        return 0

    bad: list[str] = []
    for slug, text in want.items():
        path = DOCS / f"{slug}.md"
        if not path.exists():
            bad.append(f"{path.relative_to(ROOT)} is missing")
        elif path.read_text() != text:
            bad.append(f"{path.relative_to(ROOT)} is out of date")
    for path in sorted(DOCS.glob("*.md")) if DOCS.exists() else []:
        if path.stem not in want:
            bad.append(f"{path.relative_to(ROOT)} is for no category")

    if orphans:
        print(f"{len(orphans)} member(s) of Cast are in no category:")
        for name in orphans:
            print(f"  c.{name:28} {_one_line(members[name])[:60]}")
        print("\nPlace each one in `CATEGORIES`, then `--write`. A verb nobody"
              "\ncan find is a verb somebody files a gap for.")
        return 1
    if stale:
        print(f"{len(stale)} name(s) in the taxonomy are not on Cast: "
              f"{', '.join(stale)}")
        return 1
    if reader_orphans:
        print(f"{len(reader_orphans)} function(s) in query.py are in no "
              f"section of `reading.md`:")
        for name in reader_orphans:
            print(f"  query.{name:24} {_one_line(readers[name])[:60]}")
        print("\nPlace each one in `READERS`, then `--write`. This gate"
              "\nexists because `query.cover_between` was marked missing by a"
              "\nrow that needed it, and `query.since_turn_began` was filed as"
              "\na gap while 21 content helpers already wrapped it. #648.")
        return 1
    if reader_stale:
        print(f"{len(reader_stale)} name(s) in `READERS` are not in query.py: "
              f"{', '.join(reader_stale)}")
        return 1
    if misdirected:
        print(f"{len(misdirected)} cross-reference(s) point at the wrong file:")
        for line in misdirected:
            print(f"  {line}")
        print("\nFix `SEE_ALSO`. A pointer into nowhere is worse than no"
              "\npointer -- it reads as 'the verb does not exist'.")
        return 1
    if bad:
        for line in bad:
            print(f"  {line}")
        print("\nRun `uv run scripts/symbols.py --write`.")
        return 1
    if unknown:
        print(f"{len(unknown)} gate(s) read a context key nothing writes:")
        for ref, key, where in unknown:
            print(f"  {ref or '(no row)':14} ctx[{key!r}]   {where}")
        print("\nA ctx is a plain dict, so this is not an error at runtime --"
              "\nthe gate is never true and the row does nothing. Either the"
              "\nkey is a typo, or it belongs in `CTX_KEYS` with a note"
              "\nsaying where the engine writes it.")
        return 1
    if cured:
        print("KNOWN_DEAD names a gate that no longer reads that key:")
        for ref, key in cured:
            print(f"  {ref} ctx[{key!r}] -- delete the entry")
        return 1

    total = sum(len(n) for s in CATEGORIES.values() for _h, n in s["sections"])
    reads = len(_gate_reads())
    # **Undocumented readers are counted, not refused.** 15 of the 75 have no
    # docstring and `reading.md` prints `(no docstring)` for each, which is
    # the state `asking.md` already shows for `c.adjacent`. Failing on it is
    # the right next increment and is deliberately not done here: the fix is
    # edits inside `query.py`, and `audit.py` widens `--changed` to all
    # 23,060 rows for **any** change under `engine/` -- a comment included --
    # so fifteen one-line docstrings would cost a 30-minute sweep. The number
    # is printed so it cannot drift unnoticed. #648.
    thin = sum(1 for n in readers if _one_line(readers[n]) == "(no docstring)")
    print(f"{len(members)} members of Cast in {len(CATEGORIES)} categories, "
          f"{total} placed, 0 uncategorised; {reads} gates over "
          f"{len(CTX_KEYS)} context keys, {len(KNOWN_DEAD)} named dead; "
          f"{len(readers)} query readers in {len(READERS)} sections, "
          f"{thin} undocumented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
