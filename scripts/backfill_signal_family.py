"""Fill `findings.signal_family` where it was never written.

Migration 009 added the column and dcp/signal_families.py supplies the
derivation, but two populations of rows never got one:

  * 557,747 findings from the three OpenAI runs (2026-08-10/11). The
    INSERT in scripts/deepread_escalate_openai.py omitted
    `signal_family` and `family_source` from its column list from the day
    it was written. Fixed at source 2026-08-26; this is the arrears.
  * 49,039 local-model findings from 2026-08-07 to 08-09, written before
    the column existed.

Why it mattered rather than merely being untidy: two reader panels select
on the family alone — `site_profile.EIA_TEXTS_SQL` (`signal_family =
'eia_process'`) and `PARTIES_SQL` (`signal_family LIKE 'party_%'`). NULL
matches neither, and matches silently, so 46% of the corpus was invisible
to both and the panels looked like an absence of evidence. The
water/cooling query has an `OR value_text ~*` arm and was only partly
affected.

Legitimate under the project's third principle because nothing original
is touched. `signal_type` is what the model emitted and stays exactly as
it is; `signal_family` is an inferred index stored beside it, currently
absent, and it is recomputable from the label at any time. Only rows
where it IS NULL are written, so this can never overwrite a family a
model actually stated.

`family_source` is set to 'derived' — the honest value. Nothing here came
from a model naming its own family: prompt v1.0 never asked, and the
OpenAI structured-output schema has no such field.

Labels the mapper cannot place go to `unclassified` and are COUNTED and
shown, not quietly bucketed. An honest measure of what the taxonomy does
not cover is the point; see the module docstring in dcp/signal_families.py.

`--rederive-unclassified` is the second half of that honesty. The column
is derived, so when the mapper improves, the rows it could not place
before are simply recomputed — no re-read, no model call, twelve seconds.
It selects `signal_family = 'unclassified' AND family_source = 'derived'`:
only rows THIS derivation produced. A model that looked at a finding and
honestly answered "unclassified" said something, and a later regex is not
entitled to overrule it, so `family_source = 'model'` is excluded — by
the same guard, repeated inside the UPDATE, that protects the NULL pass.
Nothing here can move a row INTO `unclassified`; a label the mapper still
cannot place is left exactly as it is.

Usage:
    scripts/backfill_signal_family.py --dry-run
    scripts/backfill_signal_family.py --dry-run --model-like 'openai:%'
    scripts/backfill_signal_family.py --apply  --model-like 'openai:%'
    scripts/backfill_signal_family.py --apply  --rederive-unclassified
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402
from dcp import signal_families  # noqa: E402

# Labels per UPDATE. The work is grouped by derived family and driven by
# `signal_type = ANY(...)`, which turns 600,000 row updates into a few
# hundred statements — but an unbounded array would build one enormous
# query plan, so it is chunked.
LABEL_CHUNK = 2000


def _where(model_like: str | None, rederive: bool,
           from_family: str | None = None) -> tuple[str, list]:
    """The rows in scope, as one predicate reused for count and UPDATE.

    Three scopes, never combined: rows that never got a family, rows
    this same derivation could not place, or rows a *named* family
    holds that the mapper no longer derives. `family_source =
    'derived'` in the second and third is what keeps a model's own
    answer out of reach.

    The third exists because a mapper correction can move rows that are
    already filed somewhere plausible, which the `unclassified` scope
    cannot see. It overwrites a family a reader can currently browse, so
    it names the family it is emptying rather than sweeping every
    derived row: the change stays auditable, and a correction that
    misfires is bounded by the family it was pointed at.
    """
    if from_family:
        sql = "signal_family = %s AND family_source = 'derived'"
    elif rederive:
        sql = (f"signal_family = '{signal_families.UNCLASSIFIED}' "
               f"AND family_source = 'derived'")
    else:
        sql = "signal_family IS NULL"
    params: list = [from_family] if from_family else []
    if model_like:
        sql += " AND model LIKE %s"
        params.append(model_like)
    return sql, params


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-like", default=None, metavar="PATTERN",
                    help="Restrict to models matching this SQL LIKE "
                         "pattern, e.g. 'openai:%%'. Default: every row "
                         "with a NULL family.")
    ap.add_argument("--rederive-unclassified", action="store_true",
                    help="Recompute rows already stored as 'unclassified' "
                         "by a previous derivation, instead of rows with a "
                         "NULL family. For after the mapper improves. A "
                         "model-stated family is never in scope.")
    ap.add_argument("--rederive-from-family", default=None, metavar="FAMILY",
                    help="Recompute rows this family currently holds, for "
                         "after a mapper correction moves labels that were "
                         "already filed somewhere plausible — which "
                         "--rederive-unclassified cannot see. Overwrites a "
                         "family readers can browse, so it names the one it "
                         "is emptying. A model-stated family is never in "
                         "scope.")
    ap.add_argument("--apply", action="store_true",
                    help="Write. Without it nothing is written.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("pass --dry-run or --apply")
    if args.rederive_from_family and args.rederive_unclassified:
        ap.error("--rederive-from-family and --rederive-unclassified are "
                 "separate scopes; pass one")

    rederive = args.rederive_unclassified
    scope = (f"currently filed as {args.rederive_from_family!r}"
             if args.rederive_from_family else
             "stored 'unclassified' by a previous derivation"
             if rederive else "a NULL signal_family")
    where, params = _where(args.model_like, rederive,
                           args.rederive_from_family)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM findings WHERE {where}",
                        params)
            total = cur.fetchone()[0]
            # DISTINCT labels, not rows: the derivation is a pure function
            # of the label, so 600,000 rows are a few tens of thousands of
            # distinct decisions.
            cur.execute(
                f"SELECT signal_type, count(*) FROM findings WHERE {where} "
                f"GROUP BY 1 ORDER BY 2 DESC", params)
            labels = cur.fetchall()
        print(f"rows with {scope}: {total:,}")
        print(f"distinct signal_type labels among them: {len(labels):,}")
        if not total:
            print("nothing in scope")
            return 0

        by_family: dict[str, list[str]] = {}
        rows_by_family: dict[str, int] = {}
        for label, n in labels:
            fam = signal_families.family_for(label)
            by_family.setdefault(fam, []).append(label)
            rows_by_family[fam] = rows_by_family.get(fam, 0) + n

        print("\nderived families (rows, distinct labels):")
        for fam, n in sorted(rows_by_family.items(), key=lambda kv: -kv[1]):
            print(f"  {fam:26} {n:>9,}  {len(by_family[fam]):>7,} labels")

        unc = signal_families.UNCLASSIFIED
        n_unc = rows_by_family.get(unc, 0)
        print(f"\n{unc}: {n_unc:,} rows ({100 * n_unc / total:.1f}% of the "
              f"scope) across {len(by_family.get(unc, [])):,} labels the "
              f"mapper cannot place. They are stored as '{unc}', not forced "
              f"into a bucket." +
              (" Re-deriving leaves them exactly as they are."
               if rederive else ""))
        if by_family.get(unc):
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT signal_type, count(*) FROM findings "
                    f"WHERE {where} AND signal_type = ANY(%s) "
                    f"GROUP BY 1 ORDER BY 2 DESC LIMIT 15",
                    params + [by_family[unc]])
                print("  commonest unclassified labels:")
                for lbl, n in cur.fetchall():
                    print(f"    {n:>7,}  {lbl}")

        if not args.apply:
            print("\ndry run — nothing written")
            return 0

        t0 = time.time()
        written = 0
        for fam, lbls in sorted(by_family.items()):
            if rederive and fam == unc:
                # Already stored as 'unclassified'; writing it again
                # would dirty the row to say nothing.
                print(f"  {fam:26} unchanged, {rows_by_family[fam]:,} rows")
                continue
            for i in range(0, len(lbls), LABEL_CHUNK):
                chunk = lbls[i:i + LABEL_CHUNK]
                with conn.cursor() as cur:
                    # The scope guard is repeated in the UPDATE itself,
                    # not just in the selection above: a concurrent
                    # writer could have set a family between the two, and
                    # a model-stated family must never be overwritten by
                    # a derived one.
                    cur.execute(
                        f"UPDATE findings SET signal_family = %s, "
                        f"family_source = 'derived' "
                        f"WHERE {where} AND signal_type = ANY(%s)",
                        [fam] + params + [chunk])
                    written += cur.rowcount
                conn.commit()
            print(f"  {fam:26} written, running total {written:,}")
        verb = "re-derived" if rederive else "backfilled"
        print(f"\n{verb} {written:,} rows in {time.time() - t0:.0f}s")

        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM findings WHERE {where}",
                        params)
            left = cur.fetchone()[0]
        print(f"rows still matching this scope: {left:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
