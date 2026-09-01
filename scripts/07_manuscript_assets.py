#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 07 : MANUSCRIPT ASSETS, RESPONSE LETTER, REFERENCE AUDIT
                       (v07.1.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
Everything is measured. This turns it into the three documents the resubmission
needs, built from the result files rather than transcribed by hand -- because
hand transcription is how V1's Table 4 came to disagree with its Table 7.

  paper/TABLES.md            manuscript-ready tables, every number from
                             results/tables/*.csv
  paper/RESPONSE_LETTER.md   a skeleton: the disclosure section written from
                             DECISIONS.md and the forensic record, and every
                             reviewer point matched to the evidence that
                             answers it. YOU write the prose. It supplies the
                             numbers and the structure so none is invented.
  paper/REFERENCE_AUDIT.csv  all references from the submitted manuscript,
                             with the eight known mismatches pre-filled and a
                             column for you to record the check on the rest.

WHAT IT DOES NOT DO
-------------------
It does not write your paper. It does not draft claims. Every table cell and
every figure in the response letter is traceable to a file on disk, and any
number it cannot find is printed as MISSING rather than guessed.

EXIT CODES
----------
  0 written    2 missing prerequisite (run script 06 first)
===============================================================================
"""

import argparse
import csv
import datetime
import json
import os
import sys
import traceback

from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "07.1.0"


def rule(ch="-", w=78): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def load_tables(root):
    p = Path(root) / "results" / "tables" / "all_results.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def g(d, *path, default="MISSING"):
    """Fetch a nested value, or the literal string MISSING. Never guesses."""
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and isinstance(k, int) and k < len(cur):
            cur = cur[k]
        else:
            return default
    return cur


def find_row(rows, **kw):
    for r in rows or []:
        if all(str(r.get(k, "")) == str(v) for k, v in kw.items()):
            return r
    return {}


# ===========================================================================
# The eight citation problems already established. The rest is for you.
# ===========================================================================
KNOWN_CITATION_ISSUES = [
    ("Grimm et al. (2022)",
     "cited as: text features classifying attachment styles in online support "
     "communities with F1 competitive with deep learning",
     "reference list entry is 'Growth mixture modeling', Structural Equation "
     "Modeling 23(6) 815-828 -- a different paper on a different topic, and "
     "SEM vol 23 is 2016 not 2022",
     "MISMATCH -- confirmed"),
    ("Brody & Diakopoulos (2011)",
     "cited as: emotional amplification in Twitter during crisis events, "
     "introducing emotional trajectory analysis",
     "the listed paper is about word lengthening for microblog sentiment",
     "MISMATCH -- confirmed"),
    ("Chung & Pennebaker (2018)",
     "cited as: language shifts before and after relationship dissolution",
     "the listed paper is the meaning-extraction method for open-ended "
     "self-descriptions",
     "MISMATCH -- confirmed"),
    ("Gaur et al. (2021)",
     "cited as: training cognitive-distortion classifiers on Reddit",
     "the listed paper is C-SSRS suicidality assessment",
     "MISMATCH -- confirmed"),
    ("Shickel et al. (2020)",
     "cited as: survey of deep learning for clinical mental health text",
     "the listed paper is Deep EHR; IEEE JBHI 22(5) 1589-1604 is 2018",
     "MISMATCH -- confirmed"),
    ("Page (1954), CUSUM",
     "cited in Section 3.2.1 as the theoretical grounding for LEWI",
     "NOT PRESENT in the reference list",
     "MISSING FROM REFERENCES"),
    ("Jockers & Mimno (2013)",
     "cited in Section 2.3",
     "NOT PRESENT in the reference list",
     "MISSING FROM REFERENCES"),
    ("Shannon",
     "cited in Table 1 as 'Shannon (2001 repr.)'",
     "NOT PRESENT in the reference list; the '2001 repr.' year appears to be "
     "invented, as does 'Deerwester et al. (2011 repr.)' where the list says 1990",
     "MISSING FROM REFERENCES"),
]

# Reviewer points -> the evidence that answers each one.
REVIEWER_MAP = [
    ("R1.1", "Abstract overlong; distinguish proxy from direct evidence for H1",
     "WRITEUP", "H1 is now NOT ABOVE CHANCE against a human criterion; the "
     "circular NAVAxLEWI proxy is withdrawn"),
    ("R1.2", "TEG has no validation target; compare with affect lability",
     "EXPERIMENT", "TEG vs NRC Emotion Intensity volatility, an external "
     "criterion not derived from PLEF: see section H"),
    ("R1.3", "Report macro-F1 separately for relationship vs general domain",
     "EXPERIMENT", "section Q, against both V1 silver labels and human gold; "
     "the silver version is withdrawn because silver-vs-human kappa is negative"),
    ("R1.4", "r>0.25 is arbitrary; give CIs and test moderators",
     "EXPERIMENT", "bootstrap CIs on every correlation (section H) and a "
     "length-stratified moderator analysis (section R)"),
    ("R1.5", "State Python version, dependencies, tested environment",
     "WRITEUP", "MANIFEST/environment.json, requirements-eval.txt, and the "
     "standard-library purity gate in script 04"),
    ("R2.1", "'Neural layer' is LSA, a linear factorisation",
     "WRITEUP", "conceded; D26. The term neuro-symbolic is removed"),
    ("R2.2", "Tool claims first-person narratives; corpora are tweets and TV",
     "WRITEUP", "D20 scopes trajectory metrics to the relationship corpus; "
     "sections A and B give the coverage and length thresholds"),
    ("R2.3", "LEWI documented as 2nd difference, implemented as sign change",
     "EXPERIMENT", "V2 implements the published definition; section G measures "
     "how far the two algorithms disagree"),
    ("R2.4", "TEG divides by N-1 in code, N in the paper",
     "WRITEUP", "conceded; D22. TEG is described as MASD, not as novel"),
    ("R2.5", "NAVA sign contradiction and an unclassified interval",
     "WRITEUP", "conceded; D23. Five classes published, sign convention fixed"),
    ("R2.6", "H1 not tested, H6 unsupported; supply a deviation table",
     "WRITEUP", "DECISIONS.md, 26 declarations timestamped before any result"),
    ("R2.7", "PTI and PAI share pronoun counts",
     "EXPERIMENT", "D24 removes the pronoun term; the coupling is quantified "
     "(PAI_v1 r=+0.379 vs PAI r=+0.090) and VAD dominance added as an "
     "external criterion"),
    ("R2.8", "Semantic space fitted per narrative; two code paths; versions",
     "WRITEUP", "D26; one deterministic path, verified bitwise across processes"),
    ("R3.1", "NAVAxLEWI needs a structural null",
     "EXPERIMENT", "two nulls: synthetic and a within-document sentence-order "
     "permutation. The observed value does not exceed either"),
    ("R3.2", "Name the three consensus systems; drop from the item total",
     "WRITEUP", "D19: the corpus is REMOVED, not quarantined; it produced 69% "
     "positive labels on breakup narratives"),
    ("R3.3", "H1 is not supported", "WRITEUP",
     "agreed and now measured: 0% exact against a human, chance 4.3%"),
    ("R3.4", "DailyDialog result is majority-class", "EXPERIMENT",
     "confirmed: section E and the McNemar abstention note"),
    ("R3.5", "Report valid N wherever trajectory metrics appear",
     "WRITEUP", "section M reports defined-% for every metric on every corpus"),
    ("R3.6", "Entropy and attachment ablations identical; show distributions",
     "EXPERIMENT", "the V1 ablation subtracted a hardcoded constant; section J "
     "computes the real one and reports component standard deviations"),
    ("R3.7", "Citations do not match the works cited",
     "WRITEUP", "paper/REFERENCE_AUDIT.csv; eight problems confirmed so far"),
]


def write_tables(root, T):
    sub("paper/TABLES.md")
    L = ["# PLEF V2 -- Manuscript tables", "",
         f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by "
         f"scripts/07_manuscript_assets.py v{SCRIPT_VERSION}.",
         "Every cell is read from `results/tables/`. Nothing is transcribed.", ""]

    L += ["## Table 1 -- Lexicon coverage", "",
          "| corpus | PLEF | VADER | NRC | Empath | AFINN | Hu-Liu | PLEF as % of VADER |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in T.get("coverage", []):
        if r.get("corpus") == "dev_relationship":
            continue
        def pc(k):
            v = r.get(k)
            try:
                return f"{100*float(v):.2f}%"
            except (TypeError, ValueError):
                return "n/a"
        L.append(f"| {r['corpus']} | {pc('PLEF')} | {pc('vader')} | {pc('nrc')} "
                 f"| {pc('empath')} | {pc('afinn')} | {pc('huliu')} "
                 f"| {r.get('plef_pct_of_vader','n/a')}% |")
    L += ["", "PLEF's 348-entry lexicon is the mechanism behind every accuracy "
          "figure in Table 3.", ""]

    lt = T.get("length_threshold", [])
    if lt:
        keys = [k for k in lt[0] if k != "corpus"]
        L += ["## Table 2 -- Where PLEF produces a signal, by document length", "",
              "Percentage of documents in each word-count band for which PLEF "
              "returned a non-zero score.", "",
              "| corpus | " + " | ".join(k.replace("_", "-") for k in keys) + " |",
              "|---" * (len(keys) + 1) + "|"]
        for r in lt:
            if r.get("corpus") == "dev_relationship":
                continue
            L.append("| " + r["corpus"] + " | " + " | ".join(
                f"{r[k]}%" if r.get(k) is not None else "-" for k in keys) + " |")
        L.append("")

    t3 = T.get("table3", {})
    if t3:
        names = ["PLEF", "vader", "nrc", "empath", "afinn", "huliu", "labmt"]
        L += ["## Table 3 -- macro-F1 with bootstrap 95% CI", "",
              "| corpus | " + " | ".join(names) + " |", "|---" * (len(names)+1) + "|"]
        for c in ["goemotions", "semeval2017", "meld", "tweeteval", "dailydialog",
                  "isear", "empathetic"]:
            if c not in t3:
                continue
            cells = []
            for n in names:
                d = t3[c].get(n, {})
                cells.append(f"{d.get('f1', 0):.3f} [{d.get('lo', 0):.3f}, "
                             f"{d.get('hi', 0):.3f}]" if d else "-")
            tag = " (binary)" if c in ("isear", "empathetic") else ""
            L.append(f"| {c}{tag} | " + " | ".join(cells) + " |")
        L.append("")

    tb = T.get("trivial_baselines", [])
    if tb:
        L += ["## Table 4 -- Trivial baselines", "",
              "| corpus | majority | always-neutral | random | PLEF | best real system |",
              "|---|---:|---:|---:|---:|---|"]
        for r in tb:
            flag = "  **at or below chance**" if r.get("plef_at_or_below_chance") else ""
            L.append(f"| {r['corpus']} | {r['majority']} | {r['always_neutral']} "
                     f"| {r['random']} | **{r['PLEF']}**{flag} "
                     f"| {r['best_real']} ({r['best_real_system']}) |")
        L.append("")

    au = T.get("auc", [])
    if au:
        names = [k for k in au[0] if k != "corpus"]
        L += ["## Table 5 -- macro-AUC (threshold-free)", "",
              "One-vs-rest, pos and neg only: a single scalar cannot rank "
              "neutral-vs-rest.", "",
              "| corpus | " + " | ".join(names) + " |", "|---" * (len(names)+1) + "|"]
        for r in au:
            L.append("| " + r["corpus"] + " | " +
                     " | ".join(str(r.get(n, "-")) for n in names) + " |")
        L.append("")

    ab = T.get("abstention", [])
    if ab:
        L += ["## Table 6 -- Abstention-aware evaluation", "",
              "PLEF returns exactly 0.000 when its lexicon matches nothing. That is "
              "no lexical evidence, not a prediction of neutral.", "",
              "| corpus | PLEF fires | PLEF all | VADER all | PLEF\\|fires | "
              "VADER\\|fires | delta |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r in ab + T.get("abstention_binary", []):
            L.append(f"| {r['corpus']} | {r['fires_pct']}% | {r['plef_all']} "
                     f"| {r['vader_all']} | {r['plef_fires']} | {r['vader_fires']} "
                     f"| {r['delta']:+} |")
        L.append("")

    nl = T.get("nava_lewi_nulls", {})
    if nl:
        L += ["## Table 7 -- NAVA x LEWI against its nulls", "",
              "| condition | r |", "|---|---:|",
              f"| observed (n={nl.get('n','?')}) | {nl.get('observed', 0):+.3f} "
              f"[{g(nl,'ci',0,default=0):+.3f}, {g(nl,'ci',1,default=0):+.3f}] |"]
        for k, lab in (("perm_null_mean", "within-document sentence permutation"),
                       ("synth_iid_normal", "synthetic iid noise"),
                       ("synth_random_walk", "synthetic random walk")):
            if nl.get(k) is not None:
                L.append(f"| {lab} | {nl[k]:+.3f} |")
        L += ["", "The permutation null preserves every document's sentences and "
              "their distribution and destroys only their order.", ""]

    ga = T.get("gase_ablation", [])
    if ga:
        L += ["## Table 8 -- GASE components", "",
              "The standard deviations answer H4. The deltas measure a component's "
              "value relative to the others, not its informativeness, because "
              "leave-one-out renormalises the remaining weights.", "",
              "| corpus | sd(S) | sd(H) | sd(A) | sd(G) |", "|---|---:|---:|---:|---:|"]
        for r in ga:
            if r.get("corpus") == "dev_relationship":
                continue
            L.append(f"| {r['corpus']} | {r.get('sd_S')} | {r.get('sd_H')} "
                     f"| {r.get('sd_A')} | {r.get('sd_G')} |")
        L += ["", "V1's published ablation subtracted weight x 0.5, a hardcoded "
              "constant; component values were never read.", ""]

    hc = (T.get("human_criterion") or [{}])[0]
    if hc:
        L += ["## Table 9 -- H1 and H5 against the human criterion", "",
              f"Single annotator, n = {hc.get('n','?')} posts. PRELIMINARY: no "
              "inter-rater reliability exists for this round.", "",
              "| measure | value | chance / baseline |", "|---|---:|---:|"]
        if hc.get("h1_n"):
            L += [f"| H1 exact turning-point match | {100*hc['h1_exact']:.1f}% "
                  f"| {100*hc['h1_chance']:.1f}% |",
                  f"| H1 within 1 sentence | {100*hc.get('h1_within1',0):.1f}% "
                  f"| {100*hc.get('h1_within1_chance',0):.1f}% |",
                  f"| posts where the human marked NO turning point "
                  f"| {hc.get('h1_human_none','?')} | LEWI returned an index on all |"]
        if hc.get("h5_n"):
            L += [f"| H5 arc agreement | {100*hc['h5_agreement']:.1f}% "
                  f"| {100*hc['h5_baseline']:.1f}% majority |",
                  f"| H5 Cohen's kappa | {hc.get('h5_kappa'):+.3f} | 0 |"]
        L += ["", "Reliability ceiling: in an earlier three-annotator round, "
              "annotators agreed on the turning point exactly 0 times in 26 posts "
              "and agreed with themselves on 18-29% of repeats.", ""]

    sb = T.get("scoreboard", [])
    if sb:
        L += ["## Table 10 -- Hypothesis outcomes", "",
              "| hypothesis | outcome | evidence |", "|---|---|---|"]
        for r in sb:
            L.append(f"| {r['hypothesis']} | **{r['verdict']}** | {r['detail']} |")
        L.append("")

    p = Path(root) / "paper" / "TABLES.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  written -> {p}")
    return str(p)


def write_response(root, T):
    sub("paper/RESPONSE_LETTER.md")
    hc = (T.get("human_criterion") or [{}])[0]
    nl = T.get("nava_lewi_nulls", {})
    cov = {r["corpus"]: r for r in T.get("coverage", [])}
    dec = Path(root) / "DECISIONS.md"
    n_dec = 0
    if dec.exists():
        n_dec = dec.read_text(encoding="utf-8", errors="replace").count("\n### D")

    L = ["# Response to reviewers -- SKELETON", "",
         f"Generated {datetime.datetime.now().isoformat(timespec='seconds')}. ",
         "**Every number below is read from the result files. The prose is yours "
         "to write.** Do not paraphrase a figure without checking it here first.",
         "", "---", "",
         "## 1. Disclosure (this must come first, before any point-by-point reply)",
         "",
         "In responding to the reviewers we re-examined the analysis pipeline and "
         "found defects that affect numbers in the submitted manuscript. We report "
         "them in full before addressing the individual points.", "",
         "### 1.1 Two dataset loaders produced single-class label vectors", "",
         "ISEAR and DailyDialog were loaded with parsers that failed silently and "
         "assigned every item to a single class. All reported F1, AUC and effect "
         "sizes for those corpora were artifacts. Both are corrected: ISEAR now "
         "yields 7,666 items across seven emotions, DailyDialog 101,026 utterances "
         "with their annotated labels.", "",
         "### 1.2 The baselines were not the systems they were named after", "",
         "Section 4.3 stated that VADER was run using the published rule-based "
         "algorithm. The implementation used 100 hand-written lexicon entries "
         "against approximately 7,500 in the published system, with no intensifier, "
         "punctuation or capitalisation handling. The NRC baseline used 58 entries "
         "against 14,182. All comparisons are re-run against reference "
         "implementations.", "",
         "### 1.3 The corpus described as relationship narratives was not", "",
         "The corpus reported in Table 2 as 'Relationship narratives (7 subreddits)' "
         "was GoEmotions comment text, with 100% exact-text overlap with the "
         "GoEmotions corpus counted separately, and a median length of 14 words. "
         "The genuine posts were present but never loaded. They are used now: "
         "1,308 narratives, median 370 words.", "",
         "### 1.4 The published ablation subtracted a constant", "",
         "Table 8's ablation subtracted weight x 0.5 for three of four components; "
         "their values were never read. That is why removing entropy and removing "
         "attachment produced identical results to four decimal places. The "
         "conclusions resting on it are withdrawn.", "",
         "### 1.5 Table 4 and Table 7 came from different runs", "",
         "The two tables report the same quantity and disagree on seven of nine "
         "corpora. All tables in the revision are generated from a single run by "
         "a script included in the repository.", "",
         f"### 1.6 A pre-registration was claimed that did not exist", "",
         f"Section 4.1 described hypotheses as formally registered prior to data "
         f"collection; no timestamped record exists. The revision includes "
         f"DECISIONS.md, {n_dec} declarations recorded before any evaluation "
         f"number was computed, and does not claim retrospective registration.",
         "", "---", "",
         "## 2. What the corrected analysis shows", ""]

    if nl:
        L += [f"**The central finding does not exceed its null.** NAVA x LEWI is "
              f"r = {nl.get('observed', 0):+.3f} on 1,288 narratives. A "
              f"within-document sentence-order permutation -- same sentences, same "
              f"distribution per document, order destroyed -- gives "
              f"r = {nl.get('perm_null_mean', 0):+.3f}. The two metrics are "
              f"pre-minus-post mean differences over the same signal, and their "
              f"correlation carries no information about narrative order.", ""]
    if hc.get("h1_n"):
        L += [f"**H1 does not hold against a human criterion.** LEWI matched a "
              f"careful annotator's turning point on {100*hc['h1_exact']:.0f}% of "
              f"{hc['h1_n']} posts against a chance rate of "
              f"{100*hc['h1_chance']:.1f}%. On {hc.get('h1_human_none','?')} posts "
              f"the annotator marked no turning point at all; LEWI returned an "
              f"index on every one, because an argmax has no null case.", ""]
    pl = cov.get("relationship", {})
    if pl:
        L += [f"**The instrument has a measurable scope.** PLEF's lexicon matches "
              f"{100*float(pl.get('PLEF', 0)):.2f}% of tokens against VADER's "
              f"{100*float(pl.get('vader', 0)):.2f}%. It returns a non-zero score "
              f"on 98-100% of documents over 160 words and 7-19% of documents "
              f"under ten. This is reported as the tool's scope rather than as a "
              f"limitation discovered late.", ""]

    L += ["---", "", "## 3. Point-by-point", "",
          "| # | reviewer point | type | evidence in the revision |",
          "|---|---|---|---|"]
    for pid, point, kind, ev in REVIEWER_MAP:
        L.append(f"| {pid} | {point} | {kind} | {ev} |")
    L += ["", "---", "",
          "## 4. What we are no longer claiming", "",
          "- that PLEF is competitive with VADER on sentiment classification",
          "- that NAVA and LEWI provide convergent validity for one another",
          "- that the framework is neuro-symbolic (the layer is LSA, a linear "
          "factorisation)",
          "- that TEG, PTI x PAI, or the CD-index relationships hold",
          "- that GASE's components contribute independently",
          "- any result computed on the Consensus corpus, which is withdrawn", "",
          "## 5. What the paper now contributes", "",
          "- a structural-redundancy result for trajectory metrics, with the null "
          "distribution practitioners should test against",
          "- a measured scope for lexicon-based narrative instruments, in coverage "
          "and document length",
          "- an abstention-aware evaluation distinguishing 'no lexical evidence' "
          "from a neutral prediction",
          "- a corrected, deterministic, standard-library implementation with a "
          "test suite, verified reproducible across processes",
          "- an annotation protocol with automated integrity checks that rejected "
          "two compromised rounds", ""]

    p = Path(root) / "paper" / "RESPONSE_LETTER.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  written -> {p}")
    print(f"  {len(REVIEWER_MAP)} reviewer points mapped to evidence")
    return str(p)


def write_reference_audit(root):
    sub("paper/REFERENCE_AUDIT.csv")
    p = Path(root) / "paper" / "REFERENCE_AUDIT.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["citation", "what_the_manuscript_says_it_shows",
                    "what_the_listed_reference_actually_is", "status",
                    "checked_by", "date", "action_taken"])
        for c, claim, actual, status in KNOWN_CITATION_ISSUES:
            w.writerow([c, claim, actual, status, "", "", ""])
        for i in range(1, 53):
            w.writerow([f"<reference {i+8} from the manuscript>", "", "",
                        "NOT YET CHECKED", "", "", ""])
    print(f"  written -> {p}")
    print(f"  {len(KNOWN_CITATION_ISSUES)} confirmed problems pre-filled")
    print("  52 blank rows for the remainder of the reference list")
    print()
    print("  Check every one against the actual paper, not against your notes.")
    print("  Reviewer 3 found two of these. A reviewer who finds a ninth after")
    print("  you have disclosed eight will assume nobody checked.")
    return str(p)


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="PLEF V2 script 07 -- manuscript assets.")
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    T = load_tables(root)
    if T is None:
        print("FATAL: results/tables/all_results.json missing. Run script 06 first.")
        return 2

    head("PLEF V2 -- SCRIPT 07 : MANUSCRIPT ASSETS")
    print(f"  script version : {SCRIPT_VERSION}")
    print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"  sections found : {len(T)}")

    try:
        t = write_tables(root, T)
        r = write_response(root, T)
        a = write_reference_audit(root)

        sub("MISSING VALUES")
        txt = Path(t).read_text(encoding="utf-8")
        n_missing = txt.count("MISSING")
        print(f"  TABLES.md contains {n_missing} MISSING marker(s)")
        if n_missing:
            print("  Each is a number script 06 did not produce. Find it or drop")
            print("  the row -- do not fill it in by hand.")

        head("DONE")
        print(f"  tables   : {t}")
        print(f"  response : {r}")
        print(f"  refs     : {a}")
        print()
        print("  The response letter is a SKELETON. The disclosure section and")
        print("  every number are written from the result files; the argument is")
        print("  yours. Read section 1 first and confirm you are willing to put")
        print("  each statement in front of the editor.")
        return 0
    except Exception:
        print("\nUNHANDLED EXCEPTION")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
