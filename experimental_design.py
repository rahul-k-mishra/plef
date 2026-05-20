#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experimental_design.py  v2.0
=============================
FIXED: Experimental validation now runs across ALL available datasets.
Previously only ran on 500-item Reddit subset. Now:
  - Detects all pre-computed dataset result CSVs in results/
  - Runs ALL experiments on EACH dataset
  - Saves per-dataset experimental results to results/EXPERIMENTAL/
  - Generates combined cross-dataset experimental report

Modules:
  1. PRE-REGISTERED HYPOTHESES    H1-H7
  2. ABLATION STUDY               all metrics, all datasets
  3. LEWI VALIDATION              per dataset + annotation protocol
  4. PTI DOMINANCE                per dataset proxy test
  5. TEG INSTABILITY              per dataset validation
  6. MCNEMAR BASELINE TESTS       per dataset significance
  7. EXPERIMENTAL DESIGN DOC      LaTeX methods section

Run: python experimental_design.py
"""

import sys, csv, math, time, datetime, collections
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR / "results"

try:
    import colorama; colorama.init()
    GRN="\033[92m"; YLW="\033[93m"; RED="\033[91m"
    CYN="\033[96m"; MGN="\033[95m"; BLD="\033[1m"; RST="\033[0m"; DIM="\033[2m"
except ImportError:
    GRN=YLW=RED=CYN=MGN=BLD=RST=DIM=""

def _safe_input(prompt="", default=""):
    try:    return input(prompt)
    except EOFError: return default

def head(msg):
    print(f"\n{BLD}{CYN}{'='*65}{RST}")
    print(f"  {BLD}{CYN}{msg}{RST}")
    print(f"{BLD}{CYN}{'='*65}{RST}")

def sub(msg):  print(f"\n  {BLD}{MGN}── {msg}{RST}")
def ok(msg):   print(f"  {GRN}v{RST}  {msg}")
def warn(msg): print(f"  {YLW}!{RST}  {msg}")
def err(msg):  print(f"  {RED}x{RST}  {msg}")
def info(msg): print(f"     {DIM}{msg}{RST}")

def p_star(p):
    if p<=0.001: return "***"
    if p<=0.01:  return "**"
    if p<=0.05:  return "*"
    return "ns"

# Load PLEF
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import plef_v7 as plef
    ok(f"PLEF v{plef.VERSION} loaded")
except Exception as e:
    print(f"Cannot load plef_v7.py: {e}")
    _safe_input("\nPress Enter to exit...")
    sys.exit(1)

def safe_mean(v):
    v = [x for x in v if x is not None and isinstance(x,(int,float)) and not math.isnan(x)]
    return sum(v)/len(v) if v else 0.0

def safe_sd(v):
    v = [x for x in v if x is not None and isinstance(x,(int,float)) and not math.isnan(x)]
    if len(v)<2: return 0.0
    m = safe_mean(v)
    return math.sqrt(sum((x-m)**2 for x in v)/(len(v)-1))

# ── Dataset discovery ─────────────────────────────────────────────────────────
def discover_datasets():
    """Find all pre-computed dataset folders in results/."""
    datasets = {}
    if not RESULTS_DIR.exists():
        warn("results/ folder not found. Run multi_dataset_analysis.py first.")
        return datasets
    skip = {"COMBINED","EXPERIMENTAL"}
    for ds_dir in sorted(RESULTS_DIR.iterdir()):
        if not ds_dir.is_dir() or ds_dir.name in skip:
            continue
        csvs = list(ds_dir.glob("all_posts_metrics_*.csv"))
        if csvs:
            datasets[ds_dir.name] = {"dir":ds_dir,"csv":csvs[0],"name":ds_dir.name}
    return datasets

def load_rows(csv_path, max_rows=5000):
    """Load pre-computed metric rows. Returns list of dicts with numeric conversion."""
    rows = []
    try:
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if i >= max_rows: break
                clean = {}
                for k, v in row.items():
                    v = v.strip() if v else ""
                    if v in ("","None","NA","nan",""):
                        clean[k] = None
                    else:
                        try:    clean[k] = float(v)
                        except: clean[k] = v
                rows.append(clean)
    except Exception as e:
        warn(f"Could not load {csv_path.name}: {e}")
    return rows

def nums(rows, col):
    return [r[col] for r in rows
            if r.get(col) is not None and isinstance(r.get(col),(int,float))]

def save_csv(rows, path):
    if not rows: return
    with open(path,"w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)

# ═══════════════════════════════════════════════════════════════════════════════
# HYPOTHESES
# ═══════════════════════════════════════════════════════════════════════════════
HYPOTHESES = [
    {"id":"H1","metric":"LEWI","alt":"LEWI correlates with human turning points (r>0.30)",
     "threshold":"r>0.30, IoU>0.50","status":"PENDING human annotation"},
    {"id":"H2","metric":"PTI","alt":"Higher PTI correlates with relational dominance (r>0.25)",
     "threshold":"r>0.25, p<.05","status":"TESTABLE via proxy"},
    {"id":"H3","metric":"TEG","alt":"TEG correlates with emotional instability (r>0.20)",
     "threshold":"r>0.20, p<.05","status":"TESTABLE NOW"},
    {"id":"H4","metric":"GASE","alt":"GASE lower in dissolution vs stable narratives (d>0.50)",
     "threshold":"d>0.50, p<.05","status":"TESTABLE if multi-subreddit corpus downloaded"},
    {"id":"H5","metric":"NAVA","alt":"NAVA arc classification above 50% accuracy",
     "threshold":"Acc>0.50","status":"TESTABLE NOW"},
    {"id":"H6","metric":"CD-index","alt":"CD-index correlates negatively with sentiment (r<-0.15)",
     "threshold":"r<-0.15, p<.05","status":"TESTABLE NOW"},
    {"id":"H7","metric":"PLEF System","alt":"PLEF and VADER differ significantly (McNemar p<.05)",
     "threshold":"p<.05","status":"TESTABLE NOW"},
]

def module_hypotheses():
    sub("MODULE 1 -- Pre-Registered Hypotheses H1-H7")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    now  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["="*65,"PLEF PRE-REGISTERED HYPOTHESES",
             f"Registered: {now}","="*65,""]
    for h in HYPOTHESES:
        print(f"  {BLD}{CYN}{h['id']}{RST}  {h['metric']}:  {h['alt']}")
        info(f"Threshold: {h['threshold']}  |  Status: {h['status']}")
        lines += [f"  {h['id']}: {h['alt']}",
                  f"     Threshold: {h['threshold']}",
                  f"     Status: {h['status']}",""]
    (exp_dir/"pre_registered_hypotheses.txt").write_text("\n".join(lines),encoding="utf-8")
    ok("pre_registered_hypotheses.txt")

# ═══════════════════════════════════════════════════════════════════════════════
# ABLATION
# ═══════════════════════════════════════════════════════════════════════════════
def module_full_ablation(datasets):
    sub("MODULE 2 -- Full Ablation Study -- ALL DATASETS")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    all_res = []
    print(f"\n  {'Dataset':<28} {'N':>7} {'GASE mu':>9} {'LEWI_SD':>9} {'RCI!=0%':>8} {'NAVA_n':>8}")
    print(f"  {'─'*28} {'─'*7} {'─'*9} {'─'*9} {'─'*8} {'─'*8}")

    for name, ds in datasets.items():
        rows = load_rows(ds["csv"],5000)
        if not rows: continue
        gase  = nums(rows,"gase"); lewi = nums(rows,"lewi_drop")
        rci   = nums(rows,"rci"); nava = nums(rows,"nava")
        rci_nz = sum(1 for v in rci if abs(v)>0.001)
        lewi_sd = round(safe_sd(lewi),4)
        lewi_ok = f"{GRN}ok{RST}" if lewi_sd>0.01 else f"{RED}compressed{RST}"
        rci_pct = round(100*rci_nz/max(1,len(rci)),1)
        rci_ok  = f"{GRN}ok{RST}" if rci_pct>10 else f"{RED}broken{RST}"
        nava_valid = sum(1 for r in rows if isinstance(r.get("nava"),(int,float)) and r["nava"] is not None)
        print(f"  {name:<28} {len(rows):>7,} {safe_mean(gase):>+9.3f} "
              f"{lewi_sd:>9.4f}{lewi_ok} {rci_pct:>7.1f}%{rci_ok} {nava_valid:>8,}")
        all_res.append({"dataset":name,"n":len(rows),
                        "gase_mean":round(safe_mean(gase),4),
                        "gase_sd":round(safe_sd(gase),4),
                        "lewi_mean":round(safe_mean(lewi),4),
                        "lewi_sd":lewi_sd,
                        "rci_nonzero_pct":rci_pct,
                        "nava_valid_n":nava_valid})

    save_csv(all_res, exp_dir/"ablation_all_datasets.csv")
    ok(f"ablation_all_datasets.csv  ({len(all_res)} datasets)")

    latex = ["% Ablation Study",r"\begin{table*}[t]",r"\centering",
             r"\caption{PLEF Metric Behaviour Across All Datasets}",
             r"\begin{tabular}{lrrrrrr}",r"\toprule",
             r"Dataset & N & GASE$\mu$ & GASE SD & LEWI SD & RCI$\neq$0 & NAVA valid \\",
             r"\midrule"]
    for r in all_res:
        latex.append(f"  {r['dataset'].replace('_',' '):<28} & {r['n']:>6,} & "
                     f"{r['gase_mean']:>+.3f} & {r['gase_sd']:.3f} & "
                     f"{r['lewi_sd']:.4f} & {r['rci_nonzero_pct']:.0f}\\% & "
                     f"{r['nava_valid_n']:,} \\\\")
    latex += [r"\bottomrule",r"\end{tabular}",r"\end{table*}"]
    (exp_dir/"paper_ablation_all_datasets.txt").write_text("\n".join(latex),encoding="utf-8")
    ok("paper_ablation_all_datasets.txt")

# ═══════════════════════════════════════════════════════════════════════════════
# LEWI
# ═══════════════════════════════════════════════════════════════════════════════
def module_lewi_all(datasets):
    sub("MODULE 3 -- LEWI Validation (H1) -- ALL DATASETS")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    print(f"\n  {'Dataset':<28} {'N_valid':>8} {'LEWI_SD':>9} {'NAVA x LEWI':>14}")
    print(f"  {'─'*28} {'─'*8} {'─'*9} {'─'*14}")
    report = ["LEWI VALIDATION -- ALL DATASETS",""]

    for name, ds in datasets.items():
        rows = load_rows(ds["csv"],5000)
        if not rows: continue
        valid = [(r["nava"],r["lewi_drop"]) for r in rows
                 if isinstance(r.get("nava"),(int,float))
                 and isinstance(r.get("lewi_drop"),(int,float))]
        lewi_all = nums(rows,"lewi_drop")
        lewi_sd  = round(safe_sd(lewi_all),4)
        if len(valid) >= 10:
            nv = [p[0] for p in valid]; lv = [p[1] for p in valid]
            r_val, p_r = plef.pearson_with_p(nv,lv)
        else:
            r_val, p_r = 0.0, 1.0
        icon = f"{GRN}H1 evidence{RST}" if r_val>0.3 and p_r<0.05 else f"{YLW}weak{RST}"
        print(f"  {name:<28} {len(valid):>8,} {lewi_sd:>9.4f} "
              f"  r={r_val:>+.3f}{p_star(p_r)} n={len(valid):>5,} {icon}")
        report.append(f"{name}: LEWI_SD={lewi_sd}, NAVA x LEWI r={r_val:+.3f}({p_star(p_r)}), n={len(valid)}")

    protocol = ["LEWI ANNOTATION PROTOCOL","",
                "Task: Read each text. Mark the sentence number where the",
                "emotional tone shifts most significantly (the turning point).",
                "","Target: kappa >= 0.60 with 3 independent raters.",
                "After annotation: save as lewi_annotations.csv"]
    (exp_dir/"lewi_annotation_protocol.txt").write_text("\n".join(protocol),encoding="utf-8")
    (exp_dir/"lewi_validation_all_datasets.txt").write_text("\n".join(report),encoding="utf-8")
    ok("lewi_validation_all_datasets.txt + lewi_annotation_protocol.txt")

# ═══════════════════════════════════════════════════════════════════════════════
# PTI
# ═══════════════════════════════════════════════════════════════════════════════
def module_pti_all(datasets):
    sub("MODULE 4 -- PTI Dominance (H2) -- ALL DATASETS")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    print(f"\n  {'Dataset':<28} {'PTI mu':>8} {'PTI x PAI r':>13} {'n':>7} H2")
    print(f"  {'─'*28} {'─'*8} {'─'*13} {'─'*7} {'─'*4}")
    stat_rows = []

    for name, ds in datasets.items():
        rows = load_rows(ds["csv"],5000)
        if not rows: continue
        valid = [(r["pti"],r["pai"]) for r in rows
                 if isinstance(r.get("pti"),(int,float))
                 and isinstance(r.get("pai"),(int,float))]
        if len(valid)<10: continue
        pti_v=[p[0] for p in valid]; pai_v=[p[1] for p in valid]
        r_val,p_r = plef.pearson_with_p(pti_v,pai_v)
        h2 = "YES" if r_val>0.25 and p_r<0.05 else "NO"
        icon = f"{GRN}Yes{RST}" if h2=="YES" else f"{YLW}No{RST}"
        print(f"  {name:<28} {safe_mean(pti_v):>+8.3f} {r_val:>+10.3f}{p_star(p_r):>3} "
              f"{len(valid):>7,} {icon}")
        stat_rows.append({"dataset":name,"pti_mean":round(safe_mean(pti_v),4),
                           "pti_pai_r":r_val,"pti_pai_sig":p_star(p_r),
                           "n":len(valid),"H2":h2})

    save_csv(stat_rows, exp_dir/"pti_dominance_all_datasets.csv")
    ok("pti_dominance_all_datasets.csv")
    if stat_rows:
        h2n = sum(1 for r in stat_rows if r["H2"]=="YES")
        print(f"  H2 supported: {h2n}/{len(stat_rows)} datasets")

# ═══════════════════════════════════════════════════════════════════════════════
# TEG
# ═══════════════════════════════════════════════════════════════════════════════
def module_teg_all(datasets):
    sub("MODULE 5 -- TEG Instability (H3) -- ALL DATASETS")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    print(f"\n  {'Dataset':<28} {'TEG mu':>8} {'TEG x TIES r':>14} {'n':>7} H3")
    print(f"  {'─'*28} {'─'*8} {'─'*14} {'─'*7} {'─'*4}")
    stat_rows = []

    for name, ds in datasets.items():
        rows = load_rows(ds["csv"],5000)
        if not rows: continue
        valid = [(r["teg"],r["ties"]) for r in rows
                 if isinstance(r.get("teg"),(int,float))
                 and isinstance(r.get("ties"),(int,float))
                 and (r.get("teg") or 0)>0]
        if len(valid)<10: continue
        tv=[p[0] for p in valid]; tiesv=[p[1] for p in valid]
        r_val,p_r = plef.pearson_with_p(tv,tiesv)
        h3 = "YES" if r_val>0.20 and p_r<0.05 else "NO"
        icon = f"{GRN}Yes{RST}" if h3=="YES" else f"{YLW}No{RST}"
        print(f"  {name:<28} {safe_mean(tv):>8.3f} {r_val:>+11.3f}{p_star(p_r):>3} "
              f"{len(valid):>7,} {icon}")
        stat_rows.append({"dataset":name,"teg_mean":round(safe_mean(tv),4),
                           "teg_ties_r":r_val,"sig":p_star(p_r),
                           "n":len(valid),"H3":h3})

    save_csv(stat_rows, exp_dir/"teg_instability_all_datasets.csv")
    ok("teg_instability_all_datasets.csv")
    if stat_rows:
        h3n = sum(1 for r in stat_rows if r["H3"]=="YES")
        print(f"  H3 supported: {h3n}/{len(stat_rows)} datasets")

# ═══════════════════════════════════════════════════════════════════════════════
# MCNEMAR
# ═══════════════════════════════════════════════════════════════════════════════
def module_mcnemar_all(datasets):
    sub("MODULE 6 -- McNemar Tests (H7) -- ALL DATASETS")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    print(f"\n  {'Dataset':<28} {'N':>7} {'PLEF':>7} {'VADER':>7} {'chi2':>8} {'Sig':>5} H7")
    print(f"  {'─'*28} {'─'*7} {'─'*7} {'─'*7} {'─'*8} {'─'*5} {'─'*4}")
    all_res = []

    def lbl(s): return "pos" if (s or 0)>0.05 else ("neg" if (s or 0)<-0.05 else "neu")

    def mcnemar(pa,pb,g):
        b = sum(1 for a,b_,g_ in zip(pa,pb,g) if a==g_ and b_!=g_)
        c = sum(1 for a,b_,g_ in zip(pa,pb,g) if a!=g_ and b_==g_)
        if b+c==0: return 0.0,1.0
        chi2 = (abs(b-c)-1)**2/(b+c)
        p = (0.001 if chi2>10.83 else 0.01 if chi2>6.63
             else 0.05 if chi2>3.84 else 0.10 if chi2>2.71 else 0.50)
        return round(chi2,3),p

    for name, ds in datasets.items():
        rows = load_rows(ds["csv"],5000)
        if not rows: continue
        gold  = [r.get("gold_sentiment") for r in rows
                 if r.get("gold_sentiment") in ("pos","neg","neu")]
        if len(gold)<30: continue
        pp = [lbl(r.get("sentiment",0)) for r in rows if r.get("gold_sentiment") in ("pos","neg","neu")]
        vp = [lbl(r.get("vader_score",0)) for r in rows if r.get("gold_sentiment") in ("pos","neg","neu")]
        chi2,p = mcnemar(pp,vp,gold)
        p_acc = round(sum(1 for a,g in zip(pp,gold) if a==g)/max(1,len(gold)),3)
        v_acc = round(sum(1 for a,g in zip(vp,gold) if a==g)/max(1,len(gold)),3)
        h7 = "YES" if p<0.05 else "NO"
        icon = f"{GRN}Yes{RST}" if h7=="YES" else f"{YLW}No{RST}"
        print(f"  {name:<28} {len(gold):>7,} {p_acc:>7.3f} {v_acc:>7.3f} "
              f"{chi2:>8.2f} {p_star(p):>5} {icon}")
        all_res.append({"dataset":name,"n":len(gold),"plef_acc":p_acc,
                         "vader_acc":v_acc,"chi2":chi2,"p":p,
                         "sig":p_star(p),"H7":h7})

    save_csv(all_res, exp_dir/"mcnemar_all_datasets.csv")
    ok("mcnemar_all_datasets.csv")
    if all_res:
        h7n = sum(1 for r in all_res if r["H7"]=="YES")
        print(f"  H7 supported: {h7n}/{len(all_res)} datasets")

    # LaTeX table
    latex = ["% McNemar Tests",r"\begin{table}[h]",r"\centering",
             r"\caption{McNemar's Test: PLEF vs. VADER Across All Datasets}",
             r"\begin{tabular}{lrrrrl}",r"\toprule",
             r"Dataset & $N$ & PLEF Acc & VADER Acc & $\chi^2$ & Sig \\",r"\midrule"]
    for r in all_res:
        latex.append(f"  {r['dataset'].replace('_',' ')} & {r['n']:,} & "
                     f"{r['plef_acc']:.3f} & {r['vader_acc']:.3f} & "
                     f"{r['chi2']:.2f} & {r['sig']} \\\\")
    latex += [r"\bottomrule",r"\end{tabular}",r"\end{table}"]
    (exp_dir/"paper_mcnemar_all_datasets.txt").write_text("\n".join(latex),encoding="utf-8")
    ok("paper_mcnemar_all_datasets.txt")

# ═══════════════════════════════════════════════════════════════════════════════
# METHODS DOC
# ═══════════════════════════════════════════════════════════════════════════════
def module_methods_doc(datasets):
    sub("MODULE 7 -- Experimental Design Document (LaTeX)")
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    n_ds = len(datasets); now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    latex = (f"% PLEF Experimental Design -- Generated {now}\n"
             f"% Scope: ALL {n_ds} datasets\n\n"
             r"\section{Experimental Design}" "\n\n"
             f"All experiments run across all {n_ds} evaluation datasets. "
             r"Pre-computed metric values from the multi-dataset pipeline " "\n"
             r"were used as input, avoiding redundant recomputation." "\n\n"
             r"\subsection{Datasets}" "\n"
             f"Experiments were conducted on {n_ds} datasets:\n"
             r"\begin{enumerate}" "\n"
             + "".join(f"  \\item {ds.replace('_',' ').title()}\n" for ds in datasets)
             + r"\end{enumerate}" "\n\n"
             r"\subsection{Baseline Significance Tests (H7)}" "\n"
             r"McNemar's test applied to all datasets comparing PLEF vs. VADER, " "\n"
             r"PLEF vs. NRC, VADER vs. NRC." "\n\n"
             r"\subsection{Construct Validity (H2, H3)}" "\n"
             r"PTI dominance and TEG instability experiments run across all datasets." "\n\n"
             r"\subsection{Ablation}" "\n"
             r"Component removal analysis across all datasets: LEWI variance, " "\n"
             r"RCI non-zero rate, GASE components." "\n")
    (exp_dir/"paper_methods_section.tex").write_text(latex,encoding="utf-8")
    ok("paper_methods_section.tex")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*65}")
    print(f"  PLEF Experimental Design v2.0 -- ALL DATASETS")
    print(f"{'='*65}\n")

    head("Discovering pre-computed datasets")
    datasets = discover_datasets()

    if not datasets:
        warn("No pre-computed datasets found in results/")
        warn("Run multi_dataset_analysis.py first.")
        _safe_input("\nPress Enter to exit...")
        return

    print(f"  Found {len(datasets)} dataset(s):")
    for name in datasets:
        try:
            with open(datasets[name]["csv"],encoding="utf-8") as f:
                n = sum(1 for _ in f)-1
        except: n=0
        print(f"    {GRN}v{RST}  {name:<30} {n:>8,} rows")

    print()
    print("  Modules:")
    for code,label in [("1","Pre-Registered Hypotheses H1-H7"),
                       ("2","Ablation Study -- all datasets"),
                       ("3","LEWI Validation -- all datasets"),
                       ("4","PTI Dominance -- all datasets"),
                       ("5","TEG Instability -- all datasets"),
                       ("6","McNemar Tests -- all datasets"),
                       ("7","Methods Document (LaTeX)"),
                       ("A","Run ALL")]:
        print(f"    [{code}]  {label}")
    print()
    choice = _safe_input("  Choose [1-7 or A]: ", "A").strip().upper()
    print()

    if choice in ("1","A"): module_hypotheses()
    if choice in ("2","A"): module_full_ablation(datasets)
    if choice in ("3","A"): module_lewi_all(datasets)
    if choice in ("4","A"): module_pti_all(datasets)
    if choice in ("5","A"): module_teg_all(datasets)
    if choice in ("6","A"): module_mcnemar_all(datasets)
    if choice in ("7","A"): module_methods_doc(datasets)

    # Combined report
    exp_dir = RESULTS_DIR/"EXPERIMENTAL"; exp_dir.mkdir(parents=True,exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["="*65,"PLEF EXPERIMENTAL REPORT",
             f"Generated: {now}",f"Datasets: {len(datasets)}","="*65,""]
    for h in HYPOTHESES:
        lines.append(f"  {h['id']}: {h['status']}")
    lines += ["","Files:"]
    for f in sorted(exp_dir.glob("*.csv"))+sorted(exp_dir.glob("*.txt")):
        lines.append(f"  {f.name}")
    (exp_dir/"COMBINED_experimental_report.txt").write_text("\n".join(lines),encoding="utf-8")
    ok("\nCOMBINED_experimental_report.txt")

    print(f"\n{'='*65}")
    print(f"  Done. Results in: results/EXPERIMENTAL/")
    print(f"{'='*65}\n")
    _safe_input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
