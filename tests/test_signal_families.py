"""A token the vocabulary spells out must be findable in a real label.

`dcp/signal_families.py` matches free-form snake_case labels. Several of
its patterns delimited a short token with `\\b` — `eia\\b`, `suds\\b`,
`chp\\b`, `ups\\b`, `dno\\b`, `mva\\b`, `bng\\b`, `cemp\\b`, `lpa\\b`,
`pue\\b`, `sac\\b`, `spa\\b`, `scr\\b`, `crac\\b`, `crah\\b`, `kv\\b`,
`hvo\\b`, `gia\\b`, `gea\\b`, `\\bmw\\b`. `\\b` is a word boundary and
`_` is a word character, so not one of them could ever match the labels
it was written for: `eia\\b` matched a bare `eia` and never `eia_status`.
The family `eia_process` did not classify as `eia_process`. Measured
across the corpus on 2026-08-26: 16,239 rows moved once the boundary was
corrected, 14,042 of them out of `unclassified`, +5,528 into `eia_process`
— a family two reader panels select on by name.

These tests assert the rule over the whole vocabulary rather than the
tokens that happened to be broken, because the next token someone adds
will be written the same way. Three shapes:

  * every delimited token must match when used as a snake_case word,
  * no pattern may delimit with `\\b` at all,
  * and the correction must not have gone the other way — deleting the
    boundary instead of fixing it would let `eia` match `eiaslop`, which
    is the more damaging repair and the obvious one to reach for.

No database and no network. What these cannot check is whether a family
should claim a token in the first place: FAMILIES is an editorial answer
to how the data and visuals teams want findings sliced, and the
exceptions recorded below are theirs to settle, not this module's.
"""

from __future__ import annotations

import re

import pytest

from dcp import signal_families as sf

# A literal token immediately followed by a delimiter — either the
# corrected snake_case boundary or the `\b` that could not do the job.
DELIMITED = re.compile(
    r"([a-z0-9]{2,})(?:" + re.escape(sf.TOK_END) + r"|\\b)")

# Left with the broken boundary on purpose, and why. `ward` is the only
# token in the vocabulary where correcting the delimiter recruits more
# labels it was not written for than labels it was: measured 2026-08-26,
# 41 rows of `upward_light_ratio`, `seaward_boundary_distance`,
# `outward_hdv_peak` and `sward_target` against 21 rows of electoral
# wards. Correcting it needs a *leading* boundary too, which also stops
# it matching today's `upward` — a change of scope, not of delimiting,
# so it is a person's call.
BOUNDARY_LEFT_FOR_A_PERSON = {("site_identity", "ward")}

# Family names that do not classify as themselves for a VOCABULARY
# reason, not a boundary one. Recorded rather than fixed: adding a token
# to a family, or reordering two families, changes what the teams see.
#
#   party_authority  -> party_other. It *was* party_adviser, because
#       `author` had no delimiter and matched inside "authority" while
#       party_adviser is declared first — so party_authority's own
#       explicit `local_planning_authority` token could never win, and
#       11,706 rows filed the decision-maker among the consultants
#       acting for the applicant. Delimiting `author` fixed that
#       (2026-08-26; party_authority 10,812 -> 19,526 rows). What is
#       left is a genuine vocabulary gap and not a boundary one: the
#       family claims `local_planning_authority`, `planning_authority`,
#       `local_authority` and `authority_name`, none of which is a
#       substring of the bare label "party_authority", so it falls
#       through to party_other. Closing it means adding a token, which
#       changes what the teams see.
#   land_quality     -> unclassified. The family is spelled out as
#       contamination, geology and remediation; it claims no token
#       containing the word "land".
#   application_admin-> unclassified. It claims `application_(reference|
#       type|number|date|status)`, and "admin" is not in that list.
SELF_CLASSIFICATION_EXCEPTIONS = {
    "party_authority": "party_other",
    "land_quality": sf.UNCLASSIFIED,
    "application_admin": sf.UNCLASSIFIED,
}


def _tokens(family) -> list[str]:
    """Literal delimited tokens declared by one family's pattern."""
    return [m.group(1) for m in DELIMITED.finditer(family.pattern)]


def _literal_runs(family) -> list[str]:
    """Every literal snake_case run in a pattern, delimited or not.

    A crude reading of the regex — `part(y|ies)` yields `part`, `ies` —
    which is fine for the one thing it is used for below: a family only
    has to be claimable by ONE of these for it to be reachable.
    """
    return [r for r in re.findall(r"[a-z0-9_]{3,}", family.pattern)]


@pytest.mark.parametrize("family", sf.FAMILIES, ids=lambda f: f.name)
def test_delimited_tokens_match_as_snake_case_words(family):
    """`eia` must be findable in `eia_status` and in `flood_eia`."""
    pattern = family.compiled()
    broken = []
    for tok in _tokens(family):
        if (family.name, tok) in BOUNDARY_LEFT_FOR_A_PERSON:
            continue
        for probe in (tok, f"{tok}_status", f"proposed_{tok}",
                      f"proposed_{tok}_status"):
            if not pattern.search(probe):
                broken.append((tok, probe))
    assert not broken, (
        f"{family.name} declares tokens it cannot match in a snake_case "
        f"label — `\\b` will not do this job, `_` is a word character:\n" +
        "\n".join(f"  `{t}` does not match {p!r}" for t, p in broken))


@pytest.mark.parametrize("family", sf.FAMILIES, ids=lambda f: f.name)
def test_no_pattern_delimits_with_a_word_boundary(family):
    """The rule itself, so a new token cannot reintroduce the defect."""
    offenders = [t for t in re.findall(r"([a-z0-9]{2,})\\b", family.pattern)
                 if (family.name, t) not in BOUNDARY_LEFT_FOR_A_PERSON]
    assert not offenders, (
        f"{family.name} delimits {offenders} with `\\b`, which cannot end a "
        f"snake_case token because `_` is a word character. Use "
        f"signal_families.TOK_END (and TOK_START where the token also has "
        f"to start one), or record a deliberate exception in "
        f"BOUNDARY_LEFT_FOR_A_PERSON with the measurement behind it.")


@pytest.mark.parametrize("family", sf.FAMILIES, ids=lambda f: f.name)
def test_a_delimited_token_still_will_not_match_glued_to_more_letters(family):
    """The boundary was corrected, not deleted.

    Dropping `\\b` altogether would make every one of these tokens a bare
    substring: `eia` inside `eiaslop`, `sac` inside `sachet`. That
    silently inflates coverage, which is the failure the module's
    docstring exists to refuse.
    """
    pattern = family.compiled()
    leaks = [tok for tok in _tokens(family)
             if pattern.search(f"{tok}zqx") or pattern.search(f"{tok}9zqx")]
    assert not leaks, (
        f"{family.name} matches {leaks} glued to more characters, so the "
        f"token is a bare substring rather than a delimited word")


def test_every_family_name_classifies_as_itself():
    """A family that cannot recognise its own name is a rule failing itself.

    This is how the `eia\\b` defect announced itself: `family_for(
    'eia_process')` returned `unclassified`.
    """
    wrong = {f.name: sf.family_for(f.name) for f in sf.FAMILIES
             if sf.family_for(f.name) != f.name}
    assert wrong == SELF_CLASSIFICATION_EXCEPTIONS, (
        f"family names that do not classify as themselves changed.\n"
        f"  expected (recorded vocabulary gaps): "
        f"{SELF_CLASSIFICATION_EXCEPTIONS}\n"
        f"  actual: {wrong}")


def test_no_family_is_unreachable():
    """Every family must be able to claim at least one of its own tokens.

    A family whose every token is swallowed by an earlier family is dead
    vocabulary: it appears in the prompt's controlled list and in the
    reader's filters, and never holds a row.
    """
    unreachable = []
    for family in sf.FAMILIES:
        probes = _tokens(family) + _literal_runs(family) + [family.name]
        if not any(sf.family_for(p) == family.name for p in probes):
            unreachable.append(family.name)
    assert not unreachable, (
        f"{unreachable} cannot claim any label built from their own "
        f"tokens — an earlier family takes all of them")


def test_the_boundary_constants_are_what_they_claim():
    """TOK_END ends a snake_case token; TOK_START starts one."""
    end = re.compile("eia" + sf.TOK_END)
    assert end.search("eia") and end.search("eia_status")
    assert end.search("flood_eia") and end.search("eia-status")
    assert not end.search("eias") and not end.search("eia2")

    start = re.compile(sf.TOK_START + "mw")
    assert start.search("mw") and start.search("mw_total")
    assert start.search("it_mw") and not start.search("300mw")


def test_the_prompt_vocabulary_is_generated_from_the_families():
    """The mapper and the prompt cannot drift apart."""
    assert sf.PROMPT_FAMILY_ENUM == [f.name for f in sf.FAMILIES] + [
        sf.UNCLASSIFIED]
    block = sf.prompt_vocabulary_block()
    for f in sf.FAMILIES:
        assert f.name in block
    assert sf.UNCLASSIFIED in block


def test_an_out_of_vocabulary_family_falls_back_to_the_label():
    """A model may not invent a family; the label decides instead."""
    assert sf.validate_family("power_grid", "anything") == "power_grid"
    assert sf.validate_family("made_up", "eia_status") == "eia_process"
    assert sf.validate_family(None, "suds_feature") == "flood_drainage"
    assert sf.validate_family(None, None) == sf.UNCLASSIFIED
