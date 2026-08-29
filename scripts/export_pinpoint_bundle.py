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
import atexit
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
    # No magic number: the text formats. Three `.bin` files here are two
    # HTML pages and a saved RFC 822 message, all of which Pinpoint takes
    # once they are named honestly, and all of which were being dropped
    # as "unhandled" for want of a signature to match.
    return _sniff_text(path)


def _sniff_text(path: Path) -> str:
    out = _file_says(path)
    if "HTML" in out:
        return ".html"
    if "RFC 822" in out or "news or mail" in out:
        return ".eml"
    if "Rich Text Format" in out:
        return ".rtf"
    if "text" in out.lower():
        return ".txt"
    return ""


def _file_says(path: Path) -> str:
    """`file -b`, decoded leniently.

    Bytes then decode, never `text=True`: `file` echoes an OLE document's
    own Title and Author back, and those come out of Word in whatever
    code page the author used. A 0xab guillemet in one title raised
    UnicodeDecodeError and killed a sweep 93% of the way through.
    """
    try:
        raw = subprocess.run(["file", "-b", str(path)], capture_output=True,
                             timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return raw.decode("utf-8", errors="replace")


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
    """Which OLE compound document this is, from its own stream names.

    `file` alone is not enough. It reports many of these as a generic
    "Composite Document File V2", and treating that as a `.msg` — which
    an earlier version did — sent a spreadsheet to the Outlook parser,
    where it failed with "does not contain a property stream" and was
    dropped. The container's directory names are decisive and cheap:
    an Outlook message holds `__substg1.0_` streams, a Word document a
    `WordDocument` stream, a workbook a `Workbook` or `Book` stream.
    They are stored UTF-16LE, hence the interleaved nulls.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(1 << 20)
    except OSError:
        return ""

    def u16(s: str) -> bytes:
        return s.encode("utf-16-le")

    if u16("__substg1.0_") in head or u16("__properties_version") in head:
        return ".msg"
    if u16("WordDocument") in head:
        return ".doc"
    if u16("Workbook") in head or u16("Book") in head:
        return ".xls"
    if u16("PowerPoint Document") in head:
        return ".ppt"

    out = _file_says(path)
    if "Outlook" in out:
        return ".msg"
    if "Word" in out:
        return ".doc"
    if "Excel" in out:
        return ".xls"
    if "PowerPoint" in out:
        return ".ppt"
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
    tmp = work / f"{tag}.{os.getpid()}{dst.suffix}"
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


def _eml_from_msg(msg) -> bytes | None:
    """Assemble an RFC 822 message from an Outlook one, decoding leniently.

    Headers, plain body, HTML alternative and attachments — enough that
    the reporter sees who wrote to whom, when, and what they said, which
    is the whole value of a consultee response. Bytes that do not decode
    become replacement characters rather than an exception.
    """
    from email.message import EmailMessage
    try:
        em = EmailMessage()
        for header, value in (("From", getattr(msg, "sender", None)),
                              ("To", getattr(msg, "to", None)),
                              ("Cc", getattr(msg, "cc", None)),
                              ("Subject", getattr(msg, "subject", None)),
                              ("Date", getattr(msg, "date", None))):
            if value:
                em[header] = str(value)

        html = getattr(msg, "htmlBody", None)
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        body = getattr(msg, "body", None) or ""
        em.set_content(body or (html or ""))
        if html and body:
            em.add_alternative(html, subtype="html")

        for att in getattr(msg, "attachments", []) or []:
            payload = getattr(att, "data", None)
            if not isinstance(payload, bytes):
                continue
            name = (getattr(att, "longFilename", None)
                    or getattr(att, "shortFilename", None) or "attachment")
            em.add_attachment(payload, maintype="application",
                              subtype="octet-stream", filename=str(name))
        return em.as_bytes()
    except Exception:
        return None


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
    # Council mailboxes are Windows, and the bodies come out in cp1252:
    # 0x92 a curly apostrophe, 0x95 a bullet, 0x96 an en dash. Left to
    # its default of strict UTF-8, extract_msg raised on 13 of the 16
    # messages that failed the first sweep — all of them consultee
    # correspondence. cp1252 has no undefined byte sequences, so the
    # retry cannot fail the same way; latin-1 is the last resort.
    data = None
    try:
        msg = extract_msg.Message(str(src))
    except Exception:
        return False
    try:
        data = msg.asEmailMessage().as_bytes()
    except Exception:
        # `asEmailMessage` hard-codes `htmlBody.decode('utf-8')`, so no
        # constructor argument can save it — and 13 of these messages
        # carry a cp1252 byte in the HTML part (0x92 a curly apostrophe,
        # 0x96 an en dash). Assembling the message here instead, with a
        # lenient decode, keeps correspondence that is otherwise lost:
        # every one of them is a consultee response.
        data = _eml_from_msg(msg)
    finally:
        try:
            msg.close()
        except Exception:
            pass
    if not data:
        return False
    tmp = dst.parent / "_work" / f"{dst.name}.{os.getpid()}.part"
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
            tmp = dst.parent / "_work" / f"{dst.name}.{os.getpid()}.part"
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
                tmp = out_dir / "_work" / f"{p.name}.{os.getpid()}.part"
                tmp.write_bytes(b"".join(buf))
                publish(tmp, p)
                written.append(p)
                part += 1
                buf, size = ([header] if header else []), len(header)
            buf.append(line)
            size += len(line)
        if buf and size > len(header):
            p = out_dir / f"{base} (part {part}){ext}"
            tmp = out_dir / "_work" / f"{p.name}.{os.getpid()}.part"
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

    def done(name: str, path: Path, action: str, note: str = "") -> dict:
        r = dict(row)
        r.update(pinpoint_filename=name, output_bytes=path.stat().st_size,
                 action=action, note=note)
        return r

    # Everything below is inside the guard, type sniffing included. It
    # used to sit above it, on the assumption that identifying a file
    # could not fail — which is exactly the assumption that ended a sweep
    # 93% of the way through, when `file` returned a byte that would not
    # decode. In a 42,000-file batch the cost of one unreadable file must
    # be one dropped row, never the run.
    try:
        ext = sniff(src) or src.suffix.lower()
        work = out_dir / "_work"
        work.mkdir(parents=True, exist_ok=True)
        tmp = work / f"{sha[:16]}.{os.getpid()}{ext}"
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

        if ext == ".zip":
            # Not archives of convenience — these are exported email
            # threads, one per zip: a `header.txt` carrying the From,
            # To, Subject and Date, beside the message body as RTF or
            # PDF. All fifteen in this corpus are consultee
            # correspondence — HSE, Network Rail, the Lead Local Flood
            # Authority, environmental health. Dropping the container
            # dropped the response, so the members come out as
            # documents in their own right, each keeping the archive's
            # name so the thread stays reassemblable.
            outs: list[dict] = []
            stem = flat_name(rel, "")
            with zipfile.ZipFile(src) as z:
                for member in z.infolist():
                    if member.is_dir() or member.file_size == 0:
                        continue
                    m_ext = Path(member.filename).suffix.lower()
                    if m_ext not in PASS_THROUGH or member.file_size > OTHER_MAX:
                        continue
                    leaf = Path(member.filename).name
                    name = f"{stem} — {leaf}"
                    dst = out_dir / name
                    if not dst.exists():
                        tmp = work / f"{sha[:16]}.{os.getpid()}.{leaf}"
                        tmp.write_bytes(z.read(member))
                        publish(tmp, dst)
                    outs.append(done(name, dst, "unpacked from zip"))
            if outs:
                return outs
            return [{**row, "pinpoint_filename": "", "output_bytes": 0,
                     "action": "dropped", "note": "zip held nothing usable"}]

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
    ap.add_argument("--already-uploaded", type=Path, metavar="MANIFEST_CSV",
                    help="a _manifest.csv from a bundle already linked into "
                         "Pinpoint. Its documents are skipped entirely — not "
                         "re-converted, not re-linked — and only what is new "
                         "is built, into tranches numbered after the highest "
                         "that manifest records. The old bundle's output "
                         "files are NOT needed; the manifest alone is "
                         "enough, which is the point.")
    ap.add_argument("--tranche-size", type=int, default=20_000,
                    help="max files per upload tranche (Pinpoint's daily cap)")
    ap.add_argument("--plan", action="store_true",
                    help="report what would be built, write nothing")
    args = ap.parse_args()

    if not args.src.is_dir():
        sys.exit(f"no staging tree at {args.src}")

    args.out.mkdir(parents=True, exist_ok=True)
    # Refuse to run twice against one output directory. Two sweeps were
    # once started by different people minutes apart and neither noticed
    # for over an hour: they raced on identical `_work` temp names, each
    # deleted the other's in-progress files at startup, half the corpus
    # was converted twice, and the journal recorded sizes that no longer
    # matched what was on disk. Nothing was corrupted in the end, but the
    # manifest is the provenance record and it had already drifted from
    # the files it describes. A lock is cheaper than proving that never
    # matters.
    lock = args.out / "_running.lock"
    if not args.plan:
        if lock.exists():
            try:
                other = int(lock.read_text().split()[0])
                os.kill(other, 0)
            except (ValueError, IndexError, ProcessLookupError, OSError):
                other = None
            if other:
                sys.exit(f"another sweep (pid {other}) is already writing to "
                         f"{args.out}\nwait for it, or remove {lock} if it died")
            lock.unlink(missing_ok=True)
        lock.write_text(f"{os.getpid()} {dt.datetime.now().isoformat()}\n")
        atexit.register(lambda: lock.unlink(missing_ok=True))
    logf = None if args.plan else open(args.out / "_build.log", "a",
                                       encoding="utf-8")
    g = 1 << 30
    log(logf, f"scanning {args.src}")
    kept, stats = collect(args.src, args.limit)
    log(logf, f"{stats['seen']:,} files, {stats['bytes_in']/g:.1f} GB")

    # Documents already in Pinpoint are dropped here, before conversion,
    # rather than at tranche time. Skipping late would still recompress
    # 42,000 PDFs to produce files nobody uploads, and would need the
    # previous bundle's 64GB on disk to recognise them as cached — the
    # manifest alone cannot do that, because "cached" means the output
    # file exists. Keyed on the source content hash, not the staging
    # path, because paths move: today's British Museum partition renamed
    # a site folder and every path under it (Luke, 2026-08-28).
    prior_tranche = 0
    done_sha: set[str] = set()
    prior_tranche_of: dict[str, str] = {}
    if args.already_uploaded:
        with open(args.already_uploaded, encoding="utf-8-sig", newline="") as fh:
            prior = list(csv.DictReader(fh))
        done_sha = {r["sha256"] for r in prior if r.get("sha256")}
        # The journal never carries a tranche — it is written during
        # conversion, before tranches exist — so the only record of which
        # batch an uploaded file went out in is the manifest we were
        # handed. Keep it, or re-numbering loses the audit trail.
        prior_tranche_of = {r["sha256"]: r.get("tranche", "")
                            for r in prior if r.get("sha256")}
        prior_tranche = max((int(r["tranche"]) for r in prior
                             if str(r.get("tranche", "")).isdigit()), default=0)
        before = len(kept)
        kept = [k for k in kept if k[2] not in done_sha]
        log(logf, f"- {before - len(kept):,} already uploaded "
                  f"({len(done_sha):,} in {args.already_uploaded.name}, "
                  f"tranches 1-{prior_tranche})")
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

    # The journal spans the whole bundle's history, so it holds the
    # previous tranches too — and `--already-uploaded` filtered the
    # *conversion* list, not this one. Left unfiltered, an incremental
    # run re-tranches all 49,000 files into fresh batches and then tries
    # to hard-link 42,000 outputs that were deleted once they were in
    # Pinpoint, which is exactly how the 2026-08-29 run died on its
    # first link. Prior rows keep their original tranche and stay in the
    # manifest — that is the record of what was uploaded when — but they
    # take no part in tranching or in building the upload folders.
    prior_rows: list[dict] = []
    if done_sha:
        fresh = []
        for r in rows:
            if r.get("sha256") in done_sha:
                r["tranche"] = prior_tranche_of.get(r["sha256"], r.get("tranche", ""))
                prior_rows.append(r)
            else:
                fresh.append(r)
        rows = fresh
        log(logf, f"{len(prior_rows):,} journalled rows are already uploaded "
                  f"— kept in the manifest, excluded from this tranche")
    jobs = [j for j in jobs if j[0] not in done_paths]
    log(logf, f"{len(jobs):,} to process, {args.jobs} workers")

    # Leftover parts from a killed run: nothing here is trusted, because
    # a `.part` is by definition a file that never reached its final name.
    work_dir = files_dir / "_work"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    done, failed, t0 = 0, 0, time.time()
    with open(journal_path, "a", encoding="utf-8") as jf:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(process, j) for j in jobs]
            try:
                for fut in as_completed(futures):
                    try:
                        got = fut.result()
                    except InterruptedError:
                        continue  # torn down mid-file; resume will redo it
                    except Exception as exc:
                        # A worker died in a way its own guard could not
                        # catch. Not journalling it means the resume
                        # retries it; ending the sweep would throw away
                        # everything still queued behind it.
                        failed += 1
                        log(logf, f"worker failed, will retry on resume: "
                                  f"{type(exc).__name__}: {exc}"[:200])
                        continue
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
    #
    # They break on site boundaries. Pinpoint takes 20,000 files per
    # upload, and the arithmetic would happily cut a site in half — but
    # an upload is a unit of work someone watches and re-runs when it
    # fails, and "Saunderton is half in" is a far worse thing to reason
    # about at that moment than an uneven batch. Sites stay whole; the
    # counts come out roughly even because no single site is large
    # relative to the target.
    live = [r for r in rows if r["pinpoint_filename"]]
    live.sort(key=lambda r: (r["site"], r["application"], r["pinpoint_filename"]))

    by_site: dict[str, list[dict]] = {}
    for r in live:
        by_site.setdefault(r["site"], []).append(r)
    n_tranches = max(1, -(-len(live) // args.tranche_size))
    target = -(-len(live) // n_tranches)

    # Fill each tranche to its share and move on, rather than breaking
    # only when the target is exceeded: the latter lets the final
    # tranche absorb everything left over, which put 15,555 files in a
    # batch aimed at 14,096 while the first held 12,709. Sites are still
    # never split — the boundary moves to whichever side leaves the
    # batch closer to its share.
    counts = [0] * n_tranches
    tranche = 0
    for site in sorted(by_site):
        group = by_site[site]
        if tranche < n_tranches - 1 and counts[tranche]:
            with_site = counts[tranche] + len(group)
            if abs(with_site - target) > abs(counts[tranche] - target) \
                    or with_site > args.tranche_size:
                tranche += 1
        for r in group:
            r["tranche"] = str(tranche + 1 + prior_tranche)
        counts[tranche] += len(group)

    manifest = args.out / "_manifest.csv"
    # The runbook points --already-uploaded at this very file, so the run
    # overwrites its own input. That is fine when it succeeds and fatal
    # when it does not: the 2026-08-29 run died after the write, taking
    # the record of tranches 1-3 with it. Keep the old one first — it is
    # 23MB against a 64GB bundle, and it is the only place the tranche a
    # document went out in is written down.
    if manifest.exists():
        shutil.copy2(manifest, manifest.with_suffix(".csv.prev"))
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows + prior_rows, key=lambda r: r["staging_path"]):
            w.writerow(r)

    # The tranche was previously only a column in the manifest, which
    # made it a fiction: there was nothing to drag into a browser, just
    # 42,000 files in one directory and a spreadsheet saying which
    # notional third each belonged to. These are hard links, so three
    # browsable upload folders cost directory entries rather than a
    # second copy of 61GB.
    upload = args.out / "upload"
    shutil.rmtree(upload, ignore_errors=True)
    absent = []
    for r in live:
        d = upload / f"tranche_{r['tranche']}"
        d.mkdir(parents=True, exist_ok=True)
        target_path = d / r["pinpoint_filename"]
        src = files_dir / r["pinpoint_filename"]
        if target_path.exists():
            continue
        if not src.exists():
            # Report the whole set at the end rather than raising here.
            # Dying on the first one leaves a directory that looks like a
            # finished tranche and is silently short — the worst of the
            # three outcomes for someone about to drag it into a browser.
            absent.append(r["pinpoint_filename"])
            continue
        try:
            os.link(src, target_path)
        except OSError:
            shutil.copy2(src, target_path)
    log(logf, f"upload folders: {upload}")
    if absent:
        log(logf, f"!! {len(absent):,} files are in the manifest but not in "
                  f"{files_dir} — the tranche is incomplete. First: {absent[0]}")
    for t in sorted({r["tranche"] for r in live}, key=int):
        members = [r for r in live if r["tranche"] == t]
        sites = len({r["site"] for r in members})
        log(logf, f"  tranche_{t}: {len(members):,} files, "
                  f"{sum(r['output_bytes'] for r in members)/g:.1f} GB, "
                  f"{sites} sites")

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
