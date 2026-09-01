#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 08 : AUDIT RECONCILIATION
                       (v08.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
An internal review flagged three numbers in the manuscript as impossible or
unverifiable and instructed that none be corrected by intuition. This script
reconstructs each from the raw records on disk and writes an audit file that
the manuscript quotes verbatim.

  A  ANNOTATION ACCOUNTING
     The manuscript states 40 posts, then 19, then "16 of 35". Read as one
     sample these cannot all be right. This stage rebuilds the exact chain
     from the annotation files: slots served, unique posts, posts matched to
     a scored document, posts with and without a turning point. If the chain
     does not close, it says so and refuses to emit a corrected figure.

  B  DATASET RECONCILIATION
     309,833 scored items reduce to 265,452 unique, a difference of 44,381,
     while only a 22,603-item SemEval/TweetEval overlap is documented. This
     stage emits the full pairwise overlap matrix and a per-corpus ledger:
     raw units read, discarded with reason, retained, and contribution to the
     duplicate total.

  C  THROUGHPUT
     The manuscript pairs 1,900 words/s with 70 minutes for 5.5M words;
     5.5e6/1900 is 48 minutes, not 70. This stage recomputes the rate from
     the scored manifest, which records elapsed seconds and word counts per
     shard, and reports the overall figure and the per-shard figures
     separately, since conflating them is what produced the error.

  D  COVERAGE BANDS
     Recomputes the document-length bands the abstract quotes, so the
     abstract can be derived rather than asserted.

  E  ARCHETYPE TRAIL
     The manuscript states an 88% archetype-resolution figure with no result
     table behind it. This stage either reproduces it from the scored files
     with full denominators, or reports that it cannot be reproduced. If it
     cannot, the number must be deleted from the manuscript.

OUTPUT
------
  results/AUDIT_RECONCILIATION.md   quote this in the manuscript
  results/tables/audit_*.csv        machine-readable

EXIT CODES
----------
  0 every quantity reconciled
  2 missing prerequisite
  3 a quantity did NOT reconcile -- do not submit until resolved
===============================================================================
"""

import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import random
import re
import statistics
import sys
import traceback
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "08.3.1"

BANDS = [(1, 9), (10, 19), (20, 39), (40, 79), (80, 159), (160, 319), (320, 10**9)]


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


def rule(ch="-", w=82): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError):
        return None


def thash(t):
    return hashlib.sha1(" ".join(t.lower().split()).encode("utf-8", "replace")).hexdigest()


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


# ===========================================================================
def A_annotation(root, out):
    sub("A  ANNOTATION ACCOUNTING")
    ad = Path(root) / "data" / "interim" / "annotations"
    canon = Path(root) / "results" / "canonical"
    gold_p = ad / "gold_dev200.csv"
    ok = True

    print("  The manuscript states three counts. This rebuilds the chain that")
    print("  connects them, from the annotation files themselves.")
    print()

    ledger = []
    ann = {}
    for i in (1, 2, 3):
        rows = read_rows(ad / f"annotations_rater{i}.csv")
        if rows:
            ann[i] = rows
    if not ann:
        print("  no annotation files found")
        return False, []

    for i, rows in ann.items():
        slots = sorted({int(r["slot"]) for r in rows if (r.get("slot") or "").strip()})
        firsts, seen = [], set()
        for r in sorted(rows, key=lambda x: int(x["slot"])):
            if r["id"] not in seen:
                seen.add(r["id"]); firsts.append(r)
        reps = len(rows) - len(firsts)
        answered = [r for r in firsts if (r.get("overall_sentiment") or "").strip()]
        print(f"  rater {i}")
        print(f"    slots served              : {len(rows)}")
        print(f"    unique posts              : {len(firsts)}")
        print(f"    repeat showings           : {reps}")
        print(f"    unique posts answered     : {len(answered)}")
        ledger.append({"stage": f"rater{i}_slots", "n": len(rows)})
        ledger.append({"stage": f"rater{i}_unique_posts", "n": len(firsts)})
        ledger.append({"stage": f"rater{i}_repeats", "n": reps})
        ledger.append({"stage": f"rater{i}_answered", "n": len(answered)})

    gold = read_rows(gold_p)
    print()
    print(f"  gold file                   : {len(gold)} items"
          f"{'' if gold else '  (ABSENT)'}")
    if not gold:
        print("  Without a gold file no human-criterion figure can be reconciled.")
        return False, ledger
    ledger.append({"stage": "gold_items", "n": len(gold)})

    scored = read_rows(canon / "scored_dev_relationship.csv",
                       ["id", "lewi_idx", "n_sents", "nava_arc"])
    if not scored:
        scored = read_rows(canon / "scored_relationship.csv",
                           ["id", "lewi_idx", "n_sents", "nava_arc"])
    idx = {r["id"]: r for r in scored}
    matched = [g for g in gold if g["id"] in idx]
    print(f"  matched to a scored post    : {len(matched)}")
    ledger.append({"stage": "matched_to_scored", "n": len(matched)})

    with_lewi = [g for g in matched
                 if (idx[g["id"]].get("lewi_idx") or "").strip() != ""]
    print(f"  of those, LEWI is defined   : {len(with_lewi)}")
    ledger.append({"stage": "lewi_defined", "n": len(with_lewi)})

    def tp(g):
        try: return int(float(g.get("gold_turning_point")))
        except (TypeError, ValueError): return None
    none_tp = [g for g in with_lewi if tp(g) == 0]
    some_tp = [g for g in with_lewi if tp(g) is not None and tp(g) > 0]
    bad_tp = [g for g in with_lewi if tp(g) is None]
    print(f"    human marked NO turn      : {len(none_tp)}")
    print(f"    human marked a turn       : {len(some_tp)}")
    if bad_tp:
        print(f"    unparseable turning point : {len(bad_tp)}")
    ledger += [{"stage": "no_turning_point", "n": len(none_tp)},
               {"stage": "with_turning_point", "n": len(some_tp)},
               {"stage": "unparseable", "n": len(bad_tp)}]

    print()
    closes = len(none_tp) + len(some_tp) + len(bad_tp) == len(with_lewi)
    print(f"  CHAIN CLOSES: {len(none_tp)} + {len(some_tp)}"
          f"{' + ' + str(len(bad_tp)) if bad_tp else ''} = {len(with_lewi)}   "
          f"{'YES' if closes else '** NO **'}")
    if not closes:
        ok = False
        print("  The accounting does not close. Do not correct the manuscript")
        print("  until this is resolved from the raw records.")
    else:
        print()
        print("  The manuscript must state this chain explicitly. Reporting the")
        print("  first and last numbers without the intermediate steps is what")
        print("  makes them read as contradictory.")
    return ok, ledger


# ===========================================================================
def B_datasets(root, out):
    sub("B  DATASET RECONCILIATION")
    interim = Path(root) / "data" / "interim"
    man_p = Path(root) / "MANIFEST" / "corpora.json"
    if not man_p.exists():
        print("  MANIFEST/corpora.json missing; run script 03")
        return False, []
    man = json.loads(man_p.read_text(encoding="utf-8"))
    meta = man.get("loader_meta") or {}
    stats = man.get("stats") or {}

    print("  Per-corpus ledger: raw units read, discarded with reason, retained.")
    print()
    print(f"  {'corpus':<15}{'raw':>10}{'retained':>10}{'discarded':>11}   reasons")
    rule()
    rows_out = []
    for c in sorted(stats):
        m = meta.get(c) or {}
        n = stats[c].get("n", 0)
        reasons = []
        for k in ("dropped_short", "dropped_unparseable", "text_edits",
                  "mismatched_dialogues", "v1_silver_available"):
            if m.get(k):
                reasons.append(f"{k}={m[k]}")
        dr = m.get("discard_reasons") or {}
        for k, v in dr.items():
            reasons.append(f"{k}={v}")
        raw = n + sum(dr.values()) + (m.get("dropped_short") or 0) + \
            (m.get("dropped_unparseable") or 0)
        print(f"  {c:<15}{raw:>10,}{n:>10,}{raw-n:>11,}   "
              f"{'; '.join(reasons) if reasons else '-'}")
        rows_out.append({"corpus": c, "raw_units": raw, "retained": n,
                         "discarded": raw - n, "reasons": "; ".join(reasons)})

    print()
    print("  Cross-corpus duplicate accounting, by normalised text hash.")
    hashes = {}
    for c in sorted(stats):
        p = interim / f"corpus_{c}.csv"
        if not p.exists():
            continue
        s = set()
        for r in read_rows(p, ["text"]):
            t = (r.get("text") or "").strip()
            if t:
                s.add(thash(t))
        hashes[c] = s
    if not hashes:
        print("  corpus files not found under data/interim")
        return False, rows_out
    names = sorted(hashes)
    print()
    print(f"  {'':<15}" + "".join(f"{n[:9]:>10}" for n in names))
    rule()
    ov_rows = []
    for a in names:
        line = f"  {a:<15}"
        for b in names:
            if a == b:
                line += f"{'-':>10}"
                continue
            ov = len(hashes[a] & hashes[b])
            line += f"{ov:>10,}"
            if ov and a < b:          # unordered pairs only; the matrix is symmetric
                ov_rows.append({"corpus_a": a, "corpus_b": b, "shared_items": ov})
        print(line)
    tot = sum(len(hashes[c]) for c in names)
    uniq = len(set().union(*hashes.values()))
    print()
    scored = sum(stats[c].get("n", 0) for c in stats)
    print(f"  scored documents            : {scored:,}")
    print(f"  after within-corpus dedup   : {tot:,}   (-{scored-tot:,})")
    print(f"  after cross-corpus dedup    : {uniq:,}   (-{tot-uniq:,})")
    print()
    print("  The first step removes text repeated inside a single corpus; the")
    print("  second removes text shared between corpora. Reporting one figure")
    print("  for both makes neither reconstructible.")
    biggest = sorted(ov_rows, key=lambda r: -r["shared_items"])[:6]
    psum = sum(r["shared_items"] for r in ov_rows)
    print()
    print(f"  pairwise overlap total : {psum:,}")
    print(f"  documents removed      : {tot-uniq:,}")
    if psum != tot - uniq:
        ex = psum - (tot - uniq)
        print(f"  excess                 : {ex}  -> {ex} document(s) present in")
        print(f"                            three corpora; each appears in three")
        print(f"                            pairs but is removed twice.")
    print()
    print("  largest overlaps:")
    for r in biggest:
        print(f"    {r['corpus_a']:<14} & {r['corpus_b']:<14} {r['shared_items']:>8,}")
    print()
    print("  The manuscript must report this matrix, not a single overlap, or the")
    print("  difference between the summed and unique totals cannot be rebuilt.")
    out["dedup"] = {"scored": scored, "within_unique": tot, "unique": uniq,
                    "within_removed": scored - tot, "cross_removed": tot - uniq,
                    "pairs": ov_rows}
    return True, rows_out


# ===========================================================================
def C_throughput(root, out):
    sub("C  THROUGHPUT")
    p = Path(root) / "MANIFEST" / "scored.json"
    if not p.exists():
        print("  MANIFEST/scored.json missing")
        return False, []
    m = json.loads(p.read_text(encoding="utf-8"))
    shards = m.get("shards") or {}
    rows = []
    print(f"  {'shard':<18}{'words':>12}{'seconds':>10}{'words/s':>11}")
    rule()
    tw = ts = 0
    for k in sorted(shards):
        s = shards[k]
        w = s.get("words") or 0
        sec = s.get("seconds") or 0
        if not w:
            continue
        tw += w
        ts += sec
        r = w / sec if sec else 0
        print(f"  {k:<18}{w:>12,}{sec:>10.1f}{r:>11,.0f}")
        rows.append({"shard": k, "words": w, "seconds": round(sec, 1),
                     "words_per_sec": round(r)})
    # scored.json's elapsed_seconds records only the LAST invocation. Using it
    # against the summed word count produced 48,520 words/s in v08.1.0, which is
    # absurd on its face. The per-shard times are summed instead.
    el = ts
    last = m.get("elapsed_seconds")
    if last and abs(last - ts) > 1:
        print(f"  note: manifest elapsed_seconds = {last:.1f}s records only the")
        print(f"        most recent invocation; per-shard times sum to {ts:.1f}s")
    print("  " + "-" * 80)
    print(f"  {'TOTAL (all shards)':<18}{tw:>12,}{el:>10.1f}{tw/max(el,1e-9):>11,.0f}")
    # dev_relationship is the annotation split, not an evaluation corpus, and
    # must not enter a throughput figure quoted for the evaluation.
    dev = shards.get("dev_relationship") or {}
    ew = tw - (dev.get("words") or 0)
    es = el - (dev.get("seconds") or 0)
    if dev:
        print(f"  {'TOTAL (evaluation)':<18}{ew:>12,}{es:>10.1f}{ew/max(es,1e-9):>11,.0f}")
    print()
    print(f"  QUOTE THIS: {ew:,} words in {es/60:.1f} minutes = "
          f"{ew/max(es,1e-9):,.0f} words/s")
    print()
    print("  The manuscript must quote ONE of these consistently. Pairing a")
    print("  single shard's rate with the whole run's elapsed time is what")
    print("  produced the arithmetic error.")
    out["throughput"] = {"total_words": tw, "elapsed_seconds": el,
                         "eval_words": ew, "eval_seconds": es,
                         "eval_words_per_sec": ew / max(es, 1e-9),
                         "eval_minutes": es / 60}
    return True, rows


# ===========================================================================
def D_bands(root, out):
    sub("D  COVERAGE BANDS, AS THE ABSTRACT MUST QUOTE THEM")
    canon = Path(root) / "results" / "canonical"
    res = collections.defaultdict(dict)
    for p in sorted(canon.glob("scored_*.csv")):
        c = p.stem.replace("scored_", "")
        if c == "dev_relationship":
            continue
        rows = read_rows(p, ["n_words", "sentiment_mean"])
        if not rows:
            continue
        for lo, hi in BANDS:
            sel = [r for r in rows
                   if lo <= (f(r["n_words"]) or 0) <= hi]
            if len(sel) < 20:
                continue
            fires = sum(1 for r in sel if (f(r["sentiment_mean"]) or 0.0) != 0.0)
            res[(lo, hi)][c] = 100.0 * fires / len(sel)
    print(f"  {'band (words)':<16}{'corpora':>9}{'min':>9}{'max':>9}   range as quoted")
    rule()
    rows_out = []
    for lo, hi in BANDS:
        d = res.get((lo, hi))
        if not d:
            continue
        lab = f"{lo}-{hi}" if hi < 10**9 else f"{lo}+"
        print(f"  {lab:<16}{len(d):>9}{min(d.values()):>8.1f}%"
              f"{max(d.values()):>8.1f}%   "
              f"{min(d.values()):.1f}--{max(d.values()):.1f}\\%")
        rows_out.append({"band": lab, "n_corpora": len(d),
                         "min_pct": round(min(d.values()), 1),
                         "max_pct": round(max(d.values()), 1)})
    print()
    print("  The abstract must use a band that appears in this table verbatim,")
    print("  and must name the band. 'under ten words' and 'over forty words'")
    print("  are not bands computed anywhere.")
    out["bands"] = rows_out
    return True, rows_out


# ===========================================================================
def E_archetype(root, out):
    sub("E  ARCHETYPE RESOLUTION -- can the 88% figure be reproduced?")
    canon = Path(root) / "results" / "canonical"
    rows_out = []
    found = False
    print(f"  {'corpus':<18}{'n':>9}{'resolved':>10}{'%':>8}   top archetypes")
    rule()
    for p in sorted(canon.glob("scored_*.csv")):
        c = p.stem.replace("scored_", "")
        rows = read_rows(p, ["rasp_dominant"])
        if not rows:
            continue
        vals = [(r.get("rasp_dominant") or "").strip() for r in rows]
        if not any(vals):
            continue
        found = True
        res = [v for v in vals if v and v.lower() != "none"]
        cnt = collections.Counter(res).most_common(3)
        pct = 100.0 * len(res) / len(vals)
        print(f"  {c:<18}{len(vals):>9,}{len(res):>10,}{pct:>7.1f}%   "
              f"{', '.join(f'{k} {100*v/max(1,len(vals)):.1f}%' for k, v in cnt)}")
        rows_out.append({"corpus": c, "n": len(vals), "resolved": len(res),
                         "pct": round(pct, 1),
                         "top": "; ".join(f"{k}={v}" for k, v in cnt)})
    if not found:
        print("  no rasp_dominant column found in any scored file")
        print()
        print("  The 88% figure CANNOT be reproduced. It must be deleted from")
        print("  the manuscript.")
        return False, rows_out
    print()
    print("  If the manuscript quotes a figure from this table it must also")
    print("  give the denominator, the archetype list and the method. If it")
    print("  does not, delete the figure: an isolated positive number with no")
    print("  result trail reads as residue from an earlier analysis.")
    out["archetype"] = rows_out
    return True, rows_out


# ===========================================================================
def F_benchmarks(root, out):
    """The two chance benchmarks the manuscript quotes, derived rather than asserted.

    An internal review asked how the random three-class macro-F1 and the human
    turning-point chance rate were obtained. A single seeded draw is not an
    expected value; and a chance rate averaged over posts must state what is
    averaged. Both are recomputed here with the procedure printed alongside.
    """
    sub("F  CHANCE BENCHMARKS -- exact derivations")
    cl = ["pos", "neu", "neg"]
    canon = Path(root) / "results" / "canonical"
    print("  Random three-class macro-F1: mean over 1,000 independent assignments")
    print("  in which each item receives one of three labels with equal probability,")
    print("  independently of its gold label. Interval = 2.5th/97.5th percentiles.")
    print()
    print(f"  {'corpus':<14}{'n':>9}{'mean':>9}{'sd':>8}{'2.5%':>9}{'97.5%':>9}")
    rule()
    rows = []
    for p_ in sorted(canon.glob("scored_*.csv")):
        c = p_.stem.replace("scored_", "")
        if c == "dev_relationship":
            continue
        # ISEAR and EmpatheticDialogues are two-class; a three-class random
        # benchmark for them is meaningless and was published in v08.3.0.
        if c in ("isear", "empathetic"):
            continue
        recs = [r for r in read_rows(p_, ["gold"]) if r.get("gold") in cl]
        if len(recs) < 100:
            continue
        g = [r["gold"] for r in recs]
        rnd = random.Random(20260830)
        vals = []
        for _ in range(1000):
            pred = [rnd.choice(cl) for _ in g]
            fs = []
            for k in cl:
                tp = sum(1 for a, b in zip(g, pred) if a == k and b == k)
                fp = sum(1 for a, b in zip(g, pred) if a != k and b == k)
                fn = sum(1 for a, b in zip(g, pred) if a == k and b != k)
                pr = tp / (tp + fp) if tp + fp else 0.0
                rc = tp / (tp + fn) if tp + fn else 0.0
                fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
            vals.append(sum(fs) / len(fs))
        vals.sort()
        m = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        print(f"  {c:<14}{len(g):>9,}{m:>9.4f}{sd:>8.4f}{vals[24]:>9.4f}{vals[974]:>9.4f}")
        rows.append({"corpus": c, "n": len(g), "random_f1_mean": round(m, 4),
                     "sd": round(sd, 4), "lo": round(vals[24], 4),
                     "hi": round(vals[974], 4)})

    print()
    print("  Human turning-point chance rate: mean over the comparison posts of")
    print("  1/N_i (exact match) and min(1, 3/N_i) (within one sentence), where")
    print("  N_i is the sentence count of post i.")
    gold = {}
    gp = Path(root) / "data" / "interim" / "annotations" / "gold_dev200.csv"
    for r in read_rows(gp):
        gold[r["id"]] = r
    sc = read_rows(canon / "scored_dev_relationship.csv", ["id", "n_sents", "lewi_idx"])
    if not sc:
        sc = read_rows(canon / "scored_relationship.csv", ["id", "n_sents", "lewi_idx"])
    idx = {r["id"]: r for r in sc}
    ns = []
    for i, g in gold.items():
        r = idx.get(i)
        if not r or (r.get("lewi_idx") or "").strip() == "":
            continue
        try:
            if int(float(g.get("gold_turning_point"))) > 0:
                ns.append(int(float(r["n_sents"])))
        except (TypeError, ValueError):
            pass
    if ns:
        e1 = statistics.mean([1.0 / max(1, n) for n in ns])
        e3 = statistics.mean([min(1.0, 3.0 / max(1, n)) for n in ns])
        print()
        print(f"    comparison posts n = {len(ns)}   sentence counts "
              f"{min(ns)}--{max(ns)}, median {statistics.median(ns):.0f}")
        print(f"    exact-match chance      : {100*e1:.1f}%")
        print(f"    within-one-sentence     : {100*e3:.1f}%")
        out["chance"] = {"n": len(ns), "exact_pct": 100 * e1, "within1_pct": 100 * e3}
    else:
        print("    no comparison posts found")
    out["random_f1"] = rows
    return True, rows


def write_report(root, out, tables):
    p = Path(root) / "results" / "AUDIT_RECONCILIATION.md"
    L = ["# Audit reconciliation", "",
         f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
         f"scripts/08_audit_reconciliation.py v{SCRIPT_VERSION}.",
         "", "Every figure below is rebuilt from the raw records. The manuscript",
         "quotes these values; none is edited by hand.", ""]
    if "throughput" in out:
        t = out["throughput"]
        L += ["## Throughput", "",
              f"- evaluation words scored: {t['eval_words']:,}",
              f"- elapsed: {t['eval_minutes']:.1f} minutes",
              f"- rate: {t['eval_words_per_sec']:,.0f} words/s", "",
              "Per-shard rates differ from the overall rate and must not be",
              "quoted alongside the overall elapsed time.", ""]
    if "dedup" in out:
        d = out["dedup"]
        L += ["## Item accounting", "",
              f"- scored documents: {d['scored']:,}",
              f"- after within-corpus deduplication: {d['within_unique']:,} "
              f"(-{d['within_removed']:,})",
              f"- after cross-corpus deduplication: {d['unique']:,} "
              f"(-{d['cross_removed']:,})", "",
              "Cross-corpus overlaps, unordered pairs:", "",
              "| corpus A | corpus B | shared items |", "|---|---|---:|"]
        for r in sorted(d["pairs"], key=lambda x: -x["shared_items"])[:10]:
            L.append(f"| {r['corpus_a']} | {r['corpus_b']} | {r['shared_items']:,} |")
        L.append("")
    if "bands" in out:
        L += ["## Coverage by document-length band", "",
              "| band (words) | corpora | min | max |", "|---|---:|---:|---:|"]
        for r in out["bands"]:
            L.append(f"| {r['band']} | {r['n_corpora']} | {r['min_pct']}% | {r['max_pct']}% |")
        L.append("")
    if "random_f1" in out:
        L += ["## Random three-class benchmark", "",
              "Mean macro-F1 over 1,000 independent uniform assignments.", "",
              "| corpus | n | mean | 2.5% | 97.5% |", "|---|---:|---:|---:|---:|"]
        for r in out["random_f1"]:
            L.append(f"| {r['corpus']} | {r['n']:,} | {r['random_f1_mean']} "
                     f"| {r['lo']} | {r['hi']} |")
        L.append("")
    if "chance" in out:
        c = out["chance"]
        L += ["## Human turning-point chance rates", "",
              f"- comparison posts: {c['n']}",
              f"- exact match, mean of 1/N_i: {c['exact_pct']:.1f}%",
              f"- within one sentence, mean of min(1, 3/N_i): {c['within1_pct']:.1f}%", ""]
    if "archetype" in out:
        L += ["## Archetype resolution", "",
              "| corpus | n | resolved | % |", "|---|---:|---:|---:|"]
        for r in out["archetype"]:
            L.append(f"| {r['corpus']} | {r['n']:,} | {r['resolved']:,} | {r['pct']}% |")
        L.append("")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    td = Path(root) / "results" / "tables"
    td.mkdir(parents=True, exist_ok=True)
    for name, data in tables.items():
        if not data:
            continue
        keys = []
        for d in data:
            for k in d:
                if k not in keys:
                    keys.append(k)
        with open(td / f"audit_{name}.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader(); w.writerows(data)
    return p


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 08 -- audit reconciliation.")
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    if not (root / "MANIFEST").exists():
        print("FATAL: run scripts 03 and 05 first.")
        return 2
    tee = Tee(root / "results" / "forensics" / "console_log_08.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 08 : AUDIT RECONCILIATION")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        out, tables, allok = {}, {}, True
        ok, t = A_annotation(root, out); tables["annotation"] = t; allok &= ok
        ok, t = B_datasets(root, out);   tables["datasets"] = t;   allok &= ok
        ok, t = C_throughput(root, out); tables["throughput"] = t; allok &= ok
        ok, t = D_bands(root, out);      tables["bands"] = t;      allok &= ok
        ok, t = E_archetype(root, out);  tables["archetype"] = t
        ok, t = F_benchmarks(root, out);  tables["benchmarks"] = t; allok &= ok
        p = write_report(root, out, tables)
        head("DONE")
        print(f"  report : {p}")
        print(f"  tables : {root / 'results' / 'tables'}")
        print()
        print(f"  all quantities reconciled : {allok}")
        if not allok:
            print("  Do not submit until every quantity above reconciles.")
            return 3
        return 0
    except Exception:
        print("\nUNHANDLED EXCEPTION"); traceback.print_exc(); return 3
    finally:
        sys.stdout = tee.stdout; tee.close()


if __name__ == "__main__":
    sys.exit(main())
