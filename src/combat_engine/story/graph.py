"""What a campaign knows: entities, facts, and where each fact came from.

`docs/STORY_GRAPH.md` is the design and the reasoning; this is the store.
The short version of why it exists: a player asked an NPC about a man the
adventure names once, and the model invented a knighthood, a fall from
grace and a death -- for somebody the party is hired to rescue alive two
scenes later. Nothing distinguished that from the adventure's own text.
#830.

Three things this does that a vector store cannot.

**It answers "no".** A mention that resolves to nothing returns `None`, and
*"I never met him"* is a true answer. Top-k retrieval never returns
nothing; it returns the nearest thing, which is the failure affordances
were built to prevent, one layer over.

**It tags provenance.** A fact knows whether it came off the page, was paid
for with a die roll, or was made up at the table -- so an invention stays
consistent on the next mention, stays distinguishable from canon, and stays
reversible.

**It keeps the DM's half out.** A `Graph` holds the setting and campaign
layers. What the module knows -- who is lying, what is in the next room --
is `module.py`'s and never comes through here.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

#: Where a fact came from. The whole point of the field is that these are
#: never confusable, so they are a closed set and an unknown one is refused
#: at load rather than carried.
SOURCES = ("page", "earned", "invented")

#: Entity kinds, kept small on purpose. The Planescape graph used seven over
#: 4,269 entities and that was enough for twenty-seven books.
KINDS = ("person", "place", "thing", "group", "creature", "idea")

#: The relation on a **derived** edge: two entities named in one grounded
#: quote, with that quote as the evidence. Unlabelled on purpose -- it says
#: they are connected and leaves what the connection *is* to the sentence,
#: which is the half a DM can read for themselves.
NAMED_WITH = "named_with"

#: Relations a module or an ingest pass may **state**, which is the other
#: half and the one that carries meaning.
#:
#: **A vocabulary, not a closed set.** `from_dict` briefly refused a
#: relation that was not in here, on the reasoning that an unreadable
#: `kind` or `source` is refused -- and that was wrong twice over. An
#: unknown relation launders nothing, which is what those two refusals are
#: for, and `around()` follows it perfectly well. It also broke a graph
#: driver that had been declaring a `lives in` edge since before this list
#: existed. So an unrecognised relation passes through; this names the
#: five the page gives, for whoever writes the labelled pass.
#:
#: Five of them are DMG2's own organisation fields, and the vocabulary is
#: taken from there rather than invented: Leadership, Headquarters, Enemies,
#: Rivals, Factions. The **Enemies/Rivals split is why an edge is typed
#: rather than a bare set** -- *"openly or violently conflicts with"* against
#: *"political opponents with whom the group engages in peaceful intrigue"*
#: are different answers to "who opposes this group", and collapsing them
#: hands the DM the wrong register.
RELATIONS = (
    NAMED_WITH, "led_by", "based_at", "enemy_of", "rival_of", "faction_of",
)


class GraphError(RuntimeError):
    """A graph file that cannot be trusted. Reported, never patched over."""


def _fold(text: str) -> str:
    """Casefold, strip accents, drop a leading article, squeeze spaces.

    The key for exact lookup. `"The Cage"`, `"the cage"` and `"Cage"` are
    one name; this is the whole of what "exact" means here, and it is
    deliberately not fuzzy -- a near-miss must miss, because the valuable
    answer is the absence.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s'-]", " ", text).casefold()
    text = re.sub(r"^(the|a|an)\s+", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Fact:
    """One thing that is true, and the record of who says so."""

    text: str
    #: `page`, `earned` or `invented`. See `SOURCES`.
    source: str
    #: Where it came from: a page number for `page`, a scene id for
    #: `earned` and `invented`. Always set -- a fact whose origin is not
    #: recorded cannot be audited, which is most of the value.
    where: str = ""
    #: The adventure's own words, for a `page` fact. Validated against the
    #: source at ingest and replaced with the document's span on a match,
    #: so what is stored is what the page says.
    quote: str = ""
    #: Who may say this unprompted. Empty means nobody volunteers it and it
    #: has to be asked for or rolled for -- **knowing and telling are
    #: different**, and an NPC who knows a secret will say it if it reaches
    #: their prompt.
    told_by: tuple[str, ...] = ()
    #: The skill and DC that recall it, when it is reachable by thinking.
    #: No skill means it is not: you need the person, or an affordance.
    skill: str = ""
    dc: int = 0

    @property
    def canon(self) -> bool:
        """Did this come from the adventure rather than the table?"""
        return self.source in ("page", "earned")


@dataclass
class Entity:
    """Somebody or something the adventure names."""

    id: str
    name: str
    kind: str = "person"
    aliases: tuple[str, ...] = ()
    facts: list[Fact] = field(default_factory=list)
    #: Typed edges out, as `(relation, entity id)`. One hop of these is the
    #: graph half of the retrieval -- asking about a person turns up the
    #: place they are tied to, which a query on the name alone would miss.
    links: tuple[tuple[str, str], ...] = ()

    def names(self) -> list[str]:
        return [self.name, *self.aliases]

    def known(self, *, canon_only: bool = False) -> list[Fact]:
        return [f for f in self.facts if f.canon or not canon_only]


@dataclass
class Graph:
    """One layer of what is known: a setting, or one campaign's own.

    Two of these are live at once and they are **not** merged on disk. The
    setting layer is built at ingest, shared, and never written to in play;
    the campaign layer starts empty and only grows. An invention must not
    leak from one table's game into another's world.
    """

    entities: dict[str, Entity] = field(default_factory=dict)
    #: Folded name -> entity id. Rebuilt on load and kept in step by `add`.
    index: dict[str, str] = field(default_factory=dict)

    def add(self, entity: Entity) -> Entity:
        """Put it in, or merge its facts and aliases into what is there."""
        there = self.entities.get(entity.id)
        if there is None:
            self.entities[entity.id] = entity
        else:
            there.facts += entity.facts
            there.aliases = tuple(dict.fromkeys(there.aliases + entity.aliases))
            there.links = tuple(dict.fromkeys(there.links + entity.links))
            entity = there
        for name in entity.names():
            key = _fold(name)
            if key:
                self.index.setdefault(key, entity.id)
        return entity

    def find(self, mention: str) -> Entity | None:
        """The entity that mention names, or **`None`**, which is an answer.

        Exact after folding, and nothing else. A near miss returns `None`
        on purpose: *"I never met him"* is true and useful, and a
        plausible-adjacent entity is the one thing this layer exists to
        refuse.
        """
        return self.entities.get(self.index.get(_fold(mention), ""))

    def mentions(self, text: str) -> list[Entity]:
        """Every entity named in a line, longest name first.

        For resolving what a player just typed. Longest first so a name
        that contains another does not lose to it.
        """
        folded = _fold(text)
        out: dict[str, Entity] = {}
        for key in sorted(self.index, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", folded):
                found = self.entities[self.index[key]]
                out.setdefault(found.id, found)
        return list(out.values())

    def around(self, entity: Entity) -> list[Entity]:
        """One hop out along its links. The graph half of the retrieval."""
        return [self.entities[eid] for _, eid in entity.links
                if eid in self.entities]

    def between(self, one: Entity, two: Entity) -> list[Fact]:
        """Every fact that names **both**. The pair lookup.

        **The question `mentions` cannot answer**, and the one this whole
        issue was opened over: Camille asked how two entities were related
        and got two separate fact lists, because `mentions` resolves each
        name independently and nothing looked at a pair. A fact naming both
        is the sentence that connects them, which is what a DM wants handed
        over rather than a relation word.

        Searched over both entities' facts and de-duplicated, because the
        same sentence is usually filed under one of them and not the other.
        """
        out: dict[str, Fact] = {}
        for owner, other in ((one, two), (two, one)):
            for fact in owner.facts:
                # **The owner counts as named.** A fact filed under
                # somebody often does not repeat their name -- *"He is the
                # banker"* -- so requiring both names in the span would
                # drop exactly the facts most worth having.
                named = {e.id for e in self.mentions(fact.quote or fact.text)}
                if other.id in named:
                    out.setdefault(fact.quote or fact.text, fact)
        return list(out.values())

    def remember(self, name: str, text: str, *, where: str,
                 kind: str = "person") -> Entity:
        """Write down something the table made up, tagged `invented`.

        Creates the entity if this is the first anybody has heard of them,
        which is the common case: the DM improvises a barkeep and the
        barkeep is now a person with a history.
        """
        found = self.find(name)
        if found is None:
            found = self.add(Entity(id=_slug(name), name=name, kind=kind))
        found.facts.append(Fact(text=text, source="invented", where=where))
        return found


def derive(graph: Graph) -> int:
    """Draw an edge between entities named in one grounded quote. #934.

    **The graph had no edges at all**: 99 entities, 148 facts, **0 links**,
    so `around()` had never returned anything and the structure was a bag
    of facts rather than a graph. `scripts/ingest.py` extracts entities and
    quotes and writes no edge.

    This is the version that *"costs nothing at all"* and it is worth what
    it costs. Measured over the one converted module: **207 edges across 75
    of the 99 entities**, with a degree distribution that looks like an
    adventure rather than an artifact -- 16 entities with a single edge, a
    long tail through the middle, and a handful of hubs that are the
    adventure's principal person, its principal place and the party.

    **Unlabelled, and that is the honest shape**: these say two things are
    connected and hand over the sentence that connects them, which is what
    a DM can read for themselves. A *labelled* edge -- `led_by`,
    `based_at`, the DMG2 organisation vocabulary in `RELATIONS` -- is a
    second pass that has to come from the page, and nothing here invents
    one.

    **Groundable in a span, like every fact.** The evidence is a quote that
    was already extracted and already cited, so an edge cannot exist here
    without a sentence behind it. That is the same rule the facts follow
    and the reason this needs no model call.

    **One known distortion, measured rather than assumed.** An entity
    carrying a generic alias is over-connected by it: the party's own node
    has the alias *"characters"*, which appears in a great many quotes, and
    it lands in the top three by degree on that alone. The edges are not
    *wrong* -- the quote really does name both -- but the node is central
    for a grammatical reason rather than a narrative one. Worth knowing
    before anybody reads degree as importance.

    Idempotent and symmetric: both ends get the edge, and running twice
    adds nothing.
    """
    drawn = 0
    pairs: set[tuple[str, str]] = set()
    for owner in list(graph.entities.values()):
        for fact in owner.facts:
            here = {e.id for e in graph.mentions(fact.quote or fact.text)}
            here.add(owner.id)
            for one in here:
                for two in here:
                    if one < two:
                        pairs.add((one, two))
    for one, two in pairs:
        for a, b in ((one, two), (two, one)):
            entity = graph.entities[a]
            if (NAMED_WITH, b) in entity.links:
                continue
            entity.links = (*entity.links, (NAMED_WITH, b))
            drawn += 1
    return drawn


def reconcile(graph: Graph) -> list[tuple[str, str]]:
    """Fold a short name into the long one it is the tail of. #903.

    One ingest run produced a banker under both his surname and his full
    name, and a keep under both its short and full name -- each with a
    different subset of the facts, so a lookup for one missed what the
    other held.

    **The rule is tighter than "one name contains the other", on purpose.**
    The short name must be the *last* word of the long one and the kinds
    must agree. That is the surname and head-noun pattern -- a banker to
    his full name, a keep to its full name -- and it excludes the case
    that worries: a first name shared by two people, where the short form
    is the *leading* word and merging a father into his son would be
    wrong.

    **Merged as an alias, not by deleting.** The long name stays canonical
    and the short one resolves to it, so every fact from both is reachable
    under either. Nothing is discarded, which matters because the rule is
    a heuristic: if it is ever wrong the cost is a lookup that is too
    broad, not one that silently lost half its facts.

    No model. The Planescape pipeline this borrows from needed a verifier
    for its fuzzy pairs because it worked across twenty-seven books, where
    two deities one letter apart are different people. Inside one
    adventure the tail rule is exact, and a verifier is the thing to add
    when a second source arrives (`#903`).
    """
    merged: list[tuple[str, str]] = []
    for short in sorted(graph.entities.values(), key=lambda e: len(e.name)):
        head = _fold(short.name)
        if not head or " " in head:
            continue
        for long in graph.entities.values():
            if long.id == short.id or long.kind != short.kind:
                continue
            words = _fold(long.name).split()
            if len(words) > 1 and words[-1] == head:
                long.facts += short.facts
                long.aliases = tuple(dict.fromkeys(
                    (*long.aliases, short.name, *short.aliases)))
                del graph.entities[short.id]
                # Re-point every key that named the short entity. **And
                # nothing more** -- a loop re-indexing the long entity's
                # own names used to follow this, and breaking it changed
                # no assertion, which is what a dead line looks like
                # rather than an untested one. The long entity's names
                # were already in the index, and its new aliases are the
                # short one's keys, which this rewrites.
                graph.index = {
                    k: (long.id if v == short.id else v)
                    for k, v in graph.index.items()
                }
                merged.append((short.name, long.name))
                break
    return merged


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-") or "unnamed"


def to_dict(graph: Graph) -> dict:
    return {
        "version": 1,
        "entities": [
            {
                "id": e.id, "name": e.name, "kind": e.kind,
                "aliases": list(e.aliases),
                # **Only the stated edges.** A derived one is recomputed
                # on every load, so writing it would make the file the
                # record of a derivation rather than of what the page
                # said -- and a stale derived edge would outlive the fact
                # it came from.
                "links": [list(x) for x in e.links
                          if x[0] != NAMED_WITH],
                "facts": [
                    {"text": f.text, "source": f.source, "where": f.where,
                     "quote": f.quote, "told_by": list(f.told_by),
                     "skill": f.skill, "dc": f.dc}
                    for f in e.facts
                ],
            }
            for e in graph.entities.values()
        ],
    }


def from_dict(raw: dict) -> Graph:
    got = raw.get("version", 0)
    if got != 1:
        raise GraphError(f"graph version {got}, this build reads 1")
    graph = Graph()
    for item in raw.get("entities", ()):
        kind = str(item.get("kind", "person"))
        if kind not in KINDS:
            raise GraphError(
                f"{item.get('id')!r} is a {kind!r}; one of: "
                f"{', '.join(KINDS)}")
        facts = []
        for f in item.get("facts", ()):
            source = str(f.get("source", ""))
            if source not in SOURCES:
                # **Refused, not defaulted.** An unreadable provenance is
                # the one thing this file cannot guess at: treating it as
                # `page` would launder an invention into canon, and as
                # `invented` would throw away a citation.
                raise GraphError(
                    f"{item.get('id')!r} has a fact from {source!r}; "
                    f"one of: {', '.join(SOURCES)}")
            facts.append(Fact(
                text=str(f.get("text", "")), source=source,
                where=str(f.get("where", "")), quote=str(f.get("quote", "")),
                told_by=tuple(str(x) for x in f.get("told_by", ())),
                skill=str(f.get("skill", "")), dc=int(f.get("dc", 0) or 0)))
        graph.add(Entity(
            id=str(item.get("id", "")), name=str(item.get("name", "")),
            kind=kind,
            aliases=tuple(str(a) for a in item.get("aliases", ())),
            links=tuple((str(r), str(t)) for r, t in item.get("links", ())),
            facts=facts))
    derive(graph)
    return graph


def load(path: Path) -> Graph:
    """Read one, or an empty graph if it is not there yet."""
    if not path.exists():
        return Graph()
    try:
        return from_dict(json.loads(path.read_text()))
    except json.JSONDecodeError as exc:
        raise GraphError(f"{path}: {exc}") from exc


def save(graph: Graph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_dict(graph), indent=2, ensure_ascii=False) + "\n")


@dataclass
class Known:
    """What may be said about something, and what is deliberately withheld.

    The answer to one lookup. `nothing` is the useful case and the reason
    the whole layer exists: it means no node, so the honest reply is that
    nobody here has heard of them.
    """

    entity: Entity | None = None
    #: Facts this speaker would volunteer, already filtered. **Usually
    #: empty, and that is correct** -- see `ask`.
    say: list[Fact] = field(default_factory=list)
    #: Facts reachable by thinking: they carry a skill and a DC, so a
    #: character may roll for them. Never handed to a prompt directly --
    #: the roll happens in the engine and the fact is printed, the way
    #: `module.Lore` already works.
    recall: list[Fact] = field(default_factory=list)
    #: Facts held back from this speaker. Counted, never shown, and here
    #: only so an instrument can tell "nothing to say" from "nothing
    #: known".
    held: int = 0
    #: Entities one hop away, for context.
    near: list[Entity] = field(default_factory=list)

    @property
    def nothing(self) -> bool:
        return self.entity is None


def ask(graph: Graph, mention: str, *, speaker: str = "") -> Known:
    """What this speaker can say about that mention.

    **An empty `told_by` means nobody volunteers it**, and the first draft
    of this read it the other way round -- so a lookup for a patron handed
    back the fact that he secretly serves a snake god, which is the
    chapter's twist, because nothing was marked as unsayable. The safe
    default is the one the field already documented and the whole component
    keeps re-learning: withhold unless told otherwise.

    So `say` is usually short or empty, and that is the design working. A
    fact with a skill and a DC goes to `recall` instead, where the engine
    rolls for it; a fact with neither needs the affordance that prises it
    out of somebody.
    """
    found = graph.find(mention)
    if found is None:
        return Known()
    say = [f for f in found.facts if speaker and speaker in f.told_by]
    recall = [f for f in found.facts if f.skill and f not in say]
    held = len(found.facts) - len(say) - len(recall)
    return Known(entity=found, say=say, recall=recall, held=held,
                 near=graph.around(found))
