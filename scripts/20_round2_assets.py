#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 20 : ROUND-2 ASSETS   (20_round2_assets.py, v1.2.0)
===============================================================================

CHANGES IN v1.2.0
-----------------
  * Stage 4: the draft Methods sentence no longer contains a typed-in post
    count. The count is the number of rows of corpus_relationship.csv plus the
    rows of dev_split_relationship.csv. The two id sets must be disjoint
    (exit 3 if not). If the sum differs from the 1,508 stated in the
    manuscript (section 2.2), both counts and the sum are printed and the
    draft sentence is not emitted.
  * Stage 5: the test of whether an evaluation post's fingerprint occurs in an
    annotation-development post's text pads both the fingerprint and the text
    with a leading and a trailing space, so a 12-word match is always on whole
    words and cannot run across a word boundary.

CHANGES IN v1.1.0
-----------------
  * Stage 3 crashed in v1.0.0 with KeyError 'impl_diff'. The cause was not a
    missing column: annotation_audit_v2.csv has every column stage 3 reads.
    Stage 3 appended each summary row to the same list it was counting over,
    so the second count reached a summary row, which has no per-post
    difference. Post rows and summary rows are now kept in separate lists and
    the counts run over post rows only.
  * Stage 3 DERIVES, per post and per alignment, four columns that are not in
    annotation_audit_v2.csv:
        <a>_human   impl, plus1: h_disp        full: h_sent
        <a>_metric  impl: lewi_zero_based      plus1, full: lewi_one_based
        <a>_diff    <a>_metric - <a>_human     (signed, in sentences)
        <a>_match   exact / within1 / within2 / offN from |<a>_diff|
    from the file's columns h_disp, h_sent, lewi_zero_based, lewi_one_based;
    <a>_match is then checked against the file's match_impl, match_plus1,
    match_full, and lewi_one_based against lewi_zero_based + 1.
  * New stage 0 validates every input before anything runs: each CSV must
    have every column the script indexes, human_criterion_v2.csv every key
    stages 2 and 3 read, and the optional Old/PLEF provenance files, if
    present, their id and subreddit columns. A missing file, column or key
    exits with code 2 and names it. Every column the script indexes was checked
    against the actual headers of the committed inputs when v1.1.0 was written;
    there were no other mismatches.

WHAT THIS DOES (plain language)
-------------------------------
Builds the figures and supplementary tables that the second revision needs,
from the outputs of scripts 18 and 19. Nothing those scripts produced is
recomputed here; this script reads their tables, checks them, and lays them
out. It also answers two provenance questions that no earlier script logged.

  1. FIGURES. Fig. 1 redrawn as results/figures/fig1_coverage_scope_v2.png:
     panel (a) unchanged, from the published results/tables/coverage.csv;
     panel (b) with two line styles per corpus, documents with a non-zero
     score (the published definition) and documents with at least one lexicon
     match (the Table 6 definition), from abstention_v2.csv. Fig. 4 redrawn as
     fig4_gase_abstention_v2.png: panel (a) unchanged, from the published
     gase_ablation.csv; panel (b) with the fired-by-match point beside the
     fired-by-score point for every corpus. Same size (7.2 x 2.7 in, 300 dpi,
     2160 x 810 px) as the published PNGs. BEFORE drawing, the published
     Table 6 (abstention.csv, abstention_binary.csv) and Fig. 1b
     (length_threshold.csv) values are checked against the score-based
     columns of abstention_v2.csv, and the class counts of abstention_v2.csv
     against the per-document match_counts_*.csv. Any difference stops the
     script before a figure is written (exit 3).

  2. results/tables/supp_annotation_intervals.csv: every proportion of
     Table 9 and Section 3.6, with k, n, the proportion, its Wilson 95%
     interval, its chance benchmark and the ratio, one row per quantity, in a
     Table 9 block, a Section 3.6 block, a per-pair block and a per-rater
     block. All values are read from human_criterion_v2.csv; each k/n and
     interval is checked against its own row (exit 3 on mismatch).

  3. results/tables/supp_alignment_comparison.csv: the 19 round-4 comparison
     posts from annotation_audit_v2.csv with the three alignments side by side
     (as implemented, +1 only, +1 with the displayed-line-to-sentence map) and
     a summary block: exact / within-one / within-two counts, Wilson intervals,
     chance means, expected counts and Poisson-binomial P(X >= observed) and
     P(X <= observed), read from human_criterion_v2.csv. It shows why
     Reviewer 3's +1 gives 2 exact matches and the verified map gives 1: on
     one post the displayed line the annotator chose is a later line than its
     sentence number.

  4. THE EIGHTH SUBREDDIT. Reads the two collection scripts at the
     pre-revision tag of the release repository (git show, read-only, no
     optional locks) and lists every subreddit each queries. Counts the ids of
     the 1,308-post corpus and the 200-post dev split by subreddit prefix and
     counts the ids with no prefix. For unprefixed ids it looks for evidence
     of origin in the original collection outputs under Old/PLEF (read as
     data only; no Old code is run), after checking by SHA-256 against
     MANIFEST/corpora.json that they are the files 03_dataset_rebuild.py read:
       - a per-subreddit file Old/PLEF/corpus_<sub>.csv holding the id as
         "<sub>_<id>"
       - Old/PLEF/relationship_corpus_FULL.csv, whose rows carry a subreddit
       - Old/PLEF/reddit_raw.json and reddit_posts/<id>.txt, the outputs of
         reddit_download.py, whose subreddit is a constant in that script
     It reports whether any post can be attributed to r/NarcissisticAbuse,
     how many unprefixed ids can be attributed and on what evidence, and
     prints what the Methods paragraph can truthfully say.
     Writes results/tables/supp_corpus_sources.csv.

  5. RELEASED TEXT OVERLAP. Reproduces, in a forensics log, the count of
     relationship posts whose text appears in the release working tree, by
     the method of round2_audit/r2d_release_text.py: for each of the 1,508
     posts, the first 12 words ([a-z0-9']+, lower-case) of up to three
     sentences of >= 12 words (released core's splitter); a file contains a
     post if one of that post's fingerprints occurs as a contiguous word
     sequence. For every evaluation-set post found, the dev posts whose text
     contains the fingerprint are listed. Reads PLEF_V2/release read-only and
     writes nothing there. Writes results/tables/supp_released_text_overlap.csv.

  6. Lists every placeholder in paper/round2/MANUSCRIPT_CHANGES_ROUND2.md that
     the tables now resolve, with its value, and every one still unresolved.

WHAT THE RESULT MEANS
---------------------
  exit 0  every check passed; figures and tables written
  exit 2  a required input file, column or key is missing (stage 0 names it)
  exit 3  an internal check failed (published values not reproduced, a k/n or
          interval inconsistent, a match type inconsistent); nothing past the
          failing stage is written
  exit 5  everything written, but stage 5 did not reproduce the audit's
          counts (210 posts: 200 dev, 10 evaluation); read the log

DEPENDENCIES
------------
Standard library, plus matplotlib for the two figures (the evaluation harness
already requires it; the framework core never does). Imports the released core
from src/ without writing bytecode, for its sentence splitter only. Calls git
read-only. Deterministic: no randomness; all outputs sorted.

Writes only: results/figures/fig1_coverage_scope_v2.png,
results/figures/fig4_gase_abstention_v2.png, the four supp_*.csv tables, and
results/forensics/console_log_20.txt.

USAGE
-----
  python 20_round2_assets.py --root <path to PLEF_V2>   [--workers N]
"""
import argparse
import collections
import csv
import datetime
import hashlib
import importlib.util
import io
import json
import math
import re
import subprocess
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

sys.dont_write_bytecode = True
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

VERSION = "1.2.0"
LEXICON_SHA256 = "18294c6727f66003df67c0c01ab9e66073dca34d3c60541878c35ba84825165c"
MANUSCRIPT_COLLECTION_N = 1508          # manuscript section 2.2, "1,508-post collection"
EIGHT = ["dailydialog", "empathetic", "goemotions", "isear", "meld",
         "relationship", "semeval2017", "tweeteval"]
THREE = ["goemotions", "semeval2017", "meld", "tweeteval", "dailydialog"]
BINARY = ["isear", "empathetic"]
# panel (a) order of the published Fig. 1, and the five bands it shows
FIG1A_ORDER = ["semeval2017", "tweeteval", "meld", "dailydialog", "isear",
               "relationship", "empathetic", "goemotions"]
FIG1B_BANDS = [("1_9", "1-9"), ("10_19", "10-19"), ("20_39", "20-39"),
               ("40_79", "40-79"), ("80_159", "80-159")]
COLOURS = {"dailydialog": "#2b6cb0", "empathetic": "#c05621", "goemotions": "#2f855a",
           "isear": "#6b46c1", "meld": "#b83280", "relationship": "#4a5568",
           "semeval2017": "#975a16", "tweeteval": "#3182ce"}
PAIRS = ["1v2", "1v3", "2v3"]
CONV = [("impl", "as implemented (stored line vs zero-based index)"),
        ("plus1", "+1 only (stored line vs one-based index)"),
        ("full", "+1 and displayed line mapped to its sentence")]
AUDIT_EXPECTED = {"posts": 210, "dev": 200, "evaluation": 10}
K = 12


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


class CheckFailed(Exception):
    pass


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_csv(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        return list(csv.DictReader(io.StringIO(txt, newline="")))
    raise RuntimeError(f"cannot decode {p}")


def f(v):
    try:
        v = ("" if v is None else str(v)).strip()
        return float(v) if v != "" else None
    except ValueError:
        return None


def wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path}  ({len(rows)} rows)")


def load_core(src):
    if sha256_file(Path(src) / "plef_lexicons.json") != LEXICON_SHA256:
        raise RuntimeError("lexicon hash mismatch")
    spec = importlib.util.spec_from_file_location("plef_core_released",
                                                  str(Path(src) / "plef_core.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ workers
def _class_counts(path):
    cnt = collections.Counter()
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            cnt[r["class"]] += 1
    return str(path), dict(cnt)


WORD = re.compile(r"[a-z0-9']+")
FP = None


def _init_fp(fp):
    global FP
    FP = collections.defaultdict(lambda: collections.defaultdict(set))
    for pid, words in fp:
        FP[words[0]][tuple(words)].add(pid)


def _hits(job):
    label, data = job
    if data is None:
        data = Path(label).read_bytes()
    try:
        t = data.decode("utf-8")
    except UnicodeDecodeError:
        t = data.decode("latin-1")
    w = WORD.findall(t.lower())
    found = collections.defaultdict(set)          # post id -> fingerprints seen
    for i, x in enumerate(w):
        d = FP.get(x)
        if d:
            key = tuple(w[i:i + K])
            for pid in d.get(key, ()):
                found[pid].add(key)
    return label, {p: sorted(v) for p, v in found.items()}


# ================================================================ stage 0
def required_hc_keys():
    """Every human_criterion_v2.csv key that stages 2 and 3 read."""
    keys = []
    for c, _ in CONV:
        for m in ("exact", "within1", "within2"):
            keys += [f"{m}_{c}", f"chance_{m}_mean_{c}", f"expected_{m}_{c}",
                     f"p_ge_{m}_{c}", f"p_le_{m}_{c}"]
    keys += ["r4_no_tp_prop", "arc_agreement", "arc_majority_baseline",
             "r3_unanimous_tp_3way", "r3_majority_tp_3way", "round1_chance_same_sentence_n",
             "gap_all_rounds_under41", "repeat_fraction_round3", "repeat_fraction_round4"]
    for p in PAIRS:
        keys += [f"round1_tp_identical_{p}", f"r3_raw_{p}", f"r3_existence_{p}",
                 f"r3_existence_chance_{p}", f"r3_location_{p}"]
        for ck in ("n", "n2", "emp_loo"):
            keys += [f"r3_location_chance_{ck}_{p}", f"r3_location_ratio_{ck}_{p}"]
    for rnd, raters in ((3, (1, 2, 3)), (4, (1,))):
        for r in raters:
            for fld in ("sentiment", "arc", "tp", "tp_within1"):
                keys.append(f"rep_round{rnd}_rater{r}_{fld}")
    return keys


def stage0_validate(root):
    """Open every input and check every column (and key) the script uses."""
    sub("0  INPUT VALIDATION: FILES, COLUMNS, KEYS")
    t = root / "results" / "tables"
    bands = [tag for tag, _ in FIG1B_BANDS]
    req = {
        t / "abstention_v2.csv": ["corpus", "n_nomatch", "n_cancel", "n_nonzero",
                                  "fires_score_pct_labelled", "fires_match_pct_labelled",
                                  "plef_all_f1", "vader_all_f1", "plef_fired_score_f1",
                                  "vader_fired_score_f1", "delta_fired_score", "delta_fired_match"]
                                 + [f"band_{b}_{k}" for b in bands for k in ("score", "match")],
        t / "abstention.csv": ["corpus", "fires_pct", "plef_all", "vader_all", "plef_fires",
                               "vader_fires", "delta"],
        t / "abstention_binary.csv": ["corpus", "fires_pct", "plef_all", "vader_all", "plef_fires",
                                      "vader_fires", "delta"],
        t / "length_threshold.csv": ["corpus"] + bands,
        t / "coverage.csv": ["corpus", "PLEF", "vader"],
        t / "gase_ablation.csv": ["corpus", "sd_S", "sd_H", "sd_A", "sd_G"],
        t / "human_criterion_v2.csv": ["key", "value", "k", "n", "wilson_lo", "wilson_hi"],
        t / "annotation_audit_v2.csv": ["id", "N", "N_disp", "h_disp", "h_sent", "lewi_zero_based",
                                        "lewi_one_based", "boundary_sent", "match_impl",
                                        "match_plus1", "match_full"],
        root / "data" / "interim" / "corpus_relationship.csv": ["id", "text"],
        root / "data" / "interim" / "dev_split_relationship.csv": ["id", "text"],
    }
    for c in EIGHT + ["dev_relationship"]:
        req[t / f"match_counts_{c}.csv"] = ["class"]
    old = root.parent.parent / "Old" / "PLEF"
    optional = {}
    if old.exists():
        for p in sorted(old.glob("corpus_*.csv")):
            optional[p] = ["id", "subreddit"]
        for n in ("reddit_posts_corpus.csv", "relationship_corpus_FULL.csv"):
            optional[old / n] = ["id", "subreddit"]
    problems = []
    for path, cols in list(req.items()) + list(optional.items()):
        if not path.exists():
            if path in req:
                problems.append(f"{path}: file missing")
            continue
        raw = path.read_bytes()[:1 << 16]
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                first = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        hdr = next(csv.reader(io.StringIO(first, newline="")), [])
        miss = [c for c in cols if c not in hdr]
        for c in miss:
            problems.append(f"{path}: missing column '{c}'")
        print(f"  {'OK ' if not miss else 'BAD'} {path.relative_to(root.parent.parent)}  "
              f"({len(cols)} columns used)")
    raw_json = old / "reddit_raw.json"
    if raw_json.exists():
        try:
            d = json.loads(raw_json.read_text(encoding="utf-8"))
            if not (isinstance(d, list) and d and "id" in d[0]):
                problems.append(f"{raw_json}: not a list of records with an 'id' field")
        except ValueError as e:
            problems.append(f"{raw_json}: unreadable JSON ({e})")
    hcp = t / "human_criterion_v2.csv"
    if hcp.exists():
        have = {r["key"] for r in read_csv(hcp)}
        for k in required_hc_keys():
            if k not in have:
                problems.append(f"{hcp}: missing key '{k}'")
        print(f"  human_criterion_v2.csv: {len(required_hc_keys())} keys required")
    if not (root / "release").exists():
        problems.append(f"{root / 'release'}: release working tree missing")
    man = root / "MANIFEST" / "corpora.json"
    if not man.exists():
        problems.append(f"{man}: file missing")
    md = root / "paper" / "round2" / "MANUSCRIPT_CHANGES_ROUND2.md"
    if not md.exists():
        print(f"  note: {md} absent; stage 6 will report nothing")
    if problems:
        print()
        for x in problems:
            print(f"  MISSING  {x}")
    else:
        print("  every input file, column and key present")
    return problems


# ================================================================ stage 1
def stage1_checks_and_figures(root, a, pool):
    tables = root / "results" / "tables"
    sub("1a  CHECK: abstention_v2.csv REPRODUCES THE PUBLISHED TABLE 6 AND FIG. 1b")
    ab = {r["corpus"]: r for r in read_csv(tables / "abstention_v2.csv")}
    pub = {}
    for fn in ("abstention.csv", "abstention_binary.csv"):
        for r in read_csv(tables / fn):
            pub[r["corpus"]] = r
    bad = 0
    pairs = (("fires_pct", "fires_score_pct_labelled", 0.01),
             ("plef_all", "plef_all_f1", 1e-4), ("vader_all", "vader_all_f1", 1e-4),
             ("plef_fires", "plef_fired_score_f1", 1e-4),
             ("vader_fires", "vader_fired_score_f1", 1e-4),
             ("delta", "delta_fired_score", 2e-4))
    for c in THREE + BINARY:
        for pk, vk, tol in pairs:
            pv, vv = f(pub[c][pk]), f(ab[c][vk])
            ok = pv is not None and vv is not None and abs(pv - vv) <= tol
            bad += not ok
            if not ok:
                print(f"  DIFFERS {c} {pk}: published {pv} abstention_v2 {vv}")
    print(f"  Table 6: {len(THREE + BINARY) * len(pairs) - bad} of "
          f"{len(THREE + BINARY) * len(pairs)} values reproduced")
    lt = {r["corpus"]: r for r in read_csv(tables / "length_threshold.csv")}
    nb = 0
    for c in EIGHT:
        for tag, _ in FIG1B_BANDS:
            pv, vv = f(lt[c].get(tag)), f(ab[c].get(f"band_{tag}_score"))
            if pv is None and vv is None:
                continue
            nb += 1
            ok = pv is not None and vv is not None and abs(pv - vv) < 0.051
            bad += not ok
            if not ok:
                print(f"  DIFFERS {c} band {tag}: published {pv} abstention_v2 {vv}")
    print(f"  Fig. 1b: {nb} band values compared")

    sub("1b  CHECK: CLASS COUNTS IN abstention_v2.csv AGAINST match_counts_*.csv")
    paths = [tables / f"match_counts_{c}.csv" for c in EIGHT + ["dev_relationship"]]
    for p in paths:
        if not p.exists():
            print(f"  MISSING {p}")
            raise CheckFailed("match_counts file missing")
    for path, cnt in pool.map(_class_counts, [str(p) for p in paths]):
        c = Path(path).stem.replace("match_counts_", "")
        row = ab[c]
        for k in ("nomatch", "cancel", "nonzero"):
            ok = int(f(row[f"n_{k}"])) == cnt.get(k, 0)
            bad += not ok
            if not ok:
                print(f"  DIFFERS {c} {k}: abstention_v2 {row['n_' + k]} match_counts {cnt.get(k, 0)}")
        print(f"  {c:<17} nomatch {cnt.get('nomatch', 0):>7,}  cancel {cnt.get('cancel', 0):>5,}  "
              f"nonzero {cnt.get('nonzero', 0):>7,}")
    if bad:
        raise CheckFailed(f"{bad} published or internal values not reproduced; no figure drawn")
    print("  all checks passed; drawing")

    sub("1c  FIGURES")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    print(f"  matplotlib {matplotlib.__version__}")
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 300,
                         "savefig.dpi": 300})
    fd = root / "results" / "figures"
    fd.mkdir(parents=True, exist_ok=True)

    # ---- Fig. 1
    cov = {r["corpus"]: r for r in read_csv(tables / "coverage.csv")}
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(7.2, 2.7))
    x = list(range(len(FIG1A_ORDER)))
    axa.bar([i - 0.2 for i in x], [100 * f(cov[c]["PLEF"]) for c in FIG1A_ORDER], 0.4,
            color="#2b6cb0", label="PLEF (348 entries)")
    axa.bar([i + 0.2 for i in x], [100 * f(cov[c]["vader"]) for c in FIG1A_ORDER], 0.4,
            color="#718096", label="VADER (7,506 entries)")
    axa.set_xticks(x)
    axa.set_xticklabels(FIG1A_ORDER, rotation=35, ha="right", fontsize=6.5)
    axa.set_ylabel("tokens matched (%)")
    axa.set_title("(a) Lexicon coverage", loc="left")
    axa.legend(frameon=False, fontsize=6.5)
    for c in EIGHT:
        col = COLOURS[c]
        for kind, ls, mk in (("score", "-" if c == "relationship" else "--", "o"),
                             ("match", ":", "s")):
            xs, ys = [], []
            for i, (tag, _) in enumerate(FIG1B_BANDS):
                v = f(ab[c].get(f"band_{tag}_{kind}"))
                if v is not None:
                    xs.append(i)
                    ys.append(v)
            if xs:
                axb.plot(xs, ys, ls=ls, marker=mk, ms=2.6, lw=1.0, color=col, alpha=0.85,
                         mfc=col if kind == "score" else "none")
    axb.set_xticks(range(len(FIG1B_BANDS)))
    axb.set_xticklabels([lab for _, lab in FIG1B_BANDS])
    axb.set_xlabel("document length (words)")
    axb.set_ylabel("documents scored (%)")
    axb.set_title("(b) Where PLEF produces a signal", loc="left")
    h1 = [Line2D([], [], color=COLOURS[c], lw=1.2, label=c) for c in EIGHT]
    leg1 = axb.legend(handles=h1, frameon=False, fontsize=5.6, ncol=2, loc="upper left")
    axb.add_artist(leg1)
    h2 = [Line2D([], [], color="#333", ls="--", marker="o", ms=2.6, label="non-zero score"),
          Line2D([], [], color="#333", ls=":", marker="s", ms=2.6, mfc="none",
                 label=">= 1 lexicon match")]
    axb.legend(handles=h2, frameon=False, fontsize=5.6, loc="lower right")
    fig.tight_layout()
    p1 = fd / "fig1_coverage_scope_v2.png"
    fig.savefig(p1)
    plt.close(fig)
    print(f"  wrote {p1}")
    print("  CAPTION (b): Percentage of documents in each word-count band for which the")
    print("    framework returned a non-zero score (dashed; solid for the relationship")
    print("    corpus) and for which its lexicon matched at least one term (dotted, open")
    print("    markers). Matched terms can cancel, so the second is never below the first.")
    print("    Bands containing fewer than 20 documents are omitted.")

    # ---- Fig. 4
    gase = {r["corpus"]: r for r in read_csv(tables / "gase_ablation.csv")}
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(7.2, 2.7))
    comps = [("sd_S", "sd(S)", "#2b6cb0"), ("sd_H", "sd(H)", "#c05621"),
             ("sd_A", "sd(A)", "#2f855a"), ("sd_G", "sd(G)", "#6b46c1")]
    w = 0.2
    for j, (k, lab, col) in enumerate(comps):
        axa.bar([i + (j - 1.5) * w for i in range(len(EIGHT))],
                [f(gase[c][k]) for c in EIGHT], w, color=col, label=lab)
    axa.axhline(0.05, ls=":", color="k", lw=1)
    axa.text(len(EIGHT) - 0.6, 0.055, "0.05", fontsize=6.5)
    axa.set_xticks(range(len(EIGHT)))
    axa.set_xticklabels(EIGHT, rotation=35, ha="right", fontsize=6.5)
    axa.set_ylabel("component standard deviation")
    axa.set_title("(a) GASE component variability", loc="left")
    axa.legend(frameon=False, fontsize=6.5, ncol=2)
    for c in THREE + BINARY:
        xs, ys = f(ab[c]["fires_score_pct_labelled"]), f(ab[c]["delta_fired_score"])
        xm, ym = f(ab[c]["fires_match_pct_labelled"]), f(ab[c]["delta_fired_match"])
        col = "#2f855a" if ys > 0 else "#c05621"
        axb.plot([xs, xm], [ys, ym], color="#a0aec0", lw=0.8, zorder=1)
        axb.scatter([xs], [ys], s=22, color=col, zorder=2)
        axb.scatter([xm], [ym], s=22, facecolors="none", edgecolors=col, marker="s", zorder=2)
        axb.annotate(c, (xs, ys), xytext=(4, 4), textcoords="offset points", fontsize=6)
    axb.axhline(0, ls=":", color="k", lw=1)
    axb.set_xlabel("documents where PLEF fires (%)")
    axb.set_ylabel("macro-F1: PLEF $-$ VADER, on fired items")
    axb.set_title("(b) Accuracy where PLEF has evidence", loc="left")
    axb.legend(handles=[Line2D([], [], ls="", marker="o", color="#4a5568", label="fired: non-zero score"),
                        Line2D([], [], ls="", marker="s", mfc="none", color="#4a5568",
                               label="fired: >= 1 lexicon match")],
               frameon=False, fontsize=6, loc="center right")
    fig.tight_layout()
    p4 = fd / "fig4_gase_abstention_v2.png"
    fig.savefig(p4)
    plt.close(fig)
    print(f"  wrote {p4}")
    print("  CAPTION (b): Difference in macro-F1 between the framework and VADER on the")
    print("    fired documents, against the percentage fired; filled circles count a")
    print("    document as fired when its score is non-zero, open squares when its lexicon")
    print("    matched at least one term. Positive differences in green.")
    for c in THREE + BINARY:
        print(f"    {c:<12} score: fired {ab[c]['fires_score_pct_labelled']:>7}%  delta {ab[c]['delta_fired_score']:>8}"
              f"   match: fired {ab[c]['fires_match_pct_labelled']:>7}%  delta {ab[c]['delta_fired_match']:>8}")
    return ab


# ================================================================ stage 2/3
def load_hc(root):
    hc = {}
    for r in read_csv(root / "results" / "tables" / "human_criterion_v2.csv"):
        hc[r["key"]] = r
    bad = []
    for k, r in hc.items():
        kk, nn = f(r["k"]), f(r["n"])
        if kk is None or nn is None or nn == 0:
            continue
        v, lo, hi = f(r["value"]), f(r["wilson_lo"]), f(r["wilson_hi"])
        wl, wh = wilson(kk, nn)
        if v is None or lo is None or hi is None or abs(v - kk / nn) > 1e-6 \
                or abs(lo - wl) > 1e-6 or abs(hi - wh) > 1e-6:
            bad.append(k)
    return hc, bad


def stage2_intervals(root, hc):
    sub("2  SUPPLEMENTARY TABLE: ANNOTATION PROPORTIONS WITH INTERVALS")
    rows = []

    def add(block, section, quantity, key, chance_key=None, ratio_key=None):
        for kk_ in (key, chance_key, ratio_key):
            if kk_ and kk_ not in hc:
                raise CheckFailed(f"key {kk_} missing from human_criterion_v2.csv")
        r = hc[key]
        ch = f(hc[chance_key]["value"]) if chance_key else None
        prop = f(r["value"])
        if ratio_key:
            ratio, src = f(hc[ratio_key]["value"]), f"human_criterion_v2:{ratio_key}"
        elif ch:
            ratio, src = prop / ch, "proportion / chance"
        else:
            ratio, src = None, ""
        rows.append({"block": block, "section": section, "quantity": quantity, "key": key,
                     "k": r["k"], "n": r["n"], "proportion": r["value"],
                     "wilson_lo": r["wilson_lo"], "wilson_hi": r["wilson_hi"],
                     "chance": "" if ch is None else f"{ch:.6f}", "chance_key": chance_key or "",
                     "ratio": "" if ratio is None else f"{ratio:.4f}", "ratio_source": src})

    for c, lab in CONV:
        for m, mlab in (("exact", "exact sentence"), ("within1", "within one sentence"),
                        ("within2", "within two sentences")):
            add("table9", "Table 9 / 3.5", f"watershed {mlab}, {lab}", f"{m}_{c}",
                f"chance_{m}_mean_{c}")
    add("table9", "Table 9 / 3.5", "posts marked no turning point", "r4_no_tp_prop")
    add("table9", "Table 9 / 3.5", "arc agreement (chance = majority class)", "arc_agreement",
        "arc_majority_baseline")
    add("table9", "Table 9 / 3.5", "arc majority-class baseline", "arc_majority_baseline")
    add("section3.6", "3.6", "unanimous turning point, three-way posts", "r3_unanimous_tp_3way")
    add("section3.6", "3.6", "two-of-three majority, three-way posts", "r3_majority_tp_3way")
    for p in PAIRS:
        add("section3.6", "3.6", f"round 1 identical turning point, pair {p}",
            f"round1_tp_identical_{p}", "round1_chance_same_sentence_n")
    add("section3.6", "2.6", "repeat gaps under 41 items, rounds 3 and 4", "gap_all_rounds_under41")
    for rnd in (3, 4):
        add("section3.6", "2.6", f"repeat showings, round {rnd}", f"repeat_fraction_round{rnd}")
    for p in PAIRS:
        blk = f"pair_{p}"
        add(blk, "3.6", "raw agreement incl. shared no-turn (no single chance rate)", f"r3_raw_{p}")
        add(blk, "3.6", "existence agreement (marginal chance)", f"r3_existence_{p}",
            f"r3_existence_chance_{p}")
        add(blk, "3.6", "location agreement, chance 1/N", f"r3_location_{p}",
            f"r3_location_chance_n_{p}", f"r3_location_ratio_n_{p}")
        add(blk, "3.6", "location agreement, chance 1/(N-2) (submitted)", f"r3_location_{p}",
            f"r3_location_chance_n2_{p}", f"r3_location_ratio_n2_{p}")
        add(blk, "3.6", "location agreement, chance empirical (leave-one-out)", f"r3_location_{p}",
            f"r3_location_chance_emp_loo_{p}", f"r3_location_ratio_emp_loo_{p}")
    for rnd, raters in ((3, (1, 2, 3)), (4, (1,))):
        for r in raters:
            blk = f"rater_round{rnd}_{r}"
            for fld, lab in (("sentiment", "sentiment"), ("arc", "arc"), ("tp", "turning point exact"),
                             ("tp_within1", "turning point within one")):
                add(blk, "3.6", f"repeat agreement, {lab}", f"rep_round{rnd}_rater{r}_{fld}")
    print(f"  {'block':<17}{'quantity':<56}{'k/n':>8}  {'prop':>6}  {'95% CI':<14}{'chance':>8}{'ratio':>7}")
    rule()
    for x in rows:
        kn = f"{int(f(x['k']))}/{int(f(x['n']))}"
        print(f"  {x['block']:<17}{x['quantity'][:55]:<56}{kn:>8}  {100*f(x['proportion']):5.1f}%  "
              f"[{100*f(x['wilson_lo']):4.1f}, {100*f(x['wilson_hi']):4.1f}]"
              f"{'' if not x['chance'] else format(100*f(x['chance']), '7.2f') + '%':>9}"
              f"{x['ratio'] and format(f(x['ratio']), '6.2f'):>7}")
    write_csv(root / "results" / "tables" / "supp_annotation_intervals.csv", rows,
              ["block", "section", "quantity", "key", "k", "n", "proportion", "wilson_lo",
               "wilson_hi", "chance", "chance_key", "ratio", "ratio_source"])


def mtype(h, m):
    d = abs(h - m)
    return "exact" if d == 0 else ("within1" if d == 1 else ("within2" if d == 2 else f"off{d}"))


def stage3_alignment(root, hc):
    sub("3  SUPPLEMENTARY TABLE: THE THREE ALIGNMENTS SIDE BY SIDE")
    aud = read_csv(root / "results" / "tables" / "annotation_audit_v2.csv")
    posts, summary, bad = [], [], 0
    for x in sorted(aud, key=lambda r: r["id"]):
        hd, hs = int(x["h_disp"]), int(x["h_sent"])
        l0, l1 = int(x["lewi_zero_based"]), int(x["lewi_one_based"])
        if l1 != l0 + 1:
            bad += 1
        row = {"block": "post", "id": x["id"], "N": x["N"], "N_disp": x["N_disp"],
               "h_disp": hd, "h_sent": hs, "boundary_sent": x["boundary_sent"],
               "lewi_zero_based": l0, "lewi_one_based": l1}
        for c, h, m in (("impl", hd, l0), ("plus1", hd, l1), ("full", hs, l1)):
            row[f"{c}_human"], row[f"{c}_metric"], row[f"{c}_diff"] = h, m, m - h
            row[f"{c}_match"] = mtype(h, m)
            if row[f"{c}_match"] != x[f"match_{c}"]:
                bad += 1
                print(f"  INCONSISTENT {x['id']} {c}: {row[c + '_match']} vs stored {x['match_' + c]}")
        notes = []
        if hd != hs:
            notes.append(f"displayed line {hd} is sentence {hs}")
        if row["plus1_match"] != row["full_match"]:
            notes.append(f"+1 only gives {row['plus1_match']}, verified map gives {row['full_match']}")
        row["note"] = "; ".join(notes)
        posts.append(row)
    for c, lab in CONV:
        for m in ("exact", "within1", "within2"):
            k = int(f(hc[f"{m}_{c}"]["k"]))
            lim = {"exact": 0, "within1": 1, "within2": 2}[m]
            mine = sum(1 for r in posts if abs(r[f"{c}_diff"]) <= lim)
            if mine != k:
                bad += 1
                print(f"  INCONSISTENT count {m}_{c}: table {mine} vs human_criterion_v2 {k}")
            key = f"{m}_{c}"
            summary.append({"block": "summary", "alignment": c, "alignment_label": lab, "measure": m,
                         "k": hc[key]["k"], "n": hc[key]["n"], "proportion": hc[key]["value"],
                         "wilson_lo": hc[key]["wilson_lo"], "wilson_hi": hc[key]["wilson_hi"],
                         "chance_mean": hc[f"chance_{m}_mean_{c}"]["value"],
                         "expected": hc[f"expected_{m}_{c}"]["value"],
                         "p_ge_observed": hc[f"p_ge_{m}_{c}"]["value"],
                         "p_le_observed": hc[f"p_le_{m}_{c}"]["value"]})
    if bad:
        raise CheckFailed(f"{bad} alignment inconsistencies")
    for r in posts:
        if r["note"]:
            print(f"  {r['id']:<29} {r['note']}")
    print()
    print(f"  {'alignment':<8}{'measure':<9}{'k/n':>7}  {'prop':>6}  {'Wilson 95%':<15}{'E[X]':>7}"
          f"{'P(X>=obs)':>11}{'P(X<=obs)':>11}")
    rule()
    for r in summary:
        print(f"  {r['alignment']:<8}{r['measure']:<9}{r['k'] + '/' + r['n']:>7}  "
              f"{100*f(r['proportion']):5.1f}%  [{100*f(r['wilson_lo']):4.1f}, {100*f(r['wilson_hi']):4.1f}]  "
              f"{f(r['expected']):6.3f}{f(r['p_ge_observed']):11.3f}{f(r['p_le_observed']):11.3f}")
    print()
    print("  Why +1 gives one more exact match than the verified map: the +1 column")
    print("  compares the metric's sentence number with the annotator's displayed LINE")
    print("  number; where a sentence earlier in the post spans more than one line, those")
    print("  two numbers coincide by accident although they name different sentences.")
    cols = ["block", "id", "N", "N_disp", "h_disp", "h_sent", "boundary_sent", "lewi_zero_based",
            "lewi_one_based"]
    for c, _ in CONV:
        cols += [f"{c}_human", f"{c}_metric", f"{c}_diff", f"{c}_match"]
    cols += ["note", "alignment", "alignment_label", "measure", "k", "n", "proportion",
             "wilson_lo", "wilson_hi", "chance_mean", "expected", "p_ge_observed", "p_le_observed"]
    write_csv(root / "results" / "tables" / "supp_alignment_comparison.csv", posts + summary, cols)


# ================================================================ stage 4
def git_show(release, path):
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(release), "show",
                        f"pre-revision:{path}"], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def prefix_of(pid, known):
    for s in sorted(known, key=len, reverse=True):
        if pid.startswith(s + "_"):
            return s, pid[len(s) + 1:]
    return "", pid


def stage4_sources(root):
    sub("4  THE EIGHTH SUBREDDIT: WHAT THE COLLECTION SCRIPTS QUERY, WHERE THE POSTS CAME FROM")
    release = root / "release"
    old = root.parent.parent / "Old" / "PLEF"
    out = []
    queried = collections.OrderedDict()
    for script in ("reddit_download.py", "extended_reddit_download.py"):
        src = git_show(release, script)
        if src is None:
            raise CheckFailed(f"cannot read pre-revision:{script}")
        subs = []
        m = re.search(r"^SUBREDDITS\s*=\s*\[(.*?)^\]", src, re.S | re.M)
        if m:
            subs += re.findall(r'"name"\s*:\s*"([^"]+)"', m.group(1))
        subs += re.findall(r'^SUBREDDIT\s*=\s*"([^"]+)"', src, re.M)
        subs += [s for s in re.findall(r"reddit\.com/r/([A-Za-z0-9_]+)", src) if s not in subs]
        subs = list(dict.fromkeys(subs))
        idform = ("'{name}_{post_id}'" if re.search(r'f"\{name\}_\{post_id\}"', src)
                  else "bare Reddit post id" if re.search(r'"id":\s*post_id', src) else "unknown")
        queried[script] = subs
        print(f"  pre-revision:{script}  sha256 {hashlib.sha256(src.encode('utf-8')).hexdigest()[:16]}...")
        print(f"    subreddits queried: {', '.join(subs)}")
        print(f"    id written as     : {idform}")
        for s in subs:
            out.append({"block": "script_queries", "source": script, "subreddit": s,
                        "n": "", "evidence": f"pre-revision:{script}; id written as {idform}"})
    allq = sorted({s for v in queried.values() for s in v})
    known = set(allq)

    man = json.loads((root / "MANIFEST" / "corpora.json").read_text(encoding="utf-8"))
    mhash = {}
    for e in man.get("raw_sources", []):
        name = e.get("path", "").replace("\\", "/")
        if "/Old/PLEF/" in name:
            mhash[name.split("/Old/PLEF/", 1)[1]] = e.get("sha256")
    print()
    print(f"  Old/PLEF entries in MANIFEST/corpora.json raw_sources: {len(mhash)}")

    corpora = {"evaluation": read_csv(root / "data" / "interim" / "corpus_relationship.csv"),
               "annotation_development": read_csv(root / "data" / "interim" / "dev_split_relationship.csv")}
    ids = {sp: [r["id"] for r in rows] for sp, rows in corpora.items()}
    overlap = set(ids["evaluation"]) & set(ids["annotation_development"])
    if overlap:
        raise CheckFailed(f"evaluation and annotation-development ids overlap: "
                          f"{len(overlap)} ids, e.g. {sorted(overlap)[:5]}")
    n_eval, n_dev = len(ids["evaluation"]), len(ids["annotation_development"])
    n_coll = n_eval + n_dev
    print(f"  evaluation rows {n_eval:,} + annotation-development rows {n_dev:,} = {n_coll:,} "
          f"(id sets disjoint)")
    print()
    print(f"  {'split':<24}{'prefix':<22}{'ids':>6}")
    rule()
    unpref = {}
    for sp, lst in ids.items():
        cnt = collections.Counter(prefix_of(i, known)[0] or "(no prefix)" for i in lst)
        for p_, n_ in sorted(cnt.items()):
            print(f"  {sp:<24}{p_:<22}{n_:>6}")
            out.append({"block": "corpus_prefix", "source": sp, "subreddit": p_, "n": n_,
                        "evidence": "id prefix"})
        unpref[sp] = [i for i in lst if not prefix_of(i, known)[0]]
        na = sum(1 for i in lst if prefix_of(i, known)[0] == "NarcissisticAbuse")
        print(f"  {sp:<24}{'NarcissisticAbuse':<22}{na:>6}   <- prefix count")

    # --- evidence for unprefixed ids
    print()
    print("  evidence files under Old/PLEF (read as data; SHA-256 against the manifest):")
    ev_sub = collections.defaultdict(set)         # bare id -> {subreddit} from <sub>_<id>
    verified = {}
    if old.exists():
        for p in sorted(old.glob("corpus_*.csv")):
            rel = p.name
            ok = mhash.get(rel)
            verified[rel] = None if ok is None else (ok == sha256_file(p))
            rows = read_csv(p)
            for r in rows:
                s, bare = prefix_of(r.get("id", ""), known)
                if s:
                    ev_sub[bare].add(s)
            print(f"    {rel:<36}{len(rows):>6} rows   manifest hash "
                  f"{'not listed' if ok is None else ('MATCH' if verified[rel] else 'DIFFERS')}")
        for fname in ("reddit_posts_corpus.csv", "relationship_corpus_FULL.csv"):
            full = old / fname
            if not full.exists():
                continue
            ok = mhash.get(full.name)
            n_rows = 0
            for r in read_csv(full):
                n_rows += 1
                s, bare = prefix_of(r.get("id", ""), known)
                if r.get("subreddit"):
                    ev_sub[bare].add(r["subreddit"])
            print(f"    {full.name:<36}{n_rows:>6} rows   manifest hash "
                  f"{'not listed' if ok is None else ('MATCH' if ok == sha256_file(full) else 'DIFFERS')}")
        raw = old / "reddit_raw.json"
        raw_ids = set()
        if raw.exists():
            raw_ids = {str(x.get("id")) for x in json.loads(raw.read_text(encoding="utf-8"))}
            print(f"    reddit_raw.json: {len(raw_ids)} posts (output of reddit_download.py)")
        txt_dir = old / "reddit_posts"
        txt_ids = set()
        nmatch = 0
        if txt_dir.exists():
            for p in sorted(txt_dir.glob("*.txt")):
                txt_ids.add(p.stem)
                h = mhash.get(f"reddit_posts/{p.name}")
                if h is not None and h == sha256_file(p):
                    nmatch += 1
            print(f"    reddit_posts/*.txt: {len(txt_ids)} files, {nmatch} with a matching manifest hash")
        print(f"    reddit_download.py at pre-revision is set to: "
              f"{', '.join(queried['reddit_download.py']) or '(not found)'}")
    else:
        raw_ids, txt_ids = set(), set()
        print(f"    {old} not present; unprefixed ids cannot be attributed")

    print()
    print(f"  {'split':<24}{'unprefixed':>11}{'by <sub>_<id>':>15}{'in reddit_raw/txt only':>24}{'no evidence':>13}")
    rule()
    attrib_rows = []
    for sp, lst in unpref.items():
        by_sub = collections.Counter()
        raw_only = none = 0
        for i in lst:
            s = ev_sub.get(i)
            if s:
                key = "+".join(sorted(s))
                by_sub[key] += 1
                attrib_rows.append({"block": "unprefixed_attribution", "source": sp, "subreddit": key,
                                    "id": i, "evidence": "same Reddit id under <sub>_<id> in Old/PLEF collection files"})
            elif i in raw_ids or i in txt_ids:
                raw_only += 1
                attrib_rows.append({"block": "unprefixed_attribution", "source": sp,
                                    "subreddit": "relationship_advice (by script setting only)", "id": i,
                                    "evidence": "only in reddit_download.py outputs (reddit_raw.json / reddit_posts); "
                                                "subreddit is the script's constant, not recorded per post"})
            else:
                none += 1
                attrib_rows.append({"block": "unprefixed_attribution", "source": sp, "subreddit": "",
                                    "id": i, "evidence": "no evidence"})
        print(f"  {sp:<24}{len(lst):>11}{sum(by_sub.values()):>15}{raw_only:>24}{none:>13}")
        for k_, v_ in sorted(by_sub.items()):
            print(f"      attributed by <sub>_<id> to {k_}: {v_}")
            out.append({"block": "unprefixed_summary", "source": sp, "subreddit": k_, "n": v_,
                        "evidence": "same Reddit id under <sub>_<id> in Old/PLEF collection files"})
        out.append({"block": "unprefixed_summary", "source": sp,
                    "subreddit": "relationship_advice (by script setting only)", "n": raw_only,
                    "evidence": "only in reddit_download.py outputs"})
        out.append({"block": "unprefixed_summary", "source": sp, "subreddit": "(no evidence)", "n": none,
                    "evidence": ""})

    na_any = any("NarcissisticAbuse" in r["subreddit"] for r in attrib_rows) or any(
        r["block"] == "corpus_prefix" and r["subreddit"] == "NarcissisticAbuse" for r in out)
    present = sorted({r["subreddit"] for r in out if r["block"] == "corpus_prefix"
                      and r["subreddit"] != "(no prefix)"})
    n_unpref = sum(len(v) for v in unpref.values())
    n_rawonly = sum(1 for r in attrib_rows if r["subreddit"].startswith("relationship_advice (by"))
    n_none = sum(1 for r in attrib_rows if r["subreddit"] == "")
    print()
    print(f"  any post attributable to r/NarcissisticAbuse: {'YES' if na_any else 'NO'}")
    print(f"  subreddits present by prefix: {', '.join(present)} ({len(present)})")
    print()
    if n_coll != MANUSCRIPT_COLLECTION_N:
        print(f"  NO DRAFT SENTENCE: evaluation {n_eval:,} + annotation-development {n_dev:,} "
              f"= {n_coll:,}, not the {MANUSCRIPT_COLLECTION_N:,} stated in the manuscript.")
        write_csv(root / "results" / "tables" / "supp_corpus_sources.csv", out + attrib_rows,
                  ["block", "source", "subreddit", "n", "id", "evidence"])
        return {"na_any": na_any, "n_unpref": n_unpref, "n_rawonly": n_rawonly, "n_none": n_none}
    print("  WHAT THE METHODS PARAGRAPH CAN SAY (draft; the author decides wording):")
    print(f"    The collection scripts query {len(allq)} subreddits ({', '.join(allq)}).")
    print(f"    The {n_coll:,} collected posts carry a subreddit prefix from {len(present)} of them;")
    if not na_any:
        print("    no post can be attributed to r/NarcissisticAbuse, which is therefore not")
        print("    listed as a source.")
    else:
        print("    some posts are attributable to r/NarcissisticAbuse, which must be listed.")
    print(f"    {n_unpref} posts carry no prefix; of these, "
          f"{n_unpref - n_rawonly - n_none} share a Reddit id with a prefixed post in the")
    print(f"    collection files, {n_rawonly} occur only in the output of the single-subreddit")
    print("    script, whose configured subreddit is r/relationship_advice (an inference from")
    print("    the script, not a per-post record), and", n_none, "have no recorded origin.")
    write_csv(root / "results" / "tables" / "supp_corpus_sources.csv", out + attrib_rows,
              ["block", "source", "subreddit", "n", "id", "evidence"])
    return {"na_any": na_any, "n_unpref": n_unpref, "n_rawonly": n_rawonly, "n_none": n_none}


# ================================================================ stage 5
def stage5_overlap(root, a, core):
    sub("5  RELATIONSHIP POST TEXT IN THE RELEASE WORKING TREE")
    release = root / "release"
    splits = {"evaluation": read_csv(root / "data" / "interim" / "corpus_relationship.csv"),
              "annotation_development": read_csv(root / "data" / "interim" / "dev_split_relationship.csv")}
    split_of, text_of, fp = {}, {}, []
    for sp, rows in splits.items():
        for r in rows:
            split_of[r["id"]] = sp
            text_of[r["id"]] = r["text"]
            ws = [WORD.findall(s.lower()) for s in core.sentences(r["text"])]
            for x in [w for w in ws if len(w) >= K][:3]:
                fp.append((r["id"], x[:K]))
    have = len({p for p, _ in fp})
    print(f"  posts {len(split_of)}; with >= 1 fingerprint {have}; fingerprints {len(fp)}")
    files = sorted(p for p in release.rglob("*") if p.is_file()
                   and ".git" not in p.relative_to(release).parts)
    head_ = subprocess.run(["git", "--no-optional-locks", "-C", str(release), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    print(f"  release HEAD {head_}; {len(files)} files scanned (read-only)")
    with Pool(a.workers, initializer=_init_fp, initargs=(fp,)) as pool:
        res = pool.map(_hits, [(str(p), None) for p in files], chunksize=1)
    by_post = collections.defaultdict(set)
    fps_of = collections.defaultdict(set)
    for label, found in res:
        rel = str(Path(label).relative_to(release)).replace("\\", "/")
        if found:
            print(f"    {rel:<46} posts {len(found):>4}")
        for pid, keys in found.items():
            by_post[pid].add(rel)
            fps_of[pid].update(tuple(k) for k in keys)
    dev_texts = [(pid, t) for pid, t in text_of.items() if split_of[pid] == "annotation_development"]
    out = []
    for pid in sorted(by_post, key=lambda x: (split_of[x], x)):
        quoted = ""
        if split_of[pid] == "evaluation":
            hits = []
            for did, t in dev_texts:
                w = " " + " ".join(WORD.findall(t.lower())) + " "
                if any(" " + " ".join(k) + " " in w for k in fps_of[pid]):
                    hits.append(did)
            quoted = ";".join(sorted(hits))
        out.append({"post_id": pid, "split": split_of[pid], "files": ";".join(sorted(by_post[pid])),
                    "n_files": len(by_post[pid]), "text_found_inside_dev_posts": quoted})
    n_dev = sum(1 for r in out if r["split"] == "annotation_development")
    n_ev = sum(1 for r in out if r["split"] == "evaluation")
    print()
    print(f"  distinct posts found: {len(out)}  (annotation-development {n_dev}, evaluation {n_ev})")
    for r in out:
        if r["split"] == "evaluation":
            print(f"    evaluation post {r['post_id']:<30} text inside dev post(s): "
                  f"{r['text_found_inside_dev_posts'] or '(none found; fingerprint shared only)'}")
    exp = AUDIT_EXPECTED
    same = (len(out), n_dev, n_ev) == (exp["posts"], exp["dev"], exp["evaluation"])
    print(f"  reproduces the round-2 audit (round2_audit/console_log_r2d_release_text.txt:110-112, "
          f"{exp['posts']} = {exp['dev']} + {exp['evaluation']}): {'YES' if same else 'NO'}")
    write_csv(root / "results" / "tables" / "supp_released_text_overlap.csv", out,
              ["post_id", "split", "files", "n_files", "text_found_inside_dev_posts"])
    return {"posts": len(out), "dev": n_dev, "evaluation": n_ev, "same": same}


# ================================================================ stage 6
PH = re.compile(r"<<([^<>]+?)>>")
COLMAP = {"k": "k", "n": "n", "lo": "wilson_lo", "hi": "wilson_hi"}


def stage6_placeholders(root, ab, hc, s4, s5):
    sub("6  PLACEHOLDERS IN MANUSCRIPT_CHANGES_ROUND2.md")
    p = root / "paper" / "round2" / "MANUSCRIPT_CHANGES_ROUND2.md"
    if not p.exists():
        print(f"  {p} not found")
        return
    resolved, unresolved = collections.OrderedDict(), collections.OrderedDict()
    for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        last_key = None
        for m in PH.finditer(line):
            ph = m.group(1)
            if ph in ("18:abstention_v2:ROW:COL", "19:human_criterion_v2:KEY") or "KEY" in ph or "ROW" in ph:
                continue                                    # the convention table itself
            val, why = None, ""
            s = ph.replace("…", "...")
            if s.startswith("18:"):
                parts = s.split(":")
                if len(parts) >= 4:
                    row, col = parts[2], parts[3]
                    v = ab.get(row, {}).get(col, "")
                    if v != "":
                        val = v
                    else:
                        why = f"no value at row {row}, column {col}"
                else:
                    why = "malformed"
            elif s.startswith("19:") or s.startswith("..."):
                if s.startswith("19:"):
                    parts = s.split(":")[2:]
                else:
                    rest = s[3:]
                    parts = ([last_key] + rest[1:].split(":")) if rest.startswith(":") else rest.split(":")
                key = parts[0]
                colk = parts[1] if len(parts) > 1 else None
                if key and key in hc:
                    last_key = key
                    col = COLMAP.get(colk, "value") if colk else "value"
                    v = hc[key].get(col, "")
                    if v != "":
                        val = v
                    else:
                        why = f"key {key} has no {col}"
                else:
                    why = f"key {key!r} not in human_criterion_v2.csv"
            elif s.startswith("AUDIT:r2d:112"):
                val = f"{s5['evaluation']} (20_round2_assets.py stage 5; supp_released_text_overlap.csv)"
            elif s.startswith("AUDIT"):
                why = "audit-log number with no forensics-logged source yet"
            elif s.startswith("DATE") or s.startswith("TAG"):
                why = "set when the release correction is carried out (RELEASE_PLAN_ROUND2.md)"
            else:
                why = "unrecognised form"
            tgt = resolved if val is not None else unresolved
            tgt.setdefault(ph, {"lines": [], "value": val, "why": why})["lines"].append(ln)
    print(f"  RESOLVED ({len(resolved)} distinct placeholders)")
    for ph, d in resolved.items():
        print(f"    l.{','.join(map(str, d['lines'])):<14} <<{ph}>> = {d['value']}")
    print()
    print(f"  UNRESOLVED ({len(unresolved)} distinct placeholders)")
    for ph, d in unresolved.items():
        print(f"    l.{','.join(map(str, d['lines'])):<14} <<{ph}>>  -- {d['why']}")
    print()
    print("  Open items of MANUSCRIPT_CHANGES_ROUND2.md now covered by this script:")
    print("    O1  count of evaluation posts quoted in released dev-post text: stage 5")
    print("    O2  Fig. 1b and Fig. 4b redrawn: stage 1 (fig1_coverage_scope_v2.png, fig4_gase_abstention_v2.png)")
    print("    O3  Table S-x of per-pair and per-rater intervals: stage 2 (supp_annotation_intervals.csv)")
    print("    O4  unchanged: the 84.9% neutral share and AUC values come from console_log_06 / auc.csv")
    print(f"  Eighth subreddit (stage 4): NarcissisticAbuse attributable: "
          f"{'yes' if s4['na_any'] else 'no'}; unprefixed ids {s4['n_unpref']}, "
          f"by script setting only {s4['n_rawonly']}, no evidence {s4['n_none']}")


# =========================================================================
def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 20 -- round-2 assets.")
    ap.add_argument("--root", required=True, help="path to PLEF_V2")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count()))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    tables = root / "results" / "tables"
    tee = Tee(root / "results" / "forensics" / "console_log_20.txt")
    sys.stdout = tee
    code = 0
    try:
        head(f"PLEF V2 -- SCRIPT 20 : ROUND-2 ASSETS   v{VERSION}")
        print(f"  root      : {root}")
        print(f"  started   : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  python    : {sys.version.split()[0]}   workers {a.workers}")
        need = ["abstention_v2.csv", "human_criterion_v2.csv", "annotation_audit_v2.csv",
                "abstention.csv", "abstention_binary.csv", "length_threshold.csv",
                "coverage.csv", "gase_ablation.csv"]
        if stage0_validate(root):
            head("STOPPED (exit 2): missing input file, column or key; see stage 0")
            return 2
        for n in need:
            print(f"  input     : tables/{n}  sha256 {sha256_file(tables / n)[:16]}...")
        core = load_core(root / "src")

        with Pool(a.workers) as pool:
            ab = stage1_checks_and_figures(root, a, pool)
        hc, badk = load_hc(root)
        sub("2/3  CHECK: human_criterion_v2.csv k/n AND WILSON INTERVALS")
        print(f"  {len(hc)} keys; {len(badk)} with value or interval inconsistent with k/n")
        if badk:
            raise CheckFailed(f"inconsistent keys: {badk[:10]}")
        stage2_intervals(root, hc)
        stage3_alignment(root, hc)
        s4 = stage4_sources(root)
        s5 = stage5_overlap(root, a, core)
        stage6_placeholders(root, ab, hc, s4, s5)
        if not s5["same"]:
            code = 5
        head("DONE" if code == 0 else "DONE, with a stage-5 difference from the audit (exit 5)")
        return code
    except CheckFailed as e:
        print()
        print(f"  CHECK FAILED: {e}")
        head("STOPPED (exit 3)")
        return 3
    finally:
        print(f"  finished  : {datetime.datetime.now().isoformat(timespec='seconds')}")
        sys.stdout = tee.stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(main())
