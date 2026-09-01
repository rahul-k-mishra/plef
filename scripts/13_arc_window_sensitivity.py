#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 13 : ARC-WINDOW SENSITIVITY
                       (v13.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
The arc metric uses a piecewise window,

    k = max(1, floor(N/4))   for N < 9
    k = max(1, floor(N/3))   for N >= 9

and nothing motivates the threshold at nine sentences. Since the arc metric is
one half of the paper's primary null analysis, a reviewer can reasonably ask
whether the central conclusion depends on that arbitrary choice.

This script answers it. It recomputes the observed correlation AND the full
within-document permutation null under three window rules:

    A   k = max(1, floor(N/4))   for every N
    B   k = max(1, floor(N/3))   for every N
    C   the piecewise rule actually used

If the conclusion -- that the observed correlation is not unusually large
relative to the permutation null -- holds under all three, the choice does not
matter and the paper can say so. If it does not, the paper has a problem that
no wording can fix, and this script says which rule breaks it.

The watershed metric is unchanged across the three conditions; only the arc
window varies, so any difference is attributable to k alone.

OUTPUT
------
  results/ARC_WINDOW_SENSITIVITY.md
  results/tables/arc_window_sensitivity.csv

EXIT CODES
----------
  0 the conclusion holds under all three rules
  2 missing prerequisite
  3 the conclusion does NOT hold under some rule -- read the output
===============================================================================
"""

import argparse
import csv
import datetime
import math
import random
import statistics
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "13.1.0"
SEED = 20260830


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


def pearson(x, y):
    n = len(x)
    if n < 3: return None
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return num / (dx * dy) if dx and dy else None


def smooth(sig, w):
    out = []
    for i in range(len(sig)):
        lo, hi = max(0, i - w), min(len(sig), i + w + 1)
        out.append(sum(sig[lo:hi]) / (hi - lo))
    return out


def lewi_drop(s):
    n = len(s); w = max(1, n // 4); sm = smooth(s, w)
    bi, bv = None, -1.0
    for i in range(1, len(sm) - 1):
        v = abs(sm[i + 1] - 2.0 * sm[i] + sm[i - 1])
        if v > bv + 1e-12: bv, bi = v, i
    if bi is None: bi = max(1, min(n - 1, n // 2))
    return sum(s[:bi]) / bi - sum(s[bi:]) / (n - bi)


# the three window rules
def k_quarter(n):   return max(1, n // 4)
def k_third(n):     return max(1, n // 3)
def k_piecewise(n): return max(1, n // 4 if n < 9 else n // 3)


def nava(s, kf):
    n = len(s); k = kf(n)
    return sum(s[:k]) / k - sum(s[n - k:]) / k


def corr(seqs, kf):
    a = [nava(v, kf) for v in seqs]
    b = [lewi_drop(v) for v in seqs]
    return pearson(a, b)


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 13 -- arc-window sensitivity.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--perm", type=int, default=1000)
    args = ap.parse_args()
    root = Path(args.root)
    canon = root / "results" / "canonical"
    if not canon.exists():
        print("FATAL: run script 05 first."); return 2

    tee = Tee(root / "results" / "forensics" / "console_log_13.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 13 : ARC-WINDOW SENSITIVITY")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  permutations   : {args.perm} per rule")
        print(f"  seed           : {SEED}")

        seqs = []
        for r in csv.DictReader(open(canon / "scored_relationship.csv",
                                     encoding="utf-8", errors="replace", newline="")):
            v = [f(x) for x in (r.get("sent_scores") or "").split(";") if x.strip()]
            v = [x for x in v if x is not None]
            if len(v) >= 4:
                seqs.append(v)
        if not seqs:
            print("FATAL: no stored sentence vectors."); return 2
        print(f"  documents      : {len(seqs):,}")

        # window disjointness, checked rather than asserted
        sub("WINDOW DISJOINTNESS")
        ns = sorted({len(v) for v in seqs})
        worst = max((2 * k_piecewise(n) / n, n) for n in ns)
        bad = [n for n in ns if 2 * k_piecewise(n) > n]
        print(f"  distinct document lengths : {len(ns)}  (N from {min(ns)} to {max(ns)})")
        print(f"  lengths where 2k > N      : {bad if bad else 'none'}")
        print(f"  tightest case             : N={worst[1]}, 2k/N = {worst[0]:.4f}")
        print("  The opening and closing windows are disjoint on every document")
        print("  in this corpus under the rule actually used.")

        RULES = [("k = floor(N/4) throughout", k_quarter),
                 ("k = floor(N/3) throughout", k_third),
                 ("piecewise (used in the paper)", k_piecewise)]
        rows, verdicts = [], []
        for label, kf in RULES:
            sub(f"RULE: {label}")
            obs = corr(seqs, kf)
            rnd = random.Random(SEED)
            vals = []
            for _ in range(args.perm):
                sh = []
                for v in seqs:
                    w_ = v[:]; rnd.shuffle(w_); sh.append(w_)
                vals.append(corr(sh, kf))
            vals = sorted(v for v in vals if v is not None)
            m = statistics.mean(vals); sd = statistics.pstdev(vals)
            lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]
            ge = sum(1 for v in vals if v >= obs)
            pv = (1 + ge) / (len(vals) + 1)
            print(f"    observed r     : {obs:+.4f}")
            print(f"    null mean      : {m:+.4f}   SD {sd:.4f}")
            print(f"    null 95%       : [{lo:+.4f}, {hi:+.4f}]")
            print(f"    null >= obs    : {ge} of {len(vals)}")
            print(f"    empirical p    : {pv:.4f}")
            holds = pv > 0.05
            print(f"    conclusion holds (p > 0.05): {'YES' if holds else '** NO **'}")
            verdicts.append((label, holds, pv))
            rows.append({"rule": label, "observed_r": round(obs, 4),
                         "null_mean": round(m, 4), "null_sd": round(sd, 4),
                         "null_lo": round(lo, 4), "null_hi": round(hi, 4),
                         "n_ge_observed": ge, "draws": len(vals),
                         "empirical_p": round(pv, 4)})

        sub("SUMMARY")
        print(f"  {'rule':<34}{'observed':>10}{'null mean':>11}{'p':>9}")
        rule()
        for r_ in rows:
            print(f"  {r_['rule']:<34}{r_['observed_r']:>+10.4f}"
                  f"{r_['null_mean']:>+11.4f}{r_['empirical_p']:>9.4f}")

        td = root / "results" / "tables"; td.mkdir(parents=True, exist_ok=True)
        with open(td / "arc_window_sensitivity.csv", "w", encoding="utf-8",
                  newline="") as fh:
            w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w_.writeheader(); w_.writerows(rows)
        p_ = root / "results" / "ARC_WINDOW_SENSITIVITY.md"
        L = ["# Arc-window sensitivity", "",
             f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
             f"scripts/13_arc_window_sensitivity.py v{SCRIPT_VERSION}.", "",
             f"{len(seqs):,} documents, {args.perm} permutation replicates per rule.",
             "The watershed metric is identical across all three conditions; only",
             "the arc window k varies, so any difference is attributable to k.", "",
             "| arc window rule | observed r | null mean | null SD | null 95% | p |",
             "|---|---:|---:|---:|---|---:|"]
        for r_ in rows:
            L.append(f"| {r_['rule']} | {r_['observed_r']:+.4f} | "
                     f"{r_['null_mean']:+.4f} | {r_['null_sd']:.4f} | "
                     f"[{r_['null_lo']:+.4f}, {r_['null_hi']:+.4f}] | "
                     f"{r_['empirical_p']:.4f} |")
        L.append("")
        p_.write_text("\n".join(L) + "\n", encoding="utf-8")
        print()
        print(f"  {td / 'arc_window_sensitivity.csv'}")
        print(f"  {p_}")

        head("DONE")
        failed = [v for v in verdicts if not v[1]]
        if not failed:
            print("  The conclusion holds under all three window rules: the observed")
            print("  correlation is not unusually large relative to its permutation")
            print("  null in any of them. The choice of k does not drive the result,")
            print("  and the manuscript may state that.")
            return 0
        print("  The conclusion does NOT hold under:")
        for lbl, _, pv in failed:
            print(f"    {lbl}  (p = {pv:.4f})")
        print("  The central result depends on the arc-window rule. This must be")
        print("  reported and cannot be resolved by wording.")
        return 3
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3
    finally:
        sys.stdout = tee.stdout; tee.close()


if __name__ == "__main__":
    sys.exit(main())
