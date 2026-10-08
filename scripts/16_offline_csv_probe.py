#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 16 : OFFLINE CSV PROBE   (16_offline_csv_probe.py, v1.0.0)
===============================================================================

WHAT WE CHECK (plain language)
------------------------------
Three files in the public release -- annotation/rejected/rater{1,2,3}_OFFLINE.csv
-- no longer reproduce their manifest hash in any uniform line-ending form.
Their sizes say the originals had CRLF between records and LF inside quoted
cells (Excel style). This script tries to recover the exact original bytes
two ways, and changes nothing:

  A. SEARCH: walk the whole project tree (excluding the release working copy
     and any .git directory) for files whose SHA-256 equals a manifest hash,
     or whose size equals a manifest size, or whose name matches *OFFLINE*.
     A hash hit is the untouched original and can simply be copied back.

  B. RECONSTRUCT from the committed (LF) content in git HEAD, restoring CR
     only at record boundaries as determined by Python's csv parser, which
     tolerates stray quotes inside unquoted fields the way Excel does.
     Also tries three re-quoting variants in case the parser route fails.
     A reconstruction counts only if its SHA-256 equals the manifest hash.

WHAT THE RESULT MEANS
---------------------
  ORIGINAL FOUND          copy that file into the release; done
  RECONSTRUCTED (hash ok) write the reconstructed bytes; provably identical
  neither                 the three files differ from the manifest in content;
                          that is a disclosure item and we inspect by hand

READ-ONLY. Prints a report; writes nothing.
"""
import argparse
import csv
import hashlib
import io
import os
import subprocess
import time
from multiprocessing import Pool, cpu_count

VERSION = "1.0.0"
TARGETS = ["annotation/rejected/rater1_OFFLINE.csv",
           "annotation/rejected/rater2_OFFLINE.csv",
           "annotation/rejected/rater3_OFFLINE.csv"]
BOM = b"\xef\xbb\xbf"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read_manifest(path):
    out = {}
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            p = line.split()
            if len(p) >= 3:
                out[" ".join(p[2:])] = (p[0], int(p[1]))
    return out


def hash_file(path):
    try:
        with open(path, "rb") as f:
            return path, os.path.getsize(path), sha(f.read())
    except Exception:
        return path, -1, ""


# ---------------------------------------------------------------- B. rebuild
class LineFeed:
    """Feeds lines to csv.reader and remembers which line finished each record."""
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.i >= len(self.lines):
            raise StopIteration
        s = self.lines[self.i] + "\n"
        self.i += 1
        return s


def parser_record_crlf(lf_bytes, strict=False):
    has_bom = lf_bytes.startswith(BOM)
    body = lf_bytes[3:] if has_bom else lf_bytes
    text = body.decode("utf-8")
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines = lines[:-1]
    feed = LineFeed(lines)
    ends = set()
    for _ in csv.reader(feed, strict=strict):
        ends.add(feed.i - 1)
    out = []
    for k, ln in enumerate(lines):
        out.append(ln)
        out.append("\r\n" if k in ends else "\n")
    if not trailing and out:
        out.pop()
    rebuilt = "".join(out).encode("utf-8")
    return (BOM if has_bom else b"") + rebuilt, len(ends)


def requote(lf_bytes, quoting):
    has_bom = lf_bytes.startswith(BOM)
    body = lf_bytes[3:] if has_bom else lf_bytes
    rows = list(csv.reader(io.StringIO(body.decode("utf-8"), newline="")))
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\r\n", quoting=quoting).writerows(rows)
    return (BOM if has_bom else b"") + buf.getvalue().encode("utf-8")


def git_show(release, rel):
    r = subprocess.run(["git", "-C", release, "show", "HEAD:" + rel],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="project root to search")
    ap.add_argument("--release", required=True, help="release working copy")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count()))
    a = ap.parse_args()
    root, release = os.path.abspath(a.root), os.path.abspath(a.release)
    t0 = time.time()
    print("=" * 78)
    print(f"PLEF V2 -- SCRIPT 16 : OFFLINE CSV PROBE   v{VERSION}")
    print("=" * 78)
    print(f"  root    : {root}")
    print(f"  release : {release}")
    man = read_manifest(os.path.join(release, "MANIFEST-RELEASE.txt"))
    want = {t: man[t] for t in TARGETS if t in man}
    for t, (h, n) in want.items():
        print(f"  target  : {t}  manifest sha {h[:12]}...  {n:,} bytes")

    # ---------------------------------------------------------- A. search
    print()
    print("A. SEARCH THE TREE FOR UNTOUCHED ORIGINALS")
    print("-" * 78)
    cands = []
    sizes = {n for (_, n) in want.values()}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git" and os.path.join(dp, d) != release]
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if "OFFLINE" in fn.upper() or sz in sizes:
                cands.append(p)
    print(f"  candidates by name or size: {len(cands)}")
    with Pool(a.workers) as pool:
        hashed = pool.map(hash_file, cands)
    by_hash = {h: p for (p, _, h) in hashed if h}
    found = {}
    for t, (h, n) in want.items():
        if h in by_hash:
            found[t] = by_hash[h]
            print(f"  ORIGINAL FOUND  {t}")
            print(f"                  {by_hash[h]}")
    for t in want:
        if t not in found:
            print(f"  not found       {t}")
    if cands:
        print("  all candidates (size, sha12, path):")
        for p, sz, h in sorted(hashed, key=lambda x: x[0]):
            print(f"    {sz:>9,}  {h[:12]}  {os.path.relpath(p, root)}")

    # ---------------------------------------------------- B. reconstruct
    print()
    print("B. RECONSTRUCT FROM GIT HEAD (LF content) BY RECORD-BOUNDARY CRLF")
    print("-" * 78)
    for t, (h, n) in want.items():
        g = git_show(release, t)
        if g is None:
            print(f"  {t}: not in git HEAD")
            continue
        lf = g.replace(b"\r\n", b"\n")
        print(f"  {t}")
        print(f"    HEAD bytes {len(g):,}  manifest bytes {n:,}  "
              f"difference {n - len(g):,}  (= CRs the original had at record ends)")
        attempts = []
        for label, fn in (
            ("csv parser, lenient", lambda b: parser_record_crlf(b, strict=False)),
            ("csv parser, strict", lambda b: parser_record_crlf(b, strict=True)),
        ):
            try:
                rb, nrec = fn(lf)
                attempts.append((label, rb, f"records {nrec}"))
            except Exception as e:
                attempts.append((label, None, f"failed: {e}"))
        for label, q in (("requote minimal", csv.QUOTE_MINIMAL),
                         ("requote all", csv.QUOTE_ALL),
                         ("requote nonnumeric", csv.QUOTE_NONNUMERIC)):
            try:
                attempts.append((label, requote(lf, q), ""))
            except Exception as e:
                attempts.append((label, None, f"failed: {e}"))
        for label, rb, note in attempts:
            if rb is None:
                print(f"    {label:<22} {note}")
                continue
            ok = sha(rb) == h
            print(f"    {label:<22} bytes {len(rb):,}  "
                  f"{'MATCHES MANIFEST' if ok else 'no'}  {note}")

    print()
    print("=" * 78)
    print(f"DONE in {time.time() - t0:.1f}s  -- nothing was modified")
    print("=" * 78)


if __name__ == "__main__":
    main()
