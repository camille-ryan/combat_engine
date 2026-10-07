# Triage: 27 non-policy issues, before the AI pivot

All 27 read with every comment. 12 policy issues (#266–#332) excluded.

**Three things changed since the last pass and they reorder the queue:**

1. **Camille answered the three issues that were waiting on her** — #437, #286
   and #346. Those stop being blocked and become the top of the queue.
2. **#360 is two rows from closing** and nobody noticed, because its marker half
   landed in `d5c04c0` and its closing condition names a second half that turns
   out to be smaller than the body says.
3. **#335 is much worse than its title** and the open question it has carried
   for two days is now answered: the printed number *is* in the compendium, as a
   glyph, and the ETL drops it and guesses — in the wrong direction, for about
   1,100 monster powers.

Target: **27 → 11**, four wide suite runs.

---

## The measurement that changes a priority: #335

The issue's own open question, twice recorded as "the next step, not done":

> are the die symbols being lost in extraction? ... if those are dropped before
> the spec is written then 6 is a guess standing in for a number that *was* on
> the page — which is a different fix, in a different place.

**Answered: yes.** The threshold is an `<img>` in `Monster.Txt`, and the
filename is the number.

```
Recharge-followed-by-glyph occurrences, whole corpus   2521

  images/symbol/5a.gif   1563
  images/symbol/4a.gif    532
  images/symbol/6a.gif    398
  images/symbol/3a.gif     25
  images/symbol/2a.gif      3
```

The ETL stores `6` for 1,623 rows. **6 is 16% of the printed thresholds.** The
commonest is 5, by four to one. No method is needed to see the problem: if `6`
were right the glyph distribution would be 6-dominant, and it is not.

A per-monster spot comparison (first glyph against that monster's recharge rows,
so it over-reports where one monster prints two thresholds):

```
stored matches the printed glyph    165
stored disagrees                   1139      sampled: all "printed 5, stored 6"
glyph present, no recharge row     1129      a second, separate half
```

**Why this outranks most of the queue.** Recharge 5 fires on 2 faces of 6;
recharge 6 fires on 1. So the ETL roughly **halves the frequency of ~1,100
monster powers**, silently, in the field that decides how often a monster's best
attack comes back. #320 made the die correct and this makes the threshold
correct; the two together are the whole mechanic.

It also splits the issue cleanly, which the title could not:

* **the glyph parse** — a real printed number recovered, `etl/monster.py`, one
  regex on the raw HTML before the scrub;
* **the ~460 condition rows** — "recharges when the target saves" — which print
  no die and must become NULL per *"parse, or store nothing"*, and then want a
  trigger. Separate, and its own issue.

Moves numbers, so **its own commit and its own re-record**, not riding anything.

---

## Phase 1 — the three Camille just unblocked

### #437 + #286 — one piece of work, now decided

> **#286:** Prefer a configurable dummy. If that's insufficient, find another
> solution.
>
> **#437:** My first thought here was to add variable creature type tags to the
> crash test dummy and use that. If that's insufficient, then add a humanoid to
> the board recipe.

So: **creature-type tags on the dummy first**, board recipe only as a fallback.
That is the narrowest version of the thing and it is the right place to start —
the board-recipe route has already gone wrong once (`KNOWN_SILENT` records a
casual widening taking every other monster's legal shift with it).

The acceptance test is already agreed on the thread and should stay: **if it
does not retire most of the 99 `KNOWN_SILENT` entries that blame the board
rather than the row, it did not earn the rewrite.**

```
KNOWN_SILENT   305 entries
  blame the row   217
  blame the board  99   <- the population this is for
```

Build order:

1. type tags on `content.dummy` (undead, humanoid, …) — Camille's first choice,
   and the 5 rows #387 folded in are exactly this;
2. the third verdict — *the gate was never true here* — which #286 asks for and
   which **cannot be reported usefully without a dummy that can make a gate
   true**. Same piece of work, as recorded on both threads;
3. the split: the dummy owns the verdict, the random sweep keeps owning raises.
   Confirmed by Camille only implicitly — she chose the dummy, not the
   replacement of the sweep — and the cost argument for going further is spent
   (#441 took two consecutive runs to 994.4s then 0.7s).

Measure by **ref-list diff, never counts**. Three times in one session a count
stayed flat while individual rows broke underneath it.

### #346 — answered and widened; 39 items, not 16

> Even if it's not currently wielded, it should show what kind of weapon it is.
> [...] Same with Armor. Implements look like they usually (always?) have the
> correct implement type [...] Shields should also specify light / heavy /
> barbed. If I'm not mistaken, other magic item types do not have base items.

Both of my open questions answered: **always substitute**, not only when
wielded; and the scope is three categories, not one. Sized:

```
category     items   name leads with a generic word
Weapon         318    15     ("Weapon of ..." 14, "Blade of ..." 1)
Armor          201    16     ("Armor of ..." 16)
Arms            85     8     ("Shield of ..." 8)
Implement      412   181     already concrete -- staff 54, rod 45, orb 42,
                              symbol 40, wand 20, totem 13
```

**39 items, and Camille's read of the implements is right** — 181 of 412 lead
with the actual implement word, so there is nothing to substitute there. Her
last line is right too: no other category has a base item.

One real gap in the way: **there is no `armour` table.** `weapon` exists and
carries the slug this already uses. For armour the word lives on
`ClassLine.armour` (`"chain"`, `"cloth"`), which is what the character is
*wearing* rather than what the item *is* — so the armour and shield halves need
a source the weapon half already has. Light/heavy/barbed for shields is the same
question. **Do the weapon 15 first** (ready today), then decide the armour
source; splitting it that way means 15 items ship instead of 0.

---

## Phase 2 — #360, two rows from done

The marker half landed (`d5c04c0`): 30 rows no longer name a parser that cannot
exist. What the body still asks for is `Defense.ANY` and "the four rows written",
and **family C is 2 rows, not 4**:

```
m790a1    "+13 vs Any ... the beam hits if it hits any defence"   the real shape
m3232a1   "+6 vs Any"                                             the real shape
m2812a3   "+7 vs. AC and +5 vs. any other defense"                NOT this family
m5215a4   "+11 vs. AC and  +9 vs. any other defense"              NOT this family
```

The second pair is a **two-bonus attack line** — one number against AC, a lower
one against anything else. That is a different construction from "hits if it hits
any defence", and `m2812a3`'s marker names `c.learn()` and has nothing to do with
this issue at all. They were counted here by a regex that matched the word.

And of the real two:

* **`m790a1` already plays it in its body**, reading the target's defences
  directly. It carries `dropped=("Attack.vs",)` and its docstring states the
  gap exactly: *"The header can only ever name one defence."* So this row needs
  the enum member and nothing else.
* **`m3232a1` is marked `compendium.attack_defence`, which is the wrong
  marker.** The card *does* print a defence — "Any". The compendium is not
  missing anything; the engine has no member for it. That marker says a source
  gap and this is an engine gap.

So: one enum member, one row re-pointed, one marker corrected. `Defense` is a
4-member `StrEnum` at `engine/types.py:21`.

---

## Phase 3 — the folded axis is not a design question any more

Four issues share one blocker and I had it recorded as *"the only part that is
genuinely a design question rather than a diff"*. That is no longer true.

**Every folded axis already has its `cf:` sub-option refs in the database:**

```
class      BUILDS legs folded in    sub-option refs that exist
warlock    6  (the pacts)           cf:warlock-f1s0 .. f1s6        7
shaman     4  (the spirits)         cf:shaman-f0s0 .. f0s3         4
sorcerer   4  (the elements)        cf:sorcerer-elementalist-f2s0..3  4
avenger    2  (the censures)        cf:avenger-f1s0 .. f1s2        3
wizard     0  (#432's implements)   cf:wizard-arcanist-f0s0 .. f0s5   6
```

**18 refs against 16 folded legs.** Nothing has to be invented or named. Two
axes simply have an option we never entered, which is a row to write rather than
a model to design.

What is actually missing is **one place on `Character.choices` to hold a
sub-option pick that is not a build.** Today:

```
a wizard carries:  ['control', 'primary:int']      <- no implement
a druid carries:   {'f1s2', 'primary:wis'}         <- the leg, doubling as the sub-option
```

That single field closes or unblocks three issues at once:

* **#432** — the 3 wizard implement arms. Its own comment proves
  `c.build("f0s0")` is *not* the fix (it answers False forever, which would take
  three working arms out of play); a second axis is.
* **#416** — the 11 inline legs need a sub-option→build join, which is the same
  mapping.
* **#235 step 4** — the 16 folded legs get somewhere to live, so they can leave
  `BUILDS` without making 51 content gates permanently false.

### And a correction to Camille's note on #235

> I think the marshal warlord is an "essentials" class which is a reimagining of
> the original warlord. [...] I believe they have a different entry in the class
> portion of the compendium db.

**Right in general, wrong about this one.** The warlord page is `ID 8`, source
*Player's Handbook, Class Compendium* — the **original** PHB warlord, filed under
a build name by the Class Compendium update. Exactly the same shape as four
siblings, which is the five classes #438 found had no bare page:

```
id 2  Cleric (<build>)      Player's Handbook, Class Compendium
id 3  Fighter (<build>)     Player's Handbook, Class Compendium
id 6  Rogue (<build>)       Player's Handbook, Class Compendium
id 8  Warlord (<build>)     Player's Handbook, Class Compendium
id 9  Wizard (<build>)      Player's Handbook, Class Compendium
```

The genuine Essentials reimaginings are **eight other pages**, all sourced
*Heroes of the Fallen Lands* / *Heroes of the Forgotten Kingdoms* — two fighter
variants, a cleric, a rogue, a wizard, two rangers, a druid. **We import none of
them.** All 25 rows in our `class` table are base classes.

So the invented sixth warlord leg is **not** explained by an Essentials page. It
is what the comment in `BUILDS` already says: the printed name of a *swordmage*
leg, which `c.build()` resolves against the character's own class so the gate
answers True and nothing ever looked wrong.

**But her underlying position is a decision #235 still needs**, and it
contradicts what that thread currently assumes. #235's comment reasons that *"a
sectionless parenthesised page is itself a leg"* — which would fold the Essentials
variants into their base class's legs. Camille's position is that they *"should be
considered as different from the base class"*. Those are opposite answers. Nothing
depends on it yet (we import no variant pages), but the sorcerer's four elements
are an Elementalist page's options sitting in the base sorcerer's legs — which is
the same question arriving early.

---

## Phase 4 — the small engine batch

#443, #444, #445 are small, were filed with the measurement already in them, and
none has been touched. #446 is the real fix behind #390 and decides what #390
becomes.

* **#443** — `movement._threat` passes an empty context, so `c.threatens(when=)`
  cannot gate on who is walking past. The `when=` forwarding landed; the context
  did not.
* **#444** — `cancel()`'s interrupt-only rule is unenforced; a reaction stops the
  attack too, and a shipped row depends on that. Measured:
  `interrupt cancel() -> True hp 33 -> 33 / reaction cancel() -> True hp 33 -> 33`.
* **#445** — `Dropped` carries no cancel, so a printed "the triggering attack
  misses" cannot answer the event it names.
* **#446** — a combat-advantage rider reads post-attack state. Two shapes weighed
  on the thread: snapshot combat advantage onto the outcome event, or make the
  `AttackDeclared` AFTER window a documented place rather than a workaround.
* **#390** then becomes a **documentation** fix — `c.hide`'s docstring tells an
  author to do the thing that does not work — unless #446 removes the limitation,
  in which case it closes for real. Decide after #446.

One wide run for the batch. `replay` strip-and-compare per fixture; re-record in
its own commit if anything moves.

### #386 — promote it; the engine half is already written

Deliberately pulled last pass for a good reason, and the reason has a cheap
answer: landing the engine half alone turns `todo.py` red with 14 rows still
carrying the marker. **So land the engine half and the 14 rows in one commit** —
which is what the thread's own last comment recommends.

Already settled on the thread: `resolve.spend_surge` is the **only** place that
decrements `Health.surges`, so one chokepoint covers all three routes. Driven
both ways: `surges 12 -> 11 / with c.no_surges 12 -> 12`.

Ten rows are an inserted call with a known duration. Four need judgement — two
empty-bodied traits wanting a watcher, one aura-scoped refusal, one tied to an
ongoing-damage lifetime — plus `m2522a3`, whose card wants reading. That is an
afternoon, not a wave.

### #334 — mechanical, and it deletes a documented trap

~40 lines moved to `src/combat_engine/db.py`, ~30 import sites rewritten. Touches
five components in one commit, which the root file allows when the seam *is* the
subject. Verify with `check.py --fast`, `api_smoke.py`, `browser.py` (the two
module-level importers), `leaks.py` (it reads `ROOT` from the module being
emptied), and assert the thing it buys: importing the read path pulls **no**
`etl.*` parser.

---

## What will still be open, honestly (11)

**Policy-blocked, and the pivot clears it for free:**

* **#283** — the one-line fix is correct and costs 1.5 rounds at level 5 until
  the AI prices a ranged basic against closing. Camille's own comment names the
  fix: *"this is likely doing a lookahead to next round's damage somehow, and
  that part could be extensible to other classes."* That is the AI work she is
  pivoting to. **Worth re-checking the moment lookahead lands** — it is one line
  plus a re-record.

**Sweep-sized, each wanting its own plan:**

* **#339 steps 3–5** — 9,249 sites, 552 files, 27 directory renames, ~12 hours
  of machine time. Decided, not urgent, and measured as **not** blocking #235
  (the collision is 7 legs of 90, not the 76 refs both issues cite).
* **#364** — 544 is the *ceiling*, not the work: a row aimed at allies where the
  caster was never a legal target is unaffected, and that subset is still
  unmeasured. **Measure the subset before committing to the sweep** — it decides
  whether this is a wave or an afternoon.
* **#420** — 88 rows. Design settled to a single polymorphic `dtype=`
  normalising at construction, so 172 scalar readers keep working. Needs the
  `__str__` comma join (two five-type rows), `Cast.hit`'s forwarding, and the
  summon-block line at `cast.py:4669` which is the known trap.
* **#389** — 45 rows waiting on a disease table that does not exist. ETL
  extraction + a new ref prefix + an engine verb + a duration that outlives a
  fight. Nothing regresses by waiting.

**Live breach of the absolute rule, found during this triage:**

* **#447** — its issue half is no longer unmeasured, and it is the larger half.
  Every issue, title, body and each comment, through `leaks._hits` +
  `_identifies`:

  ```
  issues                                      447
  text units (title + body + each comment)   1620
  findings                                     45
  distinct names                               31
  issues holding at least one                  20
  ```

  Against **22 findings in 665 commit messages**. So the issue population is
  twice the size and — unlike a commit message — **editable**, which makes it the
  one of the six places named in the root `CLAUDE.md` where a find has a remedy.

  Caveat before anybody edits: **GitHub keeps edit history on issues and
  comments**, readable through the API. A scrub removes the name from the
  rendered text, not from the record. Worth doing; not erasure; and an argument
  for the gate being pre-post.

  It also corrects something I wrote in #447's own body: that `identifies`
  "waives a race's name on purpose". It does not — four race names are findings
  here, gated on exactly that test. So the claim that roughly half the commit
  findings are exempt classes is unsupported by the test I cited for it.

  **Not scrubbed.** 20 issues is a tracker-wide edit and wants one decision, not
  20 quiet ones. One of the 20 is #346, in Camille's own words.

**Needs a sizing or a re-scope first, not a fix:**

* **#424** — concealment has no grade, and is explicitly **not sized**. The
  existing `blocks_sight` sites are the wrong population to count (they are where
  the binary flag was good enough). Sizing is step one and is the whole issue.
* **#400** — zones need a square target. The real design question is that
  `dsl.candidates` returns entity ids. Settle before any zone content is written.
* **#378** — four cases, **four different faults**, and the discriminator the
  body proposes groups nothing (0 reprint groups; no two creatures share a
  printed name). Only one of its four examples is a reprint. **Re-scope into the
  three real questions or close it and refile them** — it is not one issue, which
  is the rule.
* **#379** — 25 fragments, and most of them *must* survive: they are creature
  type words, and splitting a stranger's name into `by_word` would scrub a word
  out of rules text. Needs a frequency cut, the way `leaks.COMMON_ENOUGH` already
  decides what is vocabulary. The one-liner the body describes is proven harmful.
* **#340** — 20 rows in the open position, not the 5 recorded, and **one of the
  20 must stay as it is** (`f377`, the correct refusal). Plus the digit-leading
  word that stops `_NAMED_RITUAL`'s run — one row, and that row needs both
  halves.
* **#447** — the history walk. Its issue-text half is unmeasured and needs the
  network. A commit message cannot be reworded, so historical finds are
  information rather than failure; the gate belongs pre-commit.

**Genuinely hard, two dead ends already written up:**

* **#253** — a coloured heading's rating attributed to everything it lists.
  Truncating at the first colon is a measured no-op (0 of 2,526 resolutions);
  "is it followed by prose" does not discriminate (217 of 217 followed by prose).
  Both written up so the next attempt does not repeat them.

---

## Order, and the suite runs

1. **#360** (2 rows, one enum member) — narrow run.
2. **#346 weapon half** (15 items) — `api_smoke`, `browser`.
3. **#335 the glyph parse** — rebuild, its **own** commit, its **own** re-record.
   One wide run follows the rebuild, per the cadence rule.
4. **#334** — `check.py --fast`, `api_smoke`, `browser`, `leaks`.
5. **The engine batch: #443 #444 #445 #446, then #390's verdict** — one wide run.
6. **#386** — engine half plus all 14 rows, one commit.
7. **The second axis: #432 + #416 + #235 step 4** — one wide run, re-record likely.
8. **#437 + #286** — the configurable dummy and the third verdict. Largest, and
   the acceptance test is the 99.

Standing constraint: the wide suite blocks tree edits while it runs, so each
run is the last thing in its step. `--all` once before a push, not once per
commit.
