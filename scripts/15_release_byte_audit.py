#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 15 : RELEASE BYTE AUDIT   (15_release_byte_audit.py, v1.1.1)
===============================================================================

CHANGE HISTORY
--------------
  v1.1.1  When MANIFEST-RELEASE.txt lists the same path more than once, because a
          later dated amendment re-records a new hash for a file that changed,
          the LAST entry for that path is the current one and the only one
          audited. Each earlier entry is reported in its own section,
          SUPERSEDED ENTRIES (same path, re-recorded by a later amendment),
          with the path, the amendment block that re-recorded it (the block
          holding the next entry for the path) and whether the current entry
          verifies. An earlier entry never goes under FILES NEEDING A HUMAN
          LOOK on its own account; the path goes there only if its current
          entry fails. The moved-path handling of v1.1.0 is unchanged and works
          on current entries only, so a path that is both moved and re-recorded
          is audited once (its current entry, at the new path) and its earlier
          entries are listed as superseded. Block labels are taken from the
          nearest preceding "amendment" comment line that is not an "... ends"
          line; entries before any amendment are labelled "original manifest".
          The report CSV gains one row per earlier entry, with only path, hash,
          size and superseded_status filled.
  v1.1.0  Reads the dated amendment blocks of MANIFEST-RELEASE.txt. Every
          superseded mapping, a comment line "#   <old path>  ->  <new path>",
          is parsed (chains are followed). A manifest entry whose path is
          superseded is no longer audited at its old path, which no longer
          exists; instead:
            moved, unchanged   the NEW path reproduces the entry's own hash
                               (in any of the forms below, on disk and in HEAD)
            moved and changed  the new path does not reproduce the old hash,
                               but the new path is itself a manifest entry
                               (listed under an amendment's "Added entries")
                               and that entry verifies; e.g. the round-1 sheets
                               that lost their numbered_text column
          Both are reported in their own section, SUPERSEDED PATHS, with old
          path, new path and result, and not under FILES NEEDING A HUMAN LOOK.
          A superseded entry goes there only if its new path is missing, or its
          bytes match neither the old hash nor a verifying entry of its own.
          Superseded old paths are not reported as "in the manifest but not
          tracked in git". The report CSV gains columns superseded_to and
          superseded_status; for a superseded row the disk_*/head_* columns
          describe the new path.
  v1.0.0  First version.

WHAT WE CHECK (plain language)
------------------------------
The public release carries MANIFEST-RELEASE.txt, a list of SHA-256 hashes.
Those hashes are byte-level claims. For every file the manifest lists, this
script asks two questions:

  1. Which byte form of the file NOW ON DISK reproduces the manifest hash?
  2. Which byte form of the file STORED IN GIT (HEAD, i.e. what GitHub serves)
     reproduces the manifest hash?

Forms tried, in this order:
  raw      the bytes exactly as they are
  lf       every CRLF pair turned into LF
  nocr     every CR byte removed (differs from lf only if a lone CR exists)
  crlf     the lf form, then every LF turned into CRLF
  csvrec   the lf form with CRLF restored ONLY at record boundaries, i.e.
           outside double-quoted fields -- what Excel writes (.csv files only)

WHAT THE RESULT MEANS
---------------------
  raw      the file is byte-identical to what the manifest hashed
  lf/crlf/nocr/csvrec
           same content, different line endings; fixable without touching
           content, and the manifest stays as it is
  none     a real content difference; must be inspected by hand before
           anything is committed

The script also lists files tracked in git that the manifest does not cover,
and manifest entries that git does not track.

THIS SCRIPT IS READ-ONLY. It writes one report CSV and prints a summary.
"""
import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import time
from multiprocessing import Pool, cpu_count

VERSION = "1.1.1"
FORMS = ("raw", "lf", "nocr", "crlf", "csvrec")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def csv_record_crlf(lf_bytes):
    """CRLF at record boundaries only: LF inside double-quoted fields is kept."""
    out = bytearray()
    inq = False
    for c in lf_bytes:
        if c == 0x22:            # "
            inq = not inq
        if c == 0x0A and not inq:
            out += b"\r\n"
        else:
            out.append(c)
    return bytes(out)


def forms_of(b, is_csv):
    lf = b.replace(b"\r\n", b"\n")
    d = {
        "raw": sha(b),
        "lf": sha(lf),
        "nocr": sha(b.replace(b"\r", b"")),
        "crlf": sha(lf.replace(b"\n", b"\r\n")),
        "csvrec": sha(csv_record_crlf(lf)) if is_csv else None,
    }
    return d


def which_form(fd, target):
    for f in FORMS:
        if fd.get(f) == target:
            return f
    return "none"


def git_bytes(release, rel):
    try:
        r = subprocess.run(["git", "-C", release, "show", "HEAD:" + rel],
                           capture_output=True, check=True)
        return r.stdout
    except subprocess.CalledProcessError:
        return None


def audit_one(args):
    release, rel, want_hash, want_bytes = args
    is_csv = rel.lower().endswith(".csv")
    p = os.path.join(release, rel)
    row = {"path": rel, "manifest_sha": want_hash, "manifest_bytes": want_bytes,
           "disk_bytes": "", "disk_form": "", "disk_sha_raw": "",
           "head_bytes": "", "head_form": "", "head_sha_raw": "",
           "disk_has_cr": "", "head_has_cr": "", "bom": ""}
    if os.path.isfile(p):
        with open(p, "rb") as f:
            b = f.read()
        fd = forms_of(b, is_csv)
        row.update(disk_bytes=len(b), disk_form=which_form(fd, want_hash),
                   disk_sha_raw=fd["raw"], disk_has_cr=int(b"\r" in b),
                   bom=int(b.startswith(b"\xef\xbb\xbf")))
    else:
        row.update(disk_form="MISSING")
    g = git_bytes(release, rel)
    if g is None:
        row.update(head_form="NOT IN GIT")
    else:
        fg = forms_of(g, is_csv)
        row.update(head_bytes=len(g), head_form=which_form(fg, want_hash),
                   head_sha_raw=fg["raw"], head_has_cr=int(b"\r" in g))
    return row


def read_manifest(path):
    entries = []
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            entries.append((parts[0], int(parts[1]), " ".join(parts[2:])))
    return entries


SUPERSEDE = re.compile(r"^#\s+(\S+)\s+->\s+(\S+)\s*$")
BLOCK = re.compile(r"^#[\s-]*(amendment\s+\d{4}-\d{2}-\d{2}.*?)[\s-]*$", re.I)


def read_manifest_blocks(path):
    """Every entry line in file order, with the amendment block it belongs to."""
    out, label = [], "original manifest"
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            if line.startswith("#"):
                m = BLOCK.match(line)
                if m and not re.search(r"\bends\b", m.group(1)):
                    label = m.group(1).split("): ")[0] + (")" if "): " in m.group(1) else "")
                    label = label[:100]
                continue
            parts = line.split()
            if len(parts) >= 3:
                out.append((parts[0], int(parts[1]), " ".join(parts[2:]), label))
    return out


def read_superseded(path):
    """{old path: final new path} from the amendment blocks' superseded lines."""
    step = {}
    with open(path, "rb") as f:
        for raw in f:
            m = SUPERSEDE.match(raw.decode("utf-8", "replace").rstrip("\r\n"))
            if m:
                step[m.group(1)] = m.group(2)
    final = {}
    for old in step:
        new, seen = step[old], {old}
        while new in step and new not in seen:      # follow chains old -> mid -> new
            seen.add(new)
            new = step[new]
        final[old] = new
    return final


def ok_row(r):
    return r["disk_form"] not in ("none", "MISSING") and r["head_form"] not in ("none", "NOT IN GIT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True, help="path of the release working copy")
    ap.add_argument("--out", required=True, help="report CSV to write")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count() - 1))
    a = ap.parse_args()
    release = os.path.abspath(a.release)
    t0 = time.time()
    print("=" * 78)
    print(f"PLEF V2 -- SCRIPT 15 : RELEASE BYTE AUDIT   v{VERSION}")
    print("=" * 78)
    print(f"  release : {release}")
    print(f"  started : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(f"  workers : {a.workers}")

    man = os.path.join(release, "MANIFEST-RELEASE.txt")
    all_entries = read_manifest_blocks(man)
    last = {}
    for i, e in enumerate(all_entries):
        last[e[2]] = i
    # the current entry for a path is its last one; only current entries are audited
    entries = [(h, nb, rel) for i, (h, nb, rel, _) in enumerate(all_entries) if last[rel] == i]
    earlier = []
    for i, (h, nb, rel, blk) in enumerate(all_entries):
        if last[rel] != i:
            nxt = next(all_entries[j][3] for j in range(i + 1, len(all_entries)) if all_entries[j][2] == rel)
            earlier.append((h, nb, rel, blk, nxt))
    superseded = read_superseded(man)
    print(f"  manifest entries : {len(all_entries)} lines, {len(entries)} current "
          f"({len(earlier)} earlier entries re-recorded by a later amendment)")
    print(f"  superseded paths : {len(superseded)} (from dated amendment blocks)")
    head = subprocess.run(["git", "-C", release, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"  git HEAD         : {head}")

    regular = [(h, nb, rel) for (h, nb, rel) in entries if rel not in superseded]
    moved = [(h, nb, rel) for (h, nb, rel) in entries if rel in superseded]
    jobs = [(release, rel, h, nb) for (h, nb, rel) in regular]
    # a superseded entry is audited at its NEW path against its own (old) hash
    jobs += [(release, superseded[rel], h, nb) for (h, nb, rel) in moved]
    with Pool(a.workers) as pool:
        out = pool.map(audit_one, jobs)
    rows = out[:len(regular)]
    for r in rows:
        r["superseded_to"], r["superseded_status"] = "", ""
    by_path = {r["path"]: r for r in rows}
    srows = []
    for (h, nb, rel), r in zip(moved, out[len(regular):]):
        new = superseded[rel]
        r = dict(r, path=rel, superseded_to=new)
        own = by_path.get(new)
        if ok_row(r):
            r["superseded_status"] = "moved, unchanged: new path reproduces the entry's hash"
        elif own is not None and ok_row(own):
            r["superseded_status"] = "moved and changed: new path verified against its own added entry"
        elif not os.path.isfile(os.path.join(release, new)):
            r["superseded_status"] = "DEFECT: new path missing"
        else:
            r["superseded_status"] = ("DEFECT: new path matches neither the old hash nor a verifying entry of its own")
        srows.append(r)

    # earlier entries for a re-recorded path: reported, never audited on their own
    cur_ok = {r["path"]: ok_row(r) for r in rows}
    cur_ok.update({r["path"]: not r["superseded_status"].startswith("DEFECT") for r in srows})
    erows = []
    for (h, nb, rel, blk, nxt) in earlier:
        ok = cur_ok.get(rel, False)
        erows.append({"path": rel, "manifest_sha": h, "manifest_bytes": nb,
                      "superseded_status": f"earlier entry ({blk}); re-recorded by {nxt}; current entry "
                                           + ("verifies" if ok else "FAILS (see FILES NEEDING A HUMAN LOOK)"),
                      "_from": blk, "_by": nxt, "_ok": ok})

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cols = ["path", "manifest_sha", "manifest_bytes", "disk_bytes", "disk_form",
            "disk_has_cr", "bom", "disk_sha_raw", "head_bytes", "head_form",
            "head_has_cr", "head_sha_raw", "superseded_to", "superseded_status"]
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows + srows + erows)

    def tally(key):
        c = {}
        for r in rows:
            c[r[key]] = c.get(r[key], 0) + 1
        return c

    print()
    print("DISK vs MANIFEST -- which form of the file on disk reproduces the hash")
    print("-" * 78)
    for k, v in sorted(tally("disk_form").items(), key=lambda x: -x[1]):
        print(f"  {k:<10} {v:>4}")
    print()
    print("GIT HEAD vs MANIFEST -- which form of the committed file reproduces the hash")
    print("-" * 78)
    for k, v in sorted(tally("head_form").items(), key=lambda x: -x[1]):
        print(f"  {k:<10} {v:>4}")

    print()
    print("PER-FILE TABLE (path | disk_form | head_form | disk_has_cr | head_has_cr | bom)")
    print("-" * 78)
    for r in rows:
        print(f"  {r['path']:<48} {r['disk_form']:<8} {r['head_form']:<10} "
              f"{r['disk_has_cr']!s:>2} {r['head_has_cr']!s:>2} {r['bom']!s:>2}")

    print()
    print("SUPERSEDED PATHS (moved by a dated amendment; verified at their new path)")
    print("-" * 78)
    if not srows:
        print("  none")
    for r in srows:
        print(f"  {r['path']}")
        print(f"      -> {r['superseded_to']}   disk={r['disk_form']} head={r['head_form']}")
        print(f"      {r['superseded_status']}")
    n_un = sum(1 for r in srows if r["superseded_status"].startswith("moved, unchanged"))
    n_ch = sum(1 for r in srows if r["superseded_status"].startswith("moved and changed"))
    print(f"  {len(srows)} superseded: {n_un} moved unchanged, {n_ch} moved and changed, "
          f"{len(srows) - n_un - n_ch} defects")

    print()
    print("SUPERSEDED ENTRIES (same path, re-recorded by a later amendment)")
    print("-" * 78)
    if not erows:
        print("  none")
    for r in erows:
        print(f"  {r['path']}")
        print(f"      earlier entry ({r['_from']}) sha {r['manifest_sha'][:12]}... {r['manifest_bytes']} bytes")
        print(f"      re-recorded by: {r['_by']}")
        print(f"      current entry: {'verifies' if r['_ok'] else 'FAILS -- see FILES NEEDING A HUMAN LOOK'}")
    print(f"  {len(erows)} earlier entries; {sum(1 for r in erows if r['_ok'])} with a verifying current entry")

    bad = [r for r in rows if not ok_row(r)]
    bad += [r for r in srows if r["superseded_status"].startswith("DEFECT")]
    print()
    print("FILES NEEDING A HUMAN LOOK (real content difference, missing, or untracked)")
    print("-" * 78)
    if not bad:
        print("  none -- every mismatch is a line-ending form")
    for r in bad:
        to = f" (superseded -> {r['superseded_to']})" if r.get("superseded_to") else ""
        print(f"  {r['path']:<48} disk={r['disk_form']} head={r['head_form']} "
              f"manifest_bytes={r['manifest_bytes']} disk_bytes={r['disk_bytes']} "
              f"head_bytes={r['head_bytes']}{to}")

    tracked = subprocess.run(["git", "-C", release, "ls-files"],
                             capture_output=True, text=True).stdout.split("\n")
    tracked = [t for t in tracked if t]
    listed = {rel for (_, _, rel) in entries if rel not in superseded}
    print()
    print("TRACKED IN GIT BUT NOT IN THE MANIFEST")
    print("-" * 78)
    for t in sorted(set(tracked) - listed):
        print(f"  {t}")
    print()
    print("IN THE MANIFEST BUT NOT TRACKED IN GIT")
    print("-" * 78)
    miss = sorted(listed - set(tracked))
    print("  none" if not miss else "\n".join(f"  {m}" for m in miss))

    print()
    print("=" * 78)
    print(f"DONE in {time.time() - t0:.1f}s  -> report {a.out}")
    print("=" * 78)
    print("  Nothing was modified. The report CSV is the input to the fix step.")


if __name__ == "__main__":
    main()
