#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 17 : RELEASE BYTE FIX   (17_release_byte_fix.py, v1.0.0)
===============================================================================

WHAT THIS DOES (plain language)
-------------------------------
Puts every file in the public release working copy into exactly the byte
form that MANIFEST-RELEASE.txt describes, and completes the manifest.
Content changes nowhere. Steps, in order:

  1. Set the release repo's core.autocrlf to false and write .gitattributes
     containing '* -text', so git never again converts line endings on
     commit or checkout.
  2. Restore everything under scripts/ from the committed blobs
     (git checkout -- scripts). The committed scripts are the LF form the
     manifest hashed; the disk copies were converted to CRLF on 2026-09-01
     at 13:46 by a checkout on Windows.
  3. Copy the three untouched originals of annotation/rejected/rater{1,2,3}
     _OFFLINE.csv from data/interim/annotations/round1_compromised/.
  4. Verify that all 103 manifest entries now hash RAW on disk. If any does
     not, stop and change nothing further.
  5. Append entries for scripts/10-14 to the manifest (their disk bytes,
     which after step 2 are the committed LF bytes, the same form as
     scripts 01-09), and update the count line. The 103 original entries
     are not touched.

WHAT IT DOES NOT DO
-------------------
It does not run git add, git commit or git push. Run script 15 afterwards
to confirm, then commit and push by hand.

Default is a DRY RUN that prints what would happen. Pass --apply to do it.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time

VERSION = "1.0.0"
TODAY = time.strftime("%Y-%m-%d")
OFFLINE = ["rater1_OFFLINE.csv", "rater2_OFFLINE.csv", "rater3_OFFLINE.csv"]
ADD_SCRIPTS = ["scripts/10_null_analysis.py", "scripts/11_response_space.py",
               "scripts/12_equation_audit.py", "scripts/13_arc_window_sensitivity.py",
               "scripts/14_parallel_null.py"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git(release, *args, check=True):
    r = subprocess.run(["git", "-C", release, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"  git {' '.join(args)} failed:\n{r.stderr}")
        sys.exit(2)
    return r.stdout


def read_manifest(path):
    raw = open(path, "rb").read()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = raw.decode("utf-8").split(eol.decode())
    entries = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) >= 3:
            entries.append((p[0], int(p[1]), " ".join(p[2:])))
    return raw, eol, lines, entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True)
    ap.add_argument("--originals", required=True,
                    help="folder holding the untouched rater*_OFFLINE.csv originals")
    ap.add_argument("--apply", action="store_true", help="actually make the changes")
    a = ap.parse_args()
    release = os.path.abspath(a.release)
    originals = os.path.abspath(a.originals)
    mode = "APPLY" if a.apply else "DRY RUN"
    print("=" * 78)
    print(f"PLEF V2 -- SCRIPT 17 : RELEASE BYTE FIX   v{VERSION}   [{mode}]")
    print("=" * 78)
    print(f"  release   : {release}")
    print(f"  originals : {originals}")
    print(f"  started   : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    man_path = os.path.join(release, "MANIFEST-RELEASE.txt")
    raw, eol, lines, entries = read_manifest(man_path)
    print(f"  manifest  : {len(entries)} entries, line ending "
          f"{'CRLF' if eol == b'\\r\\n' else 'LF'}")
    want = {rel: (h, n) for (h, n, rel) in entries}

    # ------------------------------------------------------------- step 1
    print()
    print("STEP 1  disable line-ending conversion in this repo")
    print("-" * 78)
    ga = os.path.join(release, ".gitattributes")
    print(f"  git config core.autocrlf false")
    print(f"  write {ga}  ->  '* -text'")
    if a.apply:
        git(release, "config", "core.autocrlf", "false")
        with open(ga, "wb") as f:
            f.write(b"* -text\n")

    # ------------------------------------------------------------- step 2
    print()
    print("STEP 2  restore scripts/ from the committed blobs (LF form)")
    print("-" * 78)
    changed = [l for l in git(release, "status", "--short", "--", "scripts").split("\n") if l]
    print(f"  {len(changed)} script files currently differ from the commit")
    if a.apply:
        git(release, "checkout", "--", "scripts")
        left = [l for l in git(release, "status", "--short", "--", "scripts").split("\n") if l]
        print(f"  after checkout: {len(left)} still differ (must be 0)")
        if left:
            sys.exit(3)

    # ------------------------------------------------------------- step 3
    print()
    print("STEP 3  copy the three OFFLINE originals back")
    print("-" * 78)
    for fn in OFFLINE:
        rel = "annotation/rejected/" + fn
        src = os.path.join(originals, fn)
        dst = os.path.join(release, rel)
        h, n = want[rel]
        if not os.path.isfile(src):
            print(f"  MISSING original {src}")
            sys.exit(4)
        hs = sha(src)
        ok = hs == h and os.path.getsize(src) == n
        print(f"  {fn:<22} original sha {hs[:12]}... {'== manifest' if ok else '!= MANIFEST -- STOP'}")
        if not ok:
            sys.exit(5)
        if a.apply:
            shutil.copyfile(src, dst)

    # ------------------------------------------------------------- step 4
    print()
    print("STEP 4  verify all manifest entries hash raw on disk")
    print("-" * 78)
    bad = []
    for h, n, rel in entries:
        p = os.path.join(release, rel)
        if not os.path.isfile(p) or sha(p) != h or os.path.getsize(p) != n:
            bad.append(rel)
    if a.apply:
        print(f"  {len(entries) - len(bad)} of {len(entries)} match")
        for b in bad:
            print(f"  STILL WRONG  {b}")
        if bad:
            print("  stopping; manifest not amended")
            sys.exit(6)
    else:
        print(f"  (dry run) currently {len(entries) - len(bad)} of {len(entries)} match;"
              f" {len(bad)} would be corrected by steps 2-3")

    # ------------------------------------------------------------- step 5
    print()
    print("STEP 5  append scripts 10-14 to the manifest and fix the count line")
    print("-" * 78)
    already = [s for s in ADD_SCRIPTS if s in want]
    if already:
        print(f"  already listed, nothing to add: {already}")
        new_lines = []
    else:
        new_lines = []
        add_bytes = 0
        for rel in ADD_SCRIPTS:
            p = os.path.join(release, rel)
            if not os.path.isfile(p):
                print(f"  MISSING {rel}")
                sys.exit(7)
            if a.apply or True:
                # in dry run the file may still be CRLF; report but hash what is there
                hs, n = sha(p), os.path.getsize(p)
            add_bytes += n
            new_lines.append(f"{hs}  {n}  {rel}")
            print(f"  {hs}  {n:>7}  {rel}")
        old_total = sum(n for (_, n, _) in entries)
        new_total = old_total + add_bytes
        count_idx = next(i for i, l in enumerate(lines)
                         if l.startswith("#") and " files, " in l)
        old_count_line = lines[count_idx]
        new_count_line = (f"# {len(entries) + len(ADD_SCRIPTS)} files, {new_total:,} bytes"
                          f"  ({old_count_line.lstrip('# ')} at generation; "
                          f"{len(ADD_SCRIPTS)} entries appended {TODAY}, see end of file)")
        print(f"  count line: '{old_count_line}'")
        print(f"        ->    '{new_count_line}'")
        block = [
            f"# ---- amendment {TODAY} ----",
            "# The five scripts below were released on 2026-09-01 (commit a956c9c) but",
            "# were omitted from this manifest, which had been generated minutes earlier.",
            "# Hashes are of the files as stored in the repository (LF line endings, the",
            "# same form as scripts 01-09 above). The original entries are unchanged.",
        ] + new_lines
        if a.apply:
            lines[count_idx] = new_count_line
            body = lines[:]
            while body and body[-1] == "":
                body.pop()
            body += block
            out = (eol.decode().join(body) + eol.decode()).encode("utf-8")
            with open(man_path, "wb") as f:
                f.write(out)
            print(f"  manifest written: {len(entries) + len(ADD_SCRIPTS)} entries")

    print()
    print("=" * 78)
    if a.apply:
        print("DONE. Nothing committed. Next: run script 15, expect disk raw 108 of 108.")
    else:
        print("DRY RUN complete. Re-run with --apply to make these changes.")
    print("=" * 78)


if __name__ == "__main__":
    main()
