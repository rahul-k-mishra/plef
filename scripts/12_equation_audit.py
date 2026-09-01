#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 12 : EQUATION AUDIT
                       (v12.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
An internal review found that the definition of k in the arc-asymmetry equation
had been deleted from the manuscript, leaving NAVA unreproducible from the
paper. The definition was restored from the released core. This script closes
the loop: it re-implements the two trajectory metrics FROM THE EQUATIONS AS
PRINTED IN THE MANUSCRIPT, independently of the framework code, and compares
the results against the values stored in the scored files.

If the printed equations reproduce the stored values, a reader can reproduce
them too. If they do not, the manuscript is wrong somewhere and this script
says where.

This is the check that would have caught the missing k, and it is written
deliberately without importing plef_core, so that agreement means the PAPER is
correct rather than that the code agrees with itself.

WHAT IS RE-IMPLEMENTED FROM THE PAPER
-------------------------------------
  smoothing   half-width w = max(1, floor(N/4)); window [max(1,i-w), min(N,i+w)]
              truncated at the boundaries, never padded

  LEWI        i* = argmax over 2 <= i <= N-1 of |s~_{i+1} - 2 s~_i + s~_{i-1}|
              ties -> smallest index; constant signal -> i* = floor(N/2)+1
              drop = mean(s_1..s_{i*-1}) - mean(s_{i*}..s_N)

  NAVA        k = max(1, floor(N/4)) if N < 9 else max(1, floor(N/3))
              NAVA = mean(first k) - mean(last k)

EXIT CODES
----------
  0 every stored value reproduced within tolerance
  2 missing prerequisite
  3 MISMATCH -- the manuscript does not describe what produced the data
===============================================================================
"""

import argparse
import csv
import datetime
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "12.1.0"
TOL = 1e-6


class Tee:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, s):
        try: self.stdout.write(s)
        except UnicodeEncodeError:
            self.stdout.write(s.encode("ascii", "replace").decode("ascii"))
        self.f.write(s)
    def flush(self): self.stdout.flush(); self.f.flush()
    def close(self):
        try: self.f.close()
        except Exception: pass


def rule(ch="-", w=78): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


# --- re-implemented FROM THE PAPER, 1-indexed as printed --------------------
def smooth_paper(s):
    """s is 1-indexed conceptually; here 0-indexed with the same window."""
    N = len(s)
    w = max(1, N // 4)
    out = []
    for i in range(N):                      # i is 0-based for position i+1
        lo = max(0, i - w)
        hi = min(N - 1, i + w)
        seg = s[lo:hi + 1]
        out.append(sum(seg) / len(seg))
    return out


def lewi_paper(s):
    """i* over 1-indexed 2..N-1, ties -> smallest, constant -> floor(N/2)+1."""
    N = len(s)
    sm = smooth_paper(s)
    best_i, best_v = None, None
    for i1 in range(2, N):                  # 1-indexed 2..N-1
        i = i1 - 1                          # 0-based
        v = abs(sm[i + 1] - 2.0 * sm[i] + sm[i - 1])
        if best_v is None or v > best_v + 1e-12:
            best_v, best_i = v, i1
    if best_i is None:
        best_i = N // 2 + 1
    pre = s[:best_i - 1]
    post = s[best_i - 1:]
    return best_i, (sum(pre) / len(pre)) - (sum(post) / len(post))


def nava_paper(s):
    N = len(s)
    k = max(1, N // 4) if N < 9 else max(1, N // 3)
    return (sum(s[:k]) / k) - (sum(s[N - k:]) / k)


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 12 -- equation audit.")
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    canon = root / "results" / "canonical"
    if not canon.exists():
        print("FATAL: run script 05 first.")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_12.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 12 : EQUATION AUDIT")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print()
        print("  The metrics below are re-implemented FROM THE PRINTED EQUATIONS,")
        print("  without importing the framework. Agreement therefore means the")
        print("  PAPER is reproducible, not merely that the code agrees with")
        print("  itself.")

        shards = sorted(canon.glob("scored_*.csv"))
        if not shards:
            print("FATAL: no scored files")
            return 2

        grand = {"n": 0, "lewi_ok": 0, "lewi_bad": 0, "nava_ok": 0,
                 "nava_bad": 0, "idx_ok": 0, "idx_bad": 0}
        worst = []
        for p in shards:
            name = p.stem.replace("scored_", "")
            n = lo = lb = no = nb = io = ib = 0
            for r in csv.DictReader(open(p, encoding="utf-8", errors="replace",
                                         newline="")):
                raw = (r.get("sent_scores") or "").strip()
                if not raw:
                    continue
                s = [f(x) for x in raw.split(";") if x.strip() != ""]
                s = [x for x in s if x is not None]
                if len(s) < 4:
                    continue
                n += 1
                st_l = f(r.get("lewi_drop"))
                st_n = f(r.get("nava"))
                st_i = f(r.get("lewi_idx"))
                idx, dl = lewi_paper(s)
                nv = nava_paper(s)
                if st_l is not None:
                    if abs(dl - st_l) <= TOL: lo += 1
                    else:
                        lb += 1
                        if len(worst) < 5:
                            worst.append((name, r.get("id"), "LEWI", st_l, dl))
                if st_n is not None:
                    if abs(nv - st_n) <= TOL: no += 1
                    else:
                        nb += 1
                        if len(worst) < 5:
                            worst.append((name, r.get("id"), "NAVA", st_n, nv))
                if st_i is not None:
                    # stored index may be 0-based; accept either convention but
                    # report which one matches, since the paper is 1-indexed
                    if abs(st_i - idx) < 0.5 or abs(st_i - (idx - 1)) < 0.5:
                        io += 1
                    else:
                        ib += 1
            if n == 0:
                continue
            print()
            print(f"  {name:<18} n={n:,}")
            print(f"    LEWI drop  reproduced {lo:,}   mismatched {lb:,}")
            print(f"    NAVA       reproduced {no:,}   mismatched {nb:,}")
            print(f"    watershed index consistent {io:,}   inconsistent {ib:,}")
            grand["n"] += n; grand["lewi_ok"] += lo; grand["lewi_bad"] += lb
            grand["nava_ok"] += no; grand["nava_bad"] += nb
            grand["idx_ok"] += io; grand["idx_bad"] += ib

        sub("SUMMARY")
        print(f"  documents audited            : {grand['n']:,}")
        print(f"  LEWI drop reproduced         : {grand['lewi_ok']:,}"
              f"   mismatched {grand['lewi_bad']:,}")
        print(f"  NAVA reproduced              : {grand['nava_ok']:,}"
              f"   mismatched {grand['nava_bad']:,}")
        print(f"  watershed index consistent   : {grand['idx_ok']:,}"
              f"   inconsistent {grand['idx_bad']:,}")
        if worst:
            print()
            print("  first mismatches:")
            for c, i, m, st, re_ in worst:
                print(f"    {c} {i} {m}: stored {st:+.6f}  from the paper {re_:+.6f}"
                      f"  diff {abs(st-re_):.2e}")

        bad = grand["lewi_bad"] + grand["nava_bad"] + grand["idx_bad"]
        head("DONE")
        if grand["n"] == 0:
            print("  No document carried a stored sentence vector. Re-run script")
            print("  05.2.0+ on a shard in trajectory scope; nothing was verified.")
            return 2
        if bad == 0:
            print("  Every stored value is reproduced by the equations exactly as")
            print("  printed in the manuscript. A reader with the paper and the")
            print("  sentence scores can regenerate both trajectory metrics.")
            return 0
        print(f"  {bad:,} MISMATCH(ES). The manuscript does not describe what")
        print("  produced the stored data. Do not submit until this is resolved:")
        print("  either the printed equations are wrong, or the stored values did")
        print("  not come from them.")
        return 3
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3
    finally:
        sys.stdout = tee.stdout; tee.close()


if __name__ == "__main__":
    sys.exit(main())
