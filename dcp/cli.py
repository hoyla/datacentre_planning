"""Top-level CLI. Stage-and-source pattern follows fuel-finder."""

from __future__ import annotations

import click


@click.group()
def main() -> None:
    """UK data-centre planning investigation toolkit."""


@main.command()
@click.option("--source", required=True, help="Source name (planit, nsip, idox:<council>, ...).")
@click.option("--mode", type=click.Choice(["full", "incremental", "auto"]), default="auto")
def index(source: str, mode: str) -> None:
    """Stage 1: paginate recent applications from a source and upsert metadata."""
    click.echo(f"[index] source={source} mode={mode} — not implemented yet")


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
