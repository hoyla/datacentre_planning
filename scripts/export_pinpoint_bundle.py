#!/usr/bin/env python3
"""Flatten the staging tree into a Pinpoint-shaped bundle, under quota.

Pinpoint for Professionals gives one user 100GB across every collection
they own. The staging tree is 130.6GB in 50,615 files, so the corpus does
not fit and cannot be split its way into fitting. This produces a
derivative bundle that does: measured 42,647 files at ~64GB, leaving
~36GB of headroom.

**Pinpoint has no folders.** Zipped uploads are unsupported and the
namespace is flat, so `sites/<site>/<application>/NNN - kind.pdf` arrives
as `NNN - kind.pdf` with its site and application thrown away, and 1,483
application indexes all arrive as `_index.md`. Every output filename here
therefore carries `<site> — <application> — ` in front of it. Measured
over the whole corpus that lands at a 122-character median and a
234-character maximum, inside any sane limit.

Four reductions, in the order they run:

1. **Drawings are dropped** (5,536 files, 9.5GB). `classify_kind` calls
   them tier `skip` because they carry no extractable prose, and Pinpoint
   is a full-text index. Note this applies to *every* file, not just
   PDFs: `009 - PLAN.jpg` is as much a drawing as `009 - PLAN.pdf`, and
   an earlier pass that tiered only PDFs let 30MB of plans through.
2. **Exact duplicates are dropped** (2,432 files, 7.7GB), confirmed by
   content hash rather than by name or size. The same document is
   routinely filed against several applications for one site. In Drive
   that redundancy is correct — each application folder stands alone —
   but flattened it is pure waste, and Pinpoint would return the same
   document twice for every query that matched it.
3. **Types are sniffed, never trusted.** The portals serve files whose
   extension is a lie: 170 `.bin` files here are variously Word
   documents, Outlook messages, JPEGs and PDFs. Sniffing recovers ~450
   files that dropping "unsupported formats" would have discarded,
   including 237 Outlook messages whose kind is *Consultee Comment* —
   statutory consultee responses, tier A, the class the methodology
   calls the place disclosures live.
4. **PDFs are recompressed** to 110dpi with JPEG quality 45, keeping
   whichever of original and output is smaller. Measured over a
   289-file random sample spanning every size bucket that is a ratio of
   0.56. A flat "compress everything" was rejected because a good number
   of files *inflate* — vector site plans and already-low-resolution
   scans come back bigger — so the comparison is per file.

**No text is lost in recompression, but whitespace and reading order
move.** Checked twelve recompressed files: most extract within a few
characters of the original, and the one outlier — an air quality
assessment that appeared to shed 1,306 characters — turns out to have
lost nothing. Strip whitespace from both and they are *exactly* 105,128
characters; what changed is that letter-spaced running headers
("PR O J E C T C A M RO") re-flow, and one word moves position where
Ghostscript reordered a content stream. Every one of the 56 occurrences
of the scheme name survives.

So full-text search is unaffected — every word that was there is still
there — and a quote is still verbatim. The narrow caveat is that a quote
spanning a reordered region could extract in a different order than the
page reads, which is a reason to cite from the Drive original when
quoting across a table or a multi-column layout. Image resolution is the
only thing that genuinely degrades.

Which is the point to hold on to: **the bundle is a search index, not the
archive of record.** Drive keeps the originals at full resolution, and
`_manifest.csv` maps every file here back to the staging path, the site,
the application and the content hash it came from, so any document found
in Pinpoint can be traced to its source.

**Nothing is written outside the output directory.** The staging tree is
hard-linked to the canonical store — `data/raw/documents` shares its
inodes — so recompressing in place would silently rewrite original source
material. Every output is a new file.

**Built to be interrupted.** The full sweep takes around an hour and a
quarter, which is long enough that it will be. Three things make a
re-run safe rather than merely tolerable:

- Every output is written under a temporary name and `os.replace`d into
  place, so a file either exists complete or does not exist. A killed
  run leaves no half-written PDF that a resume would mistake for done.
- `_journal.jsonl` records each input file as it finishes, appended and
  flushed line by line. A re-run reads it, skips what it covers, and
  spends its time on the remainder. A truncated last line — the normal
  result of `kill` — costs exactly one redone file.
- `_build.log` carries timestamped progress, throughput and an ETA, so
  a sweep left running overnight can be read afterwards to see what it
  did and where it stopped.

`_manifest.csv` is rebuilt from the journal at the end of every run,
which means it is derived rather than accumulated, and re-running a
finished sweep just rewrites it. Delete the journal to force a full
rebuild.

Usage:
    .venv/bin/python scripts/export_pinpoint_bundle.py --plan
    .venv/bin/python scripts/export_pinpoint_bundle.py --limit 5
    .venv/bin/python scripts/export_pinpoint_bundle.py --jobs 10
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcp.deepread_select import classify_kind  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO / "data" / "exports" / "drive_staging" / "sites"
DEFAULT_OUT = REPO / "data" / "exports" / "pinpoint_bundle"

SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")

# Pinpoint's published per-file caps. PDFs get 1GB; everything else that
# is not audio or video gets 10MB. Files between 500MB and 1GB are
# accepted but silently split into several documents at Google's end,
# which is worth avoiding: a document that becomes three loses its
# identity in search results. Our recompression brings all but a handful
# under it anyway.
PDF_MAX = 1000 * 1024 * 1024
OTHER_MAX = 10 * 1024 * 1024

# Extensions Pinpoint accepts, by the family it sorts them into.
PASS_THROUGH = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
    ".csv", ".txt", ".rtf", ".md", ".markdown", ".doc", ".docx", ".xls",
    ".xlsx", ".ppt", ".pptx", ".eml", ".mbox", ".html", ".htm",
}
# Formats Pinpoint does not take, mapped to what they become. Office
# macro and binary variants convert rather than drop: an .xlsm is an
# .xlsx with macros, and the macros are not what anyone is searching.
CONVERT_TO_PDF = {".xlsm", ".xlsb", ".ods", ".odt", ".odp", ".xml"}

# Ghostscript profile. 110dpi and quality 45 were picked by measurement,
# not by taste: /ebook at 150dpi returned a ratio of only 0.76 and left
# the bundle over quota, while this returns 0.56 and still renders a
# scanned planning statement legibly on screen. Mono images stay at
# 200dpi because line drawings inside prose documents go to mush below
# that, and they cost little — a bilevel image compresses on runs, not
# on pixels.
GS_ARGS = [
    "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
    "-dCompatibilityLevel=1.5",
    "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Average",
    "-dColorImageResolution=110",
    "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Average",
    "-dGrayImageResolution=110",
    "-dDownsampleMonoImages=true", "-dMonoImageDownsampleType=/Subsample",
    "-dMonoImageResolution=200",
    "-dAutoFilterColorImages=false", "-dColorImageFilter=/DCTEncode",
    "-dAutoFilterGrayImages=false", "-dGrayImageFilter=/DCTEncode",
    "-dJPEGQ=45", "-dDetectDuplicateImages=true",
    "-dCompressFonts=true", "-dSubsetFonts=true",
]

MANIFEST_COLUMNS = [
    "pinpoint_filename", "tranche", "site", "application",
    "staging_path", "sha256", "kind", "tier",
    "original_bytes", "output_bytes", "action", "note",
]


def sniff(path: Path) -> str:
    """The extension a file's *contents* earn, ignoring the one it has.

    Cheap signatures cover the corpus: 92% of it is PDF and answers on
    four bytes. Only the two ambiguous containers need more work — a zip
    might be any OOXML or OpenDocument member, and an OLE compound file
    might be a `.msg`, a `.doc` or an `.xls`. Zips are read with
    `zipfile`; OLE files are handed to `file(1)`, which is a subprocess
    per file but there are only ~250 of them.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return ""
    if head[:4] == b"%PDF":
        return ".pdf"
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:2] in (b"II", b"MM"):
        return ".tif"
    if head[:5] == b"{\\rtf":
        return ".rtf"
    if head[:2] == b"BM":
        return ".bmp"
    if head[:4] == b"PK\x03\x04":
        return _sniff_zip(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return _sniff_ole(path)
    return ""


def _sniff_zip(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except (zipfile.BadZipFile, OSError):
        return ".zip"
    joined = "\n".join(names[:200])
    if "word/" in joined:
        return ".docx"
    if "xl/" in joined:
        return ".xlsx"
    if "ppt/" in joined:
        return ".pptx"
    if "mimetype" in names[:1]:
        return ".ods"
    return ".zip"


def _sniff_ole(path: Path) -> str:
    try:
        out = subprocess.run(["file", "-b", str(path)], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    if "Outlook" in out or "Composite Document File" in out and "Word" not in out:
        return ".msg"
    if "Word" in out:
        return ".doc"
    if "Excel" in out:
        return ".xls"
    return ""


def publish(tmp: Path, dst: Path) -> None:
    """Move a finished file into place in one indivisible step.

    A two-hour sweep will occasionally be interrupted, and a half-written
    output is worse than a missing one: on resume it looks finished, so
    it is never rebuilt and a truncated PDF goes to Pinpoint. Everything
    is therefore built under a temporary name on the same filesystem and
    `os.replace`d, which either happens or does not.
    """
    os.replace(tmp, dst)


def copy_atomic(src: Path, dst: Path, work: Path, tag: str) -> None:
    tmp = work / f"{tag}{dst.suffix}"
    shutil.copy2(src, tmp)
    publish(tmp, dst)


def kind_of(path: Path) -> str:
    """The council's own document description, from the filename.

    Staging names documents `NNN - <kind>.<ext>`, where the kind is the
    description the portal published. Stripping the ordering prefix
    recovers it, which is what `classify_kind` expects.
    """
    return re.sub(r"^\s*\d+\s*-\s*", "", path.stem)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def flat_name(rel: Path, ext: str) -> str:
    """`<site> — <application> — <document>.<ext>`, collision-free.

    The site key leads because it sorts and because display names are
    not unique — four sites here are called "Reading Quarry Berrys Lane
    Burghfield". Site-level files (the report and the findings CSV)
    already carry their site, courtesy of build_drive_staging.py, so
    they gain only the extension change.
    """
    parts = rel.parts
    site = parts[0] if parts else ""
    stem = Path(parts[-1]).stem
    if len(parts) >= 3:
        return f"{site} — {parts[1]} — {stem}{ext}"
    return f"{stem}{ext}" if stem.startswith(("_findings", "_site_report")) \
        else f"{site} — {stem}{ext}"


def compress_pdf(src: Path, dst: Path) -> bool:
    """Recompress, returning whether the output is worth keeping.

    Ghostscript is not told to give up when it would make things worse,
    so the caller compares. Roughly a fifth of this corpus comes back
    larger.
    """
    try:
        rc = subprocess.run(["gs", *GS_ARGS, f"-sOutputFile={dst}", str(src)],
                            capture_output=True, timeout=1800).returncode
    except (OSError, subprocess.SubprocessError):
        return False
    # A negative return code means Ghostscript was killed by a signal
    # rather than having failed on the file — which is what happens when
    # the sweep itself is interrupted. The two must not be conflated.
    # Treating a kill as "compression failed" makes the caller fall back
    # to copying the uncompressed original, and because that copy is a
    # complete, valid file, the next run sees it and marks it done. It
    # cost 73MB in place of 28.6MB on one file in an interrupt test:
    # correct content, silently four times the quota, and nothing on
    # screen to say so. Raising instead leaves the file unbuilt and
    # unjournalled, so the resume redoes it properly.
    if rc < 0:
        dst.unlink(missing_ok=True)
        raise InterruptedError("ghostscript killed by signal")
    if rc != 0 or not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        return False
    return dst.stat().st_size < src.stat().st_size


def soffice_to_pdf(src: Path, workdir: Path) -> Path | None:
    """Convert an Office/OpenDocument file to PDF, or return None.

    Only reached for files Pinpoint rejects outright or that exceed its
    10MB cap for non-PDFs. LibreOffice is slow and occasionally refuses;
    a refusal costs the document, so it is logged rather than raised.
    """
    if not SOFFICE.exists():
        return None
    try:
        subprocess.run(
            [str(SOFFICE), "--headless", "--norestore", "--convert-to", "pdf",
             "--outdir", str(workdir), str(src)],
            capture_output=True, timeout=900, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    out = workdir / (src.stem + ".pdf")
    return out if out.exists() and out.stat().st_size else None


def msg_to_eml(src: Path, dst: Path) -> bool:
    """`.msg` to `.eml`, because Pinpoint takes EML and MBOX and not MSG.

    A container change, not a conversion: the message keeps its headers,
    body and attachments. These are overwhelmingly Consultee Comments,
    so losing them would cost tier A material.
    """
    try:
        import extract_msg
    except ImportError:
        return False
    try:
        msg = extract_msg.Message(str(src))
        data = msg.asEmailMessage().as_bytes()
        msg.close()
    except Exception:
        return False
    tmp = dst.parent / "_work" / (dst.name + ".part")
    tmp.write_bytes(data)
    publish(tmp, dst)
    return True


def shrink_image(src: Path, dst: Path) -> bool:
    """Bring an oversized image under Pinpoint's 10MB cap."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(src) as im:
            im = im.convert("RGB")
            tmp = dst.parent / "_work" / (dst.name + ".part")
            for quality, scale in ((70, 1.0), (60, 0.7), (50, 0.5), (40, 0.35)):
                w, h = int(im.width * scale), int(im.height * scale)
                im.resize((w, h)).save(tmp, "JPEG", quality=quality, optimize=True)
                if tmp.stat().st_size <= OTHER_MAX:
                    publish(tmp, dst)
                    return True
            tmp.unlink(missing_ok=True)
        return False
    except Exception:
        return False


def split_text(src: Path, out_dir: Path, base: str, ext: str) -> list[Path]:
    """Split an oversized CSV or markdown into parts, keeping the header.

    Six findings CSVs exceed 10MB, the largest at 35.7MB. Truncation was
    rejected for the same reason export_notebook_bundle.py rejects it: a
    table that silently stops tells neither the reader nor the model that
    it stopped.
    """
    written: list[Path] = []
    header = b""
    with open(src, "rb") as fh:
        if ext == ".csv":
            header = fh.readline()
        part, size, buf = 1, len(header), [header] if header else []
        for line in fh:
            if size + len(line) > OTHER_MAX and buf:
                p = out_dir / f"{base} (part {part}){ext}"
                tmp = out_dir / "_work" / (p.name + ".part")
                tmp.write_bytes(b"".join(buf))
                publish(tmp, p)
                written.append(p)
                part += 1
                buf, size = ([header] if header else []), len(header)
            buf.append(line)
            size += len(line)
        if buf and size > len(header):
            p = out_dir / f"{base} (part {part}){ext}"
            tmp = out_dir / "_work" / (p.name + ".part")
            tmp.write_bytes(b"".join(buf))
            publish(tmp, p)
            written.append(p)
    return written


def process(job: tuple) -> list[dict]:
    """One input file to zero or more bundle files, with its manifest rows."""
    rel_s, src_s, out_s, sha, size = job
    rel, src, out_dir = Path(rel_s), Path(src_s), Path(out_s)
    parts = rel.parts
    site = parts[0] if parts else ""
    app = parts[1] if len(parts) >= 3 else ""
    kind = kind_of(rel)
    tier = classify_kind(kind)[0]
    row = {"site": site, "application": app, "staging_path": str(rel),
           "sha256": sha, "kind": kind, "tier": tier,
           "original_bytes": size, "tranche": "", "note": ""}

    ext = sniff(src) or src.suffix.lower()
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    tmp = work / f"{sha[:16]}{ext}"

    def done(name: str, path: Path, action: str, note: str = "") -> dict:
        r = dict(row)
        r.update(pinpoint_filename=name, output_bytes=path.stat().st_size,
                 action=action, note=note)
        return r

    try:
        if ext == ".pdf":
            name = flat_name(rel, ".pdf")
            dst = out_dir / name
            if dst.exists():
                return [done(name, dst, "cached")]
            if compress_pdf(src, tmp):
                shutil.move(str(tmp), dst)
                action = "recompressed"
            else:
                tmp.unlink(missing_ok=True)
                copy_atomic(src, dst, work, sha[:16])
                action = "copied (compression made it larger)"
            if dst.stat().st_size > PDF_MAX:
                return [done(name, dst, action, "OVER 1GB — Pinpoint will reject")]
            return [done(name, dst, action)]

        if ext == ".msg":
            name = flat_name(rel, ".eml")
            dst = out_dir / name
            if dst.exists():
                return [done(name, dst, "cached")]
            if msg_to_eml(src, dst):
                return [done(name, dst, "msg -> eml")]
            return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                     "action": "dropped", "note": "msg conversion failed"}]

        if ext in CONVERT_TO_PDF or (ext in PASS_THROUGH and ext not in
                                     {".pdf"} and size > OTHER_MAX and
                                     ext in {".doc", ".docx", ".xls", ".xlsx",
                                             ".ppt", ".pptx"}):
            name = flat_name(rel, ".pdf")
            dst = out_dir / name
            if dst.exists():
                return [done(name, dst, "cached")]
            pdf = soffice_to_pdf(src, work)
            if not pdf:
                return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                         "action": "dropped", "note": f"{ext} conversion failed"}]
            if compress_pdf(pdf, tmp):
                shutil.move(str(tmp), dst)
            else:
                shutil.move(str(pdf), dst)
            pdf.unlink(missing_ok=True)
            return [done(name, dst, f"{ext} -> pdf")]

        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff"}:
            if size <= OTHER_MAX:
                name = flat_name(rel, ext)
                dst = out_dir / name
                if not dst.exists():
                    copy_atomic(src, dst, work, sha[:16])
                return [done(name, dst, "copied")]
            name = flat_name(rel, ".jpg")
            dst = out_dir / name
            if dst.exists():
                return [done(name, dst, "cached")]
            if shrink_image(src, dst):
                return [done(name, dst, "downscaled")]
            return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                     "action": "dropped", "note": "image too large to shrink"}]

        if ext in {".csv", ".md", ".markdown", ".txt"}:
            if size <= OTHER_MAX:
                name = flat_name(rel, ext)
                dst = out_dir / name
                if not dst.exists():
                    copy_atomic(src, dst, work, sha[:16])
                return [done(name, dst, "copied")]
            base = flat_name(rel, "")
            outs = split_text(src, out_dir, base, ext)
            return [done(p.name, p, f"split into {len(outs)}") for p in outs]

        if ext in PASS_THROUGH:
            name = flat_name(rel, ext)
            dst = out_dir / name
            if dst.exists():
                return [done(name, dst, "cached")]
            if size > OTHER_MAX:
                return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                         "action": "dropped", "note": f"{ext} over 10MB cap"}]
            copy_atomic(src, dst, work, sha[:16])
            return [done(name, dst, "copied")]

        return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                 "action": "dropped", "note": f"unhandled type {ext or 'unknown'}"}]
    except InterruptedError:
        # Not this file's fault — the run is being torn down. Propagate
        # so the parent declines to journal it and the resume retries.
        raise
    except Exception as exc:  # one bad file must not end a 42,000-file sweep
        return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                 "action": "dropped", "note": f"error: {exc}"[:200]}]


def log(handle, message: str) -> None:
    """One line to the console and to the run log, timestamped.

    A sweep this long is normally left running, so the log is what
    someone reads afterwards to find out what it did and where it
    stopped. Timestamps make an interruption locatable.
    """
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    if handle:
        handle.write(line + "\n")
        handle.flush()


def read_journal(path: Path) -> dict[str, list]:
    """Input files already completed, from the append-only journal.

    Tolerates a truncated final line: a run killed mid-write leaves one,
    and the correct response is to redo that single file rather than to
    refuse to start.
    """
    done: dict[str, list] = {}
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done[rec["staging_path"]] = rec["rows"]
    return done


def collect(src_root: Path, limit: int | None) -> tuple[list, dict]:
    """Walk staging, tier it, drop drawings, and hash-dedup what is left."""
    sites = sorted(p for p in src_root.iterdir() if p.is_dir())
    if limit:
        sites = sites[:limit]
    kept, stats = [], {"seen": 0, "drawings": 0, "duplicates": 0,
                       "bytes_in": 0, "bytes_drawings": 0, "bytes_dupes": 0}
    seen: dict[str, str] = {}
    for site in sites:
        for path in sorted(site.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src_root)
            size = path.stat().st_size
            stats["seen"] += 1
            stats["bytes_in"] += size
            if classify_kind(kind_of(path))[0] == "skip":
                stats["drawings"] += 1
                stats["bytes_drawings"] += size
                continue
            sha = sha256_of(path)
            if sha in seen:
                stats["duplicates"] += 1
                stats["bytes_dupes"] += size
                continue
            seen[sha] = str(rel)
            kept.append((rel, path, sha, size))
    return kept, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, help="first N sites only")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--tranche-size", type=int, default=20_000,
                    help="max files per upload tranche (Pinpoint's daily cap)")
    ap.add_argument("--plan", action="store_true",
                    help="report what would be built, write nothing")
    args = ap.parse_args()

    if not args.src.is_dir():
        sys.exit(f"no staging tree at {args.src}")

    args.out.mkdir(parents=True, exist_ok=True)
    logf = None if args.plan else open(args.out / "_build.log", "a",
                                       encoding="utf-8")
    g = 1 << 30
    log(logf, f"scanning {args.src}")
    kept, stats = collect(args.src, args.limit)
    log(logf, f"{stats['seen']:,} files, {stats['bytes_in']/g:.1f} GB")
    log(logf, f"- {stats['drawings']:,} drawings "
              f"({stats['bytes_drawings']/g:.1f} GB)")
    log(logf, f"- {stats['duplicates']:,} duplicates "
              f"({stats['bytes_dupes']/g:.1f} GB)")
    log(logf, f"= {len(kept):,} files to convert "
              f"({sum(k[3] for k in kept)/g:.1f} GB in)")
    if args.plan:
        return

    files_dir = args.out / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    # Largest first. In walk order the pool finishes its small files and
    # then sits nearly idle while one 400MB environmental statement runs
    # alone — measured at 5.7 of 10 workers busy across a whole run.
    # Starting the long jobs first lets the short ones fill in around
    # them, which is longest-processing-time scheduling and costs one
    # sort.
    kept = sorted(kept, key=lambda k: -k[3])
    jobs = [(str(rel), str(path), str(files_dir), sha, size)
            for rel, path, sha, size in kept]

    # A two-hour sweep gets interrupted, so completed work is journalled
    # as it lands rather than held in memory until the end. The journal
    # is append-only and one line per input file: re-running reads it,
    # skips what it already covers, and spends the remaining budget on
    # the rest. Deleting it forces a full rebuild.
    journal_path = args.out / "_journal.jsonl"
    done_paths = read_journal(journal_path)
    rows = [r for group in done_paths.values() for r in group]
    if done_paths:
        log(logf, f"resuming: {len(done_paths):,} input files already journalled")
    jobs = [j for j in jobs if j[0] not in done_paths]
    log(logf, f"{len(jobs):,} to process, {args.jobs} workers")

    # Leftover parts from a killed run: nothing here is trusted, because
    # a `.part` is by definition a file that never reached its final name.
    work_dir = files_dir / "_work"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    done, t0 = 0, time.time()
    with open(journal_path, "a", encoding="utf-8") as jf:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(process, j) for j in jobs]
            try:
                for fut in as_completed(futures):
                    try:
                        got = fut.result()
                    except InterruptedError:
                        continue  # torn down mid-file; resume will redo it
                    rows.extend(got)
                    jf.write(json.dumps({"staging_path": got[0]["staging_path"],
                                         "rows": got}) + "\n")
                    jf.flush()
                    done += 1
                    if done % 250 == 0 or done == len(jobs):
                        out_b = sum(r["output_bytes"] for r in rows)
                        rate = done / max(0.1, time.time() - t0)
                        eta = (len(jobs) - done) / rate / 60
                        log(logf, f"{done:,}/{len(jobs):,}  {out_b/g:.1f} GB  "
                                  f"{rate:.1f} files/s  eta {eta:.0f} min")
            except KeyboardInterrupt:
                log(logf, "interrupted — journal is current, re-run to resume")
                pool.shutdown(cancel_futures=True)
                raise

    shutil.rmtree(work_dir, ignore_errors=True)

    # Tranches are assigned after the fact, over what actually got built,
    # so a conversion that dropped a file does not leave a hole in a
    # batch someone is about to upload.
    live = [r for r in rows if r["pinpoint_filename"]]
    live.sort(key=lambda r: (r["site"], r["application"], r["pinpoint_filename"]))
    for i, r in enumerate(live):
        r["tranche"] = f"{i // args.tranche_size + 1}"

    manifest = args.out / "_manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["staging_path"]):
            w.writerow(r)

    out_b = sum(r["output_bytes"] for r in live)
    dropped = [r for r in rows if not r["pinpoint_filename"]]
    log(logf, f"{len(live):,} files, {out_b/g:.1f} GB "
              f"({out_b / max(1, sum(k[3] for k in kept)):.2f} of input)")
    log(logf, f"tranches: {max((int(r['tranche']) for r in live), default=0)}")
    if dropped:
        reasons: dict[str, int] = {}
        for r in dropped:
            reasons[r["note"]] = reasons.get(r["note"], 0) + 1
        log(logf, f"dropped {len(dropped)}:")
        for note, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:10]:
            log(logf, f"  {n:5d}  {note}")
    log(logf, f"manifest: {manifest}")
    if logf:
        logf.close()


if __name__ == "__main__":
    main()
