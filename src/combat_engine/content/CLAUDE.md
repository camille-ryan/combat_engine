# Content

677 modules of hand-written rows: what each power, monster ability, item
block, feat, class feature and racial power actually *does*. Written in the
engine's DSL; read numbers from `data/game.db`; never generated.

Global rules are in the root `CLAUDE.md`. **`docs/AUTHORING.md` is the
long-form reference and must be read before writing rows** — the `Cast`
surface, and a list of the things that are *silently false* and have each
cost somebody an hour. This file is the rules; that one is the why.

## The shape of a row

A decorated function. **The decorator header is data** — read by the UI and
the AI policy without running anything — and **the body is code** against a
`Cast` called `c`.

* The body runs **once per target**. `c.first` guards a once-per-power line.
* Almost every `Cast` method defaults to `c.target`, not `c.me`. If the
  sentence is about the character, pass `on=c.me`. This is the commonest
  single mistake here.

  **In a `target=NO_TARGET` row it is not a risk, it is a certainty**, and
  `lint.py` fails you for it now. There is no target, so a bare call acts
  on nobody: `c.bloodied()` is False in every fight, `c.held()` is an
  empty list. 20 rows were written that way and **all 20 audited green**,
  because each had a second clause — a heal, a shift, a summon — that did
  fire. The row fires, does something, and reports finished. #564 is the
  harder half: in a row that *has* a target the same call is usually
  right, and only the card can say.

  **Naming the attacker does not name the victim.** `c.basic(who=other)`
  says who swings; `on=` is who gets hit, and it defaults the same way.
  Ten rows lent a swing with no `on=`, and `c.basic` returns False before
  it rolls — so "an ally can make a basic attack" never happened once.
  `_foe_beside(c, who)` in `monsters/level_01/skirmishers_sa.py` is the
  helper: adjacency to the **attacker**, since adjacency to the caster is
  the wrong question when somebody else is swinging.
* A declared trigger must be `on=Trigger(event, predicate, text)`.
  `trigger="..."` **alone is prose the engine never reads** — the row will
  never fire.
* A row holds either a printed trigger **or** standing modifiers, not both:
  declared `on=`, the body runs only when the trigger fires, so modifiers
  laid there are never laid.

## Markers — six, and three of them take words

* `todo=(symbols,)` — nothing works. Refused in play.
* `dropped=(symbols,)` — plays, one named clause missing.
* `narrative=("skill:name",)` — finished; the clause has no combat meaning.
* `obsolete="why"` — **superseded by a rules change. Never offered, not waiting.**
  A reason in plain words, because there is no symbol to wait for. The other three
  could not say this: `todo=` means "nothing works yet", so `todo.py` reports the
  row ready the moment its symbol arrives — exactly wrong for a row nobody will
  ever want. Refused by `usable` and excluded from every chargen draw, so it
  reaches neither a player's list nor the dealer's.
  Requires a docstring saying why.
* `declined="why"` — **we are not building this.** Not unfinished, not
  superseded, not a gap in the source: a decision that the mechanism is out of
  scope. A reason in plain words, and **say whose call it was and when** — the
  next reader's question is "can this be revisited" and nothing else in the row
  answers it. Refused by `usable` and excluded from every chargen draw, exactly
  as `obsolete=` is.

  The other five all say something false here. `todo=` and `dropped=` name a
  symbol, so `todo.py` reports the row ready the moment that symbol lands —
  exactly wrong for a row nobody intends to finish. `narrative=` claims it
  plays. `defect=` blames the compendium, which has the page. `obsolete=` is
  the closest and is the one worth keeping clean: that row was retired by a
  *rules change*, and writing a scope decision into it would blur the single
  word carrying that argument.

  Does not count toward `blocked.py`, which reads `todo + dropped` — a
  declined row is not work owed, and needs no bucket of its own there.

  **The unit is the thing, not the row.** First use was the 11 Fortune Card
  rows (Camille's call, 2026-10-09, #482), and the instructive one is
  `i3333x1`: it prints only a +1 to Bluff and names no card at all, and it
  is declined anyway, because `i3333p1` is a Fortune Card power and a bonus
  on an item nobody can otherwise use is not worth keeping. Decline the
  item, not the lines that happen to mention it.

  So it is **not** the marker for "one clause of a working row is declined".
  That case was designed for, built in `blocked.py`, and removed when the
  call turned out to be item-level — if it comes back, the row keeps
  `dropped=` and the bucket comes back with it.
* `defect="why"` — **the compendium is missing what the row would be written
  from.** Not a gap in this engine: a gap in the source, so no symbol will ever
  close it and `todo=`/`dropped=` both lie by naming one. Refused by `usable`
  and excluded from every chargen draw, like `obsolete=`, and it **cannot** be
  combined with any other marker or with `out_of_combat`.

  **Only when nothing survives.** A blank defence on a row that never rolls that
  line still plays, and takes `dropped=` with the clause named. Of 26 rows with
  a blank attack defence, **23 play and 3 do not** — flagging all 26 would have
  refused 23 working rows.

  **It drops the whole compendium entry, whatever kind of entry that is.**
  Camille's rule, widened on **2026-10-15** from the monster case:

  > *"defective entries should be dropped from the game… I mean that the
  > ENTIRE compendium entry should be dropped if any part of it is
  > defective."*

  A stat block already behaved that way and the argument generalises: a
  monster fielded without the ability its card is *about* is wrong in every
  fight, not merely incomplete, and so is a tome still paying out its
  Property while the Power it is named for cannot be written. Before the
  widening a defective item Power dropped only itself, so the item was
  still dealt and still worn.

  `dsl.entry_defect` is the one reader and `dsl.entry_of` is what counts as
  one entry: a stat block's abilities belong to the creature, an item's
  Power **and** Property belong to the item, and a `p…b` second card
  belongs to the power it was printed inside. A feat pair (`f959`/`f960b`)
  is two different printed ids and so genuinely two entries — the
  convention cannot be read off the ref. `loader.defective` is now one line
  over it, and that fixed a latent miss of its own: its old prefix walk
  looked for `m1932a…` and would never have matched a conjuration's
  `m1932c0a…`.

  `todo=` and `dropped=` do **not** do this, and that is the line worth
  holding: those mean unfinished, not wrong, so the rest of the creature
  plays and `todo.py` reports the row ready the day its symbol lands.
  `drivers.defective_entry` asserts both halves. #600.

  **You do not decide this yourself.** An authoring agent cannot read the
  compendium. Refer the garbled line up to the main session, which can, and
  which answers with what the page says or tells you to flag it. See
  `docs/AUTHORING.md`, "When you cannot *read* the card". #360.

Plus `out_of_combat=True` for a row that is complete and inert in a fight.

**Symbols only, never prose** — a sentence is refused at import. Reuse a
symbol already in the tree so the groups mean something:
`uv run scripts/blocked.py --group`.

**A marker names one gap.** A symbol doing duty for two different needs
cannot go red or green correctly for either: `c.ability_for(ref)` served
three, so twelve rows reported ready when a third of it landed. If two rows
wait on different things, they want different symbols.

**Check the verb does not already exist before marking.** Most gaps filed
here have turned out to exist under another name, and this line used to say
`grep -n "def verb" ../engine/cast.py` — which asks you to guess the name,
which is the thing you do not know. **In this order:**

1. **`docs/symbols/<category>.md`** — if you know what *kind* of symbol you
   want. Ten files, generated from `Cast` and gated by `check.py`, so a verb
   cannot be missing from them. Each ends with the near-misses that live in
   another file, because the category is not always where you would look:
   combat advantage is in `modifiers.md`, not `conditions.md`.
2. **`uv run scripts/vocab.py --find <word> <word>`** — if you do not.
   Searches what a symbol *says it does*. **Separate words, not a quoted
   phrase**: `--find ignore resistance` finds 36 places and
   `--find "ignore resistance"` finds none, because the arguments are ANDed
   and no docstring holds that literal string. Four verbs that exist were
   marked missing in one session over exactly this.
3. **`uv run scripts/vocab.py --brief`** — for the signature of something
   you have now found.
4. **`uv run scripts/blocked.py --group`** — to reuse the symbol other rows
   are already waiting on, rather than minting a synonym.

`grep` over `cast.py` is the last resort, not the first: 397 members across
12,017 lines, with `as_basic`/`no_basic`/`counts_as` and
`instead_of`/`instead_of_now`/`pre_empt` sitting next to each other.

## Write refs, never names

**Nothing you write may contain a printed name** — not a docstring, not a
comment, not a variable, not a section header, not a string. Two theme files
leaked a feat's name through a comment that merely *described* a power,
inferred from its keywords.

You *are* shown names, since **2026-10-12**: every spec ends with a
**glossary** listing each ref the card mentions beside its printed name, with
your row's own ref marked. Camille's call, because the old arrangement left a
row unable to tell when a clause meant **itself** — six monster rows sat
blocked asking for a facility to address another creature's aura when all six
meant their own.

So: **read the glossary to orient, copy from the body.** The body is still
all refs, which is what makes it safe to paste from. `leaks.py --cited` is in
`check.py` and fails if a file prints the name of a ref it cites; it will
name your file. Its first run found 20 real leaks the older tree-wide check
had called clean for its whole life — two of them in docstrings that *said*
they were writing around the name while printing it.

Searching the web for **a mechanic you do not understand is encouraged**.
Searching for a name is not. Reading `game.db` for **numbers** is fine;
reading it for names is not.

## By subdirectory

**`monsters/`** — numbers load from the database and are never hand-written.
A stat block prints a finished total, so `Attack(vs=AC, printed=6)` says what
the page says and the engine takes the level back out according to
`world.scaling`. Damage goes in the header as data so MM3 rescaling works.

**`items/`** — an item is a base item with properties laid on top. **The unit
of work is a block** (`i601p1`, `i601x1`), not an item. An item Power is an
ordinary `@power` with `cls="item"`; an always-on Property is `action=NONE`.
Crit riders and enhancement are columns, not body code. `Level 11:` / `21:`
lines are out of scope and must not be marked `todo`.

**`feats/`** — a feat is usually a trait. `kind=` is the word the card prints
before "bonus" and nothing else. A prerequisite is a **column** enforced by
`chargen.meets`, never `Power.requires`. A power-granting feat is a pair
(`f959` / `f960b`) — the `b` suffix is the convention for a second card with
no ref of its own.

**A feat that names one power writes its clause into that power**, gated on
`c.feat("<the feat>")`. The feat row stays declared as a pointer. #550, and
the tree still holds the old rider shape in places. `p704` is the worked
example.

**No `label=`, and this line used to say the opposite.** It said laying the
effect with `label="<the feat>"` was not optional, for credit — and
`c.bonus`, `c.penalty`, `c.flat` and `c.damage` take no `label=` at all, so
the instruction raised a `TypeError`. Credit is not the question either: the
feat row is not fired, because it carries `implemented_in=` and `audit.py`
buckets that separately. A modifier is labelled with the laying row's ref
for free. See `docs/AUTHORING.md` for the one case where a label does
matter — two *penalties* in one body, which collapse without one.

Three reasons, and the second is a rule the engine could otherwise break:

* **Nothing has to be pre-wired.** The rider shape only reached a power
  written to *ask*, and almost none were — 36 registrations against 12 read
  sites. `p1489` hard-coded `c.shift(1)` instead of `c.squares_for` and
  blocked three feats on a verb that already existed.
* **One feat per bracketed category applies to one use of a power.**
  `if c.feat(A): … elif c.feat(B): …` makes two impossible; two riders make
  it inevitable, and nothing gated it.

  **The category is in brackets after the printed name** —
  `[Arena Fighting]`, `[Lesser Style]`, `[Greater Style]`, or nothing.
  Camille's rule: one Arena Fighting, one Lesser Style, any number of
  unbracketed. So a body carries **one chain per category**, independent of
  each other, and an unbracketed feat is a plain `if` in neither. Off the
  compendium's `Associated Powers` lines: Arena Fighting 26 rows / 110
  edges, Lesser Style 17 / 51, Greater Style 57 / 140.

  **Never group by the last word of the printed name.** Arena Fighting and
  unbracketed feats are both printed "… Style", and that reading got four
  of the first five migrated rows wrong. The category **is** in `game.db`
  as `feat.category` since #557, and `scripts/spec.py` prints it in your
  brief.

  **`c.declare(category, *feats)` picks the one, and it goes before
  `c.strike()`** — the card says "declare which of each type you are using
  before making the attack", so the choice cannot depend on the roll. A
  branch then reads `if arena == "f974":`, never `c.feat("f974")`:
  `c.feat` says only that it is held, and a chain of those *falls
  through*, paying a second feat's clause when the first one's condition
  missed. #554.
* One mechanism rather than two, and the `if` was already the common one.

**The exception is a feat naming a class of powers** — "any implement
attack". There is no finite list of bodies to edit, so those keep
`c.pre_empt` / `c.instead_of`.

**`races/`** — `cls` holds a **race ref** (`r33`), not a class, for the same
reason a theme row holds `x7_642`: a printed name in that column is a leak.
A racial trait says its race in its own ref (`rt:r33-...`).

**`features/`** — class features, which no spec file lists. Distinct from
feats.

## Chargen has moved out

It used to live here as `chargen.py`. It is now
`src/combat_engine/chargen/`, its own package, because it is its own
component and six files *here* import it — which is the inversion that
argued for the move: content should be the thing chargen deals, not the
other way round.

What that means for you: `from combat_engine.chargen import LIGHT` rather
than `from combat_engine.content.chargen import LIGHT`. Six files in this
tree do that, all for a constant.

A prerequisite is still enforced by `chargen.meets` and is still not yours
to write — see above.

## Checking

Your own refs, by name:

```
uv run scripts/lint.py <your file>
uv run scripts/audit.py <your refs>
uv run scripts/show.py <ref>       printed text beside emitted events
```

Not `--monsters`, not `--class`, not `check.py`.

**Who you are changes two rules.** A parallel content agent lints **only its
own file** — a tree-wide `ruff --fix` has destroyed another agent's work —
and never touches git. The main session lints the tree and commits.

`lint.py` takes paths for exactly that reason, and **it did not until #388**:
this file said "only its own file" and named a command that walked all 776 of
them, so the one tool the rule offered did the one thing the rule forbids. Four
waves in a single round each had to pick their own faults out of a tree-wide
report. With no argument it still lints everything, which is what `check.py`
wants.

Running it tree-wide while other agents are writing is its own trap: the walk
sees whatever half-finished state they are in. One wave reported a tree-wide
blocker that the owning agent had already fixed by the time anyone looked.

`audit` reporting `ok` is weaker than it looks for a row hanging clauses on
a `Hit`: it once credited the harness's own provocation to the row. Fixed,
but if a row's verdict matters, prove it with a positive **and** a negative
control.
