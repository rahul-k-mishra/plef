#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_analysis.py
================
Fully automated PLEF research pipeline.
Runs every metric on every Reddit post. No user input needed.
Double-click run_auto_analysis.bat to start.

What this produces (all saved in E:\Research\PLEF\results\):
  1. all_posts_metrics.csv       - every metric for every post
  2. corpus_summary.csv          - mean, SD, min, max across all posts
  3. baseline_comparison.csv     - PLEF vs VADER vs NRC vs LIWC accuracy
  4. statistical_tests.csv       - Pearson r, Spearman, p-values, Cohen's d
  5. roc_auc_results.csv         - ROC/AUC scores per class per system
  6. paper_table1.txt            - LaTeX Table 1 (corpus statistics)
  7. paper_table2.txt            - LaTeX Table 2 (baseline comparison)
  8. paper_table3.txt            - LaTeX Table 3 (statistical tests)
  9. full_report.txt             - complete readable summary report
"""

import sys
import os
import csv
import json
import math
import time
import datetime
import collections
from pathlib import Path

def _safe_input(prompt="", default=""):
    """input() wrapper that handles EOFError in automated/piped mode."""
    try:
        return input(prompt)
    except EOFError:
        return default

# ── Locate files ──────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
CORPUS_CSV   = SCRIPT_DIR / "reddit_posts_corpus.csv"
REDDIT_POSTS = SCRIPT_DIR / "reddit_posts"
RESULTS_DIR  = SCRIPT_DIR / "results"
PLEF_SCRIPT  = SCRIPT_DIR / "plef_v7.py"

# ── Colour support ────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init()
    GRN="\033[92m"; YLW="\033[93m"; RED="\033[91m"
    CYN="\033[96m"; MGN="\033[95m"; BLD="\033[1m"; RST="\033[0m"; DIM="\033[2m"
except ImportError:
    GRN=YLW=RED=CYN=MGN=BLD=RST=DIM=""

def head(msg):
    print(f"\n{BLD}{CYN}{'═'*62}{RST}")
    print(f"  {BLD}{CYN}{msg}{RST}")
    print(f"{BLD}{CYN}{'═'*62}{RST}")

def ok(msg):   print(f"  {GRN}✓{RST}  {msg}")
def warn(msg): print(f"  {YLW}!{RST}  {msg}")
def err(msg):  print(f"  {RED}✗{RST}  {msg}")
def info(msg): print(f"  {DIM}{msg}{RST}")

# ── Import PLEF functions ─────────────────────────────────────────────────────
head("Loading PLEF engine...")
if not PLEF_SCRIPT.exists():
    err(f"plef_v7.py not found at {PLEF_SCRIPT}")
    err("Make sure auto_analysis.py is in the same folder as plef_v7.py")
    _safe__safe_input("\nPress Enter to exit..."); sys.exit(1)

sys.path.insert(0, str(SCRIPT_DIR))
try:
    import plef_v7 as plef
    ok("PLEF engine loaded successfully")
    ok(f"Lexicon entries: {len(plef.LEXICON)}")
except Exception as e:
    err(f"Could not load plef_v7.py: {e}")
    _safe__safe_input("\nPress Enter to exit..."); sys.exit(1)

# ── Progress bar ──────────────────────────────────────────────────────────────
def progress_bar(current, total, start_time, width=40):
    pct   = current / max(1, total)
    filled = int(pct * width)
    bar   = f"{GRN}{'█'*filled}{DIM}{'░'*(width-filled)}{RST}"
    elapsed = time.time() - start_time
    eta   = (elapsed / max(1, current)) * (total - current) if current > 0 else 0
    eta_s = f"{int(eta//60)}m{int(eta%60):02d}s" if eta > 0 else "--:--"
    print(f"\r  [{bar}] {pct:>5.1%}  {current}/{total}  ETA: {eta_s}  ", end="", flush=True)

# ── Load corpus ───────────────────────────────────────────────────────────────
def load_corpus():
    """Load reddit_posts_corpus.csv. Falls back to reading individual txt files."""
    if CORPUS_CSV.exists():
        rows = []
        with open(CORPUS_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("text","").strip():
                    rows.append(row)
        ok(f"Loaded {len(rows)} posts from {CORPUS_CSV.name}")
        return rows

    # Fallback: read individual .txt files
    if REDDIT_POSTS.exists():
        warn("No reddit_posts_corpus.csv found. Reading individual .txt files...")
        rows = []
        for txt_file in sorted(REDDIT_POSTS.glob("*.txt")):
            text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                rows.append({
                    "id": txt_file.stem,
                    "text": text,
                    "sentiment": "neu",
                    "emotion": "none",
                    "attachment": "none"
                })
        ok(f"Loaded {len(rows)} posts from {REDDIT_POSTS}/")
        return rows

    err("No corpus found. Run reddit_download.py first.")
    return []

# ── Compute all metrics for one post ─────────────────────────────────────────
def analyse_post(text):
    """Run all PLEF metrics on one text. Returns dict of scores."""
    result = {}
    try:
        # Core stats
        stats     = plef.compute_stats(text)
        text_obj  = plef.score_text(text)
        sr        = text_obj["sentence_results"]

        result["n_words"]    = stats["n_words"]
        result["n_sents"]    = stats["n_sents"]
        result["flesch_re"]  = round(stats["flesch_re"], 2)
        result["sentiment"]  = round(text_obj["mean"], 4)

        # PLEF novel metrics
        gase, _  = plef.compute_gase(text, stats, sr, text_obj["horsemen"])
        pti, _   = plef.compute_pti(text)
        teg, _   = plef.compute_teg(sr)
        rci      = plef.compute_rci(text)
        pai, _   = plef.compute_pai(text, stats)
        nava, _, _, arc = plef.compute_nava(sr)
        idx_w, pre_w, post_w, drop_w, _ = plef.compute_lewi(sr)
        _, cds   = plef.compute_cogs(text)
        vads, _  = plef.compute_vads(text)
        ties, _, _, _ = plef.compute_ties(text)
        dom_att, _, _, _ = plef.analyse_attachment(text)
        ri       = plef.compute_rumination_index(text, stats) if hasattr(plef, "compute_rumination_index") else 0.0
        _, _, ri_v = plef.bootstrap_ci([text_obj["mean"]]) if sr else (0,0,0)

        result["gase"]       = gase
        result["pti"]        = pti
        result["teg"]        = round(teg, 4)
        result["rci"]        = round(rci, 4)
        result["pai"]        = round(pai, 4)
        # NA flag: arc=="short_text" means NAVA/LEWI computed on too few sentences
        # These are stored as None in CSV and filtered from correlations
        result["nava"]       = round(nava, 4) if arc != "short_text" else None
        result["nava_arc"]   = arc if arc != "short_text" else "NA"
        result["lewi_idx"]   = idx_w if idx_w is not None else None
        result["lewi_drop"]  = round(drop_w, 4) if idx_w is not None else None
        result["cd_index"]   = round(cds, 4)
        result["vads"]       = round(vads, 4)
        result["ties"]       = round(ties, 4)
        result["attachment"] = dom_att

        # Horsemen
        h = text_obj["horsemen"]
        result["horsemen_total"] = sum(h.values())
        result["criticism"]      = h.get("criticism", 0)
        result["contempt"]       = h.get("contempt", 0)
        result["defensiveness"]  = h.get("defensiveness", 0)
        result["stonewalling"]   = h.get("stonewalling", 0)

        # Baselines
        result["vader_score"] = plef.vader_score(text)
        nrc_s, nrc_emos       = plef.nrc_score(text)
        result["nrc_score"]   = nrc_s
        liwc_s, _             = plef.liwc_score(text)
        result["liwc_score"]  = liwc_s

        # Emotion totals
        emos = text_obj.get("emotion_totals", {})
        for emo in ["anger","sadness","fear","joy","trust","disgust","surprise","anticipation"]:
            result[f"emo_{emo}"] = emos.get(emo, 0)

    except Exception as e:
        result["_error"] = str(e)

    return result

# ── Statistics helpers ────────────────────────────────────────────────────────
def mean(v):    return sum(v)/len(v) if v else 0.0
def stdev(v):
    if len(v) < 2: return 0.0
    m = mean(v); return math.sqrt(sum((x-m)**2 for x in v)/(len(v)-1))
def median(v):
    s = sorted(v); n = len(s)
    return (s[n//2-1]+s[n//2])/2 if n%2==0 else s[n//2] if n else 0.0

def corpus_summary(rows_data, metric):
    vals = [r[metric] for r in rows_data if isinstance(r.get(metric), (int,float))]
    if not vals: return {"mean":0,"sd":0,"median":0,"min":0,"max":0,"n":0}
    return {"mean":round(mean(vals),4), "sd":round(stdev(vals),4),
            "median":round(median(vals),4),
            "min":round(min(vals),4), "max":round(max(vals),4), "n":len(vals)}

# ── Baseline evaluation ───────────────────────────────────────────────────────
def evaluate_system(scores, gold_labels):
    """Compute P/R/F1/Acc for a system given continuous scores and gold labels."""
    classes = ["pos","neg","neu"]
    def lbl(s): return "pos" if s>0.05 else ("neg" if s<-0.05 else "neu")
    preds = [lbl(s) for s in scores]
    tp={c:0 for c in classes}; fp={c:0 for c in classes}; fn={c:0 for c in classes}
    for pred,gold in zip(preds,gold_labels):
        for c in classes:
            if pred==c and gold==c: tp[c]+=1
            elif pred==c and gold!=c: fp[c]+=1
            elif pred!=c and gold==c: fn[c]+=1
    metrics={}
    for c in classes:
        p=tp[c]/(tp[c]+fp[c]) if tp[c]+fp[c] else 0
        r=tp[c]/(tp[c]+fn[c]) if tp[c]+fn[c] else 0
        f=2*p*r/(p+r) if p+r else 0
        metrics[c]={"P":round(p,3),"R":round(r,3),"F1":round(f,3)}
    macro_f1 = round(sum(metrics[c]["F1"] for c in classes)/3, 3)
    acc = round(sum(1 for p,g in zip(preds,gold_labels) if p==g)/max(1,len(gold_labels)),3)
    return macro_f1, acc, metrics

def compute_roc_auc(y_true_bin, y_scores):
    pairs = sorted(zip(y_scores, y_true_bin), key=lambda x: -x[0])
    n_pos = sum(y_true_bin); n_neg = len(y_true_bin)-n_pos
    if n_pos==0 or n_neg==0: return 0.5
    tp=fp=0; fpr=[0.0]; tpr=[0.0]; prev=None
    for score,label in pairs:
        if score!=prev and prev is not None:
            fpr.append(fp/n_neg); tpr.append(tp/n_pos)
        if label==1: tp+=1
        else: fp+=1
        prev=score
    fpr.append(1.0); tpr.append(1.0)
    auc=sum((fpr[i+1]-fpr[i])*(tpr[i+1]+tpr[i])/2 for i in range(len(fpr)-1))
    return round(abs(auc),4)

# ── Main pipeline ─────────────────────────────────────────────────────────────
def main():
    print(f"\n{BLD}{'='*62}")
    print(f"  PLEF Automated Research Pipeline")
    print(f"  Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*62}{RST}\n")

    # Setup results folder
    RESULTS_DIR.mkdir(exist_ok=True)
    ok(f"Results will be saved to: {RESULTS_DIR}")

    # Load corpus
    head("STEP 1 of 6 — Loading corpus")
    corpus = load_corpus()
    if not corpus:
        err("No data to analyse. Exiting.")
        _safe__safe_input("\nPress Enter to exit..."); return
    info(f"Total posts to analyse: {len(corpus)}")

    # ── STEP 2: Run all metrics ───────────────────────────────────────────────
    head("STEP 2 of 6 — Running PLEF metrics on all posts")
    info("This is the main analysis step. Expected time: 3-8 minutes.")
    info("Progress shown below. Do not close this window.\n")

    all_results = []
    errors      = []
    start_time  = time.time()

    for i, post in enumerate(corpus):
        progress_bar(i+1, len(corpus), start_time)
        text = post.get("text","").strip()
        if not text:
            continue
        metrics = analyse_post(text)
        metrics["id"]          = post.get("id", f"post_{i:04d}")
        metrics["gold_sentiment"] = post.get("sentiment","neu")
        metrics["gold_emotion"]   = post.get("emotion","none")
        all_results.append(metrics)
        if "_error" in metrics:
            errors.append((metrics["id"], metrics["_error"]))

    print()  # end progress bar line
    elapsed = time.time() - start_time
    ok(f"Analysis complete in {elapsed:.0f} seconds")
    ok(f"Posts analysed: {len(all_results)}")
    if errors:
        warn(f"Posts with errors (skipped): {len(errors)}")
        for pid, emsg in errors[:5]:
            info(f"  {pid}: {emsg}")

    # ── STEP 3: Save all metrics CSV ─────────────────────────────────────────
    head("STEP 3 of 6 — Saving results files")

    good_results = [r for r in all_results if "_error" not in r]

    # File 1: all_posts_metrics.csv
    metrics_path = RESULTS_DIR / "all_posts_metrics.csv"
    if good_results:
        fields = list(good_results[0].keys())
        with open(metrics_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(good_results)
        ok(f"all_posts_metrics.csv  ({len(good_results)} rows, {len(fields)} columns)")

    # File 2: corpus_summary.csv
    summary_metrics = ["sentiment","gase","pti","teg","rci","pai",
                        "nava","lewi_drop","cd_index","vads","ties",
                        "vader_score","nrc_score","liwc_score","n_words"]
    summary_rows = []
    for m in summary_metrics:
        s = corpus_summary(good_results, m)
        s["metric"] = m
        summary_rows.append(s)
    summary_path = RESULTS_DIR / "corpus_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric","mean","sd","median","min","max","n"])
        writer.writeheader(); writer.writerows(summary_rows)
    ok(f"corpus_summary.csv  (summary statistics for all metrics)")

    # ── STEP 4: Baseline comparison ───────────────────────────────────────────
    head("STEP 4 of 6 — Baseline comparison (PLEF vs VADER vs NRC vs LIWC)")
    gold_map  = {"pos":1.0,"neu":0.0,"neg":-1.0}
    gold_lbls = [r["gold_sentiment"] for r in good_results]
    gold_num  = [gold_map.get(g, 0.0) for g in gold_lbls]

    systems = {
        "PLEF":  [r["sentiment"]   for r in good_results],
        "VADER": [r["vader_score"] for r in good_results],
        "NRC":   [r["nrc_score"]   for r in good_results],
        "LIWC":  [r["liwc_score"]  for r in good_results],
    }

    baseline_rows = []
    classes = ["pos","neg","neu"]
    for sys_name, scores in systems.items():
        macro_f1, acc, cls_metrics = evaluate_system(scores, gold_lbls)
        # Pearson r vs gold numeric
        r_val, p_val = plef.pearson_with_p(scores, gold_num)
        # AUC per class
        auc_scores = {}
        for cls in classes:
            y_bin  = [1 if g==cls else 0 for g in gold_lbls]
            y_sc   = [-s for s in scores] if cls=="neg" else ([-abs(s) for s in scores] if cls=="neu" else scores[:])
            auc_scores[cls] = compute_roc_auc(y_bin, y_sc)
        macro_auc = round(sum(auc_scores.values())/3, 4)
        row = {
            "system": sys_name,
            "macro_f1": macro_f1,
            "accuracy": acc,
            "pearson_r": r_val,
            "pearson_p": p_val,
            "auc_pos": auc_scores["pos"],
            "auc_neg": auc_scores["neg"],
            "auc_neu": auc_scores["neu"],
            "macro_auc": macro_auc,
        }
        for cls in classes:
            row[f"F1_{cls}"] = cls_metrics[cls]["F1"]
            row[f"P_{cls}"]  = cls_metrics[cls]["P"]
            row[f"R_{cls}"]  = cls_metrics[cls]["R"]
        baseline_rows.append(row)
        ok(f"{sys_name:<8}  Macro-F1={macro_f1:.3f}  AUC={macro_auc:.3f}  r={r_val:+.3f}")

    baseline_path = RESULTS_DIR / "baseline_comparison.csv"
    with open(baseline_path,"w",newline="",encoding="utf-8") as f:
        fields = list(baseline_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(baseline_rows)
    ok(f"baseline_comparison.csv saved")

    # ── STEP 5: Statistical tests ─────────────────────────────────────────────
    head("STEP 5 of 6 — Statistical tests (Pearson, Spearman, Cohen's d)")

    def p_label(p):
        if p<=0.001: return "***"
        if p<=0.01:  return "**"
        if p<=0.05:  return "*"
        return "ns"

    metric_pairs = [
        ("sentiment","gase",    "Expected +ve: more positive sentiment → higher GASE"),
        ("sentiment","cd_index","Expected -ve: more negative → more cognitive distortions"),
        ("sentiment","vads",    "Expected +ve: positive language → deeper disclosure"),
        ("pti","cd_index",      "Expected +ve: self-focus → more distortions"),
        ("pti","pai",           "Expected +ve: I-dominant → power asymmetry"),
        ("gase","lewi_drop",    "Expected -ve: higher health → smaller watershed drop"),
        ("teg","ties",          "Expected +ve: volatility → more contradictions"),
        ("vads","gase",         "Expected +ve: deeper disclosure → healthier expression"),
        ("nava","lewi_drop",    "Expected +ve: tragic arc → larger sentiment drop"),
        ("cd_index","ties",     "Expected +ve: distortions → inconsistency"),
    ]

    stat_rows = []
    for m1, m2, hypothesis in metric_pairs:
        x = [r[m1] for r in good_results if isinstance(r.get(m1),(int,float)) and isinstance(r.get(m2),(int,float))]
        y = [r[m2] for r in good_results if isinstance(r.get(m1),(int,float)) and isinstance(r.get(m2),(int,float))]
        if len(x) < 10: continue
        r_val, p_r = plef.pearson_with_p(x, y)
        rho, p_s   = plef.spearman_with_p(x, y)
        # Direction check
        expected_pos = "Expected +ve" in hypothesis
        direction_ok = (r_val>0 and expected_pos) or (r_val<0 and not expected_pos)
        stat_rows.append({
            "metric_1": m1, "metric_2": m2,
            "pearson_r": r_val, "pearson_p": p_r, "pearson_sig": p_label(p_r),
            "spearman_rho": rho, "spearman_p": p_s, "spearman_sig": p_label(p_s),
            "direction_correct": "YES" if direction_ok else "NO",
            "hypothesis": hypothesis, "n": len(x)
        })
        d_icon = f"{GRN}✓{RST}" if direction_ok else f"{RED}✗{RST}"
        print(f"  {d_icon} {m1:<14} × {m2:<14}  r={r_val:+.3f} {p_label(p_r):<4}  ρ={rho:+.3f} {p_label(p_s)}")

    stat_path = RESULTS_DIR / "statistical_tests.csv"
    with open(stat_path,"w",newline="",encoding="utf-8") as f:
        if stat_rows:
            writer = csv.DictWriter(f, fieldnames=list(stat_rows[0].keys()))
            writer.writeheader(); writer.writerows(stat_rows)
    ok(f"statistical_tests.csv saved  ({len(stat_rows)} correlation pairs)")

    # Cohen's d: positive vs negative posts
    pos_sentiment = [r["sentiment"] for r in good_results if r["gold_sentiment"]=="pos"]
    neg_sentiment = [r["sentiment"] for r in good_results if r["gold_sentiment"]=="neg"]
    d_val, g_val  = plef.cohens_d(pos_sentiment, neg_sentiment) if pos_sentiment and neg_sentiment else (0,0)
    mag = "Large" if abs(d_val)>=0.8 else "Medium" if abs(d_val)>=0.5 else "Small"
    ok(f"Effect size (pos vs neg PLEF scores): Cohen's d={d_val:+.3f}  Hedges' g={g_val:+.3f}  ({mag})")

    # ── STEP 6: Generate paper tables ────────────────────────────────────────
    head("STEP 6 of 6 — Generating LaTeX paper tables")
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    n   = len(good_results)

    # Table 1: Corpus summary
    t1_metrics = ["sentiment","gase","pti","teg","nava","lewi_drop","cd_index","vads","ties"]
    t1_labels  = {
        "sentiment": "Sentiment (PLEF-VADER)",
        "gase":      "GASE (composite health)",
        "pti":       "PTI (pronoun power)",
        "teg":       "TEG (emotional volatility)",
        "nava":      "NAVA (narrative arc)",
        "lewi_drop": "LEWI drop magnitude",
        "cd_index":  "CD-index (distortions)",
        "vads":      "VADS (disclosure depth)",
        "ties":      "TIES (inconsistency)",
    }
    table1_lines = [
        f"% Table 1: PLEF Corpus Descriptive Statistics (auto-generated {now})",
        r"\begin{table}[h]",
        r"  \centering",
        f"  \\caption{{PLEF Descriptive Statistics — r/relationship\\_advice Corpus ($N={n}$)}}",
        r"  \begin{tabular}{lrrrrrr}",
        r"    \toprule",
        r"    Metric & $\mu$ & SD & Median & Min & Max & $n$ \\",
        r"    \midrule",
    ]
    for m in t1_metrics:
        s = corpus_summary(good_results, m)
        lbl = t1_labels.get(m, m)
        table1_lines.append(
            f"    {lbl} & {s['mean']:+.4f} & {s['sd']:.4f} & "
            f"{s['median']:+.4f} & {s['min']:+.4f} & {s['max']:+.4f} & {s['n']} \\\\"
        )
    table1_lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ]
    t1_path = RESULTS_DIR / "paper_table1.txt"
    t1_path.write_text("\n".join(table1_lines), encoding="utf-8")
    ok("paper_table1.txt  (LaTeX — corpus descriptive statistics)")

    # Table 2: Baseline comparison
    table2_lines = [
        f"% Table 2: Baseline Comparison (auto-generated {now})",
        r"\begin{table}[h]",
        r"  \centering",
        r"  \caption{Baseline Comparison — Macro-F1, Macro-AUC, Pearson $r$ vs Gold Labels}",
        r"  \begin{tabular}{lrrrrr}",
        r"    \toprule",
        r"    System & Macro-F1 & Accuracy & Macro-AUC & Pearson $r$ & $p$ \\",
        r"    \midrule",
    ]
    for row in baseline_rows:
        sig = "***" if row["pearson_p"]<=0.001 else "**" if row["pearson_p"]<=0.01 else "*" if row["pearson_p"]<=0.05 else "ns"
        table2_lines.append(
            f"    {row['system']} & {row['macro_f1']:.3f} & {row['accuracy']:.3f} & "
            f"{row['macro_auc']:.3f} & {row['pearson_r']:+.3f} & {sig} \\\\"
        )
    table2_lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    t2_path = RESULTS_DIR / "paper_table2.txt"
    t2_path.write_text("\n".join(table2_lines), encoding="utf-8")
    ok("paper_table2.txt  (LaTeX — baseline comparison)")

    # Table 3: Statistical tests
    table3_lines = [
        f"% Table 3: Correlation Analysis (auto-generated {now})",
        r"\begin{table}[h]",
        r"  \centering",
        r"  \caption{Inter-metric Correlations — Pearson $r$ and Spearman $\rho$}",
        r"  \begin{tabular}{llrrrrl}",
        r"    \toprule",
        r"    Metric 1 & Metric 2 & $r$ & $p$ & $\rho$ & $p$ & Direction \\",
        r"    \midrule",
    ]
    for row in stat_rows:
        table3_lines.append(
            f"    {row['metric_1']} & {row['metric_2']} & "
            f"{row['pearson_r']:+.3f} & {row['pearson_sig']} & "
            f"{row['spearman_rho']:+.3f} & {row['spearman_sig']} & "
            f"{row['direction_correct']} \\\\"
        )
    table3_lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    t3_path = RESULTS_DIR / "paper_table3.txt"
    t3_path.write_text("\n".join(table3_lines), encoding="utf-8")
    ok("paper_table3.txt  (LaTeX — statistical tests)")

    # Full text report
    report_lines = [
        "="*62,
        "PLEF AUTOMATED ANALYSIS REPORT",
        f"Generated: {now}",
        f"Corpus: r/relationship_advice  N={n} posts",
        "="*62, "",
        "CORPUS DESCRIPTIVE STATISTICS",
        "-"*40,
    ]
    for m in t1_metrics:
        s = corpus_summary(good_results, m)
        report_lines.append(f"  {t1_labels.get(m,m):<35} μ={s['mean']:+.4f}  SD={s['sd']:.4f}")
    report_lines += ["", "BASELINE COMPARISON", "-"*40]
    for row in baseline_rows:
        report_lines.append(
            f"  {row['system']:<8}  Macro-F1={row['macro_f1']:.3f}  "
            f"AUC={row['macro_auc']:.3f}  r={row['pearson_r']:+.3f}"
        )
    report_lines += ["", "CORRELATION ANALYSIS", "-"*40]
    for row in stat_rows:
        report_lines.append(
            f"  {row['metric_1']:<14} x {row['metric_2']:<14}  "
            f"r={row['pearson_r']:+.3f}{row['pearson_sig']:<4}  "
            f"ρ={row['spearman_rho']:+.3f}{row['spearman_sig']:<4}  "
            f"direction={row['direction_correct']}"
        )
    report_lines += [
        "", "EFFECT SIZE", "-"*40,
        f"  Cohen's d (pos vs neg PLEF sentiment): d={d_val:+.3f}  g={g_val:+.3f}  ({mag})",
        "", "="*62,
        "FILES SAVED", "-"*40,
        f"  {RESULTS_DIR}/",
        "    all_posts_metrics.csv     (all metrics for all posts)",
        "    corpus_summary.csv        (mean, SD, min, max)",
        "    baseline_comparison.csv   (PLEF vs VADER vs NRC vs LIWC)",
        "    statistical_tests.csv     (Pearson, Spearman, p-values)",
        "    paper_table1.txt          (LaTeX Table 1)",
        "    paper_table2.txt          (LaTeX Table 2)",
        "    paper_table3.txt          (LaTeX Table 3)",
        "    full_report.txt           (this report)",
        "="*62,
    ]
    report_path = RESULTS_DIR / "full_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    ok("full_report.txt saved")

    # ── Done ─────────────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    print(f"\n{BLD}{GRN}{'='*62}")
    print(f"  ALL DONE in {elapsed_total:.0f} seconds")
    print(f"  Open the results\\ folder to find all your files.")
    print(f"{'='*62}{RST}\n")
    print(f"  {BLD}NEXT STEP FOR YOUR PAPER:{RST}")
    print(f"  1. Open  results\\full_report.txt     ← your results summary")
    print(f"  2. Open  results\\paper_table1.txt    ← copy into your LaTeX paper")
    print(f"  3. Open  results\\paper_table2.txt    ← baseline comparison table")
    print(f"  4. Open  results\\paper_table3.txt    ← statistical tests table")
    print(f"  5. Open  results\\all_posts_metrics.csv in Excel for further analysis\n")

    _safe_input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
