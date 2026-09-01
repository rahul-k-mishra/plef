#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- PROJECT STATE CHECK  (check_state.py, v1.0.0)
===============================================================================
Reads the artifacts on disk and reports what has actually run, when, and with
which script version. It changes nothing.

  python check_state.py --root D:\\Research\\PLEF\\Version_2\\PLEF_V2
===============================================================================
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def rule(ch="-", w=86): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def when(p):
    try:
        return datetime.datetime.fromtimestamp(
            Path(p).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def log_version(p):
    """Pull the script version out of a console log."""
    try:
        txt = Path(p).read_text(encoding="utf-8", errors="replace")[:4000]
        m = re.search(r"script version\s*:\s*([\d.]+)", txt)
        v = m.group(1) if m else "?"
        m2 = re.search(r"started\s*:\s*(\S+)", txt)
        return v, (m2.group(1) if m2 else "-")
    except Exception:
        return None, None


def count_rows(p):
    try:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 project state check.")
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    R = Path(args.root)
    if not R.exists():
        print(f"FATAL: {R} does not exist")
        return 2

    head("PLEF V2 -- PROJECT STATE")
    print(f"  root    : {R}")
    print(f"  checked : {datetime.datetime.now().isoformat(timespec='seconds')}")

    # ---- pipeline stages -------------------------------------------------
    sub("PIPELINE STAGES  (from the console logs each script writes)")
    stages = [
        ("01 forensics", "results/forensics/console_log.txt", "01."),
        ("02 baselines", "results/forensics/console_log_02.txt", "02."),
        ("03 corpora", "results/forensics/console_log_03.txt", "03."),
        ("04 core", "results/forensics/console_log_04.txt", "04."),
        ("05 full run", "results/forensics/console_log_05.txt", "05."),
        ("06 statistics", "results/forensics/console_log_06.txt", "06."),
    ]
    latest = {"01.": "01.1.0", "02.": "02.4.0", "03.": "03.4.0",
              "04.": "04.2.0", "05.": "05.3.1", "06.": "06.6.0"}
    print(f"  {'stage':<16}{'ran':<8}{'version':<10}{'latest':<10}{'when':<18} verdict")
    rule()
    for name, rel, pref in stages:
        p = R / rel
        if not p.exists():
            print(f"  {name:<16}{'NO':<8}{'-':<10}{latest[pref]:<10}{'-':<18} NEVER RUN")
            continue
        v, started = log_version(p)
        cur = latest[pref]
        verdict = "current" if v == cur else f"OLD -- rerun with {cur}"
        print(f"  {name:<16}{'yes':<8}{str(v):<10}{cur:<10}{str(started)[:16]:<18} {verdict}")

    # ---- artifacts -------------------------------------------------------
    sub("KEY ARTIFACTS")
    arts = [
        ("src/plef_core.py", "PLEF core module"),
        ("src/plef_baselines.py", "baseline adapter"),
        ("src/plef_lexicons.json", "lexicons lifted from V1"),
        ("DECISIONS.md", "pre-registration"),
        ("MANIFEST/corpora.json", "corpus manifest"),
        ("MANIFEST/scored.json", "scored manifest"),
        ("results/RESULTS.md", "results document"),
    ]
    for rel, desc in arts:
        p = R / rel
        print(f"  {'OK ' if p.exists() else '-- '} {desc:<28} {when(p) if p.exists() else 'missing':<18} {rel}")

    # ---- scored shards ---------------------------------------------------
    sub("SCORED CORPORA")
    canon = R / "results" / "canonical"
    if not canon.exists():
        print("  results/canonical does not exist -- script 05 has not run")
    else:
        tot = 0
        for d in sorted(canon.glob("scored_*.done")):
            try:
                j = json.loads(d.read_text(encoding="utf-8"))
                csvp = canon / f"scored_{j['corpus']}.csv"
                has_vec = has_cov = False
                if csvp.exists():
                    with open(csvp, encoding="utf-8", errors="replace", newline="") as f:
                        r = next(csv.DictReader(f), {})
                    has_vec = bool((r.get("sent_scores") or "").strip())
                    has_cov = (r.get("cov_plef") or "") != ""
                tot += j["rows"]
                extra = []
                if has_cov: extra.append("cov_plef")
                if has_vec: extra.append("sent_scores")
                print(f"  {j['corpus']:<16}{j['rows']:>9,} rows   {j['at'][:16]}"
                      f"   {'+' + ', '.join(extra) if extra else ''}")
            except Exception as e:
                print(f"  {d.name}: unreadable ({e})")
        print(f"  {'TOTAL':<16}{tot:>9,} rows")

    # ---- tables ----------------------------------------------------------
    sub("RESULT TABLES  (script 06 output)")
    td = R / "results" / "tables"
    if not td.exists():
        print("  results/tables does not exist -- script 06 has not run")
    else:
        fs = sorted(td.glob("*.csv"))
        for f in fs:
            print(f"  {f.name:<28}{count_rows(f) or 0:>6} rows   {when(f)}")
        if not fs:
            print("  no tables written")
    fd = R / "results" / "figures"
    n = len(list(fd.glob("*.png"))) if fd.exists() else 0
    print(f"  figures: {n} PNG(s)")

    # ---- annotation ------------------------------------------------------
    sub("ANNOTATION")
    ad = R / "data" / "interim" / "annotations"
    if not ad.exists():
        print("  no annotations directory")
    else:
        for i in (1, 2, 3):
            p = ad / f"annotations_rater{i}.csv"
            if not p.exists():
                print(f"  rater {i}: no file")
                continue
            try:
                with open(p, encoding="utf-8", errors="replace", newline="") as f:
                    rows = list(csv.DictReader(f))
                meth = {}
                for r in rows:
                    meth[r.get("entry_method", "?")] = meth.get(r.get("entry_method", "?"), 0) + 1
                print(f"  rater {i}: {len(rows):>4} rows   {meth}   {when(p)}")
            except Exception as e:
                print(f"  rater {i}: unreadable ({e})")
        golds = sorted(ad.glob("gold*.csv"))
        print()
        if not golds:
            print("  no gold file -- H1 and H5 are NOT TESTED")
        for g in golds:
            flag = ""
            if "UNUSABLE" in g.name or "QUARANT" in g.name:
                flag = "  <- quarantined, correctly ignored by script 06"
            elif g.name == "gold_dev200.csv":
                flag = ("  ** ACTIVE: script 06 WILL use this. Confirm its "
                        "reliability before running. **")
            print(f"  {g.name:<44}{count_rows(g) or 0:>5} rows{flag}")

    # ---- what to do next -------------------------------------------------
    sub("WHAT TO RUN NEXT")
    todo = []
    for name, rel, pref in stages:
        p = R / rel
        if not p.exists():
            todo.append(f"{name}: never run")
        else:
            v, _ = log_version(p)
            if v != latest[pref]:
                todo.append(f"{name}: ran {v}, latest is {latest[pref]}")
    if (ad / "gold_dev200.csv").exists():
        todo.append("gold_dev200.csv is ACTIVE -- rename it unless its alpha "
                    "clears 0.67, or script 06 will report an unusable criterion")
    if not todo:
        print("  Everything is current. Nothing to re-run.")
    else:
        for t in todo:
            print(f"  - {t}")
    print()
    print("  Re-running a stage never loses work: script 05 skips shards that")
    print("  already have a .done marker, and every other stage is idempotent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
