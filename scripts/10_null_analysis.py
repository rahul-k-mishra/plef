#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 10 : NULL DISTRIBUTIONS AND FORMAL TESTS
                       (v10.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
An internal review found that the paper's central claim rested on a single
reported correlation from a permutation procedure, described as "the null"
without stating how many permutations were drawn, what the null distribution
looked like, or what test compared the observed value to it. It also found
that the two synthetic nulls were reported to three decimal places with no
statement of the generating process, so neither could be reproduced.

This script fixes all of that. It draws proper null distributions, states
every generating parameter, and reports an empirical p-value for each.

  A  WITHIN-DOCUMENT PERMUTATION NULL
     B permutations. For each, every document's observed sentence-level
     sentiment values are randomly reordered; the metrics are recomputed and
     the correlation across documents is taken. Reports mean, SD, 2.5/97.5
     percentiles and the empirical p-value
         p = (1 + #{null r >= observed r}) / (B + 1).

  B  SYNTHETIC I.I.D. NULL, fully specified
     Each document of N sentences is replaced by N draws from
     Normal(0, sigma) where sigma is the pooled standard deviation of the
     observed sentence scores, stated in the output. Lengths are matched to
     the observed length distribution.

  C  SYNTHETIC AUTOCORRELATED RANDOM-WALK NULL, fully specified
     s_1 = 0; s_t = clip(s_{t-1} + e_t, -1, +1) with e_t ~ Normal(0, sigma_step).
     sigma_step is stated. Lengths matched. This null is reported because it
     shows the correlation an autocorrelated process produces, not because it
     is a plausible model of narrative.

  D  EVEN-WINDOW SMOOTHING CONVENTION
     Prints the exact window used at each position, so the centred moving
     average is reproducible rather than described.

  E  THE 36-POST HUMAN-LABEL COMPARISON
     Reports the macro-F1 of every system on the posts carrying human labels,
     with the denominator, so the difference quoted in the limitations can be
     reconstructed or dropped.

  F  RELATIONSHIP CORPUS LENGTH DISTRIBUTION
     Mean, SD, range and quartiles of word and sentence counts.

  G  THE TRIPLE-OVERLAP DOCUMENT
     Identifies the document present in three corpora, so the pairwise-versus-
     removed reconciliation is checkable rather than asserted.

REQUIREMENTS
------------
Stage A needs the per-sentence score vectors, which script 05.2.0+ stores for
corpora in trajectory scope. If they are absent it says so and does not
substitute a synthetic result.

EXIT CODES
----------
  0 all stages completed    2 missing prerequisite    3 stage A impossible
===============================================================================
"""

import argparse
import collections
import csv
import datetime
import json
import math
import random
import statistics
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "10.5.0"
B_PERM = 1000          # permutation draws
B_SYNTH = 1000         # synthetic-null draws
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


def rule(ch="-", w=80): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


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


def pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return num / (dx * dy) if dx and dy else None


# --- the metrics, matching the released core exactly -----------------------
def smooth(sig, w):
    """Centred moving average. At position i the window is
    [max(0, i-w), min(N, i+w+1)) -- 2w+1 wide in the interior and TRUNCATED at
    the boundaries, never padded. w is a half-width, so the window is always
    odd in the interior regardless of the parity of w."""
    out = []
    for i in range(len(sig)):
        lo, hi = max(0, i - w), min(len(sig), i + w + 1)
        out.append(sum(sig[lo:hi]) / (hi - lo))
    return out


def lewi_drop(s):
    n = len(s)
    w = max(1, n // 4)
    sm = smooth(s, w)
    bi, bv = None, -1.0
    for i in range(1, len(sm) - 1):
        v = abs(sm[i + 1] - 2.0 * sm[i] + sm[i - 1])
        if v > bv + 1e-12:
            bv, bi = v, i
    if bi is None or bi <= 0 or bi >= n:
        bi = max(1, min(n - 1, n // 2))
    return sum(s[:bi]) / bi - sum(s[bi:]) / (n - bi)


def nava(s):
    n = len(s)
    k = max(1, n // 4 if n < 9 else n // 3)
    return sum(s[:k]) / k - sum(s[n - k:]) / k


def corr_of(seqs):
    a = [nava(v) for v in seqs]
    b = [lewi_drop(v) for v in seqs]
    return pearson(a, b)


DRAWS = {}


def summarise(vals, observed, label):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        print(f"  {label}: no draws")
        return {}
    m = statistics.mean(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]
    ge = sum(1 for v in vals if v >= observed)
    p = (1 + ge) / (len(vals) + 1)
    print(f"    draws          : {len(vals)}")
    print(f"    mean r         : {m:+.4f}")
    print(f"    SD             : {sd:.4f}")
    print(f"    95% interval   : [{lo:+.4f}, {hi:+.4f}]")
    print(f"    null r >= obs  : {ge} of {len(vals)}")
    print(f"    empirical p    : {p:.4f}   "
          f"(p = (1 + #[null >= observed]) / (draws + 1))")
    DRAWS[label] = vals
    return {"label": label, "draws": len(vals), "mean": round(m, 4),
            "sd": round(sd, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "ge_observed": ge, "p": round(p, 4)}


# ===========================================================================
def _agree(A):
    """Unanimous and pairwise exact turning-point agreement within one round."""
    import itertools as _it
    for i, d in sorted(A.items()):
        print(f"    rater {i}: {len(d)} unique posts")
    if len(A) < 2:
        print("    only one rater file in this round; no agreement computable")
        return

    def _tp(r):
        try:
            return int(float(r.get("turning_point")))
        except (TypeError, ValueError):
            return None

    shared = set.intersection(*[set(d) for d in A.values()])
    print(f"    annotated by all {len(A)}: {len(shared)}")
    if len(A) >= 3 and shared:
        una = sum(1 for i in shared
                  if None not in [_tp(A[k][i]) for k in A]
                  and len({_tp(A[k][i]) for k in A}) == 1)
        print(f"    UNANIMOUS exact agreements : {una} of {len(shared)} "
              f"({100*una/len(shared):.1f}%)")
    if len(A) >= 3 and shared:
        # A two-of-three majority resolves an item when at least two annotators
        # chose the same value. The manuscript points at this count, so it must
        # be computed rather than inferred from the pairwise rates.
        res = 0
        for i in shared:
            vals = [_tp(A[k][i]) for k in A]
            vals = [v for v in vals if v is not None]
            if vals and max(vals.count(v) for v in set(vals)) >= 2:
                res += 1
        print(f"    MAJORITY-RESOLVED (>=2 of 3 agree) : {res} of {len(shared)} "
              f"({100*res/len(shared):.1f}%)")
        nz = sum(1 for i in shared
                 if [_tp(A[k][i]) for k in A].count(0) >= 2)
        print(f"      of which resolved as 'no turning point' : {nz}")
    for a_, b_ in _it.combinations(sorted(A), 2):
        ids = set(A[a_]) & set(A[b_])
        n = ex = 0
        for i in ids:
            x, y = _tp(A[a_][i]), _tp(A[b_][i])
            if x is None or y is None:
                continue
            n += 1
            ex += (x == y)
        if n:
            print(f"    PAIRWISE {a_} vs {b_}: {ex} of {n} identical "
                  f"({100*ex/n:.1f}%)")


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 10 -- nulls.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--perm", type=int, default=B_PERM)
    ap.add_argument("--synth", type=int, default=B_SYNTH)
    args = ap.parse_args()
    root = Path(args.root)
    canon = root / "results" / "canonical"
    if not canon.exists():
        print("FATAL: run script 05 first.")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_10.txt")
    sys.stdout = tee
    out, tables = {}, {}
    try:
        head("PLEF V2 -- SCRIPT 10 : NULL DISTRIBUTIONS AND FORMAL TESTS")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  permutations   : {args.perm}")
        print(f"  synthetic draws: {args.synth}")
        print(f"  seed           : {SEED}")

        rows = read_rows(canon / "scored_relationship.csv")
        seqs = []
        for r in rows:
            v = [f(x) for x in (r.get("sent_scores") or "").split(";") if x.strip()]
            v = [x for x in v if x is not None]
            if len(v) >= 4:
                seqs.append(v)
        sub("INPUT")
        print(f"  relationship documents scored     : {len(rows):,}")
        print(f"  with a stored sentence vector >=4 : {len(seqs):,}")
        if not seqs:
            print()
            print("  FATAL: no per-sentence vectors. Re-run script 05.2.0+ on the")
            print("  relationship shard; stage A cannot be computed without them")
            print("  and no substitute will be produced.")
            return 3
        observed = corr_of(seqs)
        print(f"  observed NAVA x LEWI              : r = {observed:+.4f}")
        out["observed"] = round(observed, 4)
        out["n_documents"] = len(seqs)

        # ---- A permutation null ------------------------------------------
        sub("A  WITHIN-DOCUMENT PERMUTATION NULL")
        print("  Each draw randomly reorders every document's own observed")
        print("  sentence-level sentiment values and recomputes both metrics.")
        print("  Each document's multiset of values is preserved exactly; only")
        print("  the order changes.")
        print()
        rnd = random.Random(SEED)
        vals = []
        for _ in range(args.perm):
            sh = []
            for v in seqs:
                w = v[:]
                rnd.shuffle(w)
                sh.append(w)
            vals.append(corr_of(sh))
        out["permutation"] = summarise(vals, observed, "within-document permutation")

        # ---- B iid null ---------------------------------------------------
        sub("B  SYNTHETIC I.I.D. NULL")
        allv = [x for v in seqs for x in v]
        sigma = statistics.pstdev(allv)
        mu = statistics.mean(allv)
        lens = [len(v) for v in seqs]
        print(f"  Generating process: for a document of N sentences, draw N")
        print(f"  independent values from Normal(0, sigma).")
        print(f"    sigma = pooled SD of the observed sentence scores = {sigma:.4f}")
        print(f"    (observed pooled mean {mu:+.4f}, set to 0 in the null)")
        print(f"    document lengths matched to the observed distribution")
        print(f"    N = {len(lens)} documents per draw, lengths {min(lens)}--{max(lens)}")
        print()
        rnd = random.Random(SEED + 1)
        vals = []
        for _ in range(args.synth):
            sh = [[rnd.gauss(0.0, sigma) for _ in range(L)] for L in lens]
            vals.append(corr_of(sh))
        out["iid"] = summarise(vals, observed, "synthetic i.i.d. normal")
        out["iid_sigma"] = round(sigma, 4)

        # ---- C random walk -------------------------------------------------
        sub("C  SYNTHETIC AUTOCORRELATED RANDOM-WALK NULL")
        steps = [abs(v[i] - v[i - 1]) for v in seqs for i in range(1, len(v))]
        sstep = statistics.pstdev(steps) if len(steps) > 1 else 0.25
        print(f"  Generating process: s_1 = 0;  s_t = clip(s_(t-1) + e_t, -1, +1)")
        print(f"  with e_t ~ Normal(0, sigma_step), independent across t.")
        print(f"    sigma_step = SD of the observed absolute successive")
        print(f"                 differences = {sstep:.4f}")
        print(f"    clipping to [-1, +1] matches the range of the sentiment score")
        print(f"    document lengths matched to the observed distribution")
        print()
        print("  This null is reported to show the correlation an autocorrelated")
        print("  process induces. It is not offered as a model of narrative.")
        print()
        rnd = random.Random(SEED + 2)
        vals = []
        for _ in range(args.synth):
            sh = []
            for L in lens:
                v0, s = 0.0, []
                for _ in range(L):
                    v0 = max(-1.0, min(1.0, v0 + rnd.gauss(0.0, sstep)))
                    s.append(v0)
                sh.append(s)
            vals.append(corr_of(sh))
        out["random_walk"] = summarise(vals, observed, "synthetic random walk")
        out["rw_sigma_step"] = round(sstep, 4)

        # ---- D smoothing convention ----------------------------------------
        sub("D  SMOOTHING CONVENTION")
        print("  The centred moving average uses a HALF-WIDTH w, so the window is")
        print("  2w+1 wide in the interior and is TRUNCATED at the boundaries,")
        print("  never padded and never reflected. The parity of w is therefore")
        print("  irrelevant: the window is always odd in the interior.")
        print()
        N = 12
        w = max(1, N // 4)
        print(f"  Worked example, N = {N}, w = floor(N/4) = {w}:")
        for i in (0, 1, 5, N - 2, N - 1):
            lo, hi = max(0, i - w), min(N, i + w + 1)
            print(f"    position {i:>2}: window [{lo}, {hi})  -> {hi-lo} value(s)")
        out["smoothing"] = {"half_width_rule": "w = max(1, floor(N/4))",
                            "window": "[max(0,i-w), min(N,i+w+1)), truncated",
                            "padding": "none"}

        # ---- E 36-post comparison ------------------------------------------
        sub("E  HUMAN-LABEL COMPARISON ON THE ANNOTATED POSTS")
        gold = {r["id"]: r for r in
                read_rows(root / "data" / "interim" / "annotations" / "gold_dev200.csv")}
        dev = read_rows(canon / "scored_dev_relationship.csv")
        idx = {r["id"]: r for r in dev}
        cl = ["pos", "neu", "neg"]
        def mf1(g, p):
            fs = []
            for c in cl:
                tp = sum(1 for a, b in zip(g, p) if a == c and b == c)
                fp = sum(1 for a, b in zip(g, p) if a != c and b == c)
                fn = sum(1 for a, b in zip(g, p) if a == c and b != c)
                pr = tp / (tp + fp) if tp + fp else 0.0
                rc = tp / (tp + fn) if tp + fn else 0.0
                fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
            return sum(fs) / len(fs)
        m = [(g, idx[i]) for i, g in gold.items() if i in idx
             and (g.get("gold_sentiment") or "").strip() in cl]
        if len(m) < 10:
            print(f"  only {len(m)} matched posts; not computed")
        else:
            gg = [g["gold_sentiment"] for g, _ in m]
            print(f"  posts with a human sentiment label and a score: {len(m)}")
            print(f"  label distribution: {dict(collections.Counter(gg))}")
            print()
            print(f"  {'system':<10}{'macro-F1':>10}")
            rule()
            rr = []
            for name, col in (("PLEF", "sentiment_mean"), ("vader", "b_vader"),
                              ("nrc", "b_nrc"), ("empath", "b_empath"),
                              ("afinn", "b_afinn"), ("huliu", "b_huliu")):
                pred = [("pos" if (f(r[col]) or 0) > 0.05
                         else "neg" if (f(r[col]) or 0) < -0.05 else "neu")
                        for _, r in m]
                v = mf1(gg, pred)
                print(f"  {name:<10}{v:>10.4f}")
                rr.append({"system": name, "n": len(m), "macro_f1": round(v, 4)})
            tables["human_label_f1"] = rr
            print()
            print(f"  n = {len(m)} is small; these values carry wide intervals and")
            print("  should be reported with the denominator or not at all.")

        # ---- F length distribution ------------------------------------------
        sub("F  RELATIONSHIP CORPUS LENGTH DISTRIBUTION")
        wds = sorted(int(f(r["n_words"])) for r in rows if f(r["n_words"]))
        sts = sorted(int(f(r["n_sents"])) for r in rows if f(r["n_sents"]))
        def q(a, p):
            return a[min(len(a) - 1, int(p * len(a)))]
        print("  Median is the mean of the two central values on an even-sized")
        print("  sample; quartiles are lower-index order statistics. The")
        print("  manuscript quotes the median as printed here.")
        for lab, a in (("words", wds), ("sentences", sts)):
            print(f"  {lab:<10} n={len(a):,}  mean {statistics.mean(a):.1f}  "
                  f"SD {statistics.pstdev(a):.1f}  min {min(a)}  "
                  f"Q1 {q(a,.25)}  median {statistics.median(a):g}  "
                  f"Q3 {q(a,.75)}  max {max(a)}")
        out["length"] = {"words_mean": round(statistics.mean(wds), 1),
                         "words_sd": round(statistics.pstdev(wds), 1),
                         "words_min": min(wds), "words_max": max(wds),
                         "words_median": statistics.median(wds),
                         "sents_median": statistics.median(sts)}

        # ---- G triple overlap ------------------------------------------------
        sub("G  THE TRIPLE-OVERLAP DOCUMENT")
        import hashlib
        interim = root / "data" / "interim"
        sets = {}
        for p in sorted(interim.glob("corpus_*.csv")):
            c = p.stem.replace("corpus_", "")
            if c == "relationship":
                pass
            d = {}
            for r in read_rows(p, ["id", "text"]):
                t = (r.get("text") or "").strip()
                if t:
                    d[hashlib.sha1(" ".join(t.lower().split()).encode(
                        "utf-8", "replace")).hexdigest()] = r.get("id")
            sets[c] = d
        cnt = collections.Counter()
        for c, d in sets.items():
            for h in d:
                cnt[h] += 1
        multi = [h for h, k in cnt.items() if k >= 3]
        print(f"  documents present in three or more corpora: {len(multi)}")
        for h in multi[:5]:
            where = [(c, sets[c][h]) for c in sets if h in sets[c]]
            print(f"    hash {h[:16]}  in {[w[0] for w in where]}")
            print(f"      ids: {[w[1] for w in where]}")
        out["triple_overlap"] = len(multi)
        if len(multi) == 1:
            print()
            print("  Exactly one, which is what the pairwise-versus-removed excess")
            print("  of one implies. The manuscript's explanation is confirmed.")

        # ---- H annotator agreement, unanimous vs pairwise -------------------
        sub("H  TURNING-POINT AGREEMENT: UNANIMOUS AND PAIRWISE")
        print("  The manuscript must not claim the pairwise form unless the raw")
        print("  records show it. Both are computed here, per annotation round.")
        print("  v10.2.0 searched only the annotations directory itself and")
        print("  reported 'fewer than two rater files' because the multi-annotator")
        print("  rounds had been archived into subdirectories. Those are searched")
        print("  now, and each round is reported separately: rounds are never")
        print("  pooled, since two of them were rejected.")
        ad = root / "data" / "interim" / "annotations"
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
        if not rounds:
            print(f"  no annotation files found under {ad}")
        for grp in sorted(rounds):
            print()
            print(f"  ROUND DIRECTORY: {grp}")
            _agree(rounds[grp])
        out["agreement_rounds"] = {g: len(v) for g, v in rounds.items()}
        print()
        print("  Quote the unanimous figure in the manuscript unless every")
        print("  pairwise count for the SAME round is also zero. They are")
        print("  different claims.")

        # ---- I  chance benchmarks on the metric's ADMISSIBLE support --------
        sub("I  CHANCE BENCHMARKS ON THE ADMISSIBLE SUPPORT")
        print("  Equation (1) restricts the watershed to 2 <= i* <= N-1, so the")
        print("  metric can return only N-2 positions, not N. Chance benchmarks")
        print("  computed as 1/N and 3/N therefore use the wrong support. They")
        print("  are recomputed here exactly, per post.")
        print()
        gold2 = {r["id"]: r for r in
                 read_rows(ad.parent / "annotations" / "gold_dev200.csv")}
        sc2 = read_rows(canon / "scored_dev_relationship.csv",
                        ["id", "n_sents", "lewi_idx"])
        if not sc2:
            sc2 = read_rows(canon / "scored_relationship.csv",
                            ["id", "n_sents", "lewi_idx"])
        ix2 = {r["id"]: r for r in sc2}
        Ns, hums = [], []
        for i, g in gold2.items():
            r = ix2.get(i)
            if not r or (r.get("lewi_idx") or "").strip() == "":
                continue
            try:
                t = int(float(g.get("gold_turning_point")))
                n_ = int(float(r["n_sents"]))
            except (TypeError, ValueError):
                continue
            if t > 0:
                Ns.append(n_)
                hums.append(t)
        if not Ns:
            print("  no comparison posts found")
        else:
            # exact: metric picks uniformly from {2..N-1}, size N-2
            ex_old = statistics.mean([1.0 / max(1, n_) for n_ in Ns])
            ex_new = statistics.mean([1.0 / max(1, n_ - 2) for n_ in Ns])
            # within-1: admissible metric positions within 1 of the human choice
            def w1(n_, h):
                adm = set(range(2, n_))                 # 1-indexed 2..N-1
                near = {h - 1, h, h + 1} & adm
                return len(near) / max(1, len(adm))
            w1_old = statistics.mean([min(1.0, 3.0 / max(1, n_)) for n_ in Ns])
            w1_new = statistics.mean([w1(n_, h) for n_, h in zip(Ns, hums)])
            print(f"  comparison posts n = {len(Ns)}   N range {min(Ns)}--{max(Ns)},"
                  f" median {statistics.median(Ns):g}")
            print()
            print(f"  {'benchmark':<34}{'as reported':>13}{'corrected':>12}")
            rule()
            print(f"  {'exact match':<34}{100*ex_old:>12.1f}%{100*ex_new:>11.1f}%")
            print(f"  {'within one sentence':<34}{100*w1_old:>12.1f}%{100*w1_new:>11.1f}%")
            print()
            print("  The corrected figures use the support of Equation (1):")
            print("    exact       = mean over posts of 1/(N_i - 2)")
            print("    within one  = mean over posts of |{h-1,h,h+1} n {2..N-1}|")
            print("                  / (N_i - 2), computed per post rather than")
            print("                  approximated as 3/N")
            out["chance_admissible"] = {
                "n": len(Ns), "exact_reported": round(100*ex_old, 2),
                "exact_corrected": round(100*ex_new, 2),
                "within1_reported": round(100*w1_old, 2),
                "within1_corrected": round(100*w1_new, 2)}

        # pair-specific chance for the multi-annotator rounds
        print()
        print("  PAIR-SPECIFIC CHANCE, round by round")
        allsc = {r["id"]: r for r in read_rows(canon / "scored_dev_relationship.csv",
                                              ["id", "n_sents"])}
        if not allsc:
            allsc = {r["id"]: r for r in read_rows(canon / "scored_relationship.csv",
                                                   ["id", "n_sents"])}
        import itertools as _it2
        for grp in sorted(rounds):
            A2 = rounds[grp]
            if len(A2) < 2:
                continue
            print(f"    {grp}")
            for a_, b_ in _it2.combinations(sorted(A2), 2):
                ids = set(A2[a_]) & set(A2[b_])
                ns = []
                for i in ids:
                    r = allsc.get(i)
                    if r and (r.get("n_sents") or "").strip():
                        ns.append(int(float(r["n_sents"])))
                if len(ns) < 5:
                    print(f"      {a_} vs {b_}: sentence counts unavailable "
                          f"for most shared posts; chance not computed")
                    continue
                ch = statistics.mean([1.0 / max(1, n_ - 2) for n_ in ns])
                print(f"      {a_} vs {b_}: n={len(ns)}  chance "
                      f"{100*ch:.2f}%  (mean of 1/(N_i-2))")

        # ---- write -----------------------------------------------------------
        sub("WRITING")
        td = root / "results" / "tables"
        td.mkdir(parents=True, exist_ok=True)
        (td / "nulls.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"  {td / 'nulls.json'}")
        for name, data in tables.items():
            if data:
                keys = list(data[0])
                with open(td / f"{name}.csv", "w", encoding="utf-8", newline="") as fh:
                    w_ = csv.DictWriter(fh, fieldnames=keys)
                    w_.writeheader(); w_.writerows(data)
                print(f"  {td / (name + '.csv')}")

        dp = td / "null_draws.csv"
        keys = [k for k in DRAWS]
        if keys:
            n = max(len(DRAWS[k]) for k in keys)
            with open(dp, "w", encoding="utf-8", newline="") as fh:
                w_ = csv.writer(fh)
                w_.writerow(["draw"] + keys)
                for i in range(n):
                    w_.writerow([i + 1] + [(f"{DRAWS[k][i]:.6f}"
                                            if i < len(DRAWS[k]) else "")
                                           for k in keys])
            print(f"  {dp}")
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                plt.rcParams.update({"font.size": 8, "axes.spines.top": False,
                                     "axes.spines.right": False, "figure.dpi": 300,
                                     "savefig.dpi": 300})
                fd = root / "results" / "figures"
                fd.mkdir(parents=True, exist_ok=True)
                fig, ax = plt.subplots(figsize=(3.6, 2.8))
                cols = {"synthetic i.i.d. normal": "#718096",
                        "within-document permutation": "#c05621",
                        "synthetic random walk": "#6b46c1"}
                for k in keys:
                    d = out.get({"within-document permutation": "permutation",
                                 "synthetic i.i.d. normal": "iid",
                                 "synthetic random walk": "random_walk"}[k], {})
                    ax.hist(DRAWS[k], bins=45, alpha=0.55,
                            color=cols.get(k, "#999"),
                            label=f"{k}\n$p$={d.get('p', float('nan')):.3f}")
                ax.axvline(observed, color="k", lw=1.6)
                ax.text(observed, ax.get_ylim()[1] * 0.97,
                        f"  observed\n  $r$={observed:+.3f}", fontsize=6.5, va="top")
                ax.set_xlabel(r"NAVA $\times$ LEWI  $r$")
                ax.set_ylabel("null draws")
                ax.legend(frameon=False, fontsize=5.6, loc="upper left")
                fig.tight_layout()
                fig.savefig(fd / "fig3a_null_distributions.png")
                plt.close(fig)
                print(f"  {fd / 'fig3a_null_distributions.png'}  "
                      f"(plotted from the actual draws)")
            except Exception as e:
                print(f"  figure not drawn ({type(e).__name__}); "
                      f"null_draws.csv is written and can be plotted directly")

        rp = root / "results" / "NULLS.md"
        L = ["# Null distributions and formal tests", "",
             f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
             f"scripts/10_null_analysis.py v{SCRIPT_VERSION}.", "",
             f"RNG: Python `random.Random`, seed {SEED} for the permutation null, "
             f"{SEED+1} for the i.i.d. null, {SEED+2} for the random walk.", "",
             f"Observed NAVA x LEWI on {out['n_documents']:,} documents: "
             f"r = {out['observed']:+.4f}", "",
             "| null | draws | mean r | SD | 95% interval | p |",
             "|---|---:|---:|---:|---|---:|"]
        for k in ("permutation", "iid", "random_walk"):
            d = out.get(k) or {}
            if d:
                L.append(f"| {d['label']} | {d['draws']} | {d['mean']:+.4f} "
                         f"| {d['sd']:.4f} | [{d['lo']:+.4f}, {d['hi']:+.4f}] "
                         f"| {d['p']:.4f} |")
        L += ["",
              "Empirical p is the proportion of null draws at least as large as "
              "the observed correlation, with the usual +1 correction:",
              "p = (1 + #[null r >= observed r]) / (draws + 1).", "",
              "## Generating processes", "",
              f"- **Within-document permutation.** Each document's observed "
              f"sentence-level values are randomly reordered; the multiset is "
              f"preserved exactly and only the order changes.",
              f"- **Synthetic i.i.d.** N values per document from "
              f"Normal(0, {out.get('iid_sigma')}), where the scale is the pooled "
              f"SD of the observed sentence scores; lengths matched.",
              f"- **Synthetic random walk.** s_1 = 0; "
              f"s_t = clip(s_(t-1) + e_t, -1, +1), "
              f"e_t ~ Normal(0, {out.get('rw_sigma_step')}), where the step scale "
              f"is the SD of the observed absolute successive differences; "
              f"lengths matched.", "",
              "## Smoothing", "",
              "The centred moving average uses half-width w = max(1, floor(N/4)); "
              "the window at position i is [max(0, i-w), min(N, i+w+1)), truncated "
              "at the boundaries and never padded. The window is 2w+1 wide in the "
              "interior, so the parity of w does not arise.", ""]
        rp.write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"  {rp}")

        head("DONE")
        p_perm = (out.get("permutation") or {}).get("p")
        print(f"  observed r        : {out['observed']:+.4f}")
        if p_perm is not None:
            print(f"  permutation p     : {p_perm:.4f}")
            print()
            if p_perm > 0.05:
                print("  The observed correlation is NOT larger than the permutation")
                print("  null at the conventional level. Quote the p-value, the")
                print("  number of draws and the interval, not the mean alone.")
            else:
                print("  The observed correlation DOES exceed the permutation null.")
                print("  The manuscript's central claim must be revised accordingly.")
        return 0
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3
    finally:
        sys.stdout = tee.stdout; tee.close()


if __name__ == "__main__":
    sys.exit(main())
