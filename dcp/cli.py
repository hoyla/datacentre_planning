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
def index(source: str, mode: str, since: str, until: str | None, limit: int | None, delay_seconds: float) -> None:
    """Stage 1: paginate recent applications from a source and upsert metadata."""
    if source == "planit":
        from dcp.sources import planit
        summary = planit.index(since=since, until=until, limit=limit, delay_seconds=delay_seconds)
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


if __name__ == "__main__":
    main()
