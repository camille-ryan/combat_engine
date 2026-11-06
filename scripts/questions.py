"""Every issue parked on Camille must end with a plain-language version.

Camille, asked directly, 2026-11-06:

    "can we make it required that when you add a question tag to an issue
    you give an ELI5?"

Yes, and prose in `CLAUDE.md` is not how this repo makes a thing required
-- `.importlinter` and `drivers.kinds_named` are. This is the gate.

**What it checks.** For every open issue carrying `question`: does its
**last** comment contain a plain-language section? Last, not any, because
a question is answered by reading the bottom of the thread -- that is this
repo's own first rule -- and an ELI5 buried under four later comments of
mine is not the thing Camille reads.

**Why the last comment and not the body.** `CLAUDE.md` is explicit that
the body is the stale part and the comments are the current state. A
question's *current* phrasing is therefore in a comment, and so is the
plain-language version of it.

**No network is a SKIP that says so, never a pass.** A network check that
passes quietly when it cannot reach the network is a check that has
stopped firing, which is worse than no check -- `scripts/CLAUDE.md`
records a waiver that reported "no longer needed" when it had really lost
its read. So an unreachable `gh` exits the code `check.py` already prints
as **SKIP** and keeps out of "all instruments clean".

Exit codes, matching the house convention:

    0   every parked question carries a plain-language last comment
    1   at least one does not -- named, with its last comment's opener
    3   `gh` could not answer; nothing was checked and this is not a pass

**3 and not 2**, because `check.py` already owns that number:
`NOTHING_IN_SCOPE` is its "ran and checked nothing" code, reported as
**SKIP**, counted apart from the failures and withheld from "all
instruments clean". Inventing a second skip convention would have given
this one check a private meaning for an exit code the suite already reads.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

#: `check.py`'s "ran and checked nothing" code, mirrored rather than
#: imported: `scripts/` is not a package, and `check.py` reaches every
#: instrument as a **subprocess** rather than by import, so there is
#: nothing to import it from. `audit.py` carries the same literal for the
#: same reason, and `check.py` warns out loud if the two stop matching.
NOTHING_IN_SCOPE = 3

#: The headings that count as a plain-language version.
#:
#: Matched as **headings or bold leads**, not as bare words anywhere in the
#: comment: "what I need from you" appears inside ordinary prose often
#: enough that a substring test would pass a comment that merely mentions
#: asking. Three spellings because the section has been written three ways
#: and renaming them all is churn for nothing.
MARKERS = re.compile(
    r"^\s{0,3}(?:#{1,4}\s*|\*\*)\s*"
    r"(plain version|plain english|in plain terms|eli5"
    r"|what i need from you|your options)",
    re.I | re.M,
)


#: How a comment of mine is recognised. `CLAUDE.md` requires the trailer on
#: every issue comment, precisely because the author field is always
#: Camille's -- so the absence of it is the only signal that she wrote one.
SIGNED = re.compile(r"posting on Camille's behalf", re.I)


def parked() -> list[dict]:
    """Open issues carrying `question`, newest first. Raises on no network."""
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--label", "question",
         "--limit", "200", "--json", "number,title"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "gh issue list failed")
    return json.loads(out.stdout)


def last_word(number: int) -> tuple[str, bool]:
    """The last thing Camille reads on this issue, and whether it is a comment.

    **The body counts when there are no comments**, which this got wrong on
    its first day. A freshly filed question carries its plain-language
    version in the body -- there is nowhere else to put it -- and reading
    only comments reported it as missing. `#1134` was the case: filed with
    a plain version, flagged for not having one.

    The rule is "the plain version is the last thing she reads", and for an
    issue nobody has commented on that is the body. Once a comment exists
    the body is the stale part (this repo's first rule), so the comment
    wins from then on.

    The flag is returned rather than discarded so the caller can tell
    Camille's reply from mine -- a body is always mine.
    """
    out = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "comments,body"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh issue view {number} failed")
    got = json.loads(out.stdout)
    comments = got.get("comments") or []
    if comments:
        return comments[-1]["body"], True
    return got.get("body") or "", False


def main() -> int:
    try:
        issues = parked()
    except Exception as why:
        print(f"  SKIPPED -- gh could not answer: {why}")
        print("  nothing was checked, which is not the same as a pass")
        return NOTHING_IN_SCOPE

    if not issues:
        print("  no open issue carries `question` -- nothing parked on Camille")
        return 0

    # **Three outcomes, not two.** A question whose last comment is
    # *Camille's* is not missing its plain-language version -- it has been
    # **answered**, and the ball is mine: act on the ruling and drop the
    # tag, or re-ask. Reporting that as "NO ELI5" tells me to write another
    # ask at exactly the moment I owe a reply. The first draft collapsed
    # them and said the wrong thing on its first real run.
    answered: list[tuple[int, str, str]] = []
    bad: list[tuple[int, str, str]] = []
    for issue in issues:
        number, title = issue["number"], issue["title"]
        try:
            body, from_comment = last_word(number)
        except Exception as why:
            print(f"  SKIPPED -- #{number}: {why}")
            return NOTHING_IN_SCOPE
        where = "last comment" if from_comment else "the body"
        opener = " ".join(body.split())[:70] or "(nothing written at all)"
        # A body is always mine, so only a *comment* can be Camille's.
        if from_comment and body and not SIGNED.search(body):
            answered.append((number, title, opener))
        elif not MARKERS.search(body):
            bad.append((number, title, f"{where} opens: {opener}"))

    ok = len(issues) - len(bad) - len(answered)
    print(f"  {len(issues)} tagged `question`: {ok} parked on Camille with a"
          f" plain-language ask, {len(answered)} answered and waiting on me,"
          f" {len(bad)} with no plain-language version")
    if not bad and not answered:
        print("  every parked question ends with one")
        return 0

    print()
    for number, title, opener in answered:
        print(f"  ANSWERED #{number}  {title[:62]}")
        print(f"           Camille said: {opener}")
    for number, title, opener in bad:
        print(f"  NO ELI5  #{number}  {title[:62]}")
        print(f"           {opener}")
    print()
    if bad:
        print("  A `question` tag is a request for Camille's time, so it carries")
        print("  a plain-language version as its LAST comment: what is broken,")
        print("  what is being asked, what each option means, and a pick.")
        print("  Camille's ask, 2026-11-06 -- see this file's docstring.")
    if answered:
        print("  An ANSWERED one is not waiting on Camille. Act on the ruling")
        print("  and remove the tag, or re-ask -- leaving it tagged makes the")
        print("  parked list describe work that is mine.")
    #: **The verdict goes last**, because `check._summary` reports an
    #: instrument's final line. The first version ended on a sentence of
    #: advice, so the suite's one-line report read "parked list describe
    #: work that is mine" -- true, and useless as a summary.
    print()
    print(f"  {len(answered)} answered and waiting on me,"
          f" {len(bad)} with no plain-language version")
    return 1


if __name__ == "__main__":
    sys.exit(main())
