"""Top-level CLI. Stage-and-source pattern follows fuel-finder."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def main() -> None:
    """UK data-centre planning investigation toolkit."""


@main.command()
@click.option("--source", required=True, help="Source name (planit, nsip, idox:<council>, ...).")
@click.option("--mode", type=click.Choice(["full", "incremental", "auto"]), default="auto")
@click.option("--since", default="2018-01-01", help="Earliest application start_date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Latest application start_date (YYYY-MM-DD).")
@click.option("--limit", type=int, default=None, help="Cap on applications upserted (for testing).")
@click.option("--delay", "delay_seconds", type=float, default=2.5, help="Polite inter-request delay.")
@click.option(
    "--resume/--no-resume", default=True,
    help="Serve already-snapshotted URLs from cache instead of re-fetching (default: resume).",
)
def index(
    source: str, mode: str, since: str, until: str | None,
    limit: int | None, delay_seconds: float, resume: bool,
) -> None:
    """Stage 1: paginate recent applications from a source and upsert metadata."""
    if source == "planit":
        from dcp.sources import planit
        summary = planit.index(
            since=since, until=until, limit=limit,
            delay_seconds=delay_seconds, resume=resume,
        )
        for k, v in summary.items():
            click.echo(f"  {k}: {v}")
    elif source == "nsip":
        from dcp.sources import nsip
        summary = nsip.index(limit=limit)
        for k, v in summary.items():
            click.echo(f"  {k}: {v}")
    else:
        raise click.ClickException(f"Unknown source: {source!r}")


@main.command()
@click.option("--model", default=None,
              help="Ollama model name. Defaults to OLLAMA_MODEL env var, then llama3.2.")
@click.option("--limit", type=int, default=None,
              help="Cap number of applications to triage (resume-aware — counted "
                   "against pending, not total).")
@click.option("--timeout", type=float, default=180.0,
              help="Per-call Ollama timeout in seconds (default 180).")
def triage(model: str | None, limit: int | None, timeout: float) -> None:
    """Stage 2: run LLM triage over un-triaged applications.

    \b
    Resume is automatic — apps with an existing verdict for the same `model`
    are skipped. Re-run with a different `--model` to overlay a second model's
    verdicts (versioned per `(application_id, model, inserted_at)`).
    """
    import os
    import sys
    from dotenv import load_dotenv
    from pathlib import Path
    from dcp import triage as triage_mod

    load_dotenv(Path(__file__).parent.parent / ".env")
    if model is None:
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    def _progress(row: dict) -> None:
        n = row["scanned"]; total = row["pending"]
        verdict = row.get("verdict") or "ERR"
        dr = row.get("worth_deep_read") or "-"
        conf = row.get("confidence") or "-"
        ref = (row.get("ref") or "?")[:36]
        line = (
            f"  [{n:4d}/{total:4d}] {ref:36s}  v={verdict:9s}  "
            f"dr={dr:5s}  c={conf:8s}  {row['elapsed']:5.1f}s"
        )
        if row.get("error"):
            line += f"  ERR {row['error'][:60]}"
        click.echo(line)
        sys.stdout.flush()

    summary = triage_mod.run_triage(
        model=model, limit=limit, timeout=timeout, progress=_progress,
    )
    click.echo("")
    for k, v in summary.items():
        click.echo(f"  {k}: {v}")


@main.command()
@click.option("--cohort", required=True,
              help="Named retriage cohort (see RETRIAGE_COHORTS in dcp/triage.py).")
@click.option("--model", default=None,
              help="Ollama model name. Defaults to OLLAMA_MODEL env var.")
@click.option("--limit", type=int, default=None,
              help="Cap on apps re-triaged (for smoke testing).")
@click.option("--timeout", type=float, default=180.0)
def retriage(cohort: str, model: str | None, limit: int | None, timeout: float) -> None:
    """Re-triage a named cohort, appending fresh verdicts alongside originals.

    \b
    Use when a fixable bug retroactively changed the prompt input shape and
    you want a uniform-methodology subset re-run (e.g. the council-backfill
    cohort after migration 004 resolved 317 NULL `council_gss` rows). The
    `triage` table is append-only; original verdicts stay in place. The
    worklist preview selects the latest verdict per app, so downstream
    consumers see the fresh ranking automatically.
    """
    import os
    import sys
    from dotenv import load_dotenv
    from pathlib import Path
    from dcp import triage as triage_mod

    load_dotenv(Path(__file__).parent.parent / ".env")
    if model is None:
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    def _progress(row: dict) -> None:
        n = row["scanned"]; total = row["cohort_size"]
        verdict = row.get("verdict") or "ERR"
        dr = row.get("worth_deep_read") or "-"
        conf = row.get("confidence") or "-"
        ref = (row.get("ref") or "?")[:36]
        line = (
            f"  [{n:4d}/{total:4d}] {ref:36s}  v={verdict:9s}  "
            f"dr={dr:5s}  c={conf:8s}  {row['elapsed']:5.1f}s"
        )
        if row.get("error"):
            line += f"  ERR {row['error'][:60]}"
        click.echo(line)
        sys.stdout.flush()

    summary = triage_mod.run_retriage(
        cohort=cohort, model=model, limit=limit, timeout=timeout, progress=_progress,
    )
    click.echo("")
    for k, v in summary.items():
        click.echo(f"  {k}: {v}")


@main.command()
@click.option("--model", default="granite4.1:30b",
              help="Triage model whose latest verdict per app to draw from.")
@click.option("--top", "md_top", type=int, default=50,
              help="Number of top-ranked cards to include in the markdown narrative.")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("data/exports"),
              help="Directory to write `worklist_<date>.md` + `worklist_<date>.xlsx`.")
def export(model: str, md_top: int, output_dir: Path) -> None:
    """Stage 6: hand-off export for Aisha — markdown narrative + Excel companion.

    \b
    Produces two files:
      - `worklist_<YYYY-MM-DD>.md`   — top-N curated narrative cards
      - `worklist_<YYYY-MM-DD>.xlsx` — all worklist entries, sortable / filterable
    Both refresh from the latest triage verdict per app (DISTINCT ON inserted_at).
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    from dcp import export as export_mod  # local import avoids importing openpyxl when unused

    paths = export_mod.export_worklist(
        model=model, output_dir=output_dir, md_top=md_top,
    )
    click.echo(f"Wrote markdown : {paths['markdown']}")
    click.echo(f"Wrote xlsx     : {paths['xlsx']}")


@main.command("fetch-docs")
@click.option("--source", required=True, type=click.Choice(["idox"]),
              help="Portal adapter to use (currently `idox` only).")
@click.option("--model", default="granite4.1:30b",
              help="Triage model whose worklist to draw the targets from.")
@click.option("--top", type=int, default=None,
              help="Cap on the number of worklist apps to fetch (head-of-list first).")
@click.option("--delay", "delay_seconds", type=float, default=5.0,
              help="Polite inter-request delay per portal (default 5s; "
                   "longer than PlanIt because council portals are smaller-scale).")
@click.option("--data-dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("data"),
              help="Root for bytes storage. Documents land under "
                   "<data-dir>/raw/idox/<application_ref>/<sha>.pdf.")
def fetch_docs(source: str, model: str, top: int | None,
               delay_seconds: float, data_dir: Path) -> None:
    """Stage 3: fetch source-portal documents for worklist applications.

    \b
    Currently only the Idox `online-applications` / `newplanningaccess`
    canonical layout is supported. Non-Idox URLs (Ocella, Salesforce, etc.)
    are skipped with a logged note; per-portal adapters land separately.
    """
    import sys
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    from dcp.sources import idox

    def _progress(row: dict) -> None:
        ref = row.get("ref", "?")[:40]
        if row.get("error_class"):
            cls = row["error_class"]
            click.echo(f"  {ref:40s}  SKIP[{cls}]")
        else:
            click.echo(
                f"  {ref:40s}  "
                f"links={row.get('links_found', 0):3d}  "
                f"new={row.get('downloaded', 0):3d}  "
                f"skip={row.get('skipped_existing', 0):3d}  "
                f"err={row.get('errors', 0):3d}"
            )
        sys.stdout.flush()

    total = idox.fetch_worklist(
        model=model, top=top, delay_seconds=delay_seconds,
        data_dir=data_dir, progress=_progress,
    )
    click.echo("")
    for k, v in total.items():
        click.echo(f"  {k}: {v}")


@main.command("deep-read")
@click.option("--limit", type=int, default=None)
def deep_read(limit: int | None) -> None:
    """Stage 3: download docs and extract findings for triage-matched applications."""
    click.echo(f"[deep-read] limit={limit} — not implemented yet")


@main.command()
@click.option("--source", required=True, type=click.Choice(["planit"]))
@click.option("--operators-file", default="data/operators.yaml",
              help="YAML file with operator/developer name terms to search.")
@click.option("--co-search", default="dc-keywords",
              help="Description co-filter. 'dc-keywords' (default) for the standard DC "
                   "keyword union; 'none' to omit (only valid with --auth); or a custom "
                   "PlanIt search expression.")
@click.option("--auth", default=None,
              help="Restrict to a single council by name (PlanIt 'auth' param).")
@click.option("--limit-per-term", type=int, default=None,
              help="Cap on applications upserted per term (for testing).")
@click.option("--delay", "delay_seconds", type=float, default=2.5)
@click.option("--resume/--no-resume", default=True)
def operators(source: str, operators_file: str, co_search: str, auth: str | None,
              limit_per_term: int | None, delay_seconds: float, resume: bool) -> None:
    """Phase 1d: sweep by operator/developer names (PlanIt `developer=` field).

    \b
    Data-quality caveat: PlanIt's developer search runs over applicant/agent
    address+company fields, but applicant_* are usually 'See source' (not
    extracted). So in practice this matches agent_company / agent_address
    only. Also: PlanIt's backend times out on developer-only queries, so
    either --co-search or --auth must be supplied.
    """
    import yaml
    from pathlib import Path
    from dcp.sources import planit
    cfg = yaml.safe_load(Path(operators_file).read_text())
    terms: list[str] = []
    for v in cfg.values() if isinstance(cfg, dict) else []:
        if isinstance(v, list):
            terms.extend(str(x) for x in v)
    if not terms:
        raise click.ClickException(f"No operator terms found in {operators_file}")
    if co_search == "dc-keywords":
        co_search_value: str | None = planit.DC_KEYWORDS
    elif co_search == "none":
        co_search_value = None
    else:
        co_search_value = co_search
    if co_search_value is None and not auth:
        raise click.ClickException(
            "--co-search=none requires --auth to be supplied (PlanIt's developer-only "
            "queries time out on their backend)."
        )
    click.echo(f"Sweeping {len(terms)} operator terms from {operators_file}"
               f" (co_search={'<DC keywords>' if co_search == 'dc-keywords' else co_search}, auth={auth})")
    summary = planit.index_by_developers(
        terms=terms, co_search=co_search_value, auth=auth,
        limit_per_term=limit_per_term,
        delay_seconds=delay_seconds, resume=resume,
    )
    for k, v in summary.items():
        if k == "per_term":
            continue
        click.echo(f"  {k}: {v}")


@main.group()
def colocated() -> None:
    """Phase 1c: spatial sweep for energy-generation applications near DCs.

    Two-step design: `fetch` hits PlanIt and caches raw responses; `process`
    re-derives candidate links from the cache using the current keyword
    lexicon (so vocabulary changes don't require new API calls)."""


@colocated.command("fetch")
@click.option("--source", required=True, type=click.Choice(["planit"]))
@click.option("--radius", "radius_km", type=float, default=1.0)
@click.option("--limit-anchors", type=int, default=None)
@click.option("--delay", "delay_seconds", type=float, default=2.5)
@click.option("--resume/--no-resume", default=True)
def colocated_fetch(source: str, radius_km: float, limit_anchors: int | None,
                    delay_seconds: float, resume: bool) -> None:
    """Fetch spatial neighbours for each DC anchor; cache to source_snapshots."""
    from dcp.sources import planit
    summary = planit.fetch_colocated(
        radius_km=radius_km, limit_anchors=limit_anchors,
        delay_seconds=delay_seconds, resume=resume,
    )
    for k, v in summary.items():
        click.echo(f"  {k}: {v}")


@colocated.command("process")
@click.option("--radius", "radius_km", type=float, default=1.0)
def colocated_process(radius_km: float) -> None:
    """Re-derive colocated_candidates from cached spatial responses + current lexicon."""
    from dcp.sources import planit
    summary = planit.process_colocated(radius_km=radius_km)
    for k, v in summary.items():
        click.echo(f"  {k}: {v}")


@main.command("backfill-parents")
@click.option("--source", required=True, type=click.Choice(["planit"]))
@click.option("--limit", type=int, default=None,
              help="Cap on parents successfully upserted (for testing).")
@click.option("--delay", "delay_seconds", type=float, default=2.5)
@click.option("--resume/--no-resume", default=True)
@click.option("--mine-descriptions/--no-mine-descriptions", default=False,
              help="Also extract candidate parent refs from descriptions of procedural "
                   "applications that have no associated_id (off by default; noisier).")
def backfill_parents(source: str, limit: int | None, delay_seconds: float,
                     resume: bool, mine_descriptions: bool) -> None:
    """Walk procedural applications for parent-ref pointers; fetch missing parents from PlanIt.

    \b
    Procedural records (Conditions discharges, NMAs, variations of conditions,
    reserved-matters submissions) carry pointers to substantive parent
    permissions via PlanIt's `associated_id` field. The triage rubric
    correctly tags procedurals as "unrelated" because they add no substantive
    content of their own — but the *parent* often does, and may sit outside
    our 2018+ keyword sweep (e.g. Saunderton's 2008 parent 08/05740/FULEA).
    Backfilled parents are tagged `parent_backfill:<child_ref>` in
    `applications.discovered_via`.
    """
    from dcp.sources import planit
    summary = planit.backfill_parents(
        limit=limit, delay_seconds=delay_seconds, resume=resume,
        mine_descriptions=mine_descriptions,
    )
    for k, v in summary.items():
        click.echo(f"  {k}: {v}")


if __name__ == "__main__":
    main()
