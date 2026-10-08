#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 15 : RELEASE BYTE AUDIT   (15_release_byte_audit.py, v1.0.0)
===============================================================================

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
import subprocess
import sys
import time
from multiprocessing import Pool, cpu_count

VERSION = "1.0.0"
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
    entries = read_manifest(man)
    print(f"  manifest entries : {len(entries)}")
    head = subprocess.run(["git", "-C", release, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"  git HEAD         : {head}")

    jobs = [(release, rel, h, nb) for (h, nb, rel) in entries]
    with Pool(a.workers) as pool:
        rows = pool.map(audit_one, jobs)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cols = ["path", "manifest_sha", "manifest_bytes", "disk_bytes", "disk_form",
            "disk_has_cr", "bom", "disk_sha_raw", "head_bytes", "head_form",
            "head_has_cr", "head_sha_raw"]
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

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

    bad = [r for r in rows if r["disk_form"] in ("none", "MISSING")
           or r["head_form"] in ("none", "NOT IN GIT")]
    print()
    print("FILES NEEDING A HUMAN LOOK (real content difference, missing, or untracked)")
    print("-" * 78)
    if not bad:
        print("  none -- every mismatch is a line-ending form")
    for r in bad:
        print(f"  {r['path']:<48} disk={r['disk_form']} head={r['head_form']} "
              f"manifest_bytes={r['manifest_bytes']} disk_bytes={r['disk_bytes']} "
              f"head_bytes={r['head_bytes']}")

    tracked = subprocess.run(["git", "-C", release, "ls-files"],
                             capture_output=True, text=True).stdout.split("\n")
    tracked = [t for t in tracked if t]
    listed = {rel for (_, _, rel) in entries}
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
