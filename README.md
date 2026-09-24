# Combat Engine

This project aims to recreate 4e D&D as a playable combat engine.

## Legally Distinct 4e

Game systems are not able to be trademarked, but prose is. All potentially trademarked content is to be stripped out of the main engine and stored in a separate lookup table. For example, powers will be referenced as p#### instead of "power name" within the code. If this project is distributed, users can supply their own localization. When agents are translating powers, monsters, etc. into code, they MUST NOT be supplied the flavor text or power names. Monster abilities should be stored similar to powers and should share ops.

 ## Game Paradim
 We will use Entity Component System to handle game data. Most if not all actions will need to be treated as events, becuase many of 4e's abilities trigger off of them. For example:
 - Creature enters zone
 - Creature enters square adjacenet to another creature.
 - Creature attacks another creature.
 - Creature leaves a space adjacent to another creature.

 ## Creation process
 The goal is to make things playable as we go along. This must start with a basic framework, followed by materials required for level 1 play, then level 2, then level 3, etc. Currently, the scope of this project is up to level 10 for PCs, and level 13 for monsters.

 Base set includes fighter, cleric, thief, and wizard.

 Powers and monster abilities in 4e are well defined, but often complex.

 The corpus of effects should grow as we implement powers, monsters, feats, etc. An entity MUST be fully implemented before it is added.

 All powers, monsters, etc. should be *hand coded* by claude rather than produced programmatically through regex. P

 ## System notes
 There are several kinds of effects.
 - Effects which apply only to a single entity, for example:
    - Blinded
    - Dazed
    - Deafened
    - Dying
    - Grabbed
    - Helpless
    - Immobilized
    - Marked
    - Petrified
    - Prone
    - Removed from play
    - Restrained
    - Slowed
    - Stunned
    - Surprised
    - Unconscious
    - Weakened
 - Effects which are relational
    - Grabbed (x is grabbed by y, also: x is grabbing y)
    - Hidden (x is hidden from y)
    - Marked (x is marked by y, note that a creature can only be marked by a single other entity)
    - Dominated (x is dominated by y)
    - Flanked (x is flanked by y and z. Therefore, x grants combat advantage to y and z)
    - Combat advantage (usually. Some effects may cause a creature to grant combat advantage to all enemies)
    - Ally of (creatures are not allies to themselves)
    - Enemy of
 - There are also many conditional effects which are specified by powers and monster abilities. These can be thins like "+1 ac until the end of your next turn

 - There are several types of actions:
   - Standard, Move, and Minor actions can be taken on a creature's turn. A standard action can be converted to a move action. A move action can be conveted to a minor action.
   - Immediate interrupts occur before the trigger.
   - Immediate reactions occur after the trigger.
   - A creature can only take one immediate action per round.
   - Opportunity attacks can be taken once per turn.
   - Free or no actions may be taken outside of a creature's turn if the power species.
 - Effects can have severla kinds of durations:
   - Until end of your next turn.
   - Until the end of the target's next turn.
   - Save ends
   - Until the end of combat
   - Sustain (action type) requires an action (usually minor) to be used to prolongue the effect.

 - Some powers can create zones, conurations, auras, etc. If a power has an ongoing "allies adacent" or "enemies adjacent", treat it as an aura 1. These must track who originated them. They typically act on the creator's turn, and can sometimes be dispelled or interrupted by interacting with the caster.

 ## Combat AI
 - To start, we use preprogrammed policies to determine monster actions. Open questions:
   - How do we handle compound actions like "attack dealing x damage, then move up to 2 squares". Is this treated as 25 separate options for a singal target?
   - How do we handle different ordering? (Action first, then move or vice versa)
 - Ideally at some point we can use RLHF to determine policies based on watching how the player plays.

 ## House Rules
 - Level bonuses are stored separately so that we can "mod" the game to remove or attenuate them (likely +1 per 5 levels)
 - Default mounts in 4e are creatures that die easily to AoE. Optionally, treat mounts as magic items which alter the rider's movement modes and space, and allow the mount's actions (attacks, etc.) to be used in place of the rider's. For example, use a standard action to use one of that mount's standard action abilities.
 - hex map mode
