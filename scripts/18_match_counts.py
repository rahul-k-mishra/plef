#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 18 : LEXICON MATCH COUNTS   (18_match_counts.py, v1.1.0)
===============================================================================

CHANGES IN v1.1.0
-----------------
  Every macro-F1, interval bound and delta column of abstention_v2.csv
  (*_f1, *_lo, *_hi, delta_*), including the min_/max_ range rows, is now
  written to six decimals instead of four, so that rounding to three decimals
  for the manuscript is never ambiguous (v1.0.0 wrote ISEAR PLEF all as 0.6295
  and TweetEval PLEF matched as 0.4505, both on the three-decimal boundary).
  The deltas are computed from the six-decimal values. The per-corpus tables
  match_counts_<corpus>.csv carry no F1 or delta columns; their score column
  was already six decimals. Nothing else changes. The reproduction check
  against the published Table 6 and Fig. 1b keeps its tolerances (1e-4 for
  F1, 2e-4 for delta, 0.01 for fires %, 0.051 for bands), which are set by
  the four- and one-decimal precision of the published values; the console
  printout of that check still shows four decimals.

WHAT WE CHECK (plain language)
------------------------------
The paper calls a document "fired" when the framework's lexicon matched at
least one term (Table 6 caption). The code that produced Table 6 and Fig. 1b
actually tests something else: whether the document score is non-zero
(06_statistics.py lines 346, 722, 1315). Matched terms can cancel, so the two
are not the same event. Reviewer 3 (round 2, point 2) asked for the analysis
to be redone on the real match count.

For every document in the eight evaluation corpora and the 200-post
annotation-development split, this script re-reads the text from
data/interim/, imports the released core from src/, and repeats exactly what
plef_core.score_sentence does:

  * split into sentences with plef_core.sentences
  * tokenise each sentence with plef_core.tokenize
  * count SINGLE-TOKEN matches: tokens t for which LEXICON.get(t) is truthy
    (plef_core.py lines 101-102)
  * count MULTI-WORD matches: lexicon keys containing a space that occur as a
    substring of the lower-cased sentence, at most once per key per sentence
    (plef_core.py lines 111-112)
  * the document score: mean of score_sentence() over sentences, rounded to six
    decimals (plef_core.py line 609)

and then:

  1. ASSERTS that the recomputed score equals sentiment_mean stored in
     results/canonical/scored_<corpus>.csv for every document. If any differ
     the script prints how many, writes nothing, and exits with code 3.
  2. Classifies each document:
       nomatch   no lexicon term matched (includes documents with no sentence)
       cancel    at least one match, document score exactly 0
       nonzero   document score not 0
  3. Writes results/tables/match_counts_<corpus>.csv, one row per document.
  4. Writes results/tables/abstention_v2.csv, one row per corpus:
       class counts and percentages; "fires" under the published definition
       (score != 0) and the Table 6 definition (>= 1 match), over all documents
       and, as Table 6 computes it, over the labelled documents only
       (fires_*_pct_labelled); macro-F1 of PLEF
       and VADER on all documents, the fired-by-score subset and the
       fired-by-match subset, each with a 2,000-resample bootstrap 95% interval
       computed by the same confusion-matrix bootstrap as 06_statistics.py
       (seed 42); and the Fig. 1b length-band percentages under both
       definitions. Six further rows, min_eight/max_eight, min_three/max_three
       and min_two/max_two, give each column's range over the eight evaluation
       corpora, the three-class corpora and the two-class corpora.
  5. Prints the published Table 6 (results/tables/abstention.csv and
     abstention_binary.csv) and Fig. 1b (length_threshold.csv) beside the
     recomputed values, so the reproduction is checked before anything new is
     read.

Decision rules are those of 06_statistics.py, copied, not re-derived:
  three-class  score > +0.05 pos, < -0.05 neg, otherwise neu; missing -> neu
               (06_statistics.py lines 132-133, 1242-1245)
  two-class    score > 0 pos, otherwise neg (zero included); missing -> neg
               (06_statistics.py lines 136-137, 720-722)

WHAT THE RESULT MEANS
---------------------
  reproduction OK   the published Table 6 / Fig. 1b numbers are what this code
                    computes under the published (score != 0) definition, so
                    the new columns differ from them only by the definition
  cancel = 0        on that corpus the two definitions coincide
  cancel > 0        Table 6's caption is wrong for that corpus by that many
                    documents; the fired-by-match columns are the ones that
                    match the caption

Standard library only. Deterministic: fixed bootstrap seeds, results ordered
by corpus and by input row. Writes only the files named above and its console
log results/forensics/console_log_18.txt.

USAGE
-----
  python 18_match_counts.py --root <path to PLEF_V2>   [--workers N]
"""
import argparse
import collections
import csv
import datetime
import hashlib
import importlib.util
import math
import os
import random
import statistics
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

sys.dont_write_bytecode = True          # never write __pycache__ into src/
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

VERSION = "1.1.0"
LEXICON_SHA256 = "18294c6727f66003df67c0c01ab9e66073dca34d3c60541878c35ba84825165c"
BOOT_N = 2000
THRESH = 0.05
CORPORA = ["dailydialog", "empathetic", "goemotions", "isear", "meld",
           "relationship", "semeval2017", "tweeteval", "dev_relationship"]
THREE = ["goemotions", "semeval2017", "meld", "tweeteval", "dailydialog"]
BINARY = ["isear", "empathetic"]
BANDS = [(1, 9), (10, 19), (20, 39), (40, 79), (80, 159), (160, 319), (320, 10**9)]
CHUNK = 500


# --------------------------------------------------------------------------
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
        self.stdout.flush()
        self.f.flush()

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


def rule(ch="-", w=94):
    print(ch * w)


def head(t):
    print()
    rule("=")
    print(t)
    rule("=")


def sub(t):
    print()
    print(t)
    rule()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def f(v):
    try:
        v = (v or "").strip()
        return float(v) if v != "" else None
    except (TypeError, ValueError, AttributeError):
        return None


# ------------------------------------------------- decision rules (06, copied)
def lab3(s, t=THRESH):
    return "pos" if s > t else ("neg" if s < -t else "neu")


def lab2(s):
    return "pos" if s > 0 else "neg"


def predict(scores, two_class):
    if two_class:
        return [lab2(s) if s is not None else "neg" for s in scores]
    return [lab3(s) if s is not None else "neu" for s in scores]


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
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    if n > 200:
        v = rnd.gauss(n * p, math.sqrt(max(1e-12, n * p * (1 - p))))
        return max(0, min(n, int(round(v))))
    return sum(1 for _ in range(n) if rnd.random() < p)


def _multinomial(n, probs, rnd):
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
    fs = []
    for c in classes:
        tp = cells.get((c, c), 0)
        fp = sum(cells.get((g, c), 0) for g in classes if g != c)
        fn = sum(cells.get((c, q), 0) for q in classes if q != c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(fs) / len(fs)


def boot_f1(gold, pred, classes, B=BOOT_N, seed=42):
    """06_statistics.boot_f1, verbatim in behaviour (same seed, same order)."""
    n = len(gold)
    if n < 2:
        return None, None
    cnt = collections.Counter(zip(gold, pred))
    keys = list(cnt)
    probs = [cnt[k] / n for k in keys]
    rnd = random.Random(seed)
    out = []
    for _ in range(B):
        out.append(_f1_from_cells(dict(zip(keys, _multinomial(n, probs, rnd))), classes))
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


# ---------------------------------------------------------------- workers
CORE = None
PHRASES = None


def load_core(src):
    lex = Path(src) / "plef_lexicons.json"
    if sha256(lex) != LEXICON_SHA256:
        raise RuntimeError(f"lexicon hash mismatch: {sha256(lex)}")
    spec = importlib.util.spec_from_file_location("plef_core_released",
                                                  str(Path(src) / "plef_core.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _init(src):
    global CORE, PHRASES
    sys.dont_write_bytecode = True
    CORE = load_core(src)
    PHRASES = [p for p in CORE.LEXICON if " " in p]


def _count_chunk(rows):
    out = []
    for pid, text in rows:
        sents = CORE.sentences(text)
        n_tok = tok_m = phr_m = zero_w = 0
        comps = []
        for s in sents:
            toks = CORE.tokenize(s)
            n_tok += len(toks)
            tl = s.lower()
            for t in toks:
                e = CORE.LEXICON.get(t)
                if e:
                    tok_m += 1
                    if e["s"] * e.get("i", 1.0) == 0:
                        zero_w += 1
            for p in PHRASES:
                if p in tl:
                    phr_m += 1
                    e = CORE.LEXICON[p]
                    if e["s"] * e.get("i", 1.0) == 0:
                        zero_w += 1
            comps.append(CORE.score_sentence(s)[0])
        score = round(statistics.mean(comps), 6) if comps else None
        out.append((pid, len(sents), n_tok, tok_m, phr_m, zero_w, score))
    return out


def _boot_job(job):
    key, gold, pred, classes = job
    m = macro_f1(gold, pred, classes) if gold else None
    lo, hi = boot_f1(gold, pred, classes) if len(gold) >= 2 else (None, None)
    return key, m, lo, hi, len(gold)


# ------------------------------------------------------------------ helpers
def read_rows(p):
    with open(p, encoding="utf-8-sig", errors="strict", newline="") as fh:
        return list(csv.DictReader(fh))


def corpus_file(root, c):
    d = Path(root) / "data" / "interim"
    return d / ("dev_split_relationship.csv" if c == "dev_relationship" else f"corpus_{c}.csv")


def classify(m, score):
    if m == 0:
        return "nomatch"
    if score is not None and score == 0.0:
        return "cancel"
    if score is None:
        return "nomatch"
    return "nonzero"


def fmt(v, d=4):
    return "" if v is None else f"{v:.{d}f}"


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 18 -- lexicon match counts.")
    ap.add_argument("--root", required=True, help="path to PLEF_V2")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count()))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    src = root / "src"
    tables = root / "results" / "tables"
    canon = root / "results" / "canonical"

    tee = Tee(root / "results" / "forensics" / "console_log_18.txt")
    sys.stdout = tee
    try:
        head(f"PLEF V2 -- SCRIPT 18 : LEXICON MATCH COUNTS   v{VERSION}")
        print(f"  root      : {root}")
        print(f"  started   : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  python    : {sys.version.split()[0]}   workers {a.workers}")
        print(f"  core      : {src / 'plef_core.py'}  sha256 {sha256(src / 'plef_core.py')}")
        rel_core = root / "release" / "src" / "plef_core.py"
        if rel_core.exists():
            same = sha256(rel_core) == sha256(src / "plef_core.py")
            print(f"  release/src/plef_core.py byte-identical to src/: {same}")
        print(f"  lexicon   : sha256 {sha256(src / 'plef_lexicons.json')} "
              f"(required {LEXICON_SHA256[:8]}...{LEXICON_SHA256[-6:]})")
        core = load_core(src)
        n_phr = sum(1 for k in core.LEXICON if " " in k)
        n_zero = sum(1 for e in core.LEXICON.values() if e["s"] * e.get("i", 1.0) == 0)
        print(f"  lexicon   : {len(core.LEXICON)} entries, {n_phr} multi-word, "
              f"{n_zero} with s*i == 0")

        # ---------------------------------------------------------- A. count
        sub("A  RECOUNT EVERY DOCUMENT AND CHECK THE STORED SCORE")
        per = {}
        mismatches = {}
        with Pool(a.workers, initializer=_init, initargs=(str(src),)) as pool:
            for c in CORPORA:
                cf, sf = corpus_file(root, c), canon / f"scored_{c}.csv"
                if not cf.exists() or not sf.exists():
                    print(f"  {c:<17} MISSING {cf if not cf.exists() else sf}")
                    return 2
                texts = read_rows(cf)
                scored = {r["id"]: r for r in read_rows(sf)}
                chunks = [[(r["id"], r["text"]) for r in texts[i:i + CHUNK]]
                          for i in range(0, len(texts), CHUNK)]
                res = [x for ch in pool.map(_count_chunk, chunks) for x in ch]
                bad, nostore, nw_diff = [], 0, 0
                rows = []
                for (pid, ns, ntok, tm, pm, zw, score), t in zip(res, texts):
                    s = scored.get(pid)
                    if s is None:
                        nostore += 1
                        continue
                    stored = f(s.get("sentiment_mean"))
                    if (stored is None) != (score is None) or \
                            (stored is not None and abs(stored - score) > 5e-7):
                        bad.append((pid, stored, score))
                    nwords = f(s.get("n_words"))
                    if nwords is not None and int(nwords) != ntok:
                        nw_diff += 1
                    m = tm + pm
                    rows.append({"id": pid, "n_sents": ns,
                                 "n_words": "" if nwords is None else int(nwords),
                                 "n_tokens": ntok, "token_matches": tm,
                                 "phrase_matches": pm,
                                 "score": "" if score is None else f"{score:.6f}",
                                 "class": classify(m, score),
                                 "_zero_weight_only": m > 0 and zw == m,
                                 "_gold": s.get("gold", ""),
                                 "_vader": f(s.get("b_vader")),
                                 "_score": score, "_m": m,
                                 "_nw": nwords})
                per[c] = rows
                if bad:
                    mismatches[c] = bad
                print(f"  {c:<17} docs {len(texts):>7,}  scored {len(scored):>7,}  "
                      f"not in scored file {nostore}  score mismatches {len(bad)}  "
                      f"n_words != recount {nw_diff}")
        if mismatches:
            print()
            print(f"  STOP: {sum(len(v) for v in mismatches.values()):,} documents whose "
                  f"recomputed score differs from sentiment_mean. Nothing written.")
            for c, v in mismatches.items():
                for pid, st, sc in v[:5]:
                    print(f"    {c}: {pid} stored {st} recomputed {sc}")
            return 3
        print("  every recomputed score equals the stored sentiment_mean.")

        # ---------------------------------------------------------- B. classes
        sub("B  CLASSES: nomatch / cancel / nonzero")
        print(f"  {'corpus':<17}{'docs':>8}{'nomatch':>16}{'cancel':>14}{'nonzero':>16}"
              f"{'fires(score)':>14}{'fires(match)':>14}{'0-weight only':>15}")
        rule()
        summ = {}
        for c in CORPORA:
            rows = per[c]
            n = len(rows)
            cnt = collections.Counter(r["class"] for r in rows)
            fs = sum(1 for r in rows if r["_score"] not in (None, 0.0))
            fm = sum(1 for r in rows if r["_m"] > 0)
            zw = sum(1 for r in rows if r["_zero_weight_only"])
            s = {"corpus": c, "n_docs": n}
            for k in ("nomatch", "cancel", "nonzero"):
                s[f"n_{k}"] = cnt[k]
                s[f"pct_{k}"] = round(100 * cnt[k] / n, 3)
            s["n_fires_score"], s["fires_score_pct"] = fs, round(100 * fs / n, 3)
            s["n_fires_match"], s["fires_match_pct"] = fm, round(100 * fm / n, 3)
            s["n_cancel_zero_weight_only"] = zw
            summ[c] = s
            print(f"  {c:<17}{n:>8,}{cnt['nomatch']:>8,} {100*cnt['nomatch']/n:5.1f}%"
                  f"{cnt['cancel']:>7,} {100*cnt['cancel']/n:4.2f}%"
                  f"{cnt['nonzero']:>8,} {100*cnt['nonzero']/n:5.1f}%"
                  f"{100*fs/n:>13.2f}%{100*fm/n:>13.2f}%{zw:>15,}")
        print("  0-weight only: documents whose every match has s*i == 0, so they")
        print("  are 'cancel' without any cancellation; counted inside 'cancel'.")

        # ---------------------------------------------------------- C. F1
        sub("C  MACRO-F1, PLEF AND VADER, THREE SUBSETS, BOOTSTRAP 95% CI")
        jobs = []
        for c in THREE + BINARY:
            two = c in BINARY
            classes = ["pos", "neg"] if two else ["pos", "neu", "neg"]
            rows = [r for r in per[c] if r["_gold"] in classes]
            subsets = {
                "all": rows,
                "fired_score": [r for r in rows if r["_score"] is not None and r["_score"] != 0.0],
                "fired_match": [r for r in rows if r["_m"] > 0],
            }
            for sname, sr in subsets.items():
                gold = [r["_gold"] for r in sr]
                for sysname, col in (("plef", "_score"), ("vader", "_vader")):
                    jobs.append(((c, sysname, sname), gold,
                                 predict([r[col] for r in sr], two), classes))
        with Pool(a.workers) as pool:
            fres = pool.map(_boot_job, jobs)
        for (c, sysname, sname), m, lo, hi, n in fres:
            s = summ[c]
            s[f"n_{sname}"] = n
            s[f"{sysname}_{sname}_f1"] = fmt(m, 6)
            s[f"{sysname}_{sname}_lo"] = fmt(lo, 6)
            s[f"{sysname}_{sname}_hi"] = fmt(hi, 6)
        for c in THREE + BINARY:
            s = summ[c]
            for sname in ("all", "fired_score", "fired_match"):
                p, v = f(s[f"plef_{sname}_f1"]), f(s[f"vader_{sname}_f1"])
                s[f"delta_{sname}"] = fmt(p - v if p is not None and v is not None else None, 6)
            s["fires_score_pct_labelled"] = round(100 * s["n_fired_score"] / s["n_all"], 3)
            s["fires_match_pct_labelled"] = round(100 * s["n_fired_match"] / s["n_all"], 3)
        print(f"  {'corpus':<13}{'subset':<13}{'n':>8}  {'PLEF [95% CI]':<26}"
              f"{'VADER [95% CI]':<26}{'delta':>8}")
        rule()
        for c in THREE + BINARY:
            s = summ[c]
            for sname in ("all", "fired_score", "fired_match"):
                print(f"  {c:<13}{sname:<13}{s['n_' + sname]:>8,}  "
                      f"{s['plef_' + sname + '_f1']} [{s['plef_' + sname + '_lo']}, "
                      f"{s['plef_' + sname + '_hi']}]  "
                      f"{s['vader_' + sname + '_f1']} [{s['vader_' + sname + '_lo']}, "
                      f"{s['vader_' + sname + '_hi']}]  {s['delta_' + sname]:>8}")

        # ---------------------------------------------------------- D. bands
        sub("D  FIG. 1b LENGTH BANDS: % OF DOCUMENTS PRODUCING A SIGNAL")
        print("  bands on stored n_words, bins with fewer than 20 documents blank,")
        print("  exactly as 06_statistics.B_length (lines 327-358)")
        for c in CORPORA:
            for lo_, hi_ in BANDS:
                tag = f"{lo_}_{hi_}"
                sel = [r for r in per[c] if r["_nw"] is not None and lo_ <= r["_nw"] <= hi_]
                if len(sel) < 20:
                    summ[c][f"band_{tag}_score"] = ""
                    summ[c][f"band_{tag}_match"] = ""
                    continue
                summ[c][f"band_{tag}_score"] = round(
                    100 * sum(1 for r in sel if r["_score"] not in (None, 0.0)) / len(sel), 1)
                summ[c][f"band_{tag}_match"] = round(
                    100 * sum(1 for r in sel if r["_m"] > 0) / len(sel), 1)

        # ---------------------------------------------------------- E. checks
        sub("E  REPRODUCTION OF THE PUBLISHED TABLE 6 AND FIG. 1b")
        ok_all = True
        pub = {}
        for fn in ("abstention.csv", "abstention_binary.csv"):
            p = tables / fn
            if p.exists():
                for r in read_rows(p):
                    pub[r["corpus"]] = r
        print(f"  {'corpus':<13}{'item':<12}{'published':>11}{'recomputed':>12}  check")
        rule()
        for c in THREE + BINARY:
            if c not in pub:
                print(f"  {c:<13}not in the published tables")
                ok_all = False
                continue
            r, s = pub[c], summ[c]
            pairs = [("fires %", f(r["fires_pct"]), s["fires_score_pct_labelled"], 0.01),
                     ("PLEF all", f(r["plef_all"]), f(s["plef_all_f1"]), 1e-4),
                     ("VADER all", f(r["vader_all"]), f(s["vader_all_f1"]), 1e-4),
                     ("PLEF fired", f(r["plef_fires"]), f(s["plef_fired_score_f1"]), 1e-4),
                     ("VADER fired", f(r["vader_fires"]), f(s["vader_fired_score_f1"]), 1e-4),
                     ("delta", f(r["delta"]), f(s["delta_fired_score"]), 2e-4)]
            for lab, pv, rv, tol in pairs:
                ok = pv is not None and rv is not None and abs(pv - rv) <= tol
                ok_all &= ok
                print(f"  {c:<13}{lab:<12}{fmt(pv):>11}{fmt(rv):>12}  {'OK' if ok else 'DIFFERS'}")
        lt = tables / "length_threshold.csv"
        if lt.exists():
            print()
            print(f"  {'corpus':<17}{'band':<14}{'published':>10}{'score!=0':>10}{'>=1 match':>11}  check")
            rule()
            for r in read_rows(lt):
                c = r["corpus"]
                if c not in summ:
                    continue
                for lo_, hi_ in BANDS:
                    tag = f"{lo_}_{hi_}"
                    pv = f(r.get(tag))
                    rv = summ[c][f"band_{tag}_score"]
                    rv = None if rv == "" else rv
                    if pv is None and rv is None:
                        continue
                    ok = pv is not None and rv is not None and abs(pv - rv) < 0.051
                    ok_all &= ok
                    mv = summ[c][f"band_{tag}_match"]
                    print(f"  {c:<17}{tag.replace('_1000000000', '+'):<14}"
                          f"{'' if pv is None else pv:>10}{'' if rv is None else rv:>10}"
                          f"{mv:>11}  {'OK' if ok else 'DIFFERS'}")
        print()
        print(f"  REPRODUCTION: {'OK -- published values recomputed exactly' if ok_all else 'DIFFERENCES ABOVE -- inspect before using the new columns'}")
        for lab, tag in (("1-9 words", "1_9"), ("80-159 words", "80_159")):
            for d in ("score", "match"):
                v = [summ[c][f"band_{tag}_{d}"] for c in CORPORA
                     if c != "dev_relationship" and summ[c][f"band_{tag}_{d}"] != ""]
                if v:
                    print(f"  range over the eight corpora, {lab:<13} {d:<6}: "
                          f"{min(v):.1f}-{max(v):.1f}%")

        # ---------------------------------------------------------- F. write
        sub("F  WRITING")
        tables.mkdir(parents=True, exist_ok=True)
        cols = ["id", "n_sents", "n_words", "n_tokens", "token_matches",
                "phrase_matches", "score", "class"]
        for c in CORPORA:
            p = tables / f"match_counts_{c}.csv"
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(per[c])
            print(f"  {p}  ({len(per[c]):,} rows)")
        keys = []
        for c in CORPORA:
            for k in summ[c]:
                if k not in keys:
                    keys.append(k)
        # range rows, so that every "a-b%" statement in the text has a source
        ranges = []
        for tag, group in (("eight", [c for c in CORPORA if c != "dev_relationship"]),
                           ("three", THREE), ("two", BINARY)):
            for fn_, lab in ((min, "min"), (max, "max")):
                row = {"corpus": f"{lab}_{tag}"}
                for k in keys[1:]:
                    vals = [f(str(summ[c].get(k, ""))) for c in group]
                    vals = [v for v in vals if v is not None]
                    row[k] = "" if not vals else (fmt(fn_(vals), 6) if any(
                        isinstance(summ[c].get(k), str) for c in group) else fn_(vals))
                ranges.append(row)
        p = tables / "abstention_v2.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, restval="")
            w.writeheader()
            for c in CORPORA:
                w.writerow(summ[c])
            w.writerows(ranges)
        print(f"  {p}  ({len(CORPORA)} corpus rows + {len(ranges)} range rows "
              f"min_/max_ over eight, three, two; {len(keys)} columns)")
        print(f"  columns: {', '.join(keys)}")
        head("DONE")
        return 0 if ok_all else 4
    finally:
        print(f"  finished  : {datetime.datetime.now().isoformat(timespec='seconds')}")
        sys.stdout = tee.stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(main())
