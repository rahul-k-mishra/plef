#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 11 : RESPONSE-SPACE AUDIT
                       (v11.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
An internal review identified two statistical errors that survive the previous
support correction, and both need data rather than argument.

  A  BOUNDARY SELECTIONS
     The watershed can return only interior positions 2..N-1. The annotation
     instructions placed no such restriction on the human. If an annotator
     selected sentence 1 or sentence N, the metric's probability of matching
     that response is ZERO, not 1/(N-2). The reported 5.0% exact-match
     benchmark is valid only if every human selection was interior. This stage
     checks that against the annotation records and, if any selection is on the
     boundary, recomputes the benchmark with those posts contributing zero.

  B  MIXED RESPONSE SPACES IN HUMAN-HUMAN AGREEMENT
     The reported pairwise agreement counts a shared "no turning point" as
     agreement, but compares it against 1/(N-2), the chance rate for choosing
     among interior sentences only. Those are different response spaces, so the
     "1.7 to 4.0 times chance" statement is not like-for-like.

     This stage splits the comparison into the two questions it conflates:

       EXISTENCE agreement -- did both annotators agree turn vs no-turn?
         Benchmark: the chance rate implied by each annotator's own marginal
         rate of "no turning point", so the null respects their observed
         tendencies rather than assuming 50/50.

       LOCATION agreement -- given that both selected a sentence, did they
         select the same one? Benchmark: mean of 1/(N_i-2) over exactly those
         posts, which is the correct support for that question.

OUTPUT
------
  results/RESPONSE_SPACE_AUDIT.md
  results/tables/response_space.csv

EXIT CODES
----------
  0 audit complete    2 missing prerequisite
===============================================================================
"""

import argparse
import collections
import csv
import datetime
import itertools
import statistics
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "11.2.0"


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


def read_rows(p, cols=None):
    if not Path(p).exists():
        return []
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(p, encoding=enc, newline="") as fh:
                return [({k: r.get(k) for k in cols} if cols else r)
                        for r in csv.DictReader(fh)]
        except UnicodeDecodeError:
            continue
    return []


def tp(r):
    try:
        return int(float(r.get("turning_point")))
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 11 -- response space.")
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    ad = root / "data" / "interim" / "annotations"
    canon = root / "results" / "canonical"
    if not ad.exists():
        print("FATAL: annotations directory not found")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_11.txt")
    sys.stdout = tee
    rows_out = []
    try:
        head("PLEF V2 -- SCRIPT 11 : RESPONSE-SPACE AUDIT")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")

        # sentence counts
        sc = read_rows(canon / "scored_dev_relationship.csv",
                       ["id", "n_sents", "lewi_idx"])
        if not sc:
            sc = read_rows(canon / "scored_relationship.csv",
                           ["id", "n_sents", "lewi_idx"])
        N = {}
        defined = set()
        for r in sc:
            try:
                N[r["id"]] = int(float(r["n_sents"]))
            except (TypeError, ValueError):
                pass
            if (r.get("lewi_idx") or "").strip():
                defined.add(r["id"])
        print(f"  scored posts with a sentence count : {len(N):,}")

        # ---- A boundary selections -----------------------------------------
        sub("A  BOUNDARY SELECTIONS IN THE HUMAN CRITERION")
        print("  The metric can return only positions 2..N-1. If a human selected")
        print("  sentence 1 or sentence N, the metric CANNOT match that response,")
        print("  so its exact-match probability is 0, not 1/(N-2).")
        print()
        gold = read_rows(ad / "gold_dev200.csv")
        if not gold:
            print("  no gold file; stage A not computed")
        else:
            sel = []
            for g in gold:
                i = g["id"]
                if i not in N or i not in defined:
                    continue
                t = None
                try:
                    t = int(float(g.get("gold_turning_point")))
                except (TypeError, ValueError):
                    pass
                if t is not None and t > 0:
                    sel.append((i, t, N[i]))
            if not sel:
                print("  no comparison posts")
            else:
                interior = [(i, t, n) for i, t, n in sel if 2 <= t <= n - 1]
                bound = [(i, t, n) for i, t, n in sel if not (2 <= t <= n - 1)]
                print(f"  comparison posts                 : {len(sel)}")
                print(f"  human selection INTERIOR (2..N-1): {len(interior)}")
                print(f"  human selection on the BOUNDARY  : {len(bound)}")
                for i, t, n in bound:
                    print(f"      {i}: selected sentence {t} of {n}")
                naive = statistics.mean([1.0 / max(1, n - 2) for _, _, n in sel])
                corrected = statistics.mean(
                    [(1.0 / max(1, n - 2)) if 2 <= t <= n - 1 else 0.0
                     for _, t, n in sel])
                print()
                print(f"  exact-match benchmark, all posts treated as interior : "
                      f"{100*naive:.2f}%")
                print(f"  exact-match benchmark, boundary posts contribute 0   : "
                      f"{100*corrected:.2f}%")
                if not bound:
                    print()
                    print("  No boundary selections. The reported benchmark is valid")
                    print("  as computed, and the manuscript may say so explicitly.")
                else:
                    print()
                    print("  ** Boundary selections exist. The reported benchmark is")
                    print("     too high and must be replaced by the corrected value. **")
                # point 21/22: the per-post audit table, so 4.67% and 14.2%
                # are auditable rather than trusted averages
                ap_ = root / "results" / "tables" / "chance_per_post.csv"
                with open(ap_, "w", encoding="utf-8", newline="") as fh:
                    w_ = csv.writer(fh)
                    w_.writerow(["id", "N_i", "human_selection_h_i", "boundary",
                                 "exact_contribution_1_over_N_minus_2",
                                 "within1_admissible_neighbours",
                                 "within1_contribution"])
                    for i, t, n in sel:
                        interior_ok = 2 <= t <= n - 1
                        ex = (1.0 / max(1, n - 2)) if interior_ok else 0.0
                        adm = set(range(2, n))
                        near = {t - 1, t, t + 1} & adm
                        w1 = len(near) / max(1, len(adm))
                        w_.writerow([i, n, t, "yes" if not interior_ok else "no",
                                     f"{ex:.6f}", len(near), f"{w1:.6f}"])
                print()
                print(f"  per-post audit table written: {ap_}")
                print("  It gives N_i, the annotator's selection, the boundary flag")
                print("  and each post's exact contribution, so both benchmarks are")
                print("  auditable rather than trusted averages.")
                w1m = statistics.mean(
                    [len({t-1, t, t+1} & set(range(2, n))) / max(1, n - 2)
                     for _, t, n in sel])
                print(f"  within-one-sentence benchmark recomputed here: "
                      f"{100*w1m:.2f}%")
                rows_out.append({"stage": "A", "n": len(sel),
                                 "interior": len(interior), "boundary": len(bound),
                                 "benchmark_naive": round(100*naive, 3),
                                 "benchmark_corrected": round(100*corrected, 3)})

        # ---- B existence vs location ---------------------------------------
        sub("B  EXISTENCE AND LOCATION AGREEMENT, SEPARATED")
        print("  The reported pairwise figure counts a shared zero as agreement but")
        print("  compares it against an interior-sentence chance rate. Those are")
        print("  different response spaces. Split into the two questions.")
        rounds = {}
        for pth in sorted(ad.rglob("annotations_rater*.csv")):
            grp = "current" if pth.parent == ad else pth.parent.name
            try:
                i = int(pth.stem.replace("annotations_rater", ""))
            except ValueError:
                continue
            rr = read_rows(pth)
            if not rr:
                continue
            d = {}
            for r in sorted(rr, key=lambda x: int(x["slot"])):
                d.setdefault(r["id"], r)
            rounds.setdefault(grp, {})[i] = d

        for grp in sorted(rounds):
            A = rounds[grp]
            if len(A) < 2:
                continue
            print()
            print(f"  ROUND: {grp}")
            for a, b in itertools.combinations(sorted(A), 2):
                shared = set(A[a]) & set(A[b])
                ids = [i for i in shared if i in N]
                if len(ids) < 5:
                    # v11.1.0 skipped silently here, which printed a round header
                    # with nothing under it and looked like a passing check.
                    print(f"    {a} vs {b}: {len(shared)} shared posts but only "
                          f"{len(ids)} have a sentence count in the scored files;")
                    print(f"      not computed. Ensure the scored shard covering "
                          f"these posts is present.")
                    continue
                ta = {i: tp(A[a][i]) for i in ids}
                tb = {i: tp(A[b][i]) for i in ids}
                ids = [i for i in ids if ta[i] is not None and tb[i] is not None]
                if not ids:
                    continue
                # EXISTENCE: turn vs no-turn
                ea = {i: (ta[i] > 0) for i in ids}
                eb = {i: (tb[i] > 0) for i in ids}
                agree_e = sum(1 for i in ids if ea[i] == eb[i])
                pa = sum(ea.values()) / len(ids)
                pb = sum(eb.values()) / len(ids)
                chance_e = pa * pb + (1 - pa) * (1 - pb)
                # LOCATION: both chose a sentence
                both = [i for i in ids if ta[i] > 0 and tb[i] > 0]
                agree_l = sum(1 for i in both if ta[i] == tb[i])
                chance_l = (statistics.mean([1.0 / max(1, N[i] - 2) for i in both])
                            if both else float("nan"))
                print(f"    {a} vs {b}   n={len(ids)}")
                print(f"      EXISTENCE  agree {agree_e}/{len(ids)} = "
                      f"{100*agree_e/len(ids):.1f}%   chance "
                      f"{100*chance_e:.1f}%   (marginal-based)")
                if both:
                    print(f"      LOCATION   agree {agree_l}/{len(both)} = "
                          f"{100*agree_l/len(both):.1f}%   chance "
                          f"{100*chance_l:.1f}%   (mean of 1/(N-2))")
                else:
                    print("      LOCATION   no posts where both selected a sentence")
                rows_out.append({
                    "stage": "B", "round": grp, "pair": f"{a}v{b}", "n": len(ids),
                    "existence_agree_pct": round(100*agree_e/len(ids), 2),
                    "existence_chance_pct": round(100*chance_e, 2),
                    "location_n": len(both),
                    "location_agree_pct": round(100*agree_l/len(both), 2) if both else "",
                    "location_chance_pct": round(100*chance_l, 2) if both else ""})
        print()
        print("  The manuscript must report these two separately, each against its")
        print("  own chance rate, rather than one mixed percentage against an")
        print("  interior-sentence-only benchmark.")

        # ---- write ---------------------------------------------------------
        sub("WRITING")
        td = root / "results" / "tables"
        td.mkdir(parents=True, exist_ok=True)
        if rows_out:
            keys = []
            for r in rows_out:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            with open(td / "response_space.csv", "w", encoding="utf-8",
                      newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
                w.writeheader(); w.writerows(rows_out)
            print(f"  {td / 'response_space.csv'}")
        p = root / "results" / "RESPONSE_SPACE_AUDIT.md"
        L = ["# Response-space audit", "",
             f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
             f"scripts/11_response_space.py v{SCRIPT_VERSION}.", "",
             "Two corrections that the earlier support fix did not cover:",
             "boundary human selections, which the metric cannot match at all,",
             "and the mixing of existence agreement with location agreement.", "",
             "See `tables/response_space.csv` for the machine-readable values.", ""]
        p.write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"  {p}")

        head("DONE")
        print("  Report stage A's corrected exact-match benchmark in Table 9,")
        print("  and stage B's existence and location figures separately in the")
        print("  reliability section. Do not quote one mixed percentage against")
        print("  an interior-only chance rate.")
        return 0
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3
    finally:
        sys.stdout = tee.stdout; tee.close()


if __name__ == "__main__":
    sys.exit(main())
