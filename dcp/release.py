"""Release-folder orchestrator. Produces the full Aisha-facing bundle in one
versioned folder under `data/exports/`.

Each release looks like:

  datacentre_energy_review_v<version>_<date>/
    ├── datacentre_energy_review_v<version>.html         # integrated viewer
    ├── dc_energy_review_text_only_v<version>.md         # curated cards
    ├── dc_energy_review_spreadsheet_v<version>.xlsx     # flat xlsx
    ├── dc_energy_review_map_only_v<version>.html        # standalone map
    ├── How to read this.md                              # evergreen reader doc
    ├── Map data/
    │   ├── dc_energy_review_geo_data_v<version>.geojson  # worklist points
    │   ├── dc_energy_review_geo_data_v<version>.kml      # KML companion
    │   └── dc_energy_review_osm_power_plants_v<version>.geojson  # OSM context
    └── Self-scrutiny/
        ├── dc_energy_review_findings_verification_v<version>.md
        ├── dc_energy_review_privacy_sweep_v<version>.md
        ├── dc_energy_review_foxglove_reconciliation_v<version>.md
        └── dc_energy_review_map_spotcheck_v<version>.md

Top-level holds the journalist-facing deliverables (the integrated viewer
+ the four canonical exports); `Map data/` holds the geographic data
files that feed external tools (QGIS, kepler.gl, Google Earth);
`Self-scrutiny/` holds the defensibility-trail QA artefacts.

Versioning is manual — bump `--version` deliberately for each published
release. Dates are on the folder only, not the filenames inside.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

from dcp import export as export_mod
from dcp import map as map_mod


ROOT = Path(__file__).parent.parent


def _qa_source(stem_glob: str) -> Path | None:
    """Find the most recent existing QA artefact matching the glob under
    `data/exports/`. Returns None if no match — caller treats that as a
    skip rather than a hard error.
    """
    candidates = sorted((ROOT / "data" / "exports").glob(stem_glob))
    return candidates[-1] if candidates else None


def build_release(
    *,
    version: str,
    output_root: Path = ROOT / "data" / "exports",
    model: str = "granite4.1:30b",
    md_top: int = 50,
    osm_path: Path | None = None,
    generated_at: dt.datetime | None = None,
    rerun_findings_verification: bool = False,
    rerun_map_spotcheck: bool = False,
) -> dict[str, Path | int]:
    """Build the full release bundle. Returns a manifest of paths + counts.

    `rerun_findings_verification` — when True, re-runs
        `scripts/verify_findings.py` to regenerate; otherwise copies the
        most recent existing report.
    `rerun_map_spotcheck` — when True, re-runs `scripts/map_spot_check.py`
        (slow: ~100s of Nominatim calls). Otherwise copies the most recent
        existing report.

    The privacy sweep and Foxglove reconciliation are always copy-only
    here — they were hand-written this release and have no
    fully-automated regenerator yet.
    """
    generated_at = generated_at or dt.datetime.now()
    today = generated_at.date().isoformat()

    folder = output_root / f"datacentre_energy_review_v{version}_{today}"
    folder.mkdir(parents=True, exist_ok=True)
    map_dir = folder / "Map data"
    qa_dir = folder / "Self-scrutiny"
    map_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    # Naming. The headline integrated file uses the full word; component
    # files use the abbreviated `dc_energy_review_*` stem. Top-level
    # holds journalist-facing deliverables; subfolders hold the
    # geographic data files (Map data/) and defensibility-trail QA
    # artefacts (Self-scrutiny/).
    integrated_html = folder / f"datacentre_energy_review_v{version}.html"
    text_md         = folder / f"dc_energy_review_text_only_v{version}.md"
    spreadsheet     = folder / f"dc_energy_review_spreadsheet_v{version}.xlsx"
    map_html        = folder / f"dc_energy_review_map_only_v{version}.html"
    how_to_read     = folder / "How to read this.md"
    geojson         = map_dir / f"dc_energy_review_geo_data_v{version}.geojson"
    kml             = map_dir / f"dc_energy_review_geo_data_v{version}.kml"
    osm_geojson     = map_dir / f"dc_energy_review_osm_power_plants_v{version}.geojson"
    qa_findings     = qa_dir / f"dc_energy_review_findings_verification_v{version}.md"
    qa_privacy      = qa_dir / f"dc_energy_review_privacy_sweep_v{version}.md"
    qa_foxglove     = qa_dir / f"dc_energy_review_foxglove_reconciliation_v{version}.md"
    qa_spotcheck    = qa_dir / f"dc_energy_review_map_spotcheck_v{version}.md"

    manifest: dict[str, Path | int] = {"folder": folder, "version": version}

    # --- 1. Text-only markdown + spreadsheet (the canonical export pair).
    export_mod.export_worklist(
        model=model,
        output_dir=folder,
        md_top=md_top,
        generated_at=generated_at,
        md_path=text_md,
        xlsx_path=spreadsheet,
    )
    manifest["text_md"] = text_md
    manifest["spreadsheet"] = spreadsheet

    # --- 2. Map artefacts (standalone HTML map + geojson + kml + OSM context).
    map_result = map_mod.build_map(
        model=model,
        output_dir=folder,
        osm_path=osm_path,
        generated_at=generated_at,
        html_path=map_html,
        geojson_path=geojson,
        kml_path=kml,
        plants_geojson_path=osm_geojson,
    )
    manifest["map_html"] = map_html
    manifest["geojson"] = geojson
    manifest["kml"] = kml
    manifest["osm_geojson"] = osm_geojson
    manifest["points_mapped"] = map_result.get("points_mapped", 0)
    manifest["points_dropped_no_coords"] = map_result.get("points_dropped_no_coords", 0)

    # --- 3. Integrated viewer (split-screen reader + map).
    # Build deferred until dcp.reader is in place; for now write a
    # placeholder so the release folder is structurally complete and the
    # filename slot is reserved.
    try:
        from dcp import reader as reader_mod  # type: ignore[attr-defined]
        reader_mod.build_reader(
            model=model,
            output_path=integrated_html,
            geojson_path=geojson,
            text_md_path=text_md,
            version=version,
            generated_at=generated_at,
        )
        manifest["integrated_html"] = integrated_html
        manifest["integrated_html_status"] = "built"
    except (ImportError, AttributeError) as e:
        # Placeholder: dcp.reader not yet implemented. Release folder is
        # still useful — the other six artefacts cover the existing
        # workflow.
        integrated_html.write_text(
            f"<!doctype html><meta charset=utf-8><title>Integrated viewer (placeholder)</title>"
            f"<p>Integrated viewer not yet built ({e}). "
            f"Open <code>{map_html.name}</code> and "
            f"<code>{text_md.name}</code> side-by-side until then.</p>"
        )
        manifest["integrated_html"] = integrated_html
        manifest["integrated_html_status"] = f"placeholder: {e}"

    # --- 4. Evergreen 'How to read this'.
    src_how = ROOT / "data" / "exports" / "how_to_read_this.md"
    if src_how.exists():
        shutil.copy2(src_how, how_to_read)
        manifest["how_to_read"] = how_to_read
    else:
        manifest["how_to_read"] = None

    # --- 5. QA artefacts (defensibility trail for this release).
    # 5a. Findings verification — auto-regenerable.
    if rerun_findings_verification:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_findings.py"),
             "--output", str(qa_findings)],
            check=True,
        )
    else:
        src = _qa_source("findings_verification_*.md")
        if src:
            shutil.copy2(src, qa_findings)
    manifest["qa_findings"] = qa_findings if qa_findings.exists() else None

    # 5b. Privacy sweep — copy-only.
    src = _qa_source("privacy_sweep_*.md")
    if src:
        shutil.copy2(src, qa_privacy)
        manifest["qa_privacy"] = qa_privacy
    else:
        manifest["qa_privacy"] = None

    # 5c. Foxglove reconciliation — copy-only.
    src = _qa_source("foxglove_reconciliation_*.md")
    if src:
        shutil.copy2(src, qa_foxglove)
        manifest["qa_foxglove"] = qa_foxglove
    else:
        manifest["qa_foxglove"] = None

    # 5d. Map spot-check — auto-regenerable (but rate-limited Nominatim).
    if rerun_map_spotcheck:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "map_spot_check.py"),
             "--geojson", str(geojson),
             "--xlsx", str(spreadsheet),
             "--output", str(qa_spotcheck)],
            check=True,
        )
    else:
        src = _qa_source("map_spotcheck_*.md")
        if src:
            shutil.copy2(src, qa_spotcheck)
    manifest["qa_spotcheck"] = qa_spotcheck if qa_spotcheck.exists() else None

    return manifest
