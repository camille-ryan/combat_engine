# The wave brief

Handed verbatim to every content agent. `plans/20260927-remaining-waves.md`
says which wave gets which class or category and what to add to this.

You are writing 4e-alike feat rows into a Python combat engine at
`/Users/camille/proj/combat_engine`. Work from the repo root.

**You are one of several agents working at once**, which is why you lint only
your own file and never touch git. `AUTHORING.md` says the same under "Who
this is for"; `CONTRIBUTING.md` describes the main session's rules, which are
the opposite on both counts and are not yours.

## Read first, in this order
1. `docs/AUTHORING.md` — the whole thing. The "Feats specifically",
   "A row with no combat consequence at all" and `todo=` / `dropped=`
   sections are the rules you will be judged on.
2. **`uv run scripts/vocab.py --brief`** — every verb a body can say,
   with its signature, generated from the code so it cannot be stale.
   389 lines. **Keep it and grep it.** `Cast` has 285 public members
   and nobody remembers them: six markers in one session named a verb
   that already existed — `c.curse`, `c.threatens`, `c.reroll_damage`,
   `c.shrouds`, `c.save(against=)`, `c.redirect` — and each one meant
   a row refused in play for nothing. **Grep this before you mark
   anything**, and if what you need is genuinely absent, `vocab.py`'s
   own docstring is right that the answer is usually to add a method
   rather than work around it.
3. **One** existing file near your batch, for house style — shape,
   comment density, docstring voice. One, not three. The item files
   run to three and five thousand lines and reading two of them costs
   more than the batch is worth; `vocab.py --brief` is what you
   actually needed from them.

## Your brief
Run, with YOUR class and YOUR batch size:

    uv run scripts/spec.py --feats --class <CLASS> --limit <N>

or, for an item wave:

    uv run scripts/spec.py --items --category <CATEGORY> --limit <N>

That prints only the rows nobody has written yet. It is the complete
work list; do not go looking for more.

## Hard rules
* **You are never given a printed name or flavour text, and you must not
  go and find one.** Refs only. This is the legal basis of the project.
* **Hand-write every row.** No regex, no loops that mint rows from a
  table — except the small `_feature(ref, what)`-style helper used in
  `warlord.py` and `ranger.py` for a run of rows that are genuinely the
  same marker. Read one of those before you copy the pattern.
* **A row is fully implemented before it is added**, or it carries a
  marker. **Three markers, not two:**
  * `todo=("c.verb()",)` — nothing here works. Refused in play.
  * `dropped=("c.verb()",)` — works, one named clause missing. Plays.
  * `narrative=("skill:name",)` — finished, and the clause has no combat
    meaning at all. Counted done, and it **requires** a docstring saying
    why. See `AUTHORING.md` for the test that separates this from
    `dropped=`; this brief used to say there was no third option.
  * Both take **symbols, never prose**. A prose marker is refused at
    import. Reuse symbols already in the tree so `todo.py` groups:
    `grep -rho 'todo=(\|dropped=(' -A1 src/combat_engine/content/feats/`
    then `uv run scripts/blocked.py --group`.
* **Before you mark a row, check the verb does not already exist.**
  `grep -n "def <verb>" src/combat_engine/engine/cast.py`. Three markers
  so far have been guesses about verbs that were already there, and the
  instrument catches every one.
* **`kind=` is the word the card prints before "bonus" and nothing else.**
  A plain "+1 bonus" is untyped: `c.bonus(...)` with no `kind=`.
* **The prerequisite is not yours to write.** It is a column.
* **`_who` trap**: most `Cast` methods default to `c.target`, not `c.me`.
  If the sentence is about the caster, pass `on=c.me` explicitly.
* If you do not know how a mechanic works, **search the web for the
  rule** — that is encouraged. Never search for a *name*; see the one
  rule in `AUTHORING.md`. A rule is not protectable and a name is.
* **Read the event before you read a field off it.** `Dropped` has
  `actor` and no `target`; `PowerUsed` has `targets` and no `target`;
  `Moved` has `from_` and `to` and no `squares`. A `getattr` with a
  default turns each of those into a row that quietly does nothing,
  which is worse than one that raises.
* **A row holds either a printed trigger or standing modifiers, not
  both.** Declared `on=Trigger(...)`, the body runs only when the
  trigger fires -- so modifiers laid in it are never laid at all. If a
  feat prints both, write it as a trait and use `c.watch` for the
  triggered half.

## Your loop, per file
    uv run ruff check --fix <your file>
    uv run scripts/lint.py
    uv run scripts/audit.py <your refs, named>

`audit.py` must say every writable row of yours fires and does something.
**Never run `scripts/check.py`, never run the replay or fight scripts,
never lint the whole tree** — other agents are writing at the same time
and `--fix` across the tree has destroyed another agent's work before.
Only touch your own file.

Budget: 150 tool calls. Do not commit; do not touch git at all.

## Report back
One paragraph: how many rows written, how many carry `todo=`, how many
`dropped=`, and the symbols you named with a count each.
