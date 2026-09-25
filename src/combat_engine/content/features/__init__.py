"""Class features: what makes a class itself rather than a list of powers.

Not feats -- those are the small every-other-level options, they have their
own table in the compendium, and this never touches them.

Some features have a compendium row of their own and use its id. The ones
that do not are described only in the class's own page, so they get a `cf:`
ref: `cf:rogue-extra-damage` and the like. Either way they are declared with
the same `@power` decorator as everything else, because a feature that marks
a creature or adds damage is a power by every mechanical measure.
"""

#: One of them is a *budget* rather than a row: a shared allowance that a
#: dozen rows across two classes draw on, printed on each of them as "you can
#: use only one of these per encounter". That is the `group` header field,
#: which `dsl._group_spent` enforces. The string lives here because it is
#: shared by rows in four different files, and a mistyped one fails silently
#: -- the rows simply stop sharing a budget and nothing says so.
CHANNEL_DIVINITY = "channel divinity"
