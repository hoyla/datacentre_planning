"""Top-level CLI. Stage-and-source pattern follows fuel-finder."""

from __future__ import annotations

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
@click.option("--limit", type=int, default=None, help="Cap number of applications to triage.")
def triage(limit: int | None) -> None:
    """Stage 2: run LLM triage over un-triaged applications."""
    click.echo(f"[triage] limit={limit} — not implemented yet")


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


if __name__ == "__main__":
    main()
