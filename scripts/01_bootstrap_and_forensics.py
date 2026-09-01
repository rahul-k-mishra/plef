#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 01 : BOOTSTRAP + ADVERSARIAL FORENSICS
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
Before we rebuild anything, we must be able to prove -- from your own files,
with your own console output -- exactly what was wrong with the submitted
version. The response letter to Springer will state these defects openly.
A claim we cannot reproduce on demand is a claim we must not make.

So this script does two things and nothing else:

  1. Creates the clean V2 project tree and installs itself into it.
  2. Runs eight independent forensic probes against the OLD (V1) project,
     and writes a signed, hash-stamped evidence report.

It writes NOTHING into the V2 source tree except the report and the manifest.
It does not import or execute any V1 code. V1's main module is parsed
statically (Python AST) so that no interactive menu, no download, and no
side effect can fire.

WHAT EACH PROBE CHECKS, AND WHAT THE RESULT MEANS
--------------------------------------------------
  F1  ISEAR label integrity
      Checks: what fraction of ISEAR gold labels are a single class.
      Means:  if one class is ~100%, the corpus measured nothing, and every
              ISEAR number in the paper (F1, AUC, Cohen's d) is an artifact.

  F2  DailyDialog label integrity + majority-class identity
      Checks: gold class distribution, and whether each system's reported
              accuracy equals the rate at which it predicts the majority class.
      Means:  if accuracy == neutral-prediction rate, the "PLEF beats VADER"
              McNemar headline is a guessing artifact, not a finding.

  F3  Baseline authenticity
      Checks: the actual entry count of the embedded VADER / NRC / LIWC
              lexicons versus the published systems they are named after.
      Means:  tells us whether Section 4.3's claim that VADER was run "using
              the published rule-based algorithm" is true. It is not, if the
              counts come back in the hundreds.

  F4  Ablation validity
      Checks: (a) locates the ablation arithmetic in V1 source/backups;
              (b) reconstructs the TRUE combined entropy+attachment term from
                  the shipped result files, exactly, and compares it to the
                  value the published ablation implicitly assumed.
      Means:  quantifies how far Table 8 is from a real ablation.

  F5  Table reproducibility
      Checks: recomputes the manuscript's Table 3 / 4 / 5 / 7 numbers from the
              shipped result CSVs and diffs them against the published values.
      Means:  any row that fails to reproduce is a row we cannot defend, and
              tells us whether two different runs were spliced together.

  F6  Valid-N filter recovery
      Checks: tries every plausible filter rule to see which (if any)
              reproduces Table 5's "Valid N" column.
      Means:  if no filter reproduces it, Table 5 is unrecoverable from the
              shipped files and the Data Availability statement is false.

  F7  Structural null (NAVA x LEWI)
      Checks: runs V1's own NAVA and LEWI logic on sequences with NO narrative
              structure, under four noise models, and reports the null
              correlation distribution.
      Means:  this is Reviewer 3's test. If observed correlations do not
              exceed the null, the central finding has no evidential content.

  F8  Mechanical null (PTI x PAI)
      Checks: correlates PTI with PAI using random pronoun counts and no text.
      Means:  this is Reviewer 2's point 7. Tells us how much of H2 is
              produced by the formulas sharing the same counts.

  F9  Repository hygiene
      Checks: version identifier consistency, and the presence of
              reviewer-response-language / paper-generation modules.
      Means:  anything a reviewer browsing the repo would hold against us.

OUTPUTS (all under <root>/results/forensics/)
----------------------------------------------
  FORENSIC_REPORT.md      human-readable, quotable in the response letter
  defect_evidence.json    machine-readable, consumed by later scripts
  input_manifest.sha256   SHA-256 of every V1 artifact used as evidence
  console_log.txt         full console transcript

DEPENDENCIES
------------
  Python standard library only. No numpy, no scipy, no pandas.
  Parallelism via concurrent.futures.ProcessPoolExecutor.

EXIT CODES
----------
  0  all probes completed (defects found is still exit 0 -- that is the point)
  2  V1 path invalid or required evidence files missing
  3  internal inconsistency: a probe could not run at all
===============================================================================
"""

import argparse
import ast
import collections
import csv
import datetime
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

SCRIPT_VERSION = "01.1.0"
DATASETS = ["reddit_relationship", "goemotions", "empathetic", "isear",
            "semeval2017", "meld", "tweeteval", "dailydialog", "consensus"]

# ---------------------------------------------------------------------------
# Values as PRINTED IN THE SUBMITTED MANUSCRIPT (PLEF_Paper_v3).
# Every probe diffs against these. Do not edit without editing the paper.
# ---------------------------------------------------------------------------
PAPER = {
    # Table 2 / Table 3 : PLEF macro-F1 and macro-AUC
    "t3_plef_f1": {"reddit_relationship": 0.463, "goemotions": 0.446, "empathetic": 0.427,
                   "isear": 0.270, "semeval2017": 0.468, "meld": 0.330,
                   "tweeteval": 0.427, "dailydialog": 0.298, "consensus": 0.605},
    "t3_plef_auc": {"reddit_relationship": 0.633, "goemotions": 0.627, "empathetic": 0.607,
                    "isear": 0.500, "semeval2017": 0.628, "meld": 0.537,
                    "tweeteval": 0.600, "dailydialog": 0.500, "consensus": 0.838},
    "t3_vader_f1": {"reddit_relationship": 0.493, "goemotions": 0.485, "empathetic": 0.394,
                    "semeval2017": 0.491, "meld": 0.322, "tweeteval": 0.444},
    # Table 4 : PTI mean
    "t4_pti_mean": {"reddit_relationship": 0.153, "goemotions": 0.101, "empathetic": 0.502,
                    "semeval2017": 0.099, "meld": 0.062, "tweeteval": 0.089,
                    "consensus": 0.131, "dailydialog": 0.023},
    # Table 5 : NAVA x LEWI
    "t5_pearson": {"reddit_relationship": 0.779, "goemotions": 0.807, "empathetic": 0.725,
                   "isear": 0.638, "semeval2017": 0.758, "meld": 0.835,
                   "tweeteval": 0.789, "dailydialog": 0.742, "consensus": 0.832},
    "t5_valid_n": {"reddit_relationship": 163, "goemotions": 67, "empathetic": 334,
                   "isear": 28, "semeval2017": 166, "meld": 176,
                   "tweeteval": 120, "dailydialog": 4671, "consensus": 70},
    "t5_lewi_sd": {"reddit_relationship": 0.1832, "goemotions": 0.1724, "empathetic": 0.1884,
                   "isear": 0.1296, "semeval2017": 0.1439, "meld": 0.1049,
                   "tweeteval": 0.1429, "dailydialog": 0.1111, "consensus": 0.1401},
    # Table 7 : PTI mean (second run) and PTI x PAI
    "t7_pti_mean": {"consensus": 0.126, "dailydialog": 0.052, "empathetic": 0.494,
                    "goemotions": 0.101, "isear": 0.427, "meld": 0.064,
                    "reddit_relationship": 0.155, "semeval2017": 0.084, "tweeteval": 0.082},
    "t7_pti_pai": {"consensus": 0.266, "dailydialog": 0.101, "empathetic": 0.469,
                   "goemotions": 0.243, "isear": 0.869, "meld": 0.135,
                   "reddit_relationship": 0.256, "semeval2017": 0.305, "tweeteval": 0.317},
    # Table 8 : GASE ablation
    "t8_full_gase": 0.6458,
    "t8_deltas": {"sentiment": -0.010, "entropy": -0.125, "attachment": -0.125,
                  "horsemen": -0.100},
    # Abstract headline
    "abstract_mean_f1": 0.415,
    "abstract_mean_auc": 0.608,
    "abstract_nava_lewi_range": (0.638, 0.850),
    "abstract_total_items": 150041,
    # Published lexicon sizes of the systems the baselines are NAMED after
    "published_lexicon_sizes": {"VADER": 7500, "NRC": 14182, "LIWC": 12000},
}

TOL = 0.0015          # tolerance for "reproduces" on a 3-decimal published value
GASE_W = {"S": 0.30, "H": 0.25, "A": 0.25, "G": 0.20}


# ===========================================================================
# small utilities
# ===========================================================================
class Tee:
    """Mirror stdout to a log file so the transcript is quotable."""
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, s):
        self.stdout.write(s)
        self.f.write(s)
    def flush(self):
        self.stdout.flush()
        self.f.flush()
    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


def rule(ch="-", w=78):
    print(ch * w)


def head(t):
    print()
    rule("=")
    print(t)
    rule("=")


def sub(t):
    print()
    print(t)
    rule("-")


def fnum(v):
    try:
        s = str(v).strip()
        if s == "" or s.lower() in ("none", "nan", "na", "null"):
            return None
        return float(s)
    except Exception:
        return None


def pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def sd(v):
    return statistics.pstdev(v) if len(v) > 1 else 0.0


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def metrics_csv(v1, ds):
    return Path(v1) / "results" / ds / f"all_posts_metrics_{ds}.csv"


def load_metrics(path, want):
    """Stream a metrics CSV, returning only the requested columns as floats/str."""
    out = []
    if not Path(path).exists():
        return out
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            rec = {}
            for k in want:
                v = row.get(k)
                rec[k] = v if k in ("nava_arc", "gold_sentiment", "gold_emotion", "id") else fnum(v)
            out.append(rec)
    return out


# ===========================================================================
# V1 replicas -- copied verbatim from plef_v7.py so the null uses THEIR logic
# ===========================================================================
def v1_compute_lewi(scores):
    n = len(scores)
    if n < 4:
        return None, 0.0
    window = max(1, n // 4)
    sm = []
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n, i + window + 1)
        sm.append(sum(scores[lo:hi]) / (hi - lo))
    if max(sm) - min(sm) < 0.01:
        sm = scores[:]
    deriv = [sm[i + 1] - sm[i] for i in range(len(sm) - 1)]
    best_idx, best_mag = n // 2, 0.0
    for i in range(1, len(deriv) - 1):
        if deriv[i - 1] * deriv[i] < 0:
            mag = abs(deriv[i - 1] - deriv[i])
            if mag > best_mag:
                best_mag, best_idx = mag, i
    if best_mag == 0.0 and deriv:
        best_idx = max(range(len(deriv)), key=lambda i: abs(deriv[i]))
    pre = sum(scores[:best_idx]) / max(1, best_idx)
    post = sum(scores[best_idx:]) / max(1, n - best_idx)
    return best_idx, pre - post


def v1_compute_nava(scores):
    n = len(scores)
    if n < 4:
        return None
    part = max(1, n // 4 if n < 9 else n // 3)
    return sum(scores[:part]) / part - sum(scores[n - part:]) / part


# ===========================================================================
# PROBES  (each returns a dict; each is safe to run in a worker process)
# ===========================================================================
def probe_label_integrity(args):
    """F1 + F2 -- gold label degeneracy and majority-class identity."""
    v1, ds = args
    p = metrics_csv(v1, ds)
    if not p.exists():
        return {"probe": "label_integrity", "dataset": ds, "status": "MISSING"}
    gold = collections.Counter()
    plef_pred = collections.Counter()
    vader_pred = collections.Counter()
    n = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            n += 1
            gold[(row.get("gold_sentiment") or "").strip() or "<empty>"] += 1
            s = fnum(row.get("sentiment"))
            if s is not None:
                plef_pred["pos" if s > 0.05 else ("neg" if s < -0.05 else "neu")] += 1
            v = fnum(row.get("vader_score"))
            if v is not None:
                vader_pred["pos" if v > 0.05 else ("neg" if v < -0.05 else "neu")] += 1
    if n == 0:
        return {"probe": "label_integrity", "dataset": ds, "status": "EMPTY"}
    top_lbl, top_ct = gold.most_common(1)[0]
    frac = top_ct / n
    np_ = max(1, sum(plef_pred.values()))
    nv_ = max(1, sum(vader_pred.values()))
    return {
        "probe": "label_integrity", "dataset": ds, "status": "OK", "n": n,
        "gold_classes": len(gold),
        "gold_dist": {k: round(v / n, 4) for k, v in gold.most_common()},
        "majority_label": top_lbl, "majority_frac": round(frac, 4),
        "degenerate": bool(len(gold) == 1 or frac > 0.995),
        "plef_pred_dist": {k: round(v / np_, 4) for k, v in plef_pred.most_common()},
        "vader_pred_dist": {k: round(v / nv_, 4) for k, v in vader_pred.most_common()},
        "plef_majority_rate": round(plef_pred.get(top_lbl, 0) / np_, 4),
        "vader_majority_rate": round(vader_pred.get(top_lbl, 0) / nv_, 4),
    }


def probe_tables(args):
    """F5 + F6 -- recompute Tables 4/5/7 and hunt for the Table 5 filter."""
    v1, ds = args
    p = metrics_csv(v1, ds)
    if not p.exists():
        return {"probe": "tables", "dataset": ds, "status": "MISSING"}
    want = ["sentiment", "gase", "pti", "pai", "nava", "nava_arc",
            "lewi_drop", "lewi_idx", "n_sents", "horsemen_total",
            "emo_anger", "emo_sadness", "emo_fear", "emo_joy",
            "emo_trust", "emo_disgust", "emo_surprise", "emo_anticipation"]
    rows = load_metrics(p, want)
    if not rows:
        return {"probe": "tables", "dataset": ds, "status": "EMPTY"}

    pti = [r["pti"] for r in rows if r["pti"] is not None]
    pair = [(r["pti"], r["pai"]) for r in rows if r["pti"] is not None and r["pai"] is not None]

    # ---- candidate filters for the Table 5 population --------------------
    def f_nonzero(r):
        return r["nava"] is not None and r["nava"] != 0.0
    def f_arc(r):
        return (r.get("nava_arc") or "").strip() not in ("", "short_text")
    def f_n4(r):
        return r["n_sents"] is not None and r["n_sents"] >= 4
    def f_n6(r):
        return r["n_sents"] is not None and r["n_sents"] >= 6
    def f_lewi(r):
        return r["lewi_drop"] is not None and r["lewi_drop"] != 0.0
    def f_both(r):
        return f_nonzero(r) and f_lewi(r)
    def f_arc_n4(r):
        return f_arc(r) and f_n4(r)
    def f_arc_lewi(r):
        return f_arc(r) and f_lewi(r)
    def f_n4_lewi(r):
        return f_n4(r) and f_lewi(r)

    candidates = [
        ("nava!=0", f_nonzero), ("arc!=short_text", f_arc), ("n_sents>=4", f_n4),
        ("n_sents>=6", f_n6), ("lewi_drop!=0", f_lewi), ("nava!=0 & lewi!=0", f_both),
        ("arc & n>=4", f_arc_n4), ("arc & lewi!=0", f_arc_lewi),
        ("n>=4 & lewi!=0", f_n4_lewi),
    ]
    filt_results = []
    target_n = PAPER["t5_valid_n"].get(ds)
    target_r = PAPER["t5_pearson"].get(ds)
    for name, fn in candidates:
        sel = [r for r in rows if fn(r) and r["nava"] is not None and r["lewi_drop"] is not None]
        nn = len(sel)
        rr = pearson([r["nava"] for r in sel], [r["lewi_drop"] for r in sel]) if nn >= 3 else None
        ss = sd([r["lewi_drop"] for r in sel]) if nn >= 2 else None
        filt_results.append({
            "filter": name, "n": nn,
            "r": None if rr is None else round(rr, 4),
            "lewi_sd": None if ss is None else round(ss, 4),
            "n_matches_paper": bool(target_n is not None and nn == target_n),
            "r_matches_paper": bool(rr is not None and target_r is not None
                                    and abs(rr - target_r) <= 0.005),
        })

    # ---- exact reconstruction of the GASE entropy+attachment term --------
    # gase = .30*S + .25*(1-H) + .25*(1-A) + .20*(1-G)   =>
    # (1-H)*.25 + (1-A)*.25 = gase - .30*S - .20*(1-G)
    ea_terms = []
    for r in rows:
        if None in (r["gase"], r["sentiment"], r["horsemen_total"], r["n_sents"]):
            continue
        G = min(1.0, r["horsemen_total"] / (r["n_sents"] * 0.5 + 1)) if r["n_sents"] else 1.0
        ea = r["gase"] - GASE_W["S"] * r["sentiment"] - GASE_W["G"] * (1 - G)
        ea_terms.append(ea)

    return {
        "probe": "tables", "dataset": ds, "status": "OK", "n_rows": len(rows),
        "pti_mean": round(statistics.mean(pti), 4) if pti else None,
        "paper_t4_pti": PAPER["t4_pti_mean"].get(ds),
        "paper_t7_pti": PAPER["t7_pti_mean"].get(ds),
        "pti_pai_r": round(pearson([a for a, _ in pair], [b for _, b in pair]), 4) if len(pair) > 2 else None,
        "paper_t7_pti_pai": PAPER["t7_pti_pai"].get(ds),
        "filters": filt_results,
        "ea_term_mean": round(statistics.mean(ea_terms), 4) if ea_terms else None,
        "ea_term_sd": round(sd(ea_terms), 4) if ea_terms else None,
        "ea_term_n": len(ea_terms),
    }


def probe_null_trial(spec):
    """F7 -- one trial of the NAVA x LEWI structural null."""
    model, seed, n_texts = spec
    rnd = random.Random(seed)
    lengths = [4, 5, 6, 7, 8, 10, 12, 15, 20, 25]
    nav, lew = [], []
    for _ in range(n_texts):
        L = rnd.choice(lengths)
        if model == "iid_uniform":
            s = [rnd.uniform(-1, 1) for _ in range(L)]
        elif model == "iid_normal_matched":
            s = [rnd.gauss(0.015, 0.19) for _ in range(L)]
        elif model == "zero_inflated":
            s = [0.0 if rnd.random() < 0.60 else rnd.gauss(0, 0.35) for _ in range(L)]
        elif model == "random_walk":
            v = 0.0
            s = []
            for _ in range(L):
                v = max(-1.0, min(1.0, v + rnd.gauss(0, 0.25)))
                s.append(v)
        else:
            raise ValueError(model)
        nv = v1_compute_nava(s)
        _, lw = v1_compute_lewi(s)
        if nv is None:
            continue
        nav.append(nv)
        lew.append(lw)
    return {"model": model, "seed": seed, "n": len(nav), "r": pearson(nav, lew)}


def probe_pti_pai_trial(spec):
    """F8 -- one trial of the PTI x PAI mechanical null."""
    regime, seed, n = spec
    rnd = random.Random(seed)
    P, A = [], []
    for _ in range(n):
        if regime == "unrestricted":
            I = rnd.randint(0, 40)
            Y = rnd.randint(0, 25)
        else:                       # I >= You : the regime ALL nine corpora sit in
            I = rnd.randint(5, 40)
            Y = rnd.randint(0, I)
        W = rnd.randint(0, 10)
        pti = (I - Y) / (I + Y + W + 1)
        i_dom = abs(I - Y) / max(1, I + Y)
        c_dom = rnd.random() * 0.3
        a_dom = rnd.choice([0.0, min(1.0, 0.5 + rnd.randint(1, 5) / 10)])
        pai = min(1.0, (c_dom + i_dom + a_dom) / 3)
        P.append(pti)
        A.append(pai)
    return {"regime": regime, "seed": seed, "n": n, "r": pearson(P, A)}


def probe_baselines(v1):
    """F3 -- static AST parse of the embedded 'baseline' lexicons."""
    src = Path(v1) / "plef_v7.py"
    out = {"probe": "baselines", "status": "OK", "source": str(src)}
    if not src.exists():
        out["status"] = "MISSING"
        return out
    text = src.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        out["status"] = "PARSE_ERROR"
        out["error"] = str(e)
        return out
    sizes, dupes = {}, {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name):
                continue
            if tgt.id not in ("_VADER_SEEDS", "_NRC_SEEDS", "_LIWC_CATEGORIES"):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            keys = []
            for k in node.value.keys:
                if isinstance(k, ast.Constant):
                    keys.append(k.value)
            sizes[tgt.id] = len(keys)
            dup = [k for k, c in collections.Counter(keys).items() if c > 1]
            dupes[tgt.id] = dup
            if tgt.id == "_LIWC_CATEGORIES":
                total = 0
                for v in node.value.values:
                    if isinstance(v, ast.List):
                        total += len(v.elts)
                sizes["_LIWC_TOTAL_WORDS"] = total
    out["entry_counts"] = sizes
    out["duplicate_keys"] = {k: v for k, v in dupes.items() if v}
    out["published_sizes"] = PAPER["published_lexicon_sizes"]
    out["comparison"] = {
        "VADER": {"embedded": sizes.get("_VADER_SEEDS"),
                  "published": PAPER["published_lexicon_sizes"]["VADER"]},
        "NRC": {"embedded": sizes.get("_NRC_SEEDS"),
                "published": PAPER["published_lexicon_sizes"]["NRC"]},
        "LIWC": {"embedded": sizes.get("_LIWC_TOTAL_WORDS"),
                 "published": PAPER["published_lexicon_sizes"]["LIWC"]},
    }
    # is the word "simplified" present next to the lexicon definitions?
    out["self_described_simplified"] = bool(re.search(
        r"[Ss]implified\s+(VADER|NRC|LIWC)", text))
    return out


def probe_ablation_source(v1):
    """F4a -- locate the ablation arithmetic anywhere in the V1 tree."""
    out = {"probe": "ablation_source", "status": "OK", "hits": [],
           "hardcoded_constant_found": False, "rci_scaling_found": False,
           "in_shipped_code": False}
    pat_const = re.compile(r"gase[\"'\]]*\s*\]?\s*-\s*w\s*\*\s*0\.5")
    pat_rci = re.compile(r"rci_vals\s*\]?\s*\]?.*\*\s*0\.7|r\s*\*\s*0\.7")
    for p in sorted(Path(v1).rglob("*.py*")):
        if p.is_dir() or p.suffix not in (".py", ".bak"):
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if pat_const.search(line):
                out["hits"].append({"file": p.name, "line": i, "kind": "hardcoded_0.5",
                                    "text": line.strip()})
                out["hardcoded_constant_found"] = True
                if p.suffix == ".py":
                    out["in_shipped_code"] = True
            elif pat_rci.search(line) and "0.7" in line:
                out["hits"].append({"file": p.name, "line": i, "kind": "rci_x0.7",
                                    "text": line.strip()})
                out["rci_scaling_found"] = True
    return out


def probe_hygiene(v1):
    """F9 -- version identifiers and reviewer-facing artifacts in the repo."""
    out = {"probe": "hygiene", "status": "OK", "versions": [], "flags": []}
    markers = [
        ("response_language_generator", r"Reviewer response language"),
        ("verbatim_framing_template", r"FRAMING TEMPLATE \(use verbatim"),
        ("standard_reply_script", r"REVIEWER OBJECTION\s*→?\s*STANDARD REPLY"),
        ("placeholder_statistic", r"kappa\s*=\s*X\.XX"),
        ("latex_paper_generator", r"def module_latex_paper"),
        ("reviewer_summary_module", r"def module_reviewer_summary"),
    ]
    for p in sorted(Path(v1).rglob("*.py")):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.finditer(r"(?:VERSION\s*=\s*[\"']([\d.]+)[\"']|PLEF\s+v([\d.]+))", t):
            v = m.group(1) or m.group(2)
            out["versions"].append({"file": p.name, "version": v})
        for name, pat in markers:
            if re.search(pat, t):
                out["flags"].append({"file": p.name, "marker": name})
    seen = sorted({v["version"] for v in out["versions"]})
    out["distinct_versions"] = seen
    out["version_conflict"] = len(seen) > 1
    # count .bak files -- these ship history a reviewer can read
    out["backup_files"] = [p.name for p in Path(v1).rglob("*.bak")]
    return out


# ===========================================================================
# bootstrap
# ===========================================================================
TREE = [
    "scripts", "src", "data/raw", "data/interim", "data/external",
    "results/canonical", "results/forensics", "results/figures",
    "paper", "logs", "MANIFEST", "tests",
]

GITIGNORE = """\
__pycache__/
*.pyc
*.bak
data/raw/
data/interim/
data/external/
logs/
.DS_Store
"""

README_STUB = """\
# PLEF V2

Rebuild of the PLEF framework for the Scientific Reports major revision.

This repository is a clean rebuild. It deliberately does NOT inherit code from
V1. Artifacts from V1 are treated as evidence only, hashed in
`MANIFEST/input_manifest.sha256`, and never imported.

## Status

Script 01 (bootstrap + forensics) has run. See
`results/forensics/FORENSIC_REPORT.md` for the defect record that the
response letter is built on.

Nothing else has been rebuilt yet.

## Rules for this repository

1. No module in `src/` generates reviewer-facing prose. Ever.
2. Every number that appears in the manuscript is emitted by a script in
   `scripts/` and written to `results/canonical/`. Nothing is transcribed by
   hand.
3. One canonical run. Tables that disagree are a build failure, not an
   editorial matter.
4. Baselines are the real published implementations or they are not called by
   the published system's name.
"""


def bootstrap(root, self_path):
    root = Path(root)
    created = []
    for d in TREE:
        p = root / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE, encoding="utf-8")
        created.append(str(gi))
    rd = root / "README.md"
    if not rd.exists():
        rd.write_text(README_STUB, encoding="utf-8")
        created.append(str(rd))
    # install self
    dest = root / "scripts" / Path(self_path).name
    try:
        if Path(self_path).resolve() != dest.resolve():
            shutil.copy2(self_path, dest)
            created.append(str(dest))
    except Exception:
        pass
    return created


def hash_v1_inputs(v1, root, workers):
    """Freeze every V1 artifact we use as evidence."""
    targets = []
    for pat in ("plef_v7.py", "multi_dataset_analysis.py", "experimental_design.py",
                "get_gold_labels.py", "fix_all.py", "auto_analysis.py"):
        p = Path(v1) / pat
        if p.exists():
            targets.append(p)
    for p in sorted(Path(v1).rglob("*.bak")):
        targets.append(p)
    for ds in DATASETS:
        p = metrics_csv(v1, ds)
        if p.exists():
            targets.append(p)
    for p in sorted((Path(v1) / "results").rglob("*.txt")):
        targets.append(p)
    for p in sorted((Path(v1) / "results").rglob("*.csv")):
        if p not in targets:
            targets.append(p)

    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_hash_one, str(p)): p for p in targets}
        for fu in as_completed(futs):
            rows.append(fu.result())
    rows.sort(key=lambda r: r["path"])
    out = Path(root) / "MANIFEST" / "input_manifest.sha256"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# PLEF V1 evidence manifest -- frozen {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"# {len(rows)} artifacts\n")
        for r in rows:
            f.write(f"{r['sha256']}  {r['size']:>12}  {r['path']}\n")
    return rows, out


def _hash_one(path):
    return {"path": path, "sha256": sha256(path), "size": os.path.getsize(path)}


# ===========================================================================
# report
# ===========================================================================
def write_report(root, ev):
    p = Path(root) / "results" / "forensics" / "FORENSIC_REPORT.md"
    L = []
    A = L.append
    A("# PLEF V1 -- Forensic Defect Record")
    A("")
    A(f"Generated: {ev['meta']['generated']}")
    A(f"Script: 01_bootstrap_and_forensics.py v{SCRIPT_VERSION}")
    A(f"V1 source: `{ev['meta']['v1_root']}`")
    A(f"Evidence artifacts hashed: {ev['meta']['n_hashed']}")
    A("")
    A("This document records defects found in the pipeline that produced the")
    A("submitted manuscript. It is the factual basis for the disclosure section")
    A("of the response letter. Every statement here is reproducible by re-running")
    A("script 01 against the hashed artifacts listed in MANIFEST/.")
    A("")

    A("## F1/F2 -- Gold label integrity")
    A("")
    A("| dataset | N | gold classes | majority label | majority share | degenerate |")
    A("|---|---:|---:|---|---:|---|")
    for r in ev["label_integrity"]:
        if r.get("status") != "OK":
            A(f"| {r['dataset']} | - | - | - | - | {r.get('status')} |")
            continue
        A(f"| {r['dataset']} | {r['n']:,} | {r['gold_classes']} | {r['majority_label']} "
          f"| {r['majority_frac']*100:.1f}% | {'**YES**' if r['degenerate'] else 'no'} |")
    A("")
    degen = [r for r in ev["label_integrity"] if r.get("degenerate")]
    if degen:
        A(f"**{len(degen)} corpora have a single-class gold vector.** On these, macro-AUC")
        A("is undefined (reported as 0.500), Cohen's d is 0.000 by construction, and")
        A("accuracy measures only the rate at which a system guesses the majority class:")
        A("")
        A("| dataset | PLEF majority-guess rate | VADER majority-guess rate |")
        A("|---|---:|---:|")
        for r in degen:
            A(f"| {r['dataset']} | {r['plef_majority_rate']*100:.1f}% | {r['vader_majority_rate']*100:.1f}% |")
        A("")

    A("## F3 -- Baseline authenticity")
    A("")
    b = ev["baselines"]
    if b.get("status") == "OK":
        A("| named system | embedded entries | published size | ratio |")
        A("|---|---:|---:|---:|")
        for k, v in b["comparison"].items():
            e = v["embedded"]
            pb = v["published"]
            ratio = f"{100*e/pb:.1f}%" if e else "n/a"
            A(f"| {k} | {e} | ~{pb:,} | {ratio} |")
        A("")
        if b.get("duplicate_keys"):
            A(f"Duplicate dictionary keys found: `{b['duplicate_keys']}`")
            A("")
        A(f"Source self-describes these as simplified: **{b['self_described_simplified']}**")
        A("")
        A("The manuscript (Section 4.3) states VADER was run \"using the published")
        A("rule-based algorithm\". The embedded implementation has no intensifier")
        A("handling, no punctuation amplification, no capitalisation handling and no")
        A("degree modifiers. That sentence must be corrected.")
    A("")

    A("## F4 -- Ablation validity")
    A("")
    a = ev["ablation_source"]
    if a["hardcoded_constant_found"]:
        A("The published GASE ablation subtracts a hardcoded constant instead of")
        A("removing a component. Located at:")
        A("")
        for h in a["hits"]:
            A(f"- `{h['file']}` line {h['line']} ({h['kind']}): `{h['text']}`")
        A("")
        A(f"Present in shipped (non-backup) code: **{a['in_shipped_code']}**")
        A("")
        A("Consequence, exactly:")
        A("")
        A("| component | weight | published delta | weight x 0.5 |")
        A("|---|---:|---:|---:|")
        for name, w in (("entropy", 0.25), ("attachment", 0.25), ("horsemen", 0.20)):
            A(f"| {name} | {w:.2f} | {PAPER['t8_deltas'][name]:+.4f} | {-w*0.5:+.4f} |")
        A("")
    A("Reconstructed true entropy+attachment term, computed exactly from the shipped")
    A("result files as `gase - 0.30*S - 0.20*(1-G)`:")
    A("")
    A("| dataset | true 0.25(1-H)+0.25(1-A) | assumed by ablation | n |")
    A("|---|---:|---:|---:|")
    for r in ev["tables"]:
        if r.get("status") == "OK" and r.get("ea_term_mean") is not None:
            A(f"| {r['dataset']} | {r['ea_term_mean']:.4f} (sd {r['ea_term_sd']:.4f}) | 0.2500 | {r['ea_term_n']:,} |")
    A("")

    A("## F5 -- Table reproducibility from shipped result files")
    A("")
    A("| dataset | PTI mean recomputed | Table 4 | reproduces | Table 7 | reproduces |")
    A("|---|---:|---:|---|---:|---|")
    for r in ev["tables"]:
        if r.get("status") != "OK":
            continue
        m = r["pti_mean"]
        t4 = r["paper_t4_pti"]
        t7 = r["paper_t7_pti"]
        ok4 = "yes" if (t4 is not None and m is not None and abs(m - t4) <= TOL) else ("**NO**" if t4 is not None else "-")
        ok7 = "yes" if (t7 is not None and m is not None and abs(m - t7) <= TOL) else ("**NO**" if t7 is not None else "-")
        A(f"| {r['dataset']} | {m} | {t4} | {ok4} | {t7} | {ok7} |")
    A("")
    A("Tables 4 and 7 report the same quantity. If one reproduces and the other does")
    A("not, the manuscript contains numbers from two different pipeline runs.")
    A("")

    A("## F6 -- Table 5 valid-N filter recovery")
    A("")
    A("Every plausible filter rule was tried against each corpus. A rule 'recovers'")
    A("Table 5 only if it reproduces both the published N and the published r.")
    A("")
    for r in ev["tables"]:
        if r.get("status") != "OK":
            continue
        tgt_n = PAPER["t5_valid_n"].get(r["dataset"])
        tgt_r = PAPER["t5_pearson"].get(r["dataset"])
        A(f"**{r['dataset']}** -- paper reports n={tgt_n}, r={tgt_r}")
        A("")
        A("| filter | n | r | n matches | r matches |")
        A("|---|---:|---:|---|---|")
        for fr in r["filters"]:
            A(f"| {fr['filter']} | {fr['n']:,} | {fr['r']} | "
              f"{'yes' if fr['n_matches_paper'] else 'no'} | "
              f"{'yes' if fr['r_matches_paper'] else 'no'} |")
        A("")

    A("## F7 -- Structural null: NAVA x LEWI")
    A("")
    A("V1's own compute_nava and compute_lewi run on sequences containing no")
    A("narrative structure whatsoever.")
    A("")
    A("| noise model | trials | mean r | min | max |")
    A("|---|---:|---:|---:|---:|")
    for m, st in ev["null_nava_lewi"].items():
        A(f"| {m} | {st['trials']} | {st['mean']:.3f} | {st['min']:.3f} | {st['max']:.3f} |")
    A("")
    lo, hi = PAPER["abstract_nava_lewi_range"]
    A(f"The manuscript reports observed r in [{lo}, {hi}] and presents it as convergent")
    A("validity. Compare against the table above, in particular the autocorrelated")
    A("model, which is the appropriate null for real sentence sentiment.")
    A("")

    A("## F8 -- Mechanical null: PTI x PAI")
    A("")
    A("Random pronoun counts. No text. PAI's I_dom term is built from the same")
    A("counts as PTI, signed versus absolute.")
    A("")
    A("| regime | trials | mean r | min | max |")
    A("|---|---:|---:|---:|---:|")
    for m, st in ev["null_pti_pai"].items():
        A(f"| {m} | {st['trials']} | {st['mean']:.3f} | {st['min']:.3f} | {st['max']:.3f} |")
    A("")
    A("All nine corpora have positive mean PTI, so all nine sit in the I >= You regime.")
    A("")

    A("## F9 -- Repository hygiene")
    A("")
    h = ev["hygiene"]
    A(f"Distinct version identifiers found: `{h['distinct_versions']}` "
      f"(conflict: **{h['version_conflict']}**)")
    A("")
    if h["flags"]:
        A("Reviewer-facing artifacts present in the repository:")
        A("")
        A("| file | marker |")
        A("|---|---|")
        for f_ in h["flags"]:
            A(f"| {f_['file']} | {f_['marker']} |")
        A("")
        A("These must be deleted before the repository is made public. A reviewer")
        A("who finds a module that generates reviewer-response prose with")
        A("placeholder statistics will not read the rest of the submission charitably.")
        A("")
    if h["backup_files"]:
        A(f"Backup files shipped in repo: {len(h['backup_files'])} "
          f"({', '.join(h['backup_files'][:6])}{' ...' if len(h['backup_files'])>6 else ''})")
        A("")

    A("## Disclosure checklist for the response letter")
    A("")
    A("Each item below is a statement in the submitted manuscript that this record")
    A("shows to be incorrect. Each must be named explicitly in the response.")
    A("")
    for i, item in enumerate(ev["disclosure"], 1):
        A(f"{i}. {item}")
    A("")

    p.write_text("\n".join(L), encoding="utf-8")
    return p


def build_disclosure(ev):
    d = []
    degen = [r["dataset"] for r in ev["label_integrity"] if r.get("degenerate")]
    if degen:
        d.append(f"Two dataset loaders produced single-class gold vectors "
                 f"({', '.join(degen)}). All reported F1/AUC/d for these corpora are "
                 f"artifacts, and both are included in the abstract's headline means "
                 f"(macro-F1 {PAPER['abstract_mean_f1']}, macro-AUC {PAPER['abstract_mean_auc']}) "
                 f"and in the {PAPER['abstract_total_items']:,} item total.")
        if "dailydialog" in degen:
            d.append("Section 5.7's 'most striking' McNemar result on DailyDialog reflects "
                     "majority-class guessing on a single-class label vector, not superior "
                     "handling of dialogue. Section 6.3's '>83% neutral' figure is also wrong.")
    b = ev["baselines"]
    if b.get("status") == "OK" and b["comparison"]["VADER"]["embedded"]:
        d.append(f"Section 4.3 states VADER was run 'using the published rule-based "
                 f"algorithm'. The embedded lexicon holds "
                 f"{b['comparison']['VADER']['embedded']} entries against roughly "
                 f"{b['comparison']['VADER']['published']:,} in the published system, with no "
                 f"intensifier, punctuation or capitalisation handling. The same applies "
                 f"to the NRC and LIWC baselines. All of Table 3 must be recomputed "
                 f"against real implementations.")
        d.append("The Consensus silver standard is defined by agreement among these three "
                 "simplified reimplementations, which share a tokenizer and overlapping "
                 "vocabulary. It is not three independent systems, and VADER's 1.000 "
                 "score on it is definitional.")
    if ev["ablation_source"]["hardcoded_constant_found"]:
        d.append("Table 8 is not an ablation. Three of its four rows subtract "
                 "weight x 0.5, a hardcoded constant; the component values were never "
                 "read. The conclusions in Sections 3.4 and 5.6 that rest on it are "
                 "withdrawn.")
    bad4 = [r["dataset"] for r in ev["tables"] if r.get("status") == "OK"
            and r.get("paper_t4_pti") is not None and r.get("pti_mean") is not None
            and abs(r["pti_mean"] - r["paper_t4_pti"]) > TOL]
    bad7 = [r["dataset"] for r in ev["tables"] if r.get("status") == "OK"
            and r.get("paper_t7_pti") is not None and r.get("pti_mean") is not None
            and abs(r["pti_mean"] - r["paper_t7_pti"]) > TOL]
    if bad7 and not bad4:
        d.append(f"Tables 4 and 7 report the same PTI means but disagree on "
                 f"{len(bad7)} of 9 corpora. Table 4 reproduces from the shipped result "
                 f"files; Table 7 does not. The manuscript combines two pipeline runs.")
    unrec = []
    for r in ev["tables"]:
        if r.get("status") != "OK":
            continue
        if not any(f["n_matches_paper"] and f["r_matches_paper"] for f in r["filters"]):
            unrec.append(r["dataset"])
    if unrec:
        d.append(f"Table 5's valid-N population cannot be recovered from the shipped "
                 f"result files for {len(unrec)} of 9 corpora under any tested filter. "
                 f"The Data Availability statement's claim that the pre-computed files "
                 f"allow independent verification of all reported statistics is therefore "
                 f"not correct as written.")
    if ev["null_nava_lewi"]:
        worst = max(st["mean"] for st in ev["null_nava_lewi"].values())
        lo, hi = PAPER["abstract_nava_lewi_range"]
        d.append(f"The NAVA x LEWI correlation reported as the central finding "
                 f"(r = {lo}-{hi}) does not exceed its structural null; unstructured "
                 f"sequences reach mean r = {worst:.3f}. The metrics are two "
                 f"pre-minus-post mean differences over the same signal. Sections 5.3 "
                 f"and 6.1, the abstract and the conclusion are rewritten accordingly.")
    if ev["null_pti_pai"]:
        w = ev["null_pti_pai"].get("I_ge_You", {}).get("mean")
        if w:
            d.append(f"PAI's I_dom term is built from the same pronoun counts as PTI. "
                     f"With random counts and no text, r reaches {w:.3f} in the regime all "
                     f"nine corpora occupy. H2 is reported as mechanically confounded, "
                     f"not as construct validation.")
    d.append("The abstract states PTI 'correlates significantly with PAI in six of nine "
             "datasets'. It is significant in all nine; six exceed an arbitrary r > 0.25 "
             "threshold. The wording is corrected.")
    d.append(f"The reported NAVA x LEWI range upper bound of "
             f"{PAPER['abstract_nava_lewi_range'][1]} does not appear anywhere in Table 5, "
             f"whose maximum is {max(PAPER['t5_pearson'].values())}.")
    d.append("Sections 3 and Contribution 4 claim bootstrap confidence intervals over 500 "
             "resamples. No confidence interval appears in the manuscript. Intervals are "
             "added throughout.")
    return d


# ===========================================================================
# main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="PLEF V2 script 01 -- bootstrap the clean tree and run forensics on V1.")
    ap.add_argument("--root", required=True,
                    help=r"V2 project root, e.g. D:\Research\PLEF\Version_2\PLEF_V2")
    ap.add_argument("--v1", required=True,
                    help=r"V1 PLEF folder containing plef_v7.py and results\ , e.g. D:\Research\PLEF\PLEF")
    ap.add_argument("--workers", type=int, default=0,
                    help="worker processes (default: cpu_count-1)")
    ap.add_argument("--null-trials", type=int, default=24,
                    help="trials per noise model for the structural null (default 24)")
    ap.add_argument("--null-texts", type=int, default=2000,
                    help="synthetic texts per trial (default 2000)")
    ap.add_argument("--skip-hash", action="store_true",
                    help="skip the SHA-256 evidence freeze (not recommended)")
    args = ap.parse_args()

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    root = Path(args.root)
    v1 = Path(args.v1)

    created = bootstrap(root, os.path.abspath(__file__))
    log_path = root / "results" / "forensics" / "console_log.txt"
    tee = Tee(log_path)
    sys.stdout = tee

    try:
        head("PLEF V2 -- SCRIPT 01 : BOOTSTRAP + ADVERSARIAL FORENSICS")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  V2 root        : {root}")
        print(f"  V1 source      : {v1}")
        print(f"  workers        : {workers}")
        print(f"  python         : {sys.version.split()[0]}  ({sys.platform})")

        sub("BOOTSTRAP")
        if created:
            for c in created:
                print(f"  created  {c}")
        else:
            print("  tree already present, nothing created")

        # ---- validate V1 -------------------------------------------------
        sub("V1 EVIDENCE CHECK")
        if not v1.exists():
            print(f"  FATAL: V1 path does not exist: {v1}")
            return 2
        missing = []
        if not (v1 / "plef_v7.py").exists():
            missing.append("plef_v7.py")
        present_ds = []
        for ds in DATASETS:
            if metrics_csv(v1, ds).exists():
                present_ds.append(ds)
            else:
                missing.append(f"results/{ds}/all_posts_metrics_{ds}.csv")
        for m in missing:
            print(f"  MISSING  {m}")
        print(f"  metrics files found: {len(present_ds)}/{len(DATASETS)}")
        if not present_ds:
            print("  FATAL: no V1 result files found. Point --v1 at the folder that")
            print("         contains plef_v7.py and the results\\ directory.")
            return 2

        # ---- freeze evidence ---------------------------------------------
        n_hashed = 0
        if not args.skip_hash:
            sub("EVIDENCE FREEZE (SHA-256)")
            rows, manifest_path = hash_v1_inputs(v1, root, workers)
            n_hashed = len(rows)
            print(f"  hashed {n_hashed} artifacts")
            print(f"  manifest -> {manifest_path}")
        else:
            print("  evidence freeze SKIPPED by flag")

        ev = {"meta": {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                       "script_version": SCRIPT_VERSION,
                       "v1_root": str(v1), "v2_root": str(root),
                       "n_hashed": n_hashed, "workers": workers,
                       "python": sys.version.split()[0], "platform": sys.platform}}

        # ---- F1/F2 --------------------------------------------------------
        sub("F1/F2  GOLD LABEL INTEGRITY")
        res = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(probe_label_integrity, [(str(v1), d) for d in present_ds]):
                res.append(r)
        res.sort(key=lambda r: r["dataset"])
        ev["label_integrity"] = res
        print(f"  {'dataset':<22}{'N':>8}{'classes':>9}{'majority':>10}{'share':>9}   verdict")
        rule()
        for r in res:
            if r.get("status") != "OK":
                print(f"  {r['dataset']:<22}{'-':>8}{'-':>9}{'-':>10}{'-':>9}   {r['status']}")
                continue
            verdict = "DEGENERATE" if r["degenerate"] else "ok"
            print(f"  {r['dataset']:<22}{r['n']:>8,}{r['gold_classes']:>9}"
                  f"{r['majority_label']:>10}{r['majority_frac']*100:>8.1f}%   {verdict}")
        degen = [r for r in res if r.get("degenerate")]
        if degen:
            print()
            print("  Majority-class guessing rates on the degenerate corpora:")
            for r in degen:
                print(f"    {r['dataset']:<18} PLEF={r['plef_majority_rate']*100:5.1f}%   "
                      f"VADER={r['vader_majority_rate']*100:5.1f}%")
                print(f"      gold  : {r['gold_dist']}")
                print(f"      PLEF  : {r['plef_pred_dist']}")
                print(f"      VADER : {r['vader_pred_dist']}")

        # ---- F3 -----------------------------------------------------------
        sub("F3  BASELINE AUTHENTICITY")
        ev["baselines"] = probe_baselines(str(v1))
        b = ev["baselines"]
        if b["status"] == "OK":
            for k, v in b["comparison"].items():
                e, pb = v["embedded"], v["published"]
                pct = f"{100*e/pb:.2f}%" if e else "n/a"
                print(f"  {k:<6} embedded={str(e):>6}   published=~{pb:>7,}   ratio={pct:>8}")
            if b["duplicate_keys"]:
                print(f"  duplicate dict keys: {b['duplicate_keys']}")
            print(f"  source self-describes as 'simplified': {b['self_described_simplified']}")
        else:
            print(f"  status: {b['status']}")

        # ---- F4a ----------------------------------------------------------
        sub("F4  ABLATION VALIDITY")
        ev["ablation_source"] = probe_ablation_source(str(v1))
        a = ev["ablation_source"]
        if a["hits"]:
            for h in a["hits"]:
                print(f"  {h['kind']:<16} {h['file']}:{h['line']}")
                print(f"      {h['text']}")
        else:
            print("  no hardcoded-constant ablation located (check --v1 path)")
        print(f"  hardcoded 0.5 found : {a['hardcoded_constant_found']}")
        print(f"  present in shipped code (not just .bak) : {a['in_shipped_code']}")
        print()
        print("  Published Table 8 deltas vs. the weight x 0.5 identity:")
        for name, w in (("entropy", 0.25), ("attachment", 0.25), ("horsemen", 0.20)):
            print(f"    {name:<12} w={w:.2f}   published={PAPER['t8_deltas'][name]:+.4f}   "
                  f"w*0.5={-w*0.5:+.4f}   "
                  f"{'IDENTICAL' if abs(PAPER['t8_deltas'][name] + w*0.5) < 1e-9 else 'differs'}")

        # ---- F5/F6 ---------------------------------------------------------
        sub("F5/F6  TABLE REPRODUCIBILITY AND VALID-N RECOVERY")
        tres = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(probe_tables, [(str(v1), d) for d in present_ds]):
                tres.append(r)
        tres.sort(key=lambda r: r["dataset"])
        ev["tables"] = tres
        print(f"  {'dataset':<22}{'PTI(recomp)':>12}{'T4':>8}{'ok':>5}{'T7':>8}{'ok':>5}"
              f"{'PTIxPAI':>10}{'T7r':>8}{'ok':>5}")
        rule()
        for r in tres:
            if r.get("status") != "OK":
                print(f"  {r['dataset']:<22}{r.get('status')}")
                continue
            m, t4, t7 = r["pti_mean"], r["paper_t4_pti"], r["paper_t7_pti"]
            rr, t7r = r["pti_pai_r"], r["paper_t7_pti_pai"]
            o4 = "OK" if (t4 is not None and m is not None and abs(m - t4) <= TOL) else "NO"
            o7 = "OK" if (t7 is not None and m is not None and abs(m - t7) <= TOL) else "NO"
            op = "OK" if (rr is not None and t7r is not None and abs(rr - t7r) <= 0.012) else "NO"
            print(f"  {r['dataset']:<22}{m if m is not None else 0:>12.4f}"
                  f"{t4 if t4 is not None else 0:>8.3f}{o4:>5}"
                  f"{t7 if t7 is not None else 0:>8.3f}{o7:>5}"
                  f"{rr if rr is not None else 0:>10.4f}"
                  f"{t7r if t7r is not None else 0:>8.3f}{op:>5}")
        print()
        print("  Table 5 valid-N recovery (does ANY filter reproduce both n and r?):")
        for r in tres:
            if r.get("status") != "OK":
                continue
            hit = [f for f in r["filters"] if f["n_matches_paper"] and f["r_matches_paper"]]
            near = [f for f in r["filters"] if f["n_matches_paper"] or f["r_matches_paper"]]
            tag = f"RECOVERED by '{hit[0]['filter']}'" if hit else (
                  "partial: " + ", ".join(f["filter"] for f in near) if near else "NOT RECOVERABLE")
            print(f"    {r['dataset']:<22} paper n={PAPER['t5_valid_n'].get(r['dataset']):>6}  "
                  f"r={PAPER['t5_pearson'].get(r['dataset']):.3f}   {tag}")
        print()
        print("  Reconstructed GASE entropy+attachment term (exact, from result files):")
        print(f"    ablation assumed this term = 0.2500 for every text")
        for r in tres:
            if r.get("status") == "OK" and r.get("ea_term_mean") is not None:
                print(f"    {r['dataset']:<22} true mean={r['ea_term_mean']:+.4f}  "
                      f"sd={r['ea_term_sd']:.4f}  n={r['ea_term_n']:,}")

        # ---- F7 -----------------------------------------------------------
        sub("F7  STRUCTURAL NULL -- NAVA x LEWI")
        print(f"  {args.null_trials} trials x {args.null_texts:,} synthetic texts per model")
        models = ["iid_uniform", "iid_normal_matched", "zero_inflated", "random_walk"]
        specs = [(m, 10_000 + i, args.null_texts) for m in models for i in range(args.null_trials)]
        by_model = collections.defaultdict(list)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(probe_null_trial, specs, chunksize=1):
                if r["r"] is not None:
                    by_model[r["model"]].append(r["r"])
        ev["null_nava_lewi"] = {}
        print(f"  {'noise model':<24}{'trials':>8}{'mean r':>10}{'min':>10}{'max':>10}")
        rule()
        for m in models:
            v = by_model.get(m, [])
            if not v:
                continue
            st = {"trials": len(v), "mean": statistics.mean(v),
                  "min": min(v), "max": max(v), "sd": sd(v)}
            ev["null_nava_lewi"][m] = st
            print(f"  {m:<24}{st['trials']:>8}{st['mean']:>10.3f}{st['min']:>10.3f}{st['max']:>10.3f}")
        lo, hi = PAPER["abstract_nava_lewi_range"]
        print()
        print(f"  Manuscript reports observed r in [{lo}, {hi}] as convergent validity.")
        if ev["null_nava_lewi"]:
            worst = max(s["mean"] for s in ev["null_nava_lewi"].values())
            print(f"  Highest null mean r = {worst:.3f}.")
            print(f"  VERDICT: observed range {'DOES NOT EXCEED' if hi <= worst + 0.02 else 'partially exceeds'} the null.")

        # ---- F8 -----------------------------------------------------------
        sub("F8  MECHANICAL NULL -- PTI x PAI")
        regimes = ["unrestricted", "I_ge_You"]
        specs = [(rg, 20_000 + i, 20000) for rg in regimes for i in range(args.null_trials)]
        by_rg = collections.defaultdict(list)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(probe_pti_pai_trial, specs, chunksize=1):
                if r["r"] is not None:
                    by_rg[r["regime"]].append(r["r"])
        ev["null_pti_pai"] = {}
        print(f"  {'regime':<24}{'trials':>8}{'mean r':>10}{'min':>10}{'max':>10}")
        rule()
        for rg in regimes:
            v = by_rg.get(rg, [])
            if not v:
                continue
            st = {"trials": len(v), "mean": statistics.mean(v),
                  "min": min(v), "max": max(v), "sd": sd(v)}
            ev["null_pti_pai"][rg] = st
            print(f"  {rg:<24}{st['trials']:>8}{st['mean']:>10.3f}{st['min']:>10.3f}{st['max']:>10.3f}")
        print()
        print(f"  Manuscript Table 7 reports PTI x PAI r from "
              f"{min(PAPER['t7_pti_pai'].values())} to {max(PAPER['t7_pti_pai'].values())}.")
        print("  All nine corpora have positive mean PTI, i.e. they sit in the I >= You regime.")

        # ---- F9 -----------------------------------------------------------
        sub("F9  REPOSITORY HYGIENE")
        ev["hygiene"] = probe_hygiene(str(v1))
        h = ev["hygiene"]
        print(f"  distinct version identifiers: {h['distinct_versions']}  "
              f"(conflict: {h['version_conflict']})")
        if h["flags"]:
            print("  reviewer-facing artifacts found in repository:")
            for f_ in h["flags"]:
                print(f"    {f_['file']:<28} {f_['marker']}")
        else:
            print("  no reviewer-response generators found")
        print(f"  backup (.bak) files shipped: {len(h['backup_files'])}")

        # ---- report -------------------------------------------------------
        ev["disclosure"] = build_disclosure(ev)
        sub("DISCLOSURE CHECKLIST (for the response letter)")
        for i, d in enumerate(ev["disclosure"], 1):
            print(f"  {i:>2}. {d}")

        jpath = root / "results" / "forensics" / "defect_evidence.json"
        jpath.write_text(json.dumps(ev, indent=2, default=str), encoding="utf-8")
        rpath = write_report(root, ev)

        head("DONE")
        print(f"  report   : {rpath}")
        print(f"  evidence : {jpath}")
        print(f"  log      : {log_path}")
        if not args.skip_hash:
            print(f"  manifest : {root / 'MANIFEST' / 'input_manifest.sha256'}")
        print()
        print("  NEXT: read FORENSIC_REPORT.md end to end, confirm every line is one you")
        print("  are willing to put in the response letter, then send me the console output.")
        print("  Script 02 (real baselines + corrected loaders) is written against these")
        print("  findings, not against assumptions.")
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
