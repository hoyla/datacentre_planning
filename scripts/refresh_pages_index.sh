#!/usr/bin/env bash
# Copy the latest release's integrated reader to docs/index.html so the
# GitHub Pages workflow (.github/workflows/pages.yml) can publish it.
#
# Picks the most recent data/exports/datacentre_energy_review_v*_<date>/
# folder by lexical sort (the YYYY-MM-DD suffix makes that safe).
set -euo pipefail

cd "$(dirname "$0")/.."

latest_dir=$(ls -1d data/exports/datacentre_energy_review_v*_* 2>/dev/null | sort | tail -n 1 || true)
if [ -z "${latest_dir:-}" ]; then
  echo "error: no release folder matching data/exports/datacentre_energy_review_v*_* found" >&2
  exit 1
fi

src=$(ls -1 "$latest_dir"/datacentre_energy_review_v*.html 2>/dev/null | head -n 1 || true)
if [ -z "$src" ]; then
  echo "error: no datacentre_energy_review_v*.html inside $latest_dir" >&2
  exit 1
fi

mkdir -p docs
cp "$src" docs/index.html
echo "copied $src -> docs/index.html"
