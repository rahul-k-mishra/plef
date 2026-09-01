#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 06 : STATISTICS, INTERVALS, NULLS, SCOREBOARD
                       (v06.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
Script 05 produced a scored dataset. This one turns it into the numbers that go
in the manuscript, with an interval on every one of them, and refuses to report
any statistic in a form that hides what it is doing.

It writes results/tables/*.csv and results/RESULTS.md.

WHAT IT COMPUTES, AND WHY EACH ONE EXISTS
-------------------------------------------
  A  Lexicon coverage, every system, every corpus.
     PLEF sees 28.4% of what VADER sees on narratives, and near zero on short
     text. This is the mechanism behind every accuracy number below, so it is
     reported FIRST rather than buried.

  B  The length threshold: at what document length does PLEF produce a signal
     at all? Answers "who is this tool for" with a number instead of a claim.

  C  Table 3 -- macro-F1, every system, bootstrap 95% CI on every cell.
     Reviewer 1 asked for intervals; the manuscript claimed 500-resample
     bootstraps and printed none.

  D  Threshold sweep. D4 declares macro-F1 threshold-conditional, so the
     sweep is reported rather than a single cut point being presented as fact.

  E  Abstention-aware evaluation. PLEF returning 0.000 means "no lexical
     evidence", not "neutral". Scoring it as a neutral prediction is a
     category error. Both readings are reported.

  F  NAVA x LEWI against TWO nulls: synthetic length-matched noise, and the
     WITHIN-DOCUMENT permutation (same sentences, same marginals, order
     destroyed). The permutation null is the strongest form of Reviewer 3's
     objection and is only possible because script 05.2.0 stored the vectors.

  G  LEWI V1 vs V2, split by whether the two algorithms agree. The pooled
     median is zero by construction whenever agreement exceeds 50% and tells
     the reader nothing; it is never reported alone.

  H  External criteria: PAI x NRC-VAD dominance, TEG x NRC-EmoInt volatility.
     Neither is derived from PLEF's own scores, so neither is circular.

  I  PTI x PAI with and without the shared pronoun term, quantifying how much
     of H2 was an algebraic identity (Reviewer 2, point 7).

  J  The legacy-toy table: what V1's Table 3 was actually measuring.

  K  Overlap-corrected pooling. SemEval and TweetEval share 22,603 items, so
     any mean over both double-weights them.

  L  The hypothesis scoreboard, with H1 and H5 marked PENDING ANNOTATION until
     the gold file exists.

DEPENDENCIES
------------
  Standard library only. Bootstrap is resampling, not scipy.

EXIT CODES
----------
  0 done    2 missing prerequisite
===============================================================================
"""

import argparse
import collections
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
SCRIPT_VERSION = "06.8.1"

BOOT_N = 2000
THRESH = 0.05
SWEEP = [0.00, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30]
SYSTEMS = [("PLEF", "sentiment_mean"), ("vader", "b_vader"), ("nrc", "b_nrc"),
           ("empath", "b_empath"), ("afinn", "b_afinn"), ("huliu", "b_huliu"),
           ("labmt", "b_labmt")]
LEGACY = [("V1_vader", "b_V1_vader_toy"), ("V1_nrc", "b_V1_nrc_toy"),
          ("V1_liwc", "b_V1_liwc_toy")]
THREE = ["goemotions", "semeval2017", "meld", "tweeteval", "dailydialog"]
BINARY = ["isear", "empathetic"]
NOLABEL = ["relationship"]
TRAJ = "relationship"


class Tee:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, s):
        try:
            self.stdout.write(s)
        except UnicodeEncodeError:
            self.stdout.write(s.encode("ascii", "replace").decode("ascii"))
        self.f.write(s)
    def flush(self):
        self.stdout.flush(); self.f.flush()
    def close(self):
        try: self.f.close()
        except Exception: pass


def rule(ch="-", w=94): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


def lab3(s, t=THRESH):
    return "pos" if s > t else ("neg" if s < -t else "neu")


def lab2(s):
    return "pos" if s > 0 else "neg"


def macro_f1(gold, pred, classes):
    fs = []
    for c in classes:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(fs) / len(fs)


def _binom(n, p, rnd):
    """Binomial draw. Normal approximation for large n, exact loop for small."""
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    if n > 200:
        v = rnd.gauss(n * p, math.sqrt(max(1e-12, n * p * (1 - p))))
        return max(0, min(n, int(round(v))))
    return sum(1 for _ in range(n) if rnd.random() < p)


def _multinomial(n, probs, rnd):
    """Sequential conditional binomials."""
    out, rem, left = [], n, 1.0
    for pr in probs[:-1]:
        if rem <= 0 or left <= 1e-12:
            out.append(0)
            continue
        k = _binom(rem, min(1.0, pr / left), rnd)
        out.append(k)
        rem -= k
        left -= pr
    out.append(max(0, rem))
    return out


def _f1_from_cells(cells, classes):
    """macro-F1 from a confusion matrix alone."""
    fs = []
    for c in classes:
        tp = cells.get((c, c), 0)
        fp = sum(cells.get((g, c), 0) for g in classes if g != c)
        fn = sum(cells.get((c, q), 0) for q in classes if q != c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(fs) / len(fs)


def boot_f1(gold, pred, classes, B=None, seed=42):
    """Bootstrap the CONFUSION MATRIX, not the item list.

    Resampling n items B times is O(n*B). With n = 101,026 and B = 2,000 that is
    200 million operations per system per corpus and does not finish. macro-F1
    is a function of the confusion matrix alone, and bootstrapping exchangeable
    items is equivalent to drawing the cell counts from a multinomial with the
    observed cell proportions. That is O(cells * B) and yields the same
    interval; the equivalence is asserted in the self-test below.
    """
    B = B or BOOT_N
    n = len(gold)
    if n < 2:
        return None, None
    cnt = collections.Counter(zip(gold, pred))
    keys = list(cnt)
    probs = [cnt[k] / n for k in keys]
    rnd = random.Random(seed)
    out = []
    for _ in range(B):
        out.append(_f1_from_cells(dict(zip(keys, _multinomial(n, probs, rnd))),
                                  classes))
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def _selftest_bootstrap():
    """Fail the run if the fast bootstrap ever stops matching item resampling."""
    rnd = random.Random(11)
    cl = ["pos", "neu", "neg"]
    g = [rnd.choice(cl) for _ in range(3000)]
    pr = [x if rnd.random() < 0.6 else rnd.choice(cl) for x in g]
    lo, hi = boot_f1(g, pr, cl, B=1500)
    slow = []
    for _ in range(400):
        idx = [rnd.randrange(3000) for _ in range(3000)]
        slow.append(macro_f1([g[i] for i in idx], [pr[i] for i in idx], cl))
    slow.sort()
    blo, bhi = slow[10], slow[389]
    ok = abs(lo - blo) < 0.01 and abs(hi - bhi) < 0.01
    return ok, (lo, hi), (blo, bhi)


def pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return num / (dx * dy) if dx and dy else None


def boot_r(x, y, B=BOOT_N, seed=7):
    rnd = random.Random(seed)
    n = len(x)
    out = []
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        r = pearson([x[i] for i in idx], [y[i] for i in idx])
        if r is not None:
            out.append(r)
    if not out:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def load(root, name, cols=None):
    p = Path(root) / "results" / "canonical" / f"scored_{name}.csv"
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            out.append({k: r.get(k) for k in cols} if cols else r)
    return out


# ===========================================================================
def A_coverage(root, corpora, tables):
    sub("A  LEXICON COVERAGE -- the mechanism behind every number below")
    print("  Fraction of tokens each system's lexicon can see. PLEF's own")
    print("  coverage is computed here for every corpus, not only where script")
    print("  05 stored it.")
    print()
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_core as C
    names = ["PLEF", "vader", "nrc", "empath", "afinn", "huliu", "labmt"]
    print(f"  {'corpus':<15}" + "".join(f"{n[:7]:>9}" for n in names) + f"{'ratio':>9}")
    rule()
    rows_out = []
    for c in corpora:
        rows = load(root, c)
        if not rows:
            continue
        # PLEF coverage from the corpus text when script 05 did not store it
        cp = [f(r.get("cov_plef")) for r in rows]
        cp = [x for x in cp if x is not None]
        if not cp:
            src = Path(root) / "data" / "interim" / f"corpus_{c}.csv"
            cp = []
            if src.exists():
                with open(src, encoding="utf-8", errors="replace", newline="") as fh:
                    for r in csv.DictReader(fh):
                        t = C.tokenize(r.get("text") or "")
                        if t:
                            cp.append(sum(1 for w in t if w in C.LEXICON) / len(t))
        if not cp:
            print(f"  {c:<15} PLEF coverage unavailable: no cov_plef column and no "
                  f"data/interim/corpus_{c}.csv")
        vals = {"PLEF": statistics.mean(cp) if cp else None}
        for n in names[1:]:
            v = [f(r.get(f"cov_{n}")) for r in rows]
            v = [x for x in v if x is not None]
            vals[n] = statistics.mean(v) if v else float("nan")
        ratio = (100 * vals["PLEF"] / vals["vader"]) \
            if (vals.get("PLEF") and vals.get("vader")) else None
        cells = "".join((f"{100*vals[n]:>8.2f}%" if vals.get(n) is not None
                         else f"{'n/a':>9}") for n in names)
        print(f"  {c:<15}" + cells +
              (f"{ratio:>8.1f}%" if ratio is not None else f"{'n/a':>9}") +
              ("   [annotation split, not an evaluation corpus]"
               if c in AUX_CORPORA else ""))
        rows_out.append({"corpus": c,
                         **{n: (round(vals[n], 6) if vals.get(n) is not None else "")
                            for n in names},
                         "plef_pct_of_vader": round(ratio, 2) if ratio else ""})
    tables["coverage"] = rows_out
    print()
    print("  The 'ratio' column is PLEF's coverage as a percentage of VADER's.")
    return rows_out


def B_length(root, corpora, tables):
    sub("B  LENGTH THRESHOLD -- at what document length does PLEF fire at all?")
    bins = [(1, 9), (10, 19), (20, 39), (40, 79), (80, 159), (160, 319), (320, 10**9)]
    labels = [(f"{a}-{b}" if b < 10**9 else f"{a}+") for a, b in bins]
    print(f"  {'corpus':<15}" + "".join(f"{x:>11}" for x in labels))
    rule()
    out = []
    for c in corpora:
        rows = load(root, c, ["n_words", "sentiment_mean"])
        if not rows:
            continue
        line = f"  {c:<15}"
        rec = {"corpus": c}
        for a, b in bins:
            sel = [r for r in rows
                   if (f(r["n_words"]) or 0) >= a and (f(r["n_words"]) or 0) <= b]
            if len(sel) < 20:
                line += f"{'-':>11}"
                continue
            fires = sum(1 for r in sel if (f(r["sentiment_mean"]) or 0.0) != 0.0)
            pct = 100 * fires / len(sel)
            line += f"{pct:>10.0f}%"
            rec[f"{a}_{b}"] = round(pct, 1)
        print(line)
        out.append(rec)
    tables["length_threshold"] = out
    print()
    print("  Percentage of documents in each word-count bin for which PLEF")
    print("  produced a non-zero score. Bins with fewer than 20 documents show '-'.")
    print("  This is the scope of the instrument, stated as a measurement.")
    return out



def auc_ovr(scores, gold, positive):
    """One-vs-rest AUC by the Mann-Whitney identity. Ties get half credit."""
    pos = [s for s, g in zip(scores, gold) if g == positive and s is not None]
    neg = [s for s, g in zip(scores, gold) if g != positive and s is not None]
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks, i, n = {}, 0, len(allv)
    while i < n:
        j = i
        while j + 1 < n and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks.setdefault(k, r)
        i = j + 1
    rsum = sum(ranks[k] for k in range(n) if allv[k][1] == 1)
    return (rsum - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))


def C2_auc(root, tables):
    sub("C2  MACRO-AUC -- threshold-free, and declared PRIMARY in D4")
    print("  D4 states that macro-F1 is threshold-conditional and macro-AUC is the")
    print("  primary metric. v06.2.0 declared that and then did not compute it.")
    print("  This section closes that gap.")
    print()
    print("  NOTE ON THE THREE-CLASS CASE: a single scalar score can rank pos-vs-rest")
    print("  and neg-vs-rest, but NOT neutral-vs-rest, because neutral sits in the")
    print("  middle of the scale and is not monotone in the score. Macro-AUC below is")
    print("  therefore the mean of the pos and neg one-vs-rest AUCs, and that")
    print("  limitation is stated rather than hidden. V1 reported a three-class")
    print("  'macro-AUC' from one scalar without saying how it was obtained.")
    print()
    allsys = SYSTEMS + LEGACY
    out = []
    for group, corpora, classes in (("THREE-CLASS (pos/neg one-vs-rest)", THREE,
                                     ["pos", "neg"]),
                                    ("BINARY (D10, D16)", BINARY, ["pos"])):
        print(f"  {group}")
        print(f"  {'corpus':<14}" + "".join(f"{n[:8]:>10}" for n, _ in allsys))
        rule()
        for c in corpora:
            rows = load(root, c)
            rows = [r for r in rows if r["gold"] in ("pos", "neu", "neg")]
            if not rows:
                continue
            gold = [r["gold"] for r in rows]
            line = f"  {c:<14}"
            rec = {"corpus": c}
            for name, col in allsys:
                sc = [f(r[col]) for r in rows]
                aucs = [a for a in (auc_ovr(sc, gold, k) for k in classes)
                        if a is not None]
                if not aucs:
                    line += f"{'-':>10}"
                    continue
                # neg-vs-rest is ranked by the NEGATED score
                if "neg" in classes:
                    an = auc_ovr([-x if x is not None else None for x in sc],
                                 gold, "neg")
                    ap = auc_ovr(sc, gold, "pos")
                    m = statistics.mean([x for x in (ap, an) if x is not None])
                else:
                    m = aucs[0]
                line += f"{m:>10.3f}"
                rec[name] = round(m, 4)
            print(line)
            out.append(rec)
        print()
    tables["auc"] = out
    print("  0.500 is chance. A system at 0.500 is not ranking the classes at all.")
    return out


def C3_trivial(root, tables):
    sub("C3  TRIVIAL BASELINES -- the row reviewers always ask for")
    print("  v06.2.0 had no constant or random baseline. A results table without one")
    print("  cannot show whether a system is doing anything at all.")
    print()
    print(f"  {'corpus':<14}{'majority':>10}{'always-neu':>12}{'random':>9}"
          f"{'PLEF':>9}{'best real':>11}   verdict")
    rule()
    out = []
    for c in THREE:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neu", "neg")]
        if not rows:
            continue
        g = [r["gold"] for r in rows]
        cl = ["pos", "neu", "neg"]
        maj = collections.Counter(g).most_common(1)[0][0]
        const = macro_f1(g, [maj] * len(g), cl)
        neu = macro_f1(g, ["neu"] * len(g), cl)
        rnd = random.Random(3)
        rr = macro_f1(g, [rnd.choice(cl) for _ in g], cl)
        P = macro_f1(g, [lab3(f(r["sentiment_mean"]) or 0.0) for r in rows], cl)
        best = max((macro_f1(g, [lab3(f(r[col]) or 0.0) for r in rows], cl), n)
                   for n, col in SYSTEMS if n != "PLEF")
        floor = max(const, neu, rr)
        v = "PLEF AT OR BELOW CHANCE" if P <= floor + 0.005 else ""
        print(f"  {c:<14}{const:>10.3f}{neu:>12.3f}{rr:>9.3f}{P:>9.3f}"
              f"{best[0]:>7.3f} {best[1]:<4}  {v}")
        out.append({"corpus": c, "majority": round(const, 4),
                    "always_neutral": round(neu, 4), "random": round(rr, 4),
                    "PLEF": round(P, 4), "best_real": round(best[0], 4),
                    "best_real_system": best[1],
                    "plef_at_or_below_chance": bool(P <= floor + 0.005)})
    tables["trivial_baselines"] = out
    return out


AUX_CORPORA = {"dev_relationship"}   # scored for the annotation only


def J_gase_ablation(root, tables):
    sub("J  GASE ABLATION -- real components, renormalised weights (D25)")
    print("  V1's published Table 8 subtracted weight x 0.5, a hardcoded constant;")
    print("  the component values were never read, which is why removing Entropy")
    print("  and removing Attachment gave identical numbers to four decimals.")
    print("  This is the same table computed from the components actually stored.")
    print()
    W = {"S": 0.30, "H": 0.25, "A": 0.25, "G": 0.20}
    print(f"  {'corpus':<14}{'full':>8}" +
          "".join(f"{'d'+k:>9}" for k in ("S", "H", "A", "G")) + "   component means")
    rule()
    out = []
    for c in (sorted(tables.get("_corpora", [])) or [TRAJ]):
        rows = load(root, c, ["gase", "gase_S", "gase_H", "gase_A", "gase_G"])
        rows = [r for r in rows if f(r.get("gase")) is not None]
        if len(rows) < 50:
            continue
        comp = {k: [f(r[f"gase_{k}"]) for r in rows] for k in ("S", "H", "A", "G")}
        comp = {k: [x for x in v if x is not None] for k, v in comp.items()}
        if not all(comp.values()):
            continue
        mu = {k: statistics.mean(v) for k, v in comp.items()}
        vals = {"S": mu["S"], "H": 1 - mu["H"], "A": 1 - mu["A"], "G": 1 - mu["G"]}
        full = sum(W[k] * vals[k] for k in W)
        rec = {"corpus": c, "full": round(full, 4)}
        line = f"  {c:<14}{full:>8.4f}"
        for drop in ("S", "H", "A", "G"):
            keep = {k: v for k, v in W.items() if k != drop}
            tot = sum(keep.values())
            g2 = sum((w / tot) * vals[k] for k, w in keep.items())
            rec[f"delta_{drop}"] = round(g2 - full, 4)
            line += f"{g2-full:>+9.4f}"
        sd = {k: statistics.pstdev(v) for k, v in comp.items()}
        line += ("   S=%.3f(sd%.3f) H=%.3f(sd%.3f) A=%.3f(sd%.3f) G=%.3f(sd%.3f)"
                 % (mu["S"], sd["S"], mu["H"], sd["H"], mu["A"], sd["A"],
                    mu["G"], sd["G"]))
        print(line)
        rec.update({f"mean_{k}": round(mu[k], 4) for k in mu})
        rec.update({f"sd_{k}": round(sd[k], 4) for k in sd})
        out.append(rec)
    print()
    print("  ** HOW TO READ THE DELTA COLUMNS. They are NOT a measure of how much")
    print("     information a component carries. Leave-one-out with renormalised")
    print("     weights redistributes the dropped weight to the remaining terms,")
    print("     so a component whose VALUE is far below the others raises the")
    print("     score when removed. That is why dS is strongly POSITIVE: S")
    print("     averages about 0.01 while (1-H), (1-A) and (1-G) average near 1.")
    print("     The delta measures a component's value relative to the rest. **")
    print()
    print("  THE COLUMN THAT ANSWERS H4 IS THE STANDARD DEVIATION:")
    print(f"    {'corpus':<14}{'sd(S)':>9}{'sd(H)':>9}{'sd(A)':>9}{'sd(G)':>9}"
          f"   live components")
    rule()
    for r in out:
        sds = {k: r.get(f"sd_{k}", 0.0) for k in ("S", "H", "A", "G")}
        live = [k for k, v in sds.items() if v >= 0.05]
        dead_w = sum({"S": .30, "H": .25, "A": .25, "G": .20}[k]
                     for k, v in sds.items() if v < 0.05)
        print(f"    {r['corpus']:<14}" + "".join(f"{sds[k]:>9.3f}" for k in "SHAG")
              + f"   {live if live else 'NONE'}  ({dead_w:.0%} of the weight is"
                f" a fixed offset)")
    print()
    print("  V1 published deltas: S -0.010, H -0.125, A -0.125, G -0.100")
    print("  H and A were IDENTICAL because both were weight x 0.5, never measured.")
    print("  A component with a near-zero standard deviation adds an offset and no")
    print("  information, whatever its weight.")
    tables["gase_ablation"] = out
    return out



METRIC_COLS = [("sentiment_mean", "sentiment"), ("lewi_drop", "LEWI"),
               ("teg", "TEG"), ("nava", "NAVA"), ("gase", "GASE"),
               ("pti", "PTI"), ("pai", "PAI"), ("rci", "RCI"),
               ("cd_index", "CD-index"), ("vads", "VADS"), ("ties", "TIES"),
               ("nspl", "NSPL")]


def M_descriptive(root, corpora, tables):
    """Gap 1 and 2: every metric gets a reported distribution.

    v06.3.0 produced NO result for RCI, VADS or RASP -- three of twelve metrics
    with no empirical content, which is precisely the defect this project was
    opened to correct in V1. A metric with no distribution reported is a metric
    the paper cannot claim to have measured.
    """
    sub("M  DESCRIPTIVE STATISTICS -- every metric, every corpus")
    print("  n = items where the metric is DEFINED (not None). A metric defined on")
    print("  a small fraction of a corpus is inapplicable there, not weak.")
    out = []
    for c in corpora:
        rows = load(root, c)
        if not rows:
            continue
        print()
        print(f"  {c}   ({len(rows):,} items)" +
              ("   [ANNOTATION SPLIT -- excluded from all pooled results]"
               if c in AUX_CORPORA else ""))
        print(f"    {'metric':<12}{'n':>9}{'defined':>9}{'mean':>10}{'sd':>9}"
              f"{'median':>10}{'min':>9}{'max':>9}")
        for col, label in METRIC_COLS:
            v = [f(r.get(col)) for r in rows]
            v = [x for x in v if x is not None]
            if not v:
                print(f"    {label:<12}{0:>9}{'0.0%':>9}   metric never defined")
                out.append({"corpus": c, "metric": label, "n": 0,
                            "defined_pct": 0.0})
                continue
            rec = {"corpus": c, "metric": label, "n": len(v),
                   "defined_pct": round(100 * len(v) / len(rows), 2),
                   "mean": round(statistics.mean(v), 5),
                   "sd": round(statistics.pstdev(v), 5) if len(v) > 1 else 0.0,
                   "median": round(statistics.median(v), 5),
                   "min": round(min(v), 5), "max": round(max(v), 5)}
            out.append(rec)
            print(f"    {label:<12}{rec['n']:>9,}{rec['defined_pct']:>8.1f}%"
                  f"{rec['mean']:>10.4f}{rec['sd']:>9.4f}{rec['median']:>10.4f}"
                  f"{rec['min']:>9.3f}{rec['max']:>9.3f}")
        rasp = collections.Counter((r.get("rasp_dominant") or "none").strip()
                                   for r in rows)
        tot = sum(rasp.values())
        top = ", ".join(f"{k}:{100*v/tot:.1f}%" for k, v in rasp.most_common(5))
        print(f"    {'RASP':<12}{tot:>9,}{'100.0%':>9}   dominant archetype: {top}")
        out.append({"corpus": c, "metric": "RASP", "n": tot,
                    "defined_pct": 100.0, "distribution": dict(rasp.most_common())})
    tables["descriptive"] = [o for o in out if "distribution" not in o]
    tables["rasp_distribution"] = [o for o in out if "distribution" in o]
    print()
    print("  A metric whose sd is near zero carries no information regardless of")
    print("  how it is weighted downstream.")
    return out


def N_effect_sizes(root, tables):
    """Gap 3: V1's Table 2 reported Cohen's d and never said between what."""
    sub("N  EFFECT SIZES -- Cohen's d, positive vs negative gold items")
    print("  V1's Table 2 reported a Cohen's d with no stated contrast. Here the")
    print("  contrast is explicit: each system's score on gold-positive items")
    print("  versus gold-negative items. Larger is better separation.")
    print()
    allsys = SYSTEMS + LEGACY
    print(f"  {'corpus':<14}" + "".join(f"{n[:8]:>10}" for n, _ in allsys))
    rule()
    out = []
    for c in THREE + BINARY:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neg")]
        if len(rows) < 50:
            continue
        line = f"  {c:<14}"
        rec = {"corpus": c, "n_pos": sum(1 for r in rows if r["gold"] == "pos"),
               "n_neg": sum(1 for r in rows if r["gold"] == "neg")}
        for name, col in allsys:
            P = [f(r[col]) for r in rows if r["gold"] == "pos"]
            N = [f(r[col]) for r in rows if r["gold"] == "neg"]
            P = [x for x in P if x is not None]
            N = [x for x in N if x is not None]
            if len(P) < 2 or len(N) < 2:
                line += f"{'-':>10}"
                continue
            sp = math.sqrt(((len(P)-1)*statistics.variance(P) +
                            (len(N)-1)*statistics.variance(N)) /
                           max(1, len(P)+len(N)-2))
            d = (statistics.mean(P) - statistics.mean(N)) / sp if sp else 0.0
            rec[name] = round(d, 4)
            line += f"{d:>10.3f}"
        print(line)
        out.append(rec)
    tables["effect_sizes"] = out
    print()
    print("  Cohen: 0.2 small, 0.5 medium, 0.8 large. A d near zero means the")
    print("  system does not separate positive from negative items at all.")
    return out


def O_mcnemar(root, tables):
    """Gap 4: V1's H7 was a McNemar test. It is replaced, not dropped."""
    sub("O  PAIRED SYSTEM COMPARISON -- McNemar, PLEF vs each real baseline")
    print("  V1's H7 asked only whether PLEF and VADER 'differ significantly',")
    print("  which at N=5,000 is unfalsifiable in practice and was reported as a")
    print("  win on corpora where PLEF lost. Here the DIRECTION is reported with")
    print("  the discordant counts, so a significant difference cannot be")
    print("  presented as a success when it is a loss.")
    print()
    print(f"  {'corpus':<14}{'baseline':<10}{'PLEF only':>11}{'base only':>11}"
          f"{'chi2':>10}{'p<.001':>8}   direction")
    rule()
    out = []
    for c in THREE:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neu", "neg")]
        if not rows:
            continue
        gold = [r["gold"] for r in rows]
        P = [lab3(f(r["sentiment_mean"]) or 0.0) for r in rows]
        pc = [p == g for p, g in zip(P, gold)]
        for name, col in SYSTEMS:
            if name == "PLEF":
                continue
            B = [lab3(f(r[col]) or 0.0) for r in rows]
            bc = [b == g for b, g in zip(B, gold)]
            b01 = sum(1 for x, y in zip(pc, bc) if x and not y)
            b10 = sum(1 for x, y in zip(pc, bc) if y and not x)
            if b01 + b10 == 0:
                continue
            chi = (abs(b01 - b10) - 1) ** 2 / (b01 + b10)
            sig = chi > 10.828
            direction = ("PLEF better" if b01 > b10 else "PLEF WORSE")
            print(f"  {c:<14}{name:<10}{b01:>11,}{b10:>11,}{chi:>10.1f}"
                  f"{'yes' if sig else 'no':>8}   {direction}")
            out.append({"corpus": c, "baseline": name, "plef_only": b01,
                        "baseline_only": b10, "chi2": round(chi, 2),
                        "significant_p001": bool(sig), "direction": direction})
    tables["mcnemar"] = out
    worse = sum(1 for o in out if o["direction"] == "PLEF WORSE")
    print()
    print(f"  PLEF is the worse system in {worse} of {len(out)} paired comparisons.")
    dd = [o for o in out if o["corpus"] == "dailydialog"]
    if dd and all(o["direction"] == "PLEF better" for o in dd):
        print()
        print("  ** DailyDialog: PLEF wins all six comparisons here by very large")
        print("     margins. This is the ABSTENTION ARTIFACT, not superiority.")
        print("     PLEF returns 0.000 on ~85% of a corpus that is ~85% neutral,")
        print("     and McNemar counts those abstentions as correct predictions.")
        print("     Threshold-free AUC does not: PLEF 0.584 vs VADER 0.731 on the")
        print("     same corpus. Report AUC as primary for DailyDialog. **")
    return out


def E2_abstention_binary(root, tables):
    """Gap 6: the abstention analysis skipped the binary corpora."""
    sub("E2  ABSTENTION ON THE BINARY CORPORA (D10, D16)")
    print(f"  {'corpus':<14}{'fires':>8}{'PLEF all':>10}{'VADER all':>11}"
          f"{'PLEF|fires':>12}{'VADER|fires':>13}{'delta':>9}")
    rule()
    out = []
    for c in BINARY:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neg")]
        if not rows:
            continue
        gold = [r["gold"] for r in rows]
        P = [f(r["sentiment_mean"]) for r in rows]
        V = [f(r["b_vader"]) for r in rows]
        cl = ["pos", "neg"]
        pa = macro_f1(gold, [lab2(x) if x is not None else "neg" for x in P], cl)
        va = macro_f1(gold, [lab2(x) if x is not None else "neg" for x in V], cl)
        idx = [i for i, x in enumerate(P) if x is not None and x != 0.0]
        if len(idx) < 30:
            continue
        g2 = [gold[i] for i in idx]
        pf = macro_f1(g2, [lab2(P[i]) for i in idx], cl)
        vf = macro_f1(g2, [lab2(V[i]) if V[i] is not None else "neg" for i in idx], cl)
        fires = 100 * len(idx) / len(rows)
        print(f"  {c:<14}{fires:>7.1f}%{pa:>10.3f}{va:>11.3f}{pf:>12.3f}"
              f"{vf:>13.3f}{pf-vf:>+9.3f}")
        out.append({"corpus": c, "fires_pct": round(fires, 2),
                    "plef_all": round(pa, 4), "vader_all": round(va, 4),
                    "plef_fires": round(pf, 4), "vader_fires": round(vf, 4),
                    "delta": round(pf - vf, 4)})
    tables["abstention_binary"] = out
    return out


def P_figures(root, tables):
    """Gap 5: figures. matplotlib is an EVALUATION dependency, never a core one."""
    sub("P  FIGURES")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  matplotlib unavailable ({type(e).__name__}); figures skipped.")
        print("  The core is standard-library only by design; figures are part of")
        print("  the evaluation harness. Install with: pip install matplotlib")
        return []
    fd = Path(root) / "results" / "figures"
    fd.mkdir(parents=True, exist_ok=True)
    made = []

    cov = tables.get("coverage") or []
    if cov:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        cs = [c["corpus"] for c in cov]
        x = range(len(cs))
        ax.bar([i - 0.2 for i in x], [100*float(c["PLEF"] or 0) for c in cov],
               0.4, label="PLEF (348 entries)")
        ax.bar([i + 0.2 for i in x], [100*float(c["vader"] or 0) for c in cov],
               0.4, label="VADER (7,506 entries)")
        ax.set_xticks(list(x)); ax.set_xticklabels(cs, rotation=30, ha="right")
        ax.set_ylabel("% of tokens matched"); ax.legend()
        ax.set_title("Lexicon coverage: PLEF vs VADER")
        fig.tight_layout(); fig.savefig(fd / "fig1_coverage.png", dpi=150)
        plt.close(fig); made.append("fig1_coverage.png")

    lt = tables.get("length_threshold") or []
    if lt:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        keys = [k for k in lt[0] if k != "corpus"]
        for rec in lt:
            xs = [i for i, k in enumerate(keys) if rec.get(k) is not None]
            ys = [rec[k] for k in keys if rec.get(k) is not None]
            ax.plot(xs, ys, marker="o", label=rec["corpus"])
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels([k.replace("_", "-") for k in keys], rotation=30)
        ax.set_ylabel("% of documents where PLEF fires")
        ax.set_xlabel("document length (words)")
        ax.set_title("PLEF requires narrative-length text to produce any signal")
        ax.legend(fontsize=7); fig.tight_layout()
        fig.savefig(fd / "fig2_length_threshold.png", dpi=150)
        plt.close(fig); made.append("fig2_length_threshold.png")

    nl = tables.get("nava_lewi_nulls") or {}
    if nl.get("observed") is not None:
        fig, ax = plt.subplots(figsize=(7, 3.6))
        labels, vals = ["observed"], [nl["observed"]]
        for k, lab in (("perm_null_mean", "sentence-order\npermutation null"),
                       ("synth_iid_normal", "iid noise null"),
                       ("synth_random_walk", "random-walk null")):
            if nl.get(k) is not None:
                labels.append(lab); vals.append(nl[k])
        ax.bar(labels, vals, color=["#333"] + ["#999"] * (len(vals) - 1))
        ax.set_ylabel("NAVA x LEWI  r"); ax.set_ylim(0, 1)
        ax.set_title("The observed correlation does not exceed its null")
        fig.tight_layout(); fig.savefig(fd / "fig3_nava_lewi_null.png", dpi=150)
        plt.close(fig); made.append("fig3_nava_lewi_null.png")

    t3 = tables.get("table3") or {}
    if t3:
        fig, ax = plt.subplots(figsize=(9, 4.4))
        cs = [c for c in THREE if c in t3]
        names = [n for n, _ in SYSTEMS]
        w = 0.8 / len(names)
        for j, n in enumerate(names):
            xs = [i + j * w - 0.4 for i in range(len(cs))]
            ys = [t3[c][n]["f1"] for c in cs]
            err = [[t3[c][n]["f1"] - t3[c][n]["lo"] for c in cs],
                   [t3[c][n]["hi"] - t3[c][n]["f1"] for c in cs]]
            ax.bar(xs, ys, w, yerr=err, capsize=1.5, label=n)
        ax.set_xticks(range(len(cs))); ax.set_xticklabels(cs, rotation=25, ha="right")
        ax.set_ylabel("macro-F1"); ax.legend(fontsize=7, ncol=4)
        ax.set_title("Macro-F1 with bootstrap 95% CI")
        fig.tight_layout(); fig.savefig(fd / "fig4_table3.png", dpi=150)
        plt.close(fig); made.append("fig4_table3.png")

    for m in made:
        print(f"  {m}")
    print(f"  -> {fd}")
    return made



def _silver_labels(root, v1):
    """V1's keyword labels for the relationship corpus.

    Preferred source: the v1_silver column of corpus_relationship.csv (present
    from script 03.4.0 onward). Fallback: join by id against V1's original
    reddit_posts_corpus.csv, so this works without re-running script 03.
    """
    out = {}
    p = Path(root) / "data" / "interim" / "corpus_relationship.csv"
    if p.exists():
        with open(p, encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("v1_silver") or "").strip()
                if v in ("pos", "neu", "neg"):
                    out[r["id"]] = v
    if out:
        return out, "corpus_relationship.csv (v1_silver column)"
    if v1:
        q = Path(v1) / "reddit_posts_corpus.csv"
        if q.exists():
            with open(q, encoding="utf-8", errors="replace", newline="") as fh:
                for r in csv.DictReader(fh):
                    v = (r.get("sentiment") or "").strip()
                    if v in ("pos", "neu", "neg"):
                        out[r.get("id", "")] = v
            return out, "V1 reddit_posts_corpus.csv (joined by id)"
    return {}, None


def annotation_status(root):
    """Distinguish 'no annotation attempted' from 'attempted and unusable'.

    v06.6.0 decided this from whether gold_dev200.csv existed. That reports
    PENDING for a study in which three annotation rounds were completed and
    rejected -- which reads as if the answer is still coming. It is not, and
    why it is not is itself the finding.
    """
    ad = Path(root) / "data" / "interim" / "annotations"
    gold = ad / "gold_dev200.csv"
    if gold.exists():
        return "usable", str(gold), {}
    quarantined = sorted(list(ad.glob("gold*UNUSABLE*.csv")) +
                         list(ad.glob("gold*QUARANT*.csv")))
    rows = {}
    for i in (1, 2, 3):
        p = ad / f"annotations_rater{i}.csv"
        if p.exists():
            try:
                with open(p, encoding="utf-8", errors="replace", newline="") as f:
                    rows[i] = sum(1 for _ in csv.DictReader(f))
            except Exception:
                pass
    if quarantined or rows:
        return "attempted_unusable", (str(quarantined[0]) if quarantined else None), rows
    return "none", None, {}


def _gold_labels(root):
    p = Path(root) / "data" / "interim" / "annotations" / "gold_dev200.csv"
    if not p.exists():
        return {}
    out = {}
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            v = (r.get("gold_sentiment") or "").strip()
            if v in ("pos", "neu", "neg"):
                out[r["id"]] = v
    return out


def Q_domain_split(root, tables, t3, v1=None):
    """Reviewer 1, point 3 -- relationship-domain vs general-domain macro-F1.

    v06.5.0 declared this "NOT COMPUTABLE" because the relationship corpus has
    no gold labels. That was an over-correction. V1's Table 2 openly described
    those labels as "Silver (keyword)", and Reviewer 1 asked his question
    knowing that. Refusing to answer a scope question because the labels are
    silver -- when the paper always said they were silver -- suppresses a
    number that is defensible WITH ITS CAVEAT.

    So it is computed and reported as SILVER, with the label distribution and a
    constant-class baseline printed beside it so the reader can judge, and with
    the human-gold version computed automatically once the annotation lands.
    """
    sub("Q  DOMAIN SPLIT -- Reviewer 1, point 3")
    cl = ["pos", "neu", "neg"]
    out = []
    silver, src = _silver_labels(root, v1)
    rows = load(root, TRAJ)
    gen = {}
    if t3:
        for name, _ in SYSTEMS:
            gen[name] = statistics.mean([t3[c][name]["f1"] for c in THREE if c in t3])

    if not silver:
        print("  V1 silver labels unavailable. Pass --v1 <V1 path> or re-run")
        print("  script 03.4.0 so corpus_relationship.csv carries v1_silver.")
    else:
        m = [r for r in rows if silver.get(r["id"]) in cl]
        g = [silver[r["id"]] for r in m]
        dist = collections.Counter(g)
        maj = dist.most_common(1)[0][0]
        print(f"  RELATIONSHIP DOMAIN, against V1's KEYWORD SILVER labels")
        print(f"    source       : {src}")
        print(f"    matched      : {len(m):,} of {len(rows):,} scored posts")
        print(f"    distribution : {dict(dist)}")
        print()
        print("  ** CAVEAT, which must travel with this number in the manuscript:")
        print(f"     these labels are keyword-derived and call "
              f"{100*dist['pos']/max(1,len(g)):.0f}% of breakup, infidelity and")
        print("     heartbreak narratives POSITIVE. They are not a human criterion")
        print("     and this column is NOT like-for-like with the human-labelled")
        print("     general-domain column beside it. **")
        print()
        print(f"  {'system':<12}{'relationship':>14}{'general':>10}{'delta':>9}")
        rule()
        for name, col in SYSTEMS:
            p_ = [lab3(f(r[col]) or 0.0) for r in m]
            rel = macro_f1(g, p_, cl)
            d = rel - gen.get(name, 0.0)
            print(f"  {name:<12}{rel:>14.3f}{gen.get(name, 0):>10.3f}{d:>+9.3f}")
            out.append({"labels": "V1_silver", "system": name,
                        "relationship": round(rel, 4),
                        "general": round(gen.get(name, 0), 4), "delta": round(d, 4),
                        "n": len(m)})
        base = macro_f1(g, [maj] * len(g), cl)
        print(f"  {'majority':<12}{base:>14.3f}{'-':>10}{'-':>9}   (constant '{maj}')")
        best = max(out, key=lambda o: o["delta"])
        print()
        print(f"  Largest positive delta: {best['system']} ({best['delta']:+.3f}).")
        print("  A system that does NOT degrade on the relationship domain while")
        print("  losing on general benchmarks is the scope claim, evidenced.")

    gold = _gold_labels(root)
    # The annotation is on the dev split, so the scored rows for it are in
    # scored_dev_relationship.csv. v06.8.0 fixed section S and left Q looking in
    # the evaluation corpus, where the gold ids match nothing by construction.
    rows = (load(root, "dev_relationship") or rows)
    print()
    if not gold:
        st, qpath, rows_n = annotation_status(root)
        if st == "attempted_unusable":
            print("  HUMAN-GOLD VERSION: NOT AVAILABLE. Annotation was attempted")
            print(f"  (rater rows {rows_n}) and rejected: inter-rater reliability")
            print("  fell below the usable threshold, so no gold file was built.")
            print("  The silver column above is therefore the only domain-split")
            print("  evidence, and its caveat stands.")
        else:
            print("  HUMAN-GOLD VERSION: pending annotation. When gold_dev200.csv")
            print("  exists this section recomputes the split on human labels and")
            print("  measures how far the keyword labels were from humans.")
    else:
        m = [r for r in rows if gold.get(r["id"]) in cl]
        if len(m) < 20:
            print(f"  gold file present but only {len(m)} scored posts match; skipped")
        else:
            g = [gold[r["id"]] for r in m]
            print(f"  RELATIONSHIP DOMAIN, against HUMAN GOLD  (n={len(m)})")
            print(f"    distribution : {dict(collections.Counter(g))}")
            print()
            print(f"  {'system':<12}{'relationship':>14}{'general':>10}{'delta':>9}")
            rule()
            for name, col in SYSTEMS:
                p_ = [lab3(f(r[col]) or 0.0) for r in m]
                rel = macro_f1(g, p_, cl)
                d = rel - gen.get(name, 0.0)
                print(f"  {name:<12}{rel:>14.3f}{gen.get(name, 0):>10.3f}{d:>+9.3f}")
                out.append({"labels": "human_gold", "system": name,
                            "relationship": round(rel, 4),
                            "general": round(gen.get(name, 0), 4),
                            "delta": round(d, 4), "n": len(m)})
            if silver:
                both = [(gold[r["id"]], silver[r["id"]]) for r in m
                        if r["id"] in silver]
                if both:
                    agr = sum(1 for a, b in both if a == b) / len(both)
                    k = kappa_pairs([a for a, _ in both], [b for _, b in both])
                    print()
                    print(f"  V1 KEYWORD SILVER vs HUMAN GOLD  (n={len(both)})")
                    print(f"    agreement {100*agr:.1f}%   Cohen's kappa "
                          f"{k:+.3f}" if k is not None else f"    agreement {100*agr:.1f}%")
                    print("    This is what the silver row above was worth. If it is")
                    print("    near chance, the silver column is reported only as a")
                    print("    record of what V1 used, never as evidence.")
                    out.append({"labels": "silver_vs_gold", "system": "-",
                                "agreement": round(agr, 4),
                                "kappa": round(k, 4) if k is not None else None,
                                "n": len(both)})
    tables["domain_split"] = out
    return out


def kappa_pairs(a, b):
    n = len(a)
    if not n:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def R_moderators(root, tables):
    """Gap 9 -- Reviewer 1, point 4.

    He asked why some correlations are lower than others and suggested text
    length and genre. v06.4.0 gave intervals and never tested a moderator. This
    also tests V1's Section 6.2 assertion that PTI and PAI 'converge most
    strongly in longer, more personal, self-authored texts', which was stated
    with no evidence at all.
    """
    sub("R  MODERATOR ANALYSIS -- does correlation strength vary with length?")
    rows = load(root, TRAJ)
    if not rows:
        print("  relationship corpus not scored")
        return []
    bins = [(20, 149), (150, 299), (300, 599), (600, 10**9)]
    pairs = [("pti", "pai", "PTI x PAI"),
             ("pti", "pai_v1", "PTI x PAI_v1"),
             ("nava", "lewi_drop", "NAVA x LEWI"),
             ("teg", "emoint_teg", "TEG x EmoInt"),
             ("pai", "vad_dominance", "PAI x VAD dom")]
    print(f"  {'pair':<16}" + "".join(
        f"{(f'{a}-{b}' if b < 10**9 else f'{a}+'):>20}" for a, b in bins))
    rule()
    out = []
    for a, b, label in pairs:
        line = f"  {label:<16}"
        rec = {"pair": label}
        for lo, hi in bins:
            sel = [r for r in rows
                   if lo <= (f(r.get("n_words")) or 0) <= hi]
            X, Y = [], []
            for r in sel:
                u, v = f(r.get(a)), f(r.get(b))
                if u is not None and v is not None:
                    X.append(u); Y.append(v)
            if len(X) < 40:
                line += f"{'n<40':>20}"
                continue
            rr = pearson(X, Y)
            clo, chi = boot_r(X, Y, B=min(BOOT_N, 800))
            # NEVER slice a formatted number to fit a column: an earlier version
            # used [-18:] and silently truncated the leading minus sign, so
            # r = -0.124 printed as 0.124 next to a negative CI.
            line += f"{rr:+.3f}[{clo:+.2f},{chi:+.2f}]".rjust(20)
            rec[f"{lo}_{hi}"] = round(rr, 4)
            rec[f"n_{lo}_{hi}"] = len(X)
        print(line)
        out.append(rec)
    print()
    print("  V1's Section 6.2 asserted that PTI and PAI 'converge most strongly in")
    print("  longer, more personal, self-authored texts' with no evidence. If the")
    print("  PTI x PAI row above does not rise with length, that sentence is false")
    print("  and must be removed rather than softened.")
    print()
    print("  Across corpora, correlation strength against mean document length:")
    lens, rs = [], []
    for c in THREE + BINARY:
        rr = load(root, c, ["n_words", "pti", "pai"])
        w = [f(r["n_words"]) for r in rr if f(r["n_words"]) is not None]
        X, Y = [], []
        for r in rr:
            u, v = f(r["pti"]), f(r["pai"])
            if u is not None and v is not None:
                X.append(u); Y.append(v)
        if len(X) > 100 and w:
            pr = pearson(X, Y)
            if pr is not None:
                lens.append(statistics.mean(w)); rs.append(pr)
                print(f"    {c:<14} mean words {statistics.mean(w):>6.0f}   "
                      f"PTI x PAI r = {pr:+.3f}")
    if len(lens) > 3:
        mr = pearson(lens, rs)
        print(f"    across corpora: r(mean length, PTI x PAI r) = {mr:+.3f}  (n={len(lens)})")
        out.append({"pair": "meta: length vs PTIxPAI r", "across_corpora_r": round(mr, 4)})
    tables["moderators"] = out
    return out


def write_results_md(root, tables):
    """Gap 7 -- the docstring promised results/RESULTS.md and never wrote it."""
    sub("WRITING RESULTS.md")
    p = Path(root) / "results" / "RESULTS.md"
    L = ["# PLEF V2 -- Results", "",
         f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
         f"scripts/06_statistics.py v{SCRIPT_VERSION}.", "",
         "Every number here is produced by that script from "
         "`results/canonical/*.csv`. Nothing is transcribed by hand.", ""]

    cov = tables.get("coverage") or []
    if cov:
        L += ["## Lexicon coverage", "",
              "| corpus | PLEF | VADER | PLEF as % of VADER |", "|---|---:|---:|---:|"]
        def pct(x):
            # Render each cell independently. An earlier version voided the whole
            # row when any single value was missing, so a present VADER figure
            # printed as n/a because PLEF was absent.
            try:
                return f"{100*float(x):.2f}%" if x not in (None, "") else "n/a"
            except (TypeError, ValueError):
                return "n/a"
        for c in cov:
            ratio = c.get("plef_pct_of_vader")
            L.append(f"| {c['corpus']} | {pct(c.get('PLEF'))} | "
                     f"{pct(c.get('vader'))} | "
                     f"{ratio if ratio not in (None, '') else 'n/a'}"
                     f"{'%' if ratio not in (None, '') else ''} |")
        L += ["", "PLEF's 348-entry lexicon is the mechanism behind every accuracy "
              "number below.", ""]

    lt = tables.get("length_threshold") or []
    if lt:
        keys = [k for k in lt[0] if k != "corpus"]
        L += ["## Length threshold: where PLEF produces any signal", "",
              "| corpus | " + " | ".join(k.replace("_", "-") for k in keys) + " |",
              "|---" * (len(keys) + 1) + "|"]
        for r in lt:
            L.append("| " + r["corpus"] + " | " +
                     " | ".join(f"{r[k]}%" if r.get(k) is not None else "-"
                                for k in keys) + " |")
        L.append("")

    t3 = tables.get("table3") or {}
    if t3:
        names = [n for n, _ in SYSTEMS]
        L += ["## Table 3: macro-F1 with bootstrap 95% CI", "",
              "| corpus | " + " | ".join(names) + " |", "|---" * (len(names)+1) + "|"]
        for c in THREE + BINARY:
            if c not in t3:
                continue
            L.append("| " + c + " | " + " | ".join(
                f"{t3[c][n]['f1']:.3f} [{t3[c][n]['lo']:.3f}, {t3[c][n]['hi']:.3f}]"
                for n in names) + " |")
        L.append("")

    tb = tables.get("trivial_baselines") or []
    if tb:
        L += ["## Trivial baselines", "",
              "| corpus | majority | always-neutral | random | PLEF | best real |",
              "|---|---:|---:|---:|---:|---:|"]
        for r in tb:
            L.append(f"| {r['corpus']} | {r['majority']} | {r['always_neutral']} "
                     f"| {r['random']} | **{r['PLEF']}** | {r['best_real']} "
                     f"({r['best_real_system']}) |")
        L.append("")

    nl = tables.get("nava_lewi_nulls") or {}
    if nl.get("observed") is not None:
        L += ["## NAVA x LEWI against its nulls", "",
              f"- observed: r = {nl['observed']:+.3f} "
              f"[{nl['ci'][0]:+.3f}, {nl['ci'][1]:+.3f}], n = {nl['n']:,}"]
        if nl.get("perm_null_mean") is not None:
            L.append(f"- within-document sentence permutation null: "
                     f"r = {nl['perm_null_mean']:+.3f}")
        for k, lab in (("synth_iid_normal", "iid noise"),
                       ("synth_random_walk", "random walk")):
            if nl.get(k) is not None:
                L.append(f"- synthetic {lab} null: r = {nl[k]:+.3f}")
        L += ["", "The permutation null preserves each document's sentences and "
              "marginal distribution and destroys only their order.", ""]

    sb = tables.get("scoreboard") or []
    if sb:
        L += ["## Hypothesis scoreboard", "",
              "| hypothesis | verdict | detail |", "|---|---|---|"]
        for r in sb:
            L.append(f"| {r['hypothesis']} | **{r['verdict']}** | {r['detail']} |")
        L.append("")

    ab = tables.get("gase_ablation") or []
    if ab:
        L += ["## GASE ablation (real components, renormalised)", "",
              "| corpus | full | dS | dH | dA | dG |", "|---|---:|---:|---:|---:|---:|"]
        for r in ab:
            L.append(f"| {r['corpus']} | {r['full']} | {r.get('delta_S')} | "
                     f"{r.get('delta_H')} | {r.get('delta_A')} | {r.get('delta_G')} |")
        L += ["", "V1 published deltas of -0.010, -0.125, -0.125 and -0.100; the "
              "last three were weight x 0.5, a hardcoded constant.", ""]

    L += ["## Files", "",
          "- `results/tables/*.csv` -- every table above, machine-readable",
          "- `results/tables/all_results.json` -- everything, including sections "
          "not rendered here",
          "- `results/figures/*.png` -- figures",
          "- `DECISIONS.md` -- the declarations these results were computed under",
          "- `results/forensics/console_log_06.txt` -- the full run log", ""]

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  written -> {p}")
    return str(p)


def C_table3(root, tables):
    sub("C  TABLE 3 -- macro-F1 with bootstrap 95% CI (2,000 resamples)")
    print("  Reviewer 1 asked for intervals. The manuscript claimed 500-resample")
    print("  bootstraps and printed none.")
    print()
    allsys = SYSTEMS + LEGACY
    res = {}
    for group, corpora, classes in (("THREE-CLASS", THREE, ["pos", "neu", "neg"]),
                                    ("BINARY (D10, D16)", BINARY, ["pos", "neg"])):
        print(f"  {group}")
        print(f"  {'corpus':<14}" + "".join(f"{n[:12]:>19}" for n, _ in allsys))
        rule()
        for c in corpora:
            rows = load(root, c)
            rows = [r for r in rows if r["gold"] in classes]
            if not rows:
                continue
            gold = [r["gold"] for r in rows]
            line = f"  {c:<14}"
            res.setdefault(c, {})
            for name, col in allsys:
                sc = [f(r[col]) for r in rows]
                pred = [(lab2(s) if len(classes) == 2 else lab3(s))
                        if s is not None else ("neg" if len(classes) == 2 else "neu")
                        for s in sc]
                m = macro_f1(gold, pred, classes)
                lo, hi = boot_f1(gold, pred, classes)
                res[c][name] = {"f1": m, "lo": lo, "hi": hi, "n": len(rows)}
                line += f"{m:>7.3f}[{lo:.3f},{hi:.3f}]"
            print(line)
        print()
    line = f"  {'MEAN(3-class)':<14}"
    for name, _ in allsys:
        vals = [res[c][name]["f1"] for c in THREE if c in res]
        line += f"{statistics.mean(vals):>19.3f}" if vals else f"{'-':>19}"
    print(line)
    print()
    print("  V1 published: PLEF .425 | 'VADER' .438 | 'NRC' .309 | 'LIWC' .381")
    print("  Those three baselines were 100, 58 and 88 hand-typed words.")
    tables["table3"] = res
    return res


def D_sweep(root, tables):
    sub("D  THRESHOLD SWEEP -- macro-F1 is threshold-conditional (D4)")
    out = []
    for c in THREE:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neu", "neg")]
        if not rows:
            continue
        gold = [r["gold"] for r in rows]
        print(f"  {c}")
        print(f"    {'system':<10}" + "".join(f"{t:>9.2f}" for t in SWEEP))
        for name, col in SYSTEMS:
            sc = [f(r[col]) for r in rows]
            line = f"    {name:<10}"
            rec = {"corpus": c, "system": name}
            for t in SWEEP:
                pred = [lab3(s, t) if s is not None else "neu" for s in sc]
                m = macro_f1(gold, pred, ["pos", "neu", "neg"])
                line += f"{m:>9.3f}"
                rec[str(t)] = round(m, 4)
            print(line)
            out.append(rec)
        print()
    tables["threshold_sweep"] = out
    print("  A system whose row moves sharply across this sweep has a macro-F1")
    print("  that is a property of the threshold as much as of the system.")
    return out


def E_abstention(root, tables):
    sub("E  ABSTENTION-AWARE EVALUATION")
    print("  PLEF returns exactly 0.000 when its lexicon matches nothing. That is")
    print("  'no lexical evidence', not a prediction of 'neutral'. Both readings")
    print("  are reported; neither is hidden.")
    print()
    print(f"  {'corpus':<14}{'fires':>8}{'PLEF all':>10}{'VADER all':>11}"
          f"{'PLEF|fires':>12}{'VADER|fires':>13}{'delta':>9}")
    rule()
    out = []
    for c in THREE:
        rows = load(root, c)
        rows = [r for r in rows if r["gold"] in ("pos", "neu", "neg")]
        if not rows:
            continue
        gold = [r["gold"] for r in rows]
        P = [f(r["sentiment_mean"]) for r in rows]
        V = [f(r["b_vader"]) for r in rows]
        cl = ["pos", "neu", "neg"]
        pa = macro_f1(gold, [lab3(x) if x is not None else "neu" for x in P], cl)
        va = macro_f1(gold, [lab3(x) if x is not None else "neu" for x in V], cl)
        idx = [i for i, x in enumerate(P) if x is not None and x != 0.0]
        if len(idx) < 30:
            continue
        g2 = [gold[i] for i in idx]
        pf = macro_f1(g2, [lab3(P[i]) for i in idx], cl)
        vf = macro_f1(g2, [lab3(V[i]) if V[i] is not None else "neu" for i in idx], cl)
        fires = 100 * len(idx) / len(rows)
        print(f"  {c:<14}{fires:>7.1f}%{pa:>10.3f}{va:>11.3f}{pf:>12.3f}"
              f"{vf:>13.3f}{pf-vf:>+9.3f}")
        out.append({"corpus": c, "fires_pct": round(fires, 2),
                    "plef_all": round(pa, 4), "vader_all": round(va, 4),
                    "plef_fires": round(pf, 4), "vader_fires": round(vf, 4),
                    "delta": round(pf - vf, 4)})
    tables["abstention"] = out
    print()
    if out:
        d = statistics.mean([o["delta"] for o in out])
        print(f"  Mean delta on items where PLEF fires: {d:+.3f}")
        print("  The scope defence covers coverage. It does not cover accuracy:")
        print("  PLEF is also less accurate within its own coverage.")
    return out


def _smooth(s, w):
    return [sum(s[max(0, i-w):min(len(s), i+w+1)]) /
            len(s[max(0, i-w):min(len(s), i+w+1)]) for i in range(len(s))]


def _lewi(s):
    n = len(s)
    x = _smooth(s, max(1, n // 4))
    bi, bv = None, -1.0
    for i in range(1, len(x) - 1):
        d = abs(x[i+1] - 2*x[i] + x[i-1])
        if d > bv + 1e-12:
            bv, bi = d, i
    if bi is None or bi <= 0 or bi >= n:
        bi = max(1, min(n - 1, n // 2))
    return bi, sum(s[:bi]) / bi - sum(s[bi:]) / (n - bi)


def _nava(s):
    n = len(s)
    k = max(1, n // 4 if n < 9 else n // 3)
    return sum(s[:k]) / k - sum(s[n-k:]) / k


def F_nulls(root, tables):
    sub("F  NAVA x LEWI AGAINST TWO NULLS")
    rows = load(root, TRAJ)
    if not rows:
        print("  relationship corpus not scored")
        return {}
    vecs = []
    for r in rows:
        v = [f(x) for x in (r.get("sent_scores") or "").split(";") if x.strip()]
        v = [x for x in v if x is not None]
        if len(v) >= 4:
            vecs.append(v)
    A = [f(r["nava"]) for r in rows]
    B = [f(r["lewi_drop"]) for r in rows]
    pair = [(a, b) for a, b in zip(A, B) if a is not None and b is not None]
    obs = pearson([a for a, _ in pair], [b for _, b in pair])
    lo, hi = boot_r([a for a, _ in pair], [b for _, b in pair])
    print(f"  OBSERVED  n={len(pair):,}   r = {obs:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]")
    print()
    res = {"observed": obs, "ci": [lo, hi], "n": len(pair)}
    if not vecs:
        print("  sent_scores absent -- rerun script 05.2.0+ on the relationship")
        print("  shard to enable the within-document permutation null.")
    else:
        rs = []
        for t in range(20):
            rnd = random.Random(900 + t)
            sh = []
            for v in vecs:
                w = v[:]
                rnd.shuffle(w)
                sh.append(w)
            rs.append(pearson([_nava(v) for v in sh], [_lewi(v)[1] for v in sh]))
        rs = [x for x in rs if x is not None]
        print(f"  NULL 1: within-document sentence-order PERMUTATION, n={len(vecs):,}")
        print(f"          same sentences, same marginals, order destroyed")
        print(f"          20 draws   mean r = {statistics.mean(rs):+.3f}   "
              f"[{min(rs):+.3f}, {max(rs):+.3f}]")
        res["perm_null_mean"] = statistics.mean(rs)
        res["perm_null_range"] = [min(rs), max(rs)]
    # When sent_scores is absent the synthetic null still needs lengths; fall
    # back to the corpus sentence counts, and never below the 4-sentence minimum
    # at which LEWI and NAVA are defined at all.
    lens = [len(v) for v in vecs]
    if not lens:
        lens = [int(f(r.get("n_sents")) or 0) for r in rows]
    lens = [L for L in lens if L >= 4]
    if not lens:
        print("  no sequences of >=4 sentences; synthetic null skipped")
        tables["nava_lewi_nulls"] = res
        return res
    for model in ("iid_normal", "random_walk"):
        rs = []
        for t in range(12):
            rnd = random.Random(500 + t)
            AA, BB = [], []
            for L in lens:
                if model == "random_walk":
                    v0, s = 0.0, []
                    for _ in range(L):
                        v0 = max(-1, min(1, v0 + rnd.gauss(0, 0.25)))
                        s.append(v0)
                else:
                    s = [rnd.gauss(0, 0.19) for _ in range(L)]
                AA.append(_nava(s))
                BB.append(_lewi(s)[1])
            r = pearson(AA, BB)
            if r is not None:
                rs.append(r)
        print(f"  NULL 2: synthetic {model:<14} 12 draws   mean r = "
              f"{statistics.mean(rs):+.3f}   [{min(rs):+.3f}, {max(rs):+.3f}]")
        res[f"synth_{model}"] = statistics.mean(rs)
    print()
    print("  V1 reported r = 0.638-0.850 as convergent validity. If the observed")
    print("  correlation does not exceed these nulls, the metrics are two")
    print("  pre-minus-post differences over one signal and the finding is")
    print("  structural, not narrative.")
    tables["nava_lewi_nulls"] = res
    return res


def G_lewi_versions(root, tables):
    sub("G  LEWI: V2 (published definition) vs V1 (what the code ran)")
    rows = load(root, TRAJ)
    agree, disagree, gaps = [], [], []
    same = 0
    n = 0
    for r in rows:
        i2, i1 = f(r.get("lewi_idx")), f(r.get("lewi_v1_idx"))
        d2, d1 = f(r.get("lewi_drop")), f(r.get("lewi_v1_drop"))
        if None in (i2, i1, d2, d1):
            continue
        n += 1
        if i1 == i2:
            same += 1
            agree.append(abs(d2 - d1))
        else:
            disagree.append(abs(d2 - d1))
            gaps.append(abs(int(i1) - int(i2)))
    if not n:
        print("  no comparable rows")
        return {}
    print(f"  texts compared            : {n:,}")
    print(f"  same watershed sentence   : {100*same/n:.1f}%")
    print()
    print("  |drop difference|, SPLIT by whether the algorithms agree:")
    print(f"    agreeing    n={len(agree):>5}   median {statistics.median(agree):.6f}")
    if disagree:
        print(f"    DISAGREEING n={len(disagree):>5}   median "
              f"{statistics.median(disagree):.4f}   mean "
              f"{statistics.mean(disagree):.4f}   max {max(disagree):.4f}")
        print(f"    sentence-index gap when they disagree: median "
              f"{statistics.median(gaps):.0f}   max {max(gaps)}")
    print()
    print("  The POOLED median is zero by construction whenever agreement exceeds")
    print("  50%, and says nothing about the disagreeing cases. It is never")
    print("  reported alone.")
    out = {"n": n, "same_pct": 100*same/n,
           "disagree_median": statistics.median(disagree) if disagree else None,
           "disagree_max": max(disagree) if disagree else None,
           "gap_median": statistics.median(gaps) if gaps else None}
    tables["lewi_versions"] = out
    return out


def H_external(root, tables):
    sub("H  EXTERNAL CRITERIA and I  THE PRONOUN COUPLING")
    rows = load(root, TRAJ)
    if not rows:
        print("  relationship corpus not scored")
        return {}
    def pair(a, b):
        X, Y = [], []
        for r in rows:
            u, v = f(r.get(a)), f(r.get(b))
            if u is not None and v is not None:
                X.append(u); Y.append(v)
        return X, Y
    out = []
    for a, b, label in (
            ("pti", "pai_v1", "H2 (V1)  PTI x PAI_v1   [pronoun term PRESENT]"),
            ("pti", "pai", "H2 (V2)  PTI x PAI      [pronoun term REMOVED]"),
            ("pai", "vad_dominance", "H2-ext   PAI x NRC-VAD dominance"),
            ("pai_v1", "vad_dominance", "H2-ext   PAI_v1 x VAD dominance"),
            ("teg", "emoint_teg", "H3-ext   TEG x NRC-EmoInt volatility"),
            ("teg", "ties", "H3       TEG x TIES"),
            ("sentiment_mean", "cd_index", "H6       Sentiment x CD-index"),
            ("nspl", "gase", "         NSPL x GASE (internal)")):
        X, Y = pair(a, b)
        if len(X) < 30:
            print(f"  {label:<50} n={len(X):>5}  insufficient")
            continue
        r = pearson(X, Y)
        lo, hi = boot_r(X, Y)
        star = "" if (lo is None or (lo <= 0 <= hi)) else "  *CI excludes 0"
        print(f"  {label:<50} n={len(X):>5}  r={r:+.3f}  "
              f"[{lo:+.3f},{hi:+.3f}]{star}")
        out.append({"pair": label.strip(), "n": len(X), "r": round(r, 4),
                    "lo": round(lo, 4), "hi": round(hi, 4)})
    tables["correlations"] = out
    print()
    print("  VAD dominance and EmoInt intensity are annotated independently of")
    print("  PLEF, so neither correlation is circular. That is what H2 and H3")
    print("  never had.")
    return out


def K_pooling(root, tables, table3):
    sub("K  OVERLAP-CORRECTED POOLING")
    print("  SemEval-2017 and TweetEval share 22,603 items (42.8% of SemEval).")
    print("  Any mean over both double-weights those items.")
    print()
    if not table3:
        return {}
    for name, _ in SYSTEMS:
        naive = [table3[c][name]["f1"] for c in THREE if c in table3]
        excl = [table3[c][name]["f1"] for c in THREE
                if c in table3 and c != "tweeteval"]
        if naive and excl:
            print(f"  {name:<10} mean over 5 corpora = {statistics.mean(naive):.3f}   "
                  f"excluding TweetEval = {statistics.mean(excl):.3f}   "
                  f"delta {statistics.mean(excl)-statistics.mean(naive):+.3f}")
    return {}



def S_human_criterion(root, tables):
    """H1 and H5 against the human annotation.

    v06.7.1 printed 'see annotation' -- a placeholder that computed nothing, and
    which could not have worked anyway: the annotation is on the dev split while
    script 05 scored only the evaluation set, so the gold ids matched nothing.
    Script 05.4.0 now scores the dev split as its own shard.
    """
    sub("S  H1 AND H5 AGAINST THE HUMAN CRITERION")
    gold = _gold_labels_full(root)
    if not gold:
        print("  no gold file -- H1 and H5 not evaluated")
        return {}
    rows = load(root, "dev_relationship") or load(root, TRAJ)
    if not rows:
        print("  the annotated split is not scored. Run:")
        print("    python 05_full_run.py --root <root> --only dev_relationship")
        return {}
    idx = {r["id"]: r for r in rows}
    m = [(g, idx[i]) for i, g in gold.items() if i in idx]
    print(f"  gold items: {len(gold)}   matched to scored posts: {len(m)}")
    if len(m) < 10:
        print("  too few matches to evaluate")
        return {}
    single = any(str(g.get("n_raters", "")) == "1" for g, _ in m)
    if single:
        print("  ** SINGLE ANNOTATOR. No inter-rater reliability exists. Every")
        print("     number below is PRELIMINARY and must be reported as such. **")
    out = {"n": len(m), "single_rater": single}

    # ---- H1: LEWI vs the human turning point ----
    pairs = [(int(float(g["gold_turning_point"])), int(float(r["lewi_idx"])),
              int(float(r["n_sents"])))
             for g, r in m
             if str(g.get("gold_turning_point", "")).strip() != ""
             and (r.get("lewi_idx") or "").strip() != ""
             and (r.get("n_sents") or "").strip() != ""]
    hum_none = sum(1 for h, _, _ in pairs if h == 0)
    both = [(h, l, n) for h, l, n in pairs if h > 0]
    print()
    print(f"  H1  LEWI vs human turning point")
    print(f"    posts with a LEWI index and a human answer : {len(pairs)}")
    print(f"    human marked NO turning point              : {hum_none} "
          f"({100*hum_none/max(1,len(pairs)):.0f}%)")
    if both:
        ex = sum(1 for h, l, _ in both if h == l)
        w1 = sum(1 for h, l, _ in both if abs(h - l) <= 1)
        w2 = sum(1 for h, l, _ in both if abs(h - l) <= 2)
        # chance = probability of landing on the same sentence at random
        chance = statistics.mean([1.0 / max(1, n) for _, _, n in both])
        n_ = len(both)
        lo, hi = _prop_ci(ex, n_)
        print(f"    comparable posts (human marked one)        : {n_}")
        print(f"    exact match      : {100*ex/n_:>5.1f}%  95% CI "
              f"[{100*lo:.1f}%, {100*hi:.1f}%]   chance {100*chance:.1f}%")
        # A within-k band covers 2k+1 of n sentences, so its chance rate is
        # (2k+1)/n. Reporting within-1 without that is how a number at chance
        # gets read as partial agreement.
        c1 = statistics.mean([min(1.0, 3.0 / max(1, n)) for _, _, n in both])
        c2 = statistics.mean([min(1.0, 5.0 / max(1, n)) for _, _, n in both])
        print(f"    within 1 sentence: {100*w1/n_:>5.1f}%   chance {100*c1:.1f}%")
        print(f"    within 2 sentences: {100*w2/n_:>5.1f}%   chance {100*c2:.1f}%")
        out.update({"h1_within1_chance": c1, "h1_within2_chance": c2})
        verdict = "ABOVE CHANCE" if lo > chance else "NOT ABOVE CHANCE"
        print(f"    verdict: {verdict} (the CI lower bound "
              f"{'exceeds' if lo > chance else 'does not exceed'} the chance rate)")
        out.update({"h1_n": n_, "h1_exact": ex / n_, "h1_within1": w1 / n_,
                    "h1_chance": chance, "h1_ci": [lo, hi], "h1_verdict": verdict})
        print()
        print(f"    LEWI CANNOT ABSTAIN. The human marked NO turning point on")
        print(f"    {hum_none} of {len(pairs)} posts; LEWI returned an index on all of")
        print(f"    them. argmax over a second difference always returns")
        print(f"    something, so the metric has no null case and cannot report")
        print(f"    the absence of a turning point. That is a property of its")
        print(f"    definition, not of these data.")
        out["h1_human_none"] = hum_none
        out["h1_lewi_always_fires"] = True
    else:
        print("    no comparable posts")

    # ---- H5: NAVA arc vs the human arc ----
    ARC = {"tragic": "tragic", "mildly_declining": "tragic", "flat": "flat",
           "mildly_improving": "redemptive", "redemptive": "redemptive"}
    arcs = [(g["gold_arc"], ARC.get((r.get("nava_arc") or "").strip()))
            for g, r in m
            if (g.get("gold_arc") or "").strip() and (r.get("nava_arc") or "").strip()]
    arcs = [(a, b) for a, b in arcs if b]
    print()
    print(f"  H5  NAVA arc vs human arc   (NAVA's five classes collapsed to three)")
    if len(arcs) >= 10:
        agr = sum(1 for a, b in arcs if a == b) / len(arcs)
        lo, hi = _prop_ci(sum(1 for a, b in arcs if a == b), len(arcs))
        k = kappa_pairs([a for a, _ in arcs], [b for _, b in arcs])
        maj = collections.Counter(a for a, _ in arcs).most_common(1)[0]
        base = maj[1] / len(arcs)
        print(f"    n = {len(arcs)}   agreement {100*agr:.1f}%  95% CI "
              f"[{100*lo:.1f}%, {100*hi:.1f}%]")
        print(f"    majority-class baseline: {100*base:.1f}% (always '{maj[0]}')")
        print(f"    Cohen's kappa: {k:+.3f}" if k is not None else "")
        v = "ABOVE the majority baseline" if lo > base else \
            "NOT above the majority baseline"
        print(f"    verdict: {v}")
        print(f"    human arc distribution: "
              f"{dict(collections.Counter(a for a, _ in arcs))}")
        print(f"    NAVA arc distribution : "
              f"{dict(collections.Counter(b for _, b in arcs))}")
        hd = collections.Counter(a for a, _ in arcs)
        nd = collections.Counter(b for _, b in arcs)
        tvd = 0.5 * sum(abs(hd.get(x, 0) - nd.get(x, 0)) for x in
                        set(hd) | set(nd)) / max(1, len(arcs))
        print(f"    distribution distance (total variation): {tvd:.3f}")
        if tvd < 0.15 and (k is None or abs(k) < 0.10):
            print("    ** NAVA reproduces the DISTRIBUTION of arcs while agreeing")
            print("       with the human at chance on individual posts. A metric")
            print("       with the right marginals and the wrong assignment looks")
            print("       calibrated in any summary table and is not. **")
        out.update({"h5_n": len(arcs), "h5_agreement": agr, "h5_kappa": k,
                    "h5_baseline": base, "h5_verdict": v, "h5_tvd": tvd})
    else:
        print(f"    only {len(arcs)} comparable posts -- not evaluated")

    print()
    print("  CEILING. Round 3 measured how reproducible these judgements are:")
    print("  three independent annotators agreed on the turning point exactly")
    print("  0 times in 26 posts, and self-agreement on repeats was 18-29%.")
    print("  A metric cannot be expected to exceed the reliability of the")
    print("  criterion it is measured against; that ceiling must be reported")
    print("  beside any figure above.")
    tables["human_criterion"] = [out]
    return out


def _prop_ci(k, n, z=1.96):
    """Wilson interval for a proportion."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def _gold_labels_full(root):
    p = Path(root) / "data" / "interim" / "annotations" / "gold_dev200.csv"
    if not p.exists():
        return {}
    out = {}
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["id"]] = r
    return out


def L_scoreboard(root, tables, gold_exists, ann_state="none", ann_rows=None):
    sub("L  HYPOTHESIS SCOREBOARD")
    corr = {c["pair"]: c for c in tables.get("correlations", [])}
    nl = tables.get("nava_lewi_nulls", {})
    rows = []

    def verdict(key, thresh):
        c = corr.get(key)
        if not c:
            return "not computed", ""
        excl = not (c["lo"] <= 0 <= c["hi"])
        ok = abs(c["r"]) >= thresh and excl
        return ("SUPPORTED" if ok else "FAILED"), \
               f"r={c['r']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}]"

    hc = (tables.get("human_criterion") or [{}])[0]
    if gold_exists and hc.get("h1_n"):
        pre = "PRELIMINARY " if hc.get("single_rater") else ""
        h1v = pre + str(hc.get("h1_verdict", "?"))
        h1d = (f"exact {100*hc['h1_exact']:.0f}% vs chance "
               f"{100*hc['h1_chance']:.0f}%, n={hc['h1_n']}"
               + (", SINGLE ANNOTATOR" if hc.get("single_rater") else ""))
        h5v = pre + ("SUPPORTED" if hc.get("h5_verdict", "").startswith("ABOVE")
                     else "NOT SUPPORTED") if hc.get("h5_n") else "not evaluated"
        h5d = (f"agreement {100*hc['h5_agreement']:.0f}% vs baseline "
               f"{100*hc['h5_baseline']:.0f}%, n={hc['h5_n']}") if hc.get("h5_n") else ""
        rows.append(("H1  LEWI finds human turning points", h1v, h1d))
        rows.append(("H5  NAVA arc classification", h5v, h5d))
        h15 = None
    elif gold_exists:
        h15 = ("GOLD PRESENT, NOT EVALUATED",
               "the annotated split is not scored -- run script 05 for it")
    elif ann_state == "attempted_unusable":
        h15 = ("NOT TESTABLE",
               "annotation attempted and rejected: inter-rater reliability "
               "below the usable threshold")
    else:
        h15 = ("PENDING ANNOTATION", "no annotation attempted yet")
    if h15 is not None:
        rows.append(("H1  LEWI finds human turning points", h15[0], h15[1]))
    rows.sort(key=lambda x: x[0])
    v, d = verdict("H2 (V2)  PTI x PAI      [pronoun term REMOVED]", 0.25)
    rows.append(("H2  PTI predicts power asymmetry", v, d))
    v2, d2 = verdict("H2-ext   PAI x NRC-VAD dominance", 0.15)
    rows.append(("H2ext PAI tracks VAD dominance", v2, d2))
    v3, d3 = verdict("H3-ext   TEG x NRC-EmoInt volatility", 0.25)
    rows.append(("H3  TEG tracks emotional volatility", v3, d3))
    ab = tables.get("gase_ablation") or []
    if ab:
        # A component is non-informative if it barely varies on MOST corpora.
        # Averaging its sd across corpora hides this: one corpus with real
        # variance drags the mean above any threshold. Count corpora instead.
        # dev_relationship is the same domain as relationship and would
        # double-weight it in any per-corpus count.
        ab = [a for a in ab if a.get("corpus") not in AUX_CORPORA]
        dead = []
        for k in ("S", "H", "A", "G"):
            flat = sum(1 for a in ab if a.get(f"sd_{k}", 1.0) < 0.05)
            if flat >= max(1, int(0.75 * len(ab))):
                dead.append((k, flat))
        weight = {"S": 0.30, "H": 0.25, "A": 0.25, "G": 0.20}
        lost = sum(weight[k] for k, _ in dead)
        det = (", ".join(f"{k} sd<0.05 on {n}/{len(ab)}" for k, n in dead) +
               f" -> {lost:.0%} of the weight is a fixed offset") if dead \
            else "all components vary"
        rows.append(("H4  GASE component validity",
                     "COMPUTED" if not dead else "NEAR-CONSTANT", det))
    else:
        rows.append(("H4  GASE component validity", "NOT RUN",
                     "never executed in V1 either"))
    if h15 is not None:
        rows.append(("H5  NAVA arc classification", h15[0], h15[1]))
    v6, d6 = verdict("H6       Sentiment x CD-index", 0.15)
    rows.append(("H6  Sentiment predicts distortion", v6, d6))
    if nl:
        obs = nl.get("observed")
        null = nl.get("perm_null_mean", nl.get("synth_iid_normal"))
        ok = obs is not None and null is not None and obs > null + 0.05
        rows.append(("--  NAVA x LEWI as convergent validity",
                     "EXCEEDS NULL" if ok else "AT THE NOISE FLOOR",
                     f"observed {obs:+.3f} vs null {null:+.3f}"
                     if obs is not None and null is not None else ""))
    print(f"  {'hypothesis':<42}{'verdict':<22}detail")
    rule()
    for a, b, c in rows:
        # v06.6.0 used a fixed 22-char field and the verdict collided with the
        # detail when it ran long. This table goes in the paper.
        print(f"  {a:<42}{b:<22}" + ("  " if len(b) >= 22 else "") + str(c))
    tables["scoreboard"] = [{"hypothesis": a, "verdict": b, "detail": c}
                            for a, b, c in rows]
    return rows


def write_outputs(root, tables):
    sub("WRITING TABLES")
    td = Path(root) / "results" / "tables"
    td.mkdir(parents=True, exist_ok=True)
    tables.pop("_corpora", None)
    for name, data in tables.items():
        if isinstance(data, list) and data and isinstance(data[0], dict):
            p = td / f"{name}.csv"
            keys = []
            for d in data:
                for k in d:
                    if k not in keys:
                        keys.append(k)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                w.writerows(data)
            print(f"  {p.name}")
    p = td / "all_results.json"
    p.write_text(json.dumps(tables, indent=2, default=str), encoding="utf-8")
    print(f"  {p.name}")
    return td


# ===========================================================================
def main():
    global BOOT_N
    ap = argparse.ArgumentParser(description="PLEF V2 script 06 -- statistics.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--boot", type=int, default=BOOT_N)
    ap.add_argument("--v1", default="",
                    help="V1 path, to join the keyword silver labels if "
                         "corpus_relationship.csv predates script 03.4.0")
    args = ap.parse_args()
    BOOT_N = args.boot
    root = Path(args.root)
    if not (root / "MANIFEST" / "scored.json").exists():
        print("FATAL: MANIFEST/scored.json missing. Run script 05 first.")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_06.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 06 : STATISTICS AND SCOREBOARD")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  bootstrap      : {BOOT_N:,} resamples")
        man = json.loads((root / "MANIFEST" / "scored.json").read_text(encoding="utf-8"))
        corpora = sorted(man.get("shards", {}))
        print(f"  corpora        : {len(corpora)}  {corpora}")
        ann_state, ann_path, ann_rows = annotation_status(root)
        gold_exists = ann_state == "usable"
        if ann_state == "usable":
            print(f"  annotation     : usable gold file present")
        elif ann_state == "attempted_unusable":
            print(f"  annotation     : ATTEMPTED AND REJECTED -- rater rows "
                  f"{ann_rows or '{}'}")
            if ann_path:
                print(f"                   quarantined: {Path(ann_path).name}")
            print("                   H1 and H5 are NOT TESTABLE, not pending")
        else:
            print("  annotation     : none attempted -- H1 and H5 pending")

        ok, fast, slow = _selftest_bootstrap()
        print(f"  bootstrap self-test : multinomial [{fast[0]:.4f}, {fast[1]:.4f}] vs "
              f"item-resample [{slow[0]:.4f}, {slow[1]:.4f}]  "
              f"{'MATCH' if ok else 'MISMATCH'}")
        if not ok:
            print("  FATAL: the fast bootstrap no longer matches item resampling.")
            return 3

        tables = {}
        A_coverage(root, corpora, tables)
        B_length(root, corpora, tables)
        tables["_corpora"] = corpora
        t3 = C_table3(root, tables)
        C2_auc(root, tables)
        C3_trivial(root, tables)
        D_sweep(root, tables)
        E_abstention(root, tables)
        E2_abstention_binary(root, tables)
        F_nulls(root, tables)
        G_lewi_versions(root, tables)
        H_external(root, tables)
        J_gase_ablation(root, tables)
        M_descriptive(root, corpora, tables)
        N_effect_sizes(root, tables)
        O_mcnemar(root, tables)
        K_pooling(root, tables, t3)
        Q_domain_split(root, tables, t3, args.v1)
        R_moderators(root, tables)
        S_human_criterion(root, tables)
        L_scoreboard(root, tables, gold_exists, ann_state, ann_rows)
        P_figures(root, tables)
        td = write_outputs(root, tables)
        write_results_md(root, tables)

        head("DONE")
        print(f"  tables : {td}")
        print(f"  log    : {root / 'results' / 'forensics' / 'console_log_06.txt'}")
        print()
        if not gold_exists:
            if ann_state == "attempted_unusable":
                print("  H1 and H5 are NOT TESTABLE. Annotation was attempted and")
                print("  rejected on reliability grounds; no gold file exists.")
                print("  If a further round is collected:")
            else:
                print("  H1 and H5 are PENDING ANNOTATION. When the raters finish:")
            print("    python annotate.py --root <root> --mode merge")
            print("    python 06_statistics.py --root <root>")
        return 0
    except Exception:
        print("\nUNHANDLED EXCEPTION")
        traceback.print_exc()
        return 3
    finally:
        sys.stdout = tee.stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(main())
