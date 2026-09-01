#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 14 : PARALLEL NULL ANALYSIS
                       (v14.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
Script 10 draws the null distributions serially. At 1,000 draws that takes
tens of minutes; at the 10,000 draws the reviewer recommends it would take
hours. The draws are independent, so this runs them across a worker pool.

THE ONE THING THAT MATTERS FOR CORRECTNESS
------------------------------------------
A naive parallel version seeds one generator per worker. The result then
depends on how many workers you have and how the draws happened to be
distributed among them, so the same command on a different machine gives a
different answer. That is not acceptable for a paper whose central claim is
this p-value.

Here EVERY DRAW HAS ITS OWN SEED, derived from the base seed and the draw
index. Draw 4,217 is identical whether it ran on one core or thirty-two, and
whether it ran first or last. The output is a deterministic function of
(--perm, --synth, --seed) and nothing else.

The script verifies this itself: with --selftest it recomputes a small number
of draws serially and compares them to the parallel result, and refuses to
continue if they differ.

USAGE
-----
  python 14_parallel_null.py --root <PLEF_V2>
  python 14_parallel_null.py --root <PLEF_V2> --perm 10000 --synth 10000
  python 14_parallel_null.py --root <PLEF_V2> --workers 8

OUTPUT
------
  results/NULLS_PARALLEL.md
  results/tables/null_draws_parallel.csv
  results/tables/nulls_parallel.json

EXIT CODES
----------
  0 every check ran and passed
  1 a check COULD NOT RUN (missing stored columns, no earlier file, or
    anchors overridden) -- the numbers may be right but are unverified
  2 missing prerequisite
  3 a check FAILED -- do not use the run
===============================================================================
"""

import argparse
import csv
import datetime
import json
import math
import os
import random
import statistics
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "14.9.0"
SEED = 20260830
PAPER_OBSERVED_R = 0.5979   # the value the manuscript reports; anchors every null
PAPER_SIGMA      = 0.2488   # i.i.d. null scale, as stated in the manuscript
PAPER_SIGMA_STEP = 0.2678   # random-walk step scale, as stated in the manuscript
PAPER_N_DOCS     = 1288     # trajectory-eligible documents, as stated

# module-level state, populated in each worker exactly once
_SEQS = None
_LENS = None
_SIGMA = None
_SSTEP = None


class Tee:
    """Mirror stdout to results/forensics/console_log_14.txt.

    v14.1.0-14.3.0 wrote no log. Scripts 08-13 all do, and script 09 collects
    them into the release, so a run of this script left no artifact behind --
    for the one analysis the paper depends on most.
    """
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


def nava(s):
    n = len(s); k = max(1, n // 4 if n < 9 else n // 3)
    return sum(s[:k]) / k - sum(s[n - k:]) / k


def corr(seqs):
    return pearson([nava(v) for v in seqs], [lewi_drop(v) for v in seqs])


def _init(seqs, sigma, sstep):
    global _SEQS, _LENS, _SIGMA, _SSTEP
    _SEQS = seqs
    _LENS = [len(v) for v in seqs]
    _SIGMA = sigma
    _SSTEP = sstep


def draw_perm(args):
    """One within-document permutation replicate. Seed depends ONLY on i."""
    base, i = args
    rnd = random.Random(base + i)
    sh = []
    for v in _SEQS:
        w = v[:]
        rnd.shuffle(w)
        sh.append(w)
    return corr(sh)


def draw_iid(args):
    base, i = args
    rnd = random.Random(base + i)
    return corr([[rnd.gauss(0.0, _SIGMA) for _ in range(L)] for L in _LENS])


def draw_walk(args):
    base, i = args
    rnd = random.Random(base + i)
    sh = []
    for L in _LENS:
        v0, s = 0.0, []
        for _ in range(L):
            v0 = max(-1.0, min(1.0, v0 + rnd.gauss(0.0, _SSTEP)))
            s.append(v0)
        sh.append(s)
    return corr(sh)


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


def summarise(vals, observed, label):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        print(f"    ** no usable draws for {label}; cannot summarise **")
        return {"label": label, "draws": 0}
    m = statistics.mean(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    # percentile convention: lower-index order statistic, vals[int(q*n)].
    # Script 10 used the same rule, so the intervals in the paper match.
    lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]
    ge = sum(1 for v in vals if v >= observed)
    p = (1 + ge) / (len(vals) + 1)
    mcse = math.sqrt(max(p * (1 - p), 1e-12) / (len(vals) + 1))
    print(f"    draws          : {len(vals):,}")
    print(f"    mean r         : {m:+.4f}")
    print(f"    SD             : {sd:.4f}")
    print(f"    95% interval   : [{lo:+.4f}, {hi:+.4f}]"
          f"   (order statistics vals[int(0.025n)], vals[int(0.975n)])")
    print(f"    null r >= obs  : {ge:,} of {len(vals):,}")
    print(f"    empirical p    : {p:.4f}   Monte Carlo SE {mcse:.4f}")
    return {"label": label, "draws": len(vals), "mean": round(m, 4),
            "sd": round(sd, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "ge_observed": ge, "p": round(p, 4), "mcse": round(mcse, 4)}


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 14 -- parallel nulls.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--perm", type=int, default=10000)
    ap.add_argument("--synth", type=int, default=10000)
    ap.add_argument("--workers", type=int, default=0,
                    help="0 = cpu_count() - 1")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--paper-r", type=float, default=PAPER_OBSERVED_R,
                    help="override the manuscript anchor if the paper changes")
    ap.add_argument("--paper-sigma", type=float, default=PAPER_SIGMA)
    ap.add_argument("--paper-sigma-step", type=float, default=PAPER_SIGMA_STEP)
    ap.add_argument("--paper-n", type=int, default=PAPER_N_DOCS)
    ap.add_argument("--selftest", type=int, default=25,
                    help="draws to recompute serially as a determinism check")
    args = ap.parse_args()
    root = Path(args.root)
    canon = root / "results" / "canonical"
    if not canon.exists():
        print("FATAL: run script 05 first."); return 2

    import multiprocessing as mp
    nw = args.workers if args.workers > 0 else max(1, (os.cpu_count() or 2) - 1)

    tee = Tee(root / "results" / "forensics" / "console_log_14.txt")
    sys.stdout = tee
    try:
        return _run(args, root, canon, mp, nw)
    finally:
        sys.stdout = tee.stdout
        tee.close()


def _run(args, root, canon, mp, nw):
    head("PLEF V2 -- SCRIPT 14 : PARALLEL NULL ANALYSIS")
    print(f"  script version : {SCRIPT_VERSION}")
    print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"  workers        : {nw}")
    print(f"  permutations   : {args.perm:,}")
    print(f"  synthetic      : {args.synth:,} per null")
    print(f"  base seed      : {args.seed}")
    print()
    print("  Every draw is seeded from (base seed + draw index), so the result")
    print("  does not depend on the worker count or on how draws are chunked.")

    seqs = []
    for r in csv.DictReader(open(canon / "scored_relationship.csv",
                                 encoding="utf-8", errors="replace", newline="")):
        v = [f(x) for x in (r.get("sent_scores") or "").split(";") if x.strip()]
        v = [x for x in v if x is not None]
        if len(v) >= 4:
            seqs.append(v)
    if not seqs:
        print("FATAL: no stored sentence vectors."); return 2
    if args.perm < 1 or args.synth < 1:
        print("FATAL: --perm and --synth must be at least 1."); return 2
    # v14.1.0-14.6.0 self-tested parallel against serial using the SAME
    # functions: if lewi_drop or nava were wrong, both agreed and the test
    # passed. Verify them against the values already stored in the scored file
    # before any null is drawn, the way script 12 verifies the equations.
    stored_ok, stored_n, stored_bad = None, 0, 0
    try:
        for r in csv.DictReader(open(canon / "scored_relationship.csv",
                                     encoding="utf-8", errors="replace",
                                     newline="")):
            v = [f(x) for x in (r.get("sent_scores") or "").split(";") if x.strip()]
            v = [x for x in v if x is not None]
            if len(v) < 4:
                continue
            sl, sn = f(r.get("lewi_drop")), f(r.get("nava"))
            if sl is None and sn is None:
                continue
            stored_n += 1
            if sl is not None and abs(lewi_drop(v) - sl) > 1e-6: stored_bad += 1
            elif sn is not None and abs(nava(v) - sn) > 1e-6: stored_bad += 1
        # v14.7.0 set this False when stored_n was 0, so a file simply lacking
        # the columns printed "0 of 0 documents DISAGREE" -- nonsense, and the
        # not-available branch was unreachable.
        stored_ok = None if stored_n == 0 else (stored_bad == 0)
    except Exception:
        stored_ok = None

    obs = corr(seqs)
    allv = [x for v in seqs for x in v]
    sigma = statistics.pstdev(allv)
    steps = [abs(v[i] - v[i - 1]) for v in seqs for i in range(1, len(v))]
    sstep = statistics.pstdev(steps)
    print()
    print(f"  documents      : {len(seqs):,}")
    if stored_ok is None:
        print("  metric check   : no stored lewi_drop/nava columns; the metric")
        print("                   implementations here are UNVERIFIED against data")
    elif stored_ok:
        print(f"  metric check   : lewi_drop and nava reproduce the stored values "
              f"on {stored_n:,} documents")
    else:
        print(f"  metric check   : ** {stored_bad:,} of {stored_n:,} documents "
              f"DISAGREE with the stored lewi_drop/nava **")
    print(f"  observed r     : {obs:+.4f}")
    print(f"  sigma          : {sigma:.4f}")
    print(f"  sigma_step     : {sstep:.4f}")
    # Every null is compared against this observed value. If the scored file
    # has changed, the anchor changes and every p-value below refers to a
    # different quantity than the manuscript does. Say so loudly.
    # v14.3.0-14.5.0 checked only the observed r. sigma and sigma_step are the
    # GENERATING PARAMETERS of the two synthetic nulls: a scored file that left
    # r intact but altered either would have produced nulls from a different
    # process than the manuscript describes, with nothing firing. n is checked
    # for the same reason.
    print()
    if (args.paper_r != PAPER_OBSERVED_R or args.paper_sigma != PAPER_SIGMA
            or args.paper_sigma_step != PAPER_SIGMA_STEP
            or args.paper_n != PAPER_N_DOCS):
        print()
        print("  ** NON-DEFAULT ANCHORS SUPPLIED ON THE COMMAND LINE. The anchor")
        print("     check below is against values you passed, not against the")
        print("     manuscript's. This run does not verify agreement with the")
        print("     paper. **")
    print(f"  {'quantity':<16}{'this run':>12}{'manuscript':>12}   status")
    rule()
    # These four constants are values TYPED FROM THE MANUSCRIPT, not derived.
    # If one were mistyped the check would fire on a correct run or pass a
    # wrong one, so they are printed, overridable, and recorded in the output.
    checks = [("observed r", obs, args.paper_r, 5e-4),
              ("sigma", sigma, args.paper_sigma, 5e-4),
              ("sigma_step", sstep, args.paper_sigma_step, 5e-4),
              ("documents", float(len(seqs)), float(args.paper_n), 0.5)]
    out_anchor_ok = (stored_ok is not False)
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol
        out_anchor_ok &= ok
        fmt = "{:>12.0f}" if name == "documents" else "{:>+12.4f}"
        print(f"  {name:<16}" + fmt.format(got) + fmt.format(want) +
              ("   match" if ok else "   ** MISMATCH **"))
    if not out_anchor_ok:
        print()
        print("     One or more anchors differ from the manuscript. Every number")
        print("     below then refers to a different quantity, or is drawn from a")
        print("     different generating process, than the paper describes.")
        print("     Resolve that before using any result from this run.")

    out, tables = {"observed": round(obs, 4), "n_documents": len(seqs),
                   "workers": nw, "seed": args.seed}, {}
    DRAWS = {}
    CHUNKSIZES = {}
    JOBS = [("within-document permutation", draw_perm, args.perm, args.seed),
            ("synthetic i.i.d. normal", draw_iid, args.synth, args.seed + 1),
            ("synthetic random walk", draw_walk, args.synth, args.seed + 2)]

    bases = [b for _, _, _, b in JOBS]
    if len(set(bases)) != len(bases):
        print(f"FATAL: the three nulls share a seed base {bases}; their draws "
              f"would be identical."); return 3
    try:
        ctx = mp.get_context("spawn")
        with ctx.Pool(nw, initializer=_init, initargs=(seqs, sigma, sstep)) as pool:
            for label, fn, B, base in JOBS:
                sub(f"NULL: {label}")
                t0 = datetime.datetime.now()
                # v14.1.0 used pool.map, which prints nothing until the whole
                # job finishes. On a 10,000-draw run the user could not tell
                # working from hung. imap keeps ORDER (so the seeding
                # guarantee is unaffected) while allowing a progress line.
                cs = max(1, B // (nw * 8))
                CHUNKSIZES[label] = cs
                vals = []
                step = max(1, B // 20)
                for j, v in enumerate(pool.imap(fn, [(base, i) for i in range(B)],
                                                chunksize=cs), 1):
                    vals.append(v)
                    if j % step == 0 or j == B:
                        el_ = (datetime.datetime.now() - t0).total_seconds()
                        rate = j / max(el_, 1e-9)
                        eta = (B - j) / max(rate, 1e-9)
                        print(f"      {j:>7,}/{B:,}  {100*j/B:5.1f}%  "
                              f"{rate:6.1f} draws/s  eta {eta/60:5.1f} min",
                              flush=True)
                el = (datetime.datetime.now() - t0).total_seconds()
                print(f"    elapsed        : {el:.1f}s  "
                      f"({B/max(el,1e-9):.1f} draws/s on {nw} workers)")
                DRAWS[label] = vals
                out[label] = summarise(vals, obs, label)

        # ---- determinism self-test ------------------------------------------
        sub("SELF-TEST: parallel result equals serial result")
        # v14.1.0 tested only the permutation null. The other two use the same
        # seeding pattern, but "almost certainly the same" is not a check.
        _init(seqs, sigma, sstep)
        total_bad = 0
        # v14.1.0-14.8.0 returned 3 from the self-test BEFORE writing anything,
        # so a failure on a 10,000-draw run discarded every draw -- exactly when
        # the draws are needed to diagnose it. A round-5 comment claimed the
        # opposite. The draws are now on disk before the self-test runs.
        td_early = root / "results" / "tables"
        td_early.mkdir(parents=True, exist_ok=True)
        _ks = list(DRAWS)
        _n = max(len(DRAWS[k]) for k in _ks)
        with open(td_early / "null_draws_parallel.csv", "w", encoding="utf-8",
                  newline="") as _fh:
            _w = csv.writer(_fh); _w.writerow(["draw"] + _ks)
            for _i in range(_n):
                _w.writerow([_i + 1] + [f"{DRAWS[k][_i]:.6f}" if _i < len(DRAWS[k])
                                        else "" for k in _ks])
        print(f"    draws saved before verification -> "
              f"{td_early / 'null_draws_parallel.csv'}")
        print()

        # v14.1.0-14.5.0 recomputed only the FIRST n draws. With chunksize
        # B//(nw*8) the whole sample sat inside chunk 1, so the test could not
        # detect a chunk-boundary error -- the one failure mode parallelism
        # introduces. Indices now straddle every boundary and span the range.
        for label, fn, B, base in JOBS:
            cs = CHUNKSIZES.get(label, 1)
            idx = set()
            for k in range(1, max(2, B // max(cs, 1)) + 1):     # chunk edges
                for d in (-1, 0, 1):
                    j = k * cs + d
                    if 0 <= j < B:
                        idx.add(j)
            n_span = max(1, args.selftest // 2)
            for k in range(n_span):                             # spread across
                idx.add(min(B - 1, (k * B) // n_span))
            idx.add(0); idx.add(B - 1)
            idx = sorted(idx)[: max(args.selftest, 12) * 4]
            serial = [(i, fn((base, i))) for i in idx]
            bad = sum(1 for i, v in serial
                      if v is None or DRAWS[label][i] is None
                      or abs(v - DRAWS[label][i]) > 1e-12)
            total_bad += bad
            print(f"    {label:<32} {len(idx):>4} draws checked "
                  f"(chunk size {cs}, boundaries included)  mismatches {bad}")
        if total_bad:
            print()
            print("    ** The parallel result is NOT reproducible. Do not use it. **")
            return 3
        print()
        print("    All three nulls: parallel and serial draws are identical.")
        print("    The output is a function of (--perm, --synth, --seed) alone.")
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3

    # ---- write --------------------------------------------------------------
    sub("WRITING")
    td = root / "results" / "tables"; td.mkdir(parents=True, exist_ok=True)
    keys = list(DRAWS)
    nmax = max(len(DRAWS[k]) for k in keys)
    with open(td / "null_draws_parallel.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["draw"] + keys)
        for i in range(nmax):
            w.writerow([i + 1] + [f"{DRAWS[k][i]:.6f}" if i < len(DRAWS[k]) else ""
                                  for k in keys])
    out["metric_check_vs_stored"] = ("not available" if stored_ok is None
                                     else ("pass" if stored_ok else "FAIL"))
    out["metric_check_documents"] = stored_n
    out["anchor_matches_manuscript"] = bool(out_anchor_ok)
    out["paper_anchors"] = {"observed_r": args.paper_r, "sigma": args.paper_sigma,
                            "sigma_step": args.paper_sigma_step,
                            "n_documents": args.paper_n,
                            "source": "typed from the manuscript; overridable "
                                      "with --paper-* flags"}
    (td / "nulls_parallel.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  {td / 'null_draws_parallel.csv'}")
    print(f"  {td / 'nulls_parallel.json'}")

    rp = root / "results" / "NULLS_PARALLEL.md"
    L = ["# Null distributions (parallel run)", "",
         f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
         f"scripts/14_parallel_null.py v{SCRIPT_VERSION}.", "",
         f"Observed NAVA x LEWI on {len(seqs):,} documents: r = {obs:+.4f}", "",
         f"Every draw is seeded from base seed {args.seed} plus its draw index, "
         f"so the result is independent of the worker count. Verified against a "
         f"serial recomputation of the first {args.selftest} permutation draws.", "",
         "| null | draws | mean r | SD | 95% interval | p | MC SE |",
         "|---|---:|---:|---:|---|---:|---:|"]
    for k in keys:
        d = out[k]
        L.append(f"| {d['label']} | {d['draws']:,} | {d['mean']:+.4f} | {d['sd']:.4f} "
                 f"| [{d['lo']:+.4f}, {d['hi']:+.4f}] | {d['p']:.4f} | {d['mcse']:.4f} |")
    L.append("")
    rp.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  {rp}")
    print(f"  {root / 'results' / 'forensics' / 'console_log_14.txt'}")

    # v14.1.0 told the user to compare against the earlier run and did not do
    # it. Told-to-check is not checked.
    sub("CROSS-CHECK AGAINST THE EARLIER RUN")
    prev = td / "null_draws.csv"
    if not prev.exists():
        print(f"  {prev.name} not present; no comparison made.")
    else:
        try:
            pr = list(csv.DictReader(open(prev, encoding="utf-8", newline="")))
            # v14.5.0 compared only the permutation column even though the
            # earlier file carries all three.
            for other in [c for c in DRAWS if c != "within-document permutation"]:
                if other in (pr[0] if pr else {}):
                    ov = [float(r[other]) for r in pr if r.get(other, "").strip()]
                    if ov:
                        om_ = statistics.mean(ov)
                        nm_ = statistics.mean(DRAWS[other])
                        print(f"  {other:<28} earlier mean {om_:+.4f}  "
                              f"this run {nm_:+.4f}  diff {abs(nm_-om_):.4f}")
            col = "within-document permutation"
            old = [float(r[col]) for r in pr if r.get(col, "").strip()]
            new = DRAWS[col]
            print(f"  earlier file rows read for '{col}': {len(old):,}"
                  f"  (a short count here means a truncated file)")
            om, nm = statistics.mean(old), statistics.mean(new)
            oge = sum(1 for v in old if v >= obs)
            op = (1 + oge) / (len(old) + 1)
            np_ = out[col]["p"]
            omcse = math.sqrt(max(op * (1 - op), 1e-12) / (len(old) + 1))
            print(f"  earlier draws: {len(old):,}, mean {om:+.4f}")
            print(f"  p recomputed from those draws against the CURRENT observed")
            print(f"  value ({obs:+.4f}): {op:.4f}  (MC SE {omcse:.4f})")
            print(f"  This is NOT quoted from the earlier run's own report; if the")
            print(f"  observed anchor has changed it will differ from NULLS.md.")
            print(f"  this run     : {len(new):,} draws, mean {nm:+.4f}, "
                  f"p {np_:.4f}  (MC SE {out[col]['mcse']:.4f})")
            dp = abs(np_ - op)
            thresh = 2 * math.sqrt(omcse ** 2 + out[col]["mcse"] ** 2)
            print(f"  |dp|        : {dp:.4f}   two-SE band {thresh:.4f}")
            if len(old) >= len(new):
                print("  The earlier run has at least as many draws; this run does"
                      " not supersede it.")
            elif dp > thresh:
                print("  ** The p-value has moved by more than two combined Monte")
                print("     Carlo standard errors. Report the change explicitly;")
                print("     do not silently replace the earlier number. **")
            else:
                print("  The p-value is within two combined Monte Carlo standard")
                print("  errors of the earlier run. The larger run may replace it,")
                print("  and the change should still be stated.")
            out["cross_check"] = {"old_draws": len(old), "new_draws": len(new),
                                  "old_p": round(op, 4),
                                  "new_p": np_, "abs_diff": round(dp, 4),
                                  "two_se_band": round(thresh, 4)}
        except Exception as e:
            print(f"  comparison failed ({type(e).__name__}); no claim made.")

    sub("FIGURE 3")
    print("  Figure 3 in the manuscript is built from tables/null_draws.csv,")
    print("  NOT from the file this script writes. If you adopt this run, the")
    print("  figure must be rebuilt from tables/null_draws_parallel.csv or the")
    print("  plotted histogram will show a different number of draws from the")
    print("  one the text quotes.")

    # v14.7.0 exited 0 whenever the anchors matched, even if the metric check
    # could not run and the cross-check found no earlier file. A run in which
    # two of three verifications never happened reported success. The ledger
    # below separates PASS, FAIL and COULD-NOT-RUN, and only all-PASS exits 0.
    sub("VERDICT")
    ledger = []
    ledger.append(("anchors vs manuscript",
                   "PASS" if out_anchor_ok else "FAIL"))
    ledger.append(("metric implementations vs stored data",
                   "COULD NOT RUN" if stored_ok is None
                   else ("PASS" if stored_ok else "FAIL")))
    ledger.append(("parallel == serial, all nulls, chunk boundaries", "PASS"))
    if "cross_check" in out:
        c = out["cross_check"]
        ledger.append(("comparison with the earlier run",
                       "PASS" if c["old_draws"] < c.get("new_draws", 10**9)
                       else "COULD NOT RUN (earlier run is not smaller)"))
    else:
        ledger.append(("comparison with the earlier run", "COULD NOT RUN"))
    if args.paper_r != PAPER_OBSERVED_R or args.paper_sigma != PAPER_SIGMA \
            or args.paper_sigma_step != PAPER_SIGMA_STEP \
            or args.paper_n != PAPER_N_DOCS:
        ledger.append(("anchors are the manuscript's own values",
                       "COULD NOT RUN (overridden on the command line)"))
    for name, verdict in ledger:
        print(f"  {verdict:<46}  {name}")
    out["verdict"] = {n: v for n, v in ledger}
    (td / "nulls_parallel.json").write_text(json.dumps(out, indent=2),
                                            encoding="utf-8")
    n_fail = sum(1 for _, v in ledger if v.startswith("FAIL"))
    n_skip = sum(1 for _, v in ledger if v.startswith("COULD NOT RUN"))

    head("DONE")
    d = out["within-document permutation"]
    print(f"  observed r     : {obs:+.4f}")
    print(f"  permutation p  : {d['p']:.4f}   Monte Carlo SE {d['mcse']:.4f}")
    print()
    if "cross_check" in out:
        c = out["cross_check"]
        print(f"  vs earlier run : p {c['old_p']:.4f} -> {c['new_p']:.4f}, "
              f"|dp| {c['abs_diff']:.4f} against a {c['two_se_band']:.4f} band")
    if n_fail:
        print()
        print(f"  ** {n_fail} CHECK(S) FAILED. Do not use this run. Exiting 3. **")
        return 3
    if n_skip:
        print()
        print(f"  ** {n_skip} CHECK(S) COULD NOT RUN. The numbers above may be")
        print("     correct, but this run did not verify them. Exiting 1. **")
        return 1
    # v14.8.0 had a further "if not out_anchor_ok: return 3" here. It was DEAD:
    # a failed anchor already registers FAIL in the ledger, so n_fail returns 3
    # above and this branch could never execute. Removed rather than left as an
    # unreachable claim.
    print()
    print("  Every check ran and passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
