#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_dataset_analysis.py
=========================
Fully automated multi-dataset PLEF research pipeline.

Downloads, processes, and analyses ALL available datasets automatically.
Each dataset gets its own results folder with dataset-name-suffixed files.

DATASETS INCLUDED:
  1.  reddit_relationship  — Your 492 Reddit posts (local, always available)
  2.  goemotions           — 58k Reddit comments, ACL 2020, Google
  3.  empathetic           — 25k dialogues, EMNLP 2019, Facebook
  4.  isear                — 7.6k psychology sentences, Scherer & Wallbott 1994
  5.  semeval2017          — Twitter sentiment benchmark, SemEval 2017
  6.  dailydialog          — 13k human dialogues with emotion labels
  7.  tweeteval            — Twitter emotion evaluation benchmark
  8.  meld                 — TV show dialogue with emotion labels
  9.  consensus            — Auto-generated silver standard (no download)
  10. sentiment140         — 1.6M tweets with pos/neg labels

OUTPUT STRUCTURE:
  results/
    goemotions/
      all_posts_metrics_goemotions.csv
      corpus_summary_goemotions.csv
      baseline_comparison_goemotions.csv
      statistical_tests_goemotions.csv
      paper_table1_goemotions.txt
      paper_table2_goemotions.txt
      paper_table3_goemotions.txt
      full_report_goemotions.txt
    reddit_relationship/
      (same files with _reddit_relationship suffix)
    ...
    COMBINED/
      master_report.txt
      cross_dataset_comparison.csv
      paper_table_all_datasets.txt

Run:  python multi_dataset_analysis.py
  or: double-click run_multi_analysis.bat
"""

import sys, os, re, csv, json, math, time, ssl, shutil, gzip, tarfile, zipfile
import datetime, collections, urllib.request, urllib.error, statistics
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
DATASETS_DIR = SCRIPT_DIR / "datasets"
RESULTS_DIR  = SCRIPT_DIR / "results"
DATASETS_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# ── Colours ───────────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init()
    GRN="\033[92m";YLW="\033[93m";RED="\033[91m";CYN="\033[96m"
    MGN="\033[95m";BLD="\033[1m";RST="\033[0m";DIM="\033[2m"
except ImportError:
    GRN=YLW=RED=CYN=MGN=BLD=RST=DIM=""

def head(msg):
    print(f"\n{BLD}{CYN}{'═'*65}{RST}")
    print(f"  {BLD}{CYN}{msg}{RST}")
    print(f"{BLD}{CYN}{'═'*65}{RST}")

def subhead(msg): print(f"\n  {BLD}{MGN}── {msg} ──{RST}")
def ok(msg):      print(f"  {GRN}✓{RST}  {msg}")
def warn(msg):    print(f"  {YLW}!{RST}  {msg}")
def err(msg):     print(f"  {RED}✗{RST}  {msg}")
def info(msg):    print(f"     {DIM}{msg}{RST}")
def sep():        print(f"  {DIM}{'─'*60}{RST}")

# ── Load PLEF ─────────────────────────────────────────────────────────────────
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import plef_v7 as plef
    ok(f"PLEF v{plef.VERSION} loaded  ({len(plef.LEXICON)} lexicon entries)")
except Exception as e:
    print(f"\n  {RED}Cannot load plef_v7.py: {e}{RST}")
    print(f"  Make sure multi_dataset_analysis.py is in the same folder as plef_v7.py")
    input("\nPress Enter to exit..."); sys.exit(1)

# ── Utilities ─────────────────────────────────────────────────────────────────
def make_ssl():
    try:    return ssl.create_default_context()
    except: return ssl._create_unverified_context()

SSL_CTX = make_ssl()

def download(url, dest, label="Downloading", timeout=120):
    """Download file with progress bar. Returns True on success."""
    req = urllib.request.Request(
        url, headers={"User-Agent":"Mozilla/5.0 PLEF-Research/2.0"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as r:
            total = int(r.headers.get("Content-Length",0))
            done  = 0
            with open(dest,"wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk: break
                    f.write(chunk); done += len(chunk)
                    if total:
                        pct = done/total*100
                        kb  = done//1024
                        print(f"\r    {label}: {pct:5.1f}%  ({kb:,}KB)  ",
                              end="", flush=True)
        print(); return True
    except Exception as e:
        print(); warn(f"Download failed: {e}"); return False

def lbl(score):
    return "pos" if score>0.05 else ("neg" if score<-0.05 else "neu")

def safe_mean(v):
    v = [x for x in v if isinstance(x,(int,float)) and not math.isnan(x)]
    return sum(v)/len(v) if v else 0.0

def safe_sd(v):
    v = [x for x in v if isinstance(x,(int,float)) and not math.isnan(x)]
    if len(v)<2: return 0.0
    m = safe_mean(v)
    return math.sqrt(sum((x-m)**2 for x in v)/(len(v)-1))

def p_star(p):
    if p<=0.001: return "***"
    if p<=0.01:  return "**"
    if p<=0.05:  return "*"
    return "ns"

def save_csv(rows, path, fieldnames=None):
    if not rows: return
    fields = fieldnames or list(rows[0].keys())
    with open(path,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def progress(i, total, start, prefix=""):
    pct = (i+1)/max(1,total)
    bar = int(pct*35)
    elapsed = time.time()-start
    eta = (elapsed/max(1,i+1))*(total-i-1)
    eta_s = f"{int(eta//60)}m{int(eta%60):02d}s"
    print(f"\r    {prefix}[{'█'*bar}{'░'*(35-bar)}] {pct:5.1%} {i+1}/{total} ETA:{eta_s}  ",
          end="", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  DATASET LOADERS
#  Each returns list of {"id","text","sentiment","emotion"} dicts
# ═══════════════════════════════════════════════════════════════════════════════

def load_reddit_relationship():
    """Your own Reddit relationship advice posts (local)."""
    paths = [
        SCRIPT_DIR / "reddit_posts_corpus_original.csv",
        SCRIPT_DIR / "reddit_posts_corpus.csv",
    ]
    for path in paths:
        if path.exists():
            rows = []
            with open(path, encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    text = row.get("text","").strip()
                    if text and len(text.split()) >= 20:
                        rows.append({"id": row.get("id",""),
                                     "text": text,
                                     "sentiment": row.get("sentiment","neu"),
                                     "emotion": row.get("emotion","none")})
            if rows:
                ok(f"Loaded {len(rows):,} posts from {path.name}")
                return rows
    # Fallback: read individual txt files
    txt_dir = SCRIPT_DIR / "reddit_posts"
    if txt_dir.exists():
        rows = []
        for f in sorted(txt_dir.glob("*.txt")):
            text = f.read_text(encoding="utf-8", errors="replace").strip()
            if text and len(text.split()) >= 20:
                rows.append({"id":f.stem,"text":text,"sentiment":"neu","emotion":"none"})
        if rows:
            ok(f"Loaded {len(rows):,} posts from reddit_posts/ folder")
            return rows
    warn("Reddit relationship posts not found. Run reddit_download.py first.")
    return []

def load_goemotions():
    """GoEmotions: 58k Reddit comments, 27 emotions, ACL 2020."""
    EMOTION_NAMES = [
        "admiration","amusement","anger","annoyance","approval","caring",
        "confusion","curiosity","desire","disappointment","disapproval",
        "disgust","embarrassment","excitement","fear","gratitude","grief",
        "joy","love","nervousness","optimism","pride","realization",
        "relief","remorse","sadness","surprise","neutral"
    ]
    POS = {"admiration","amusement","approval","caring","desire","excitement",
           "gratitude","joy","love","optimism","pride","relief"}
    NEG = {"anger","annoyance","disappointment","disapproval","disgust",
           "embarrassment","fear","grief","nervousness","remorse","sadness"}
    base = "https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data/"
    rows = []
    for fname in ["train.tsv","dev.tsv","test.tsv"]:
        dest = DATASETS_DIR / f"ge_{fname}"
        if not dest.exists():
            download(base+fname, dest, f"  GoEmotions {fname}")
        if not dest.exists(): continue
        with open(dest, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                parts = line.strip().split("\t")
                if len(parts)<2: continue
                text = parts[0].strip()
                if not text or len(text.split())<4: continue
                try:
                    ids  = [int(x) for x in parts[1].split(",") if x.strip().isdigit()]
                    emos = [EMOTION_NAMES[j] for j in ids if j<len(EMOTION_NAMES)]
                except: continue
                if not emos: continue
                sent = ("pos" if any(e in POS for e in emos) else
                        "neg" if any(e in NEG for e in emos) else "neu")
                rows.append({"id":f"ge_{fname[:2]}_{i:05d}",
                             "text":text, "sentiment":sent, "emotion":emos[0]})
    return rows

def load_empathetic():
    """EmpatheticDialogues / Emotion corpus loader.
    Handles ANY emotion CSV file placed in datasets/empathetic_extracted/
    including: EmpatheticDialogues, dair-ai/emotion, emotion_69k, GoEmotions lite.

    MANUAL PLACEMENT:
      Place your file in: datasets/empathetic_extracted/
      Accepted extensions: .csv  (if no extension, rename to add .csv)

    COLUMN FORMATS SUPPORTED:
      EmpatheticDialogues: conv_id, utterance_idx, context, prompt, utterance
      emotion_69k / dair-ai/emotion: text, label  (label = 0-5 integer or string)
      HuggingFace generic: text + emotion/label/sentiment column
      Single-column: just text (no labels — sentiment auto-assigned)
    """
    SENT = {
        # EmpatheticDialogues emotion strings
        "joy":"pos","love":"pos","surprise":"pos","excitement":"pos",
        "pride":"pos","gratitude":"pos","content":"pos","caring":"pos",
        "impressed":"pos","hopeful":"pos","anticipating":"pos",
        "joyful":"pos","faithful":"pos","trusting":"pos","prepared":"pos",
        "sadness":"neg","anger":"neg","fear":"neg","guilt":"neg",
        "disgust":"neg","grief":"neg","jealousy":"neg","loneliness":"neg",
        "embarrassment":"neg","devastated":"neg","terrified":"neg",
        "furious":"neg","apprehensive":"neg","ashamed":"neg",
        "disappointed":"neg","anxious":"neg","sad":"neg","afraid":"neg",
        "angry":"neg","disgusted":"neg","lonely":"neg",
        "sentimental":"neu","surprised":"neu","neutral":"neu",
        # dair-ai/emotion integer labels: 0=sadness,1=joy,2=love,3=anger,4=fear,5=surprise
        "0":"neg","1":"pos","2":"pos","3":"neg","4":"neg","5":"neu",
    }

    dest_dir = DATASETS_DIR / "empathetic_extracted"
    dest_dir.mkdir(exist_ok=True)
    rows = []

    def parse_emotion_csv(csv_path, split_name):
        """Parse any emotion CSV regardless of column layout."""
        found = []
        try:
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []

                # Detect text column — try common names
                text_col = next(
                    (h for h in headers if h.strip().lower() in
                     ("utterance","text","sentence","utt","response","tweet","content","comment")),
                    headers[0] if headers else None
                )
                # Detect emotion/label column
                emo_col = next(
                    (h for h in headers if h.strip().lower() in
                     ("context","emotion","label","emo","sentiment","feeling",
                      "tag","category","class")),
                    None
                )

            with open(csv_path, encoding="utf-8", errors="replace") as f:
                for row_num, row in enumerate(csv.DictReader(f)):
                    # Get text
                    text = ""
                    if text_col and text_col in row:
                        text = row[text_col].strip()
                    else:
                        # Try every column, take longest value as text
                        text = max(row.values(), key=lambda v: len(v.split()), default="")

                    text = text.strip().strip('"\'')
                    if not text or len(text.split()) < 3:
                        continue

                    # Get emotion label
                    emo_raw = ""
                    if emo_col and emo_col in row:
                        emo_raw = str(row[emo_col]).strip().strip('"\'').lower()

                    # Map to sentiment
                    sentiment = SENT.get(emo_raw, "neu")

                    # Build ID
                    row_id = row.get("conv_id", row.get("id", f"{row_num:06d}"))
                    turn   = row.get("utterance_idx", row.get("idx", "0"))

                    found.append({
                        "id":        f"ed_{split_name}_{row_id}_{turn}",
                        "text":      text,
                        "sentiment": sentiment,
                        "emotion":   emo_raw if emo_raw else "none",
                    })
        except Exception as e:
            warn(f"  {csv_path.name} parse error: {e}")
        return found

    # ── Check for manually placed files ──────────────────────────────────────
    # Accepts any .csv in the folder — name does not matter
    csv_files = sorted(dest_dir.glob("*.csv"))

    if csv_files:
        for csv_path in csv_files:
            ok(f"  Empathetic/Emotion loader: reading {csv_path.name}")
            found = parse_emotion_csv(csv_path, csv_path.stem[:20])
            rows.extend(found)
            ok(f"  {csv_path.name}: {len(found):,} rows loaded")

        if rows:
            ok(f"  Total emotion corpus: {len(rows):,} items")
            return rows

    # ── No CSV found — try parquet if available ───────────────────────────────
    parquet_files = sorted(dest_dir.glob("*.parquet"))
    if parquet_files:
        try:
            import pandas as pd
            for pf in parquet_files:
                ok(f"  Reading parquet: {pf.name}")
                df = pd.read_parquet(pf)
                # Convert parquet to CSV then reload
                csv_out = dest_dir / (pf.stem + ".csv")
                df.to_csv(csv_out, index=False)
                ok(f"  Converted to {csv_out.name}")
                found = parse_emotion_csv(csv_out, pf.stem[:20])
                rows.extend(found)
        except ImportError:
            warn("  Parquet file found but pandas not installed.")
            warn("  Run: pip install pandas")
            warn("  Or open the parquet file and save as CSV, then re-run.")
        except Exception as e:
            warn(f"  Parquet read error: {e}")

    if rows:
        return rows

    # ── Nothing found — try automatic download ────────────────────────────────
    warn("  No emotion CSV files found in datasets/empathetic_extracted/")
    warn("  Attempting download from GitHub...")

    SPLIT_URLS = {
        "train": "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/train.csv",
        "valid": "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/valid.csv",
        "test":  "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/test.csv",
    }
    for split, url in SPLIT_URLS.items():
        dest_csv = dest_dir / f"{split}.csv"
        if not dest_csv.exists():
            download(url, dest_csv, f"  EmpatheticDialogues {split}")
        if dest_csv.exists():
            found = parse_emotion_csv(dest_csv, split)
            rows.extend(found)

    if not rows:
        warn("Empathetic dataset: no data loaded.")
        warn(f"  Fix: place your CSV file in {dest_dir}")
        warn(f"  Filename can be anything — emotion-emotion_69k.csv is fine.")

    return rows
    SENT = {
        "joy":"pos","love":"pos","surprise":"pos","excitement":"pos",
        "pride":"pos","gratitude":"pos","content":"pos","caring":"pos",
        "impressed":"pos","hopeful":"pos","anticipating":"pos",
        "joyful":"pos","faithful":"pos","trusting":"pos","prepared":"pos",
        "sadness":"neg","anger":"neg","fear":"neg","guilt":"neg",
        "disgust":"neg","grief":"neg","jealousy":"neg","loneliness":"neg",
        "embarrassment":"neg","devastated":"neg","terrified":"neg",
        "furious":"neg","apprehensive":"neg","ashamed":"neg",
        "disappointed":"neg","anxious":"neg","sad":"neg","afraid":"neg",
        "angry":"neg","disgusted":"neg","lonely":"neg","sentimental":"neu",
        "surprised":"neu","anticipating":"pos","neutral":"neu",
    }
    dest_dir = DATASETS_DIR / "empathetic_extracted"
    dest_dir.mkdir(exist_ok=True)
    rows = []

    def parse_empathetic_csv(csv_path, split_name):
        """Parse one EmpatheticDialogues CSV regardless of column layout."""
        found = []
        try:
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                headers = [h.strip().lower() for h in (reader.fieldnames or [])]

                # Detect text column
                text_col = next((h for h in (reader.fieldnames or [])
                                 if h.strip().lower() in
                                 ("utterance","text","sentence","utt","response")), None)
                # Detect emotion/context column
                emo_col  = next((h for h in (reader.fieldnames or [])
                                 if h.strip().lower() in
                                 ("context","emotion","label","emo","situation",
                                  "prompt","feeling")), None)
                # Detect ID columns
                id_col   = next((h for h in (reader.fieldnames or [])
                                 if h.strip().lower() in ("conv_id","id","dialog_id")), None)
                idx_col  = next((h for h in (reader.fieldnames or [])
                                 if h.strip().lower() in ("utterance_idx","turn_idx","idx")), None)

            with open(csv_path, encoding="utf-8", errors="replace") as f:
                for row_num, row in enumerate(csv.DictReader(f)):
                    # Get text
                    if text_col:
                        text = row.get(text_col, "").strip()
                    else:
                        # Fall back to first non-empty column value
                        text = next((v.strip() for v in row.values()
                                     if v and len(v.strip().split()) >= 4), "")

                    if not text or len(text.split()) < 4:
                        continue

                    # Get emotion
                    emo = ""
                    if emo_col:
                        emo = row.get(emo_col, "").strip().lower()
                        # Strip quotes that sometimes wrap the emotion label
                        emo = emo.strip("'\"")

                    # Build ID
                    cid = row.get(id_col, f"{row_num:05d}") if id_col else f"{row_num:05d}"
                    uidx = row.get(idx_col, "0") if idx_col else "0"

                    found.append({
                        "id":        f"ed_{split_name}_{cid}_{uidx}",
                        "text":      text,
                        "sentiment": SENT.get(emo, "neu"),
                        "emotion":   emo if emo else "none",
                    })
        except Exception as e:
            warn(f"  EmpatheticDialogues {csv_path.name} parse error: {e}")
        return found

    # ── STEP 1: Check for manually placed files ───────────────────────────────
    # Accepted: train.csv, valid.csv, test.csv, validation.csv, or any .csv file
    manual_files_found = False
    for fname in ["train.csv", "valid.csv", "test.csv", "validation.csv"]:
        csv_path = dest_dir / fname
        if csv_path.exists():
            manual_files_found = True
            split = fname.replace("validation","valid").replace(".csv","")
            ok(f"  EmpatheticDialogues: reading {fname}")
            found = parse_empathetic_csv(csv_path, split)
            rows.extend(found)
            ok(f"  EmpatheticDialogues {fname}: {len(found):,} rows")

    # Also accept any single .csv file in the folder (any name)
    if not manual_files_found:
        all_csvs = [f for f in dest_dir.glob("*.csv")]
        if all_csvs:
            manual_files_found = True
            for csv_path in all_csvs:
                split = csv_path.stem
                ok(f"  EmpatheticDialogues: reading {csv_path.name}")
                found = parse_empathetic_csv(csv_path, split)
                rows.extend(found)
                ok(f"  EmpatheticDialogues {csv_path.name}: {len(found):,} rows")

    if rows:
        ok(f"  EmpatheticDialogues total: {len(rows):,} utterances loaded")
        return rows

    # ── STEP 2: Try automatic download if no manual files found ───────────────
    warn("  EmpatheticDialogues: no CSV files found in datasets/empathetic_extracted/")
    warn("  Attempting automatic download from GitHub...")

    SPLIT_URLS = {
        "train": [
            "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/train.csv",
            "https://raw.githubusercontent.com/LCS2-IIITD/CIA/master/data/empathetic_dialogues/train.csv",
        ],
        "valid": [
            "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/valid.csv",
        ],
        "test": [
            "https://raw.githubusercontent.com/facebookresearch/EmpatheticDialogues/master/data/test.csv",
        ],
    }
    for split, urls in SPLIT_URLS.items():
        dest_csv = dest_dir / f"{split}.csv"
        if dest_csv.exists():
            found = parse_empathetic_csv(dest_csv, split)
            rows.extend(found)
            continue
        for url in urls:
            if download(url, dest_csv, f"  EmpatheticDialogues {split}"):
                found = parse_empathetic_csv(dest_csv, split)
                rows.extend(found)
                break
        if not dest_csv.exists():
            warn(f"  EmpatheticDialogues {split}: all download URLs failed")

    if not rows:
        warn("EmpatheticDialogues: no data loaded.")
        warn(f"  Manual fix: place train.csv / valid.csv / test.csv in:")
        warn(f"  {dest_dir}")

    return rows

def load_isear():
    """ISEAR: 7,666 psychology emotion sentences, Scherer & Wallbott 1994."""
    SENT = {"joy":"pos","love":"pos","surprise":"pos","shame":"neg",
            "guilt":"neg","fear":"neg","anger":"neg","sadness":"neg","disgust":"neg"}
    urls = [
        "https://raw.githubusercontent.com/sinmaniphel/py_isear_dataset/master/isear.csv",
        "https://raw.githubusercontent.com/PoorvaRane/Emotion-Detector/master/ISEAR.csv",
        "https://raw.githubusercontent.com/dair-ai/emotion_dataset/master/data/isear.csv",
    ]
    dest = DATASETS_DIR / "isear.csv"
    if not dest.exists():
        for url in urls:
            if download(url, dest, "  ISEAR"): break
    if not dest.exists(): return []
    rows = []
    content = dest.read_text(encoding="utf-8", errors="replace")
    for sep_c in [",","|","\t",";"]:
        lines = content.splitlines()
        if len(lines)<5: continue
        cols = lines[0].split(sep_c)
        text_i = next((i for i,c in enumerate(cols) if c.strip().lower() in
                       ("text","sentence","situ","statement","text_en")),1)
        emo_i  = next((i for i,c in enumerate(cols) if c.strip().lower() in
                       ("emotion","emo","label","field1")),0)
        found  = []
        for line in lines[1:]:
            parts = line.split(sep_c)
            if len(parts)<=max(text_i,emo_i): continue
            text = parts[text_i].strip().strip('"')
            emo  = parts[emo_i].strip().strip('"').lower()
            if text and len(text.split())>=5:
                found.append({"id":f"is_{len(found):04d}","text":text,
                              "sentiment":SENT.get(emo,"neu"),"emotion":emo or "none"})
        if found: rows = found; break
    return rows

def load_semeval2017():
    """SemEval 2017 Task 4A: Twitter sentiment benchmark.

    MANUAL PLACEMENT:
      Place 2017_English_final.zip in:  datasets/
      The loader auto-extracts and reads all Subtask_A gold files.
      Total: ~50,372 labelled tweets (2013-2016 train/dev/test splits).

    Format (tab-separated):
      tweet_id \\t positive|negative|neutral \\t tweet_text
    """
    zip_path  = DATASETS_DIR / "semeval2017.zip"
    dest_dir  = DATASETS_DIR / "semeval2017_extracted"
    rows = []

    # ── STEP 1: Check for manually placed zip ────────────────────────────────
    # Also accept the original zip name if user placed it directly
    for candidate in [
        DATASETS_DIR / "semeval2017.zip",
        DATASETS_DIR / "2017_English_final.zip",
        SCRIPT_DIR   / "2017_English_final.zip",     # user might put it in main folder
    ]:
        if candidate.exists() and not zip_path.exists():
            import shutil
            shutil.copy(candidate, zip_path)
            ok(f"  SemEval 2017: found {candidate.name}")
            break

    # ── STEP 2: Extract zip ──────────────────────────────────────────────────
    if zip_path.exists() and not dest_dir.exists():
        dest_dir.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            ok(f"  SemEval 2017: extracted to {dest_dir.name}/")
        except Exception as e:
            warn(f"  SemEval 2017: extraction failed: {e}")

    # ── STEP 3: Read all gold Subtask_A files ────────────────────────────────
    # Format: tweet_id \\t label \\t text
    # We use GOLD/Subtask_A/*.txt files (highest quality — human-verified labels)
    def parse_semeval_file(filepath):
        found = []
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) < 3: continue
                    label = parts[1].strip().lower()
                    text  = "\t".join(parts[2:]).strip().strip('"\'')
                    if not text or len(text.split()) < 4: continue
                    if label in ("positive","negative","neutral","pos","neg","neu"):
                        sent = ("pos" if label.startswith("pos") else
                                "neg" if label.startswith("neg") else "neu")
                        found.append({
                            "id":        f"se_{parts[0]}",
                            "text":      text,
                            "sentiment": sent,
                            "emotion":   "none",
                        })
        except Exception as e:
            warn(f"  Could not read {filepath.name}: {e}")
        return found

    if dest_dir.exists():
        # Read all .txt files from GOLD/Subtask_A/ (human-verified gold labels)
        gold_files = sorted(dest_dir.rglob("*.txt"))
        subtask_a_files = [f for f in gold_files
                           if "Subtask_A" in str(f) and "README" not in f.name
                           and "__MACOSX" not in str(f)]
        # If no GOLD folder, read all .txt files
        if not subtask_a_files:
            subtask_a_files = [f for f in gold_files
                               if "__MACOSX" not in str(f) and "README" not in f.name
                               and ".DS_Store" not in f.name]
        for fp in subtask_a_files:
            found = parse_semeval_file(fp)
            if found:
                rows.extend(found)
                ok(f"  SemEval: {fp.name} → {len(found):,} tweets")

    if rows:
        ok(f"  SemEval 2017 total: {len(rows):,} labelled tweets")
        return rows

    # ── STEP 4: Also check for pre-extracted .txt files in datasets/ ─────────
    for txt_file in DATASETS_DIR.glob("semeval*.txt"):
        found = parse_semeval_file(txt_file)
        rows.extend(found)
    if rows:
        return rows

    # ── STEP 5: Download fallback ─────────────────────────────────────────────
    warn("  SemEval 2017: zip not found. Trying download...")
    urls = [
        "https://raw.githubusercontent.com/cardiffnlp/tweeteval/main/datasets/sentiment/test_text.txt",
        "https://raw.githubusercontent.com/cardiffnlp/tweeteval/main/datasets/sentiment/train_text.txt",
    ]
    for url in urls:
        dest = DATASETS_DIR / ("semeval_" + url.split("/")[-1])
        if not dest.exists():
            download(url, dest, "  SemEval fallback")
        if dest.exists():
            found = parse_semeval_file(dest)
            if not found:
                # Plain text — no labels, assign neutral
                with open(dest, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f):
                        t = line.strip()
                        if t and len(t.split()) >= 4:
                            rows.append({"id":f"se_dl_{i:05d}","text":t,
                                         "sentiment":"neu","emotion":"none"})
            else:
                rows.extend(found)

    if not rows:
        warn("SemEval 2017: no data loaded.")
        warn("  Fix: place 2017_English_final.zip in E:\\Research\\PLEF\\datasets\\")

    return rows

def load_dailydialog():
    """DailyDialog: 13k human-written dialogues with emotion labels.
    Supports THREE file formats automatically:
      1. User-placed CSV files (HuggingFace format) in datasets/dailydialog_extracted/
      2. Original __eou__ text format (dialogues_text.txt + dialogues_emotion.txt)
      3. Plain CSV with utterance-per-row format
    """
    EMOS = {0:"neu",1:"anger",2:"disgust",3:"fear",4:"joy",5:"sadness",6:"surprise"}
    SENT = {"joy":"pos","surprise":"pos","neu":"neu","anger":"neg",
            "disgust":"neg","fear":"neg","sadness":"neg"}
    dest_dir = DATASETS_DIR / "dailydialog_extracted"
    dest_dir.mkdir(exist_ok=True)
    rows = []

    # ── FORMAT 1: HuggingFace CSV (what you downloaded manually) ─────────────
    # Looks for train.csv / test.csv / valid.csv / validation.csv
    # Handles two HuggingFace column layouts:
    #   Layout A: columns 'dialog' (list), 'emotion' (list), 'act' (list)
    #   Layout B: columns 'utterance', 'emotion', 'act' (one row per turn)
    for fname in ["train.csv","test.csv","valid.csv","validation.csv"]:
        csv_path = dest_dir / fname
        if not csv_path.exists():
            continue
        ok(f"  DailyDialog: reading {fname}")
        try:
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                sample = f.read(500); f.seek(0)
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []

            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)

                # Layout A: one row = one full dialog stored as stringified list
                if any(h.strip().lower() == "dialog" for h in headers):
                    import ast as _ast
                    for d_idx, row in enumerate(reader):
                        raw_dialog  = row.get("dialog","").strip()
                        raw_emotion = row.get("emotion","").strip()
                        # Parse stringified Python lists
                        try:
                            utterances = _ast.literal_eval(raw_dialog)
                        except Exception:
                            # Fallback: split on __eou__
                            utterances = [u.strip() for u in
                                          raw_dialog.strip("[]'\"").split("__eou__")]
                        try:
                            emotions = _ast.literal_eval(raw_emotion)
                        except Exception:
                            emotions = [0] * len(utterances)
                        for u_idx, (utt, eid) in enumerate(zip(utterances, emotions)):
                            utt = str(utt).strip()
                            if not utt or len(utt.split()) < 5: continue
                            try:   emo = EMOS.get(int(eid), "neu")
                            except: emo = "neu"
                            rows.append({
                                "id":        f"dd_{fname[:2]}_{d_idx:04d}_{u_idx:02d}",
                                "text":      utt,
                                "sentiment": SENT.get(emo, "neu"),
                                "emotion":   emo,
                            })

                # Layout B: one row = one utterance
                elif any(h.strip().lower() in ("utterance","text","sentence")
                         for h in headers):
                    text_col = next((h for h in headers
                                     if h.strip().lower() in ("utterance","text","sentence")), headers[0])
                    emo_col  = next((h for h in headers
                                     if h.strip().lower() == "emotion"), None)
                    for u_idx, row in enumerate(reader):
                        utt = row.get(text_col, "").strip()
                        if not utt or len(utt.split()) < 4: continue
                        emo_raw = row.get(emo_col, "0").strip() if emo_col else "0"
                        try:   emo = EMOS.get(int(emo_raw), "neu")
                        except: emo = "neu"
                        rows.append({
                            "id":        f"dd_{fname[:2]}_{u_idx:05d}",
                            "text":      utt,
                            "sentiment": SENT.get(emo, "neu"),
                            "emotion":   emo,
                        })

                # Layout C: no recognisable columns — treat first column as text
                else:
                    for u_idx, row in enumerate(reader):
                        vals = list(row.values())
                        utt  = vals[0].strip() if vals else ""
                        if utt and len(utt.split()) >= 5:
                            rows.append({
                                "id":        f"dd_{fname[:2]}_{u_idx:05d}",
                                "text":      utt,
                                "sentiment": "neu",
                                "emotion":   "none",
                            })
        except Exception as e:
            warn(f"  DailyDialog {fname} parse error: {e}")

    if rows:
        ok(f"  DailyDialog: {len(rows):,} utterances loaded from CSV files")
        return rows

    # ── FORMAT 2: Original __eou__ text files (zip extraction) ───────────────
    for txt_file in dest_dir.rglob("dialogues_text.txt"):
        emo_file = txt_file.parent / "dialogues_emotion.txt"
        if not emo_file.exists(): continue
        with open(txt_file, encoding="utf-8", errors="replace") as ft, \
             open(emo_file, encoding="utf-8", errors="replace") as fe:
            for d_idx, (dl, el) in enumerate(zip(ft, fe)):
                dialogs  = dl.strip().split("__eou__")
                emotions = el.strip().split()
                for u_idx, (utt, eid) in enumerate(zip(dialogs, emotions)):
                    utt = utt.strip()
                    if not utt or len(utt.split()) < 5: continue
                    try:   emo = EMOS.get(int(eid), "neu")
                    except: emo = "neu"
                    rows.append({"id": f"dd_{d_idx:04d}_{u_idx:02d}",
                                 "text": utt,
                                 "sentiment": SENT.get(emo, "neu"),
                                 "emotion": emo})
    if rows:
        return rows

    # ── FORMAT 3: Plain __eou__ text mirror files ────────────────────────────
    for txt_file in DATASETS_DIR.glob("dailydialog_*.txt"):
        with open(txt_file, encoding="utf-8", errors="replace") as f:
            for d_idx, line in enumerate(f):
                utterances = line.strip().split("__eou__")
                for u_idx, utt in enumerate(utterances):
                    utt = utt.strip()
                    if utt and len(utt.split()) >= 5:
                        rows.append({
                            "id":        f"dd_{d_idx:05d}_{u_idx:02d}",
                            "text":      utt,
                            "sentiment": "neu",
                            "emotion":   "none",
                        })

    if not rows:
        warn("DailyDialog: no data found in any format")
        warn(f"  Place train.csv / test.csv / valid.csv in:")
        warn(f"  {dest_dir}")

    return rows

def load_meld():
    """MELD: Multimodal EmotionLines Dataset (Friends TV show), EMNLP 2019."""
    SENT_MAP = {"neutral":"neu","surprise":"pos","fear":"neg","sadness":"neg",
                "joy":"pos","disgust":"neg","anger":"neg"}
    urls = {
        "train": "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/train_sent_emo.csv",
        "dev":   "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/dev_sent_emo.csv",
        "test":  "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/test_sent_emo.csv",
    }
    rows = []
    for split, url in urls.items():
        dest = DATASETS_DIR / f"meld_{split}.csv"
        if not dest.exists():
            download(url, dest, f"  MELD {split}")
        if not dest.exists(): continue
        with open(dest, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                text = row.get("Utterance","").strip()
                emo  = row.get("Emotion","neutral").strip().lower()
                if text and len(text.split())>=4:
                    rows.append({"id":f"meld_{split}_{row.get('Sr No.','0')}",
                                 "text":text, "sentiment":SENT_MAP.get(emo,"neu"),
                                 "emotion":emo})
    return rows

def load_tweeteval():
    """TweetEval: Twitter evaluation benchmark, EMNLP 2020."""
    base = "https://raw.githubusercontent.com/cardiffnlp/tweeteval/main/datasets/sentiment/"
    rows = []
    for split in ["train","val","test"]:
        text_url = f"{base}{split}_text.txt"
        lbl_url  = f"{base}{split}_labels.txt"
        text_dest = DATASETS_DIR / f"tweeteval_{split}_text.txt"
        lbl_dest  = DATASETS_DIR / f"tweeteval_{split}_labels.txt"
        if not text_dest.exists(): download(text_url, text_dest, f"  TweetEval {split} text")
        if not lbl_dest.exists():  download(lbl_url,  lbl_dest,  f"  TweetEval {split} labels")
        if not text_dest.exists() or not lbl_dest.exists(): continue
        texts  = text_dest.read_text(encoding="utf-8",errors="replace").splitlines()
        labels = lbl_dest.read_text(encoding="utf-8",errors="replace").splitlines()
        LABEL  = {"0":"neg","1":"neu","2":"pos"}
        for i,(t,l) in enumerate(zip(texts,labels)):
            t = t.strip(); l = l.strip()
            if t and len(t.split())>=3 and l in LABEL:
                rows.append({"id":f"te_{split}_{i:05d}","text":t,
                             "sentiment":LABEL[l],"emotion":"none"})
    return rows

def load_consensus():
    """Cross-system consensus: VADER + NRC + LIWC all agree."""
    source = SCRIPT_DIR / "reddit_posts_corpus_original.csv"
    if not source.exists():
        source = SCRIPT_DIR / "reddit_posts_corpus.csv"
    if not source.exists(): return []
    with open(source, encoding="utf-8", errors="replace") as f:
        all_posts = list(csv.DictReader(f))
    rows = []
    for i, post in enumerate(all_posts):
        print(f"\r    Building consensus: {i+1}/{len(all_posts)}  kept:{len(rows)}  ",
              end="", flush=True)
        text = post.get("text","").strip()
        if not text or len(text.split())<10: continue
        try:
            v = lbl(plef.vader_score(text))
            n = lbl(plef.nrc_score(text)[0])
            l = lbl(plef.liwc_score(text)[0])
            if v==n==l:
                rows.append({"id":post.get("id",""),"text":text,
                             "sentiment":v,"emotion":"none"})
        except: pass
    print()
    return rows

# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_one(text):
    """Run all PLEF + baseline metrics on one text. Returns dict."""
    r = {}
    try:
        stats    = plef.compute_stats(text)
        tobj     = plef.score_text(text)
        sr       = tobj["sentence_results"]
        r["n_words"]    = stats["n_words"]
        r["n_sents"]    = stats["n_sents"]
        r["flesch_re"]  = round(stats["flesch_re"],2)
        r["sentiment"]  = round(tobj["mean"],4)
        gase,_   = plef.compute_gase(text,stats,sr,tobj["horsemen"])
        pti,_    = plef.compute_pti(text)
        teg,_    = plef.compute_teg(sr)
        rci      = plef.compute_rci(text)
        pai,_    = plef.compute_pai(text,stats)
        nava,_,_,arc = plef.compute_nava(sr)
        idx_w,pre_w,post_w,drop_w,_ = plef.compute_lewi(sr)
        _,cds    = plef.compute_cogs(text)
        vads,_   = plef.compute_vads(text)
        ties,_,_,_ = plef.compute_ties(text)
        dom_att,_,_,_ = plef.analyse_attachment(text)
        # NA handling: arc=="short_text" means fewer than 4 sentences — unreliable
        nava_val = round(nava,4) if arc != "short_text" else None
        drop_val = round(drop_w,4) if idx_w is not None else None
        r.update({"gase":gase,"pti":round(pti,4),"teg":round(teg,4),
                  "rci":round(rci,4),"pai":round(pai,4),
                  "nava":nava_val,"nava_arc":arc if arc!="short_text" else "NA",
                  "lewi_idx":idx_w if idx_w is not None else None,
                  "lewi_drop":drop_val,
                  "cd_index":round(cds,4),"vads":round(vads,4),
                  "ties":round(ties,4),"attachment":dom_att})
        h = tobj["horsemen"]
        r.update({"horsemen_total":sum(h.values()),
                  "criticism":h.get("criticism",0),
                  "contempt":h.get("contempt",0),
                  "defensiveness":h.get("defensiveness",0),
                  "stonewalling":h.get("stonewalling",0)})
        r["vader_score"] = plef.vader_score(text)
        r["nrc_score"]   = plef.nrc_score(text)[0]
        r["liwc_score"]  = plef.liwc_score(text)[0]
        emos = tobj.get("emotion_totals",{})
        for emo in ["anger","sadness","fear","joy","trust","disgust","surprise","anticipation"]:
            r[f"emo_{emo}"] = emos.get(emo,0)
    except Exception as e:
        r["_error"] = str(e)
    return r

def run_analysis(corpus, dataset_name, max_items=50000):
    """Run full analysis on corpus. Returns list of result dicts."""
    items = corpus[:max_items]
    results = []
    start = time.time()
    for i, post in enumerate(items):
        progress(i, len(items), start, f"{dataset_name}: ")
        text = post.get("text","").strip()
        if not text: continue
        m = analyse_one(text)
        m["id"]             = post.get("id",f"p{i:05d}")
        m["gold_sentiment"] = post.get("sentiment","neu")
        m["gold_emotion"]   = post.get("emotion","none")
        results.append(m)
    print()
    return results

# ── Statistical helpers ───────────────────────────────────────────────────────
def corpus_summary_stats(results, metric):
    vals = [r[metric] for r in results if isinstance(r.get(metric),(int,float))]
    if not vals: return {"mean":0,"sd":0,"median":0,"min":0,"max":0,"n":0}
    s = sorted(vals); n = len(s)
    med = (s[n//2-1]+s[n//2])/2 if n%2==0 else s[n//2]
    return {"mean":round(safe_mean(vals),4),"sd":round(safe_sd(vals),4),
            "median":round(med,4),"min":round(min(vals),4),
            "max":round(max(vals),4),"n":n}

def evaluate_baseline(scores, gold_lbls):
    classes = ["pos","neg","neu"]
    preds   = [lbl(s) for s in scores]
    tp={c:0 for c in classes}; fp={c:0 for c in classes}; fn={c:0 for c in classes}
    for pr,go in zip(preds,gold_lbls):
        for c in classes:
            if pr==c and go==c: tp[c]+=1
            elif pr==c and go!=c: fp[c]+=1
            elif pr!=c and go==c: fn[c]+=1
    f1s = []
    for c in classes:
        p2=tp[c]/(tp[c]+fp[c]) if tp[c]+fp[c] else 0
        r2=tp[c]/(tp[c]+fn[c]) if tp[c]+fn[c] else 0
        f1s.append(2*p2*r2/(p2+r2) if p2+r2 else 0)
    macro_f1 = round(sum(f1s)/3,3)
    acc      = round(sum(1 for p,g in zip(preds,gold_lbls) if p==g)/max(1,len(gold_lbls)),3)
    return macro_f1, acc

def roc_auc(y_bin, y_sc):
    pairs = sorted(zip(y_sc,y_bin),key=lambda x:-x[0])
    np_=sum(y_bin); nn=len(y_bin)-np_
    if np_==0 or nn==0: return 0.5
    tp=fp=0; fpr=[0.0]; tpr=[0.0]; prev=None
    for sc,lb in pairs:
        if sc!=prev and prev is not None:
            fpr.append(fp/nn); tpr.append(tp/np_)
        if lb==1: tp+=1
        else: fp+=1
        prev=sc
    fpr.append(1.0); tpr.append(1.0)
    return round(abs(sum((fpr[i+1]-fpr[i])*(tpr[i+1]+tpr[i])/2 for i in range(len(fpr)-1))),4)

# ── Save all results for one dataset ─────────────────────────────────────────
SUMMARY_METRICS = ["sentiment","gase","pti","teg","rci","pai","nava","lewi_drop",
                   "cd_index","vads","ties","vader_score","nrc_score","liwc_score","n_words"]
METRIC_LABELS   = {
    "sentiment":"Sentiment (PLEF-VADER)","gase":"GASE (composite health)",
    "pti":"PTI (pronoun power)","teg":"TEG (emotional volatility)",
    "rci":"RCI (relational coherence)","pai":"PAI (power asymmetry)",
    "nava":"NAVA (narrative arc)","lewi_drop":"LEWI drop magnitude",
    "cd_index":"CD-index (distortions)","vads":"VADS (disclosure depth)",
    "ties":"TIES (inconsistency)","vader_score":"VADER baseline",
    "nrc_score":"NRC baseline","liwc_score":"LIWC baseline","n_words":"Word count",
}

def save_dataset_results(results, dataset_name, corpus_meta):
    """Save all result files for one dataset into its own subfolder."""
    ds_dir = RESULTS_DIR / dataset_name
    ds_dir.mkdir(exist_ok=True)
    suf    = f"_{dataset_name}"
    good   = [r for r in results if "_error" not in r]
    n      = len(good)
    now    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    gold_lbls = [r["gold_sentiment"] for r in good]
    gold_num  = {"pos":1.0,"neu":0.0,"neg":-1.0}

    subhead(f"Saving results for: {dataset_name}  (N={n:,})")

    # 1 — all_posts_metrics
    if good:
        fields = list(good[0].keys())
        save_csv(good, ds_dir/f"all_posts_metrics{suf}.csv", fields)
        ok(f"all_posts_metrics{suf}.csv")

    # 2 — corpus_summary
    sum_rows = []
    for m in SUMMARY_METRICS:
        s = corpus_summary_stats(good, m)
        s["metric"] = m; s["label"] = METRIC_LABELS.get(m,m)
        sum_rows.append(s)
    save_csv(sum_rows, ds_dir/f"corpus_summary{suf}.csv",
             ["metric","label","mean","sd","median","min","max","n"])
    ok(f"corpus_summary{suf}.csv")

    # 3 — baseline comparison
    systems = {"PLEF":  [r["sentiment"]   for r in good],
               "VADER": [r["vader_score"] for r in good],
               "NRC":   [r["nrc_score"]   for r in good],
               "LIWC":  [r["liwc_score"]  for r in good]}
    bl_rows = []
    for sys_name, scores in systems.items():
        mf1, acc = evaluate_baseline(scores, gold_lbls)
        r_val, p_r = plef.pearson_with_p(scores, [gold_num.get(g,0) for g in gold_lbls])
        aucs = []
        for cls in ["pos","neg","neu"]:
            y_bin = [1 if g==cls else 0 for g in gold_lbls]
            y_sc  = ([-s for s in scores] if cls=="neg" else
                     [-abs(s) for s in scores] if cls=="neu" else scores[:])
            aucs.append(roc_auc(y_bin, y_sc))
        bl_rows.append({"system":sys_name,"macro_f1":mf1,"accuracy":acc,
                        "pearson_r":r_val,"pearson_p":p_r,
                        "auc_pos":aucs[0],"auc_neg":aucs[1],"auc_neu":aucs[2],
                        "macro_auc":round(sum(aucs)/3,4)})
    save_csv(bl_rows, ds_dir/f"baseline_comparison{suf}.csv")
    ok(f"baseline_comparison{suf}.csv")
    for row in bl_rows:
        print(f"    {row['system']:<8}  F1={row['macro_f1']:.3f}  AUC={row['macro_auc']:.3f}  r={row['pearson_r']:+.3f}")

    # 4 — statistical tests
    pairs = [
        ("sentiment","gase","Expected +ve"),("sentiment","cd_index","Expected -ve"),
        ("sentiment","vads","Expected +ve"),("pti","cd_index","Expected +ve"),
        ("pti","pai","Expected +ve"),("gase","lewi_drop","Expected -ve"),
        ("teg","ties","Expected +ve"),("vads","gase","Expected +ve"),
        ("nava","lewi_drop","Expected +ve"),("cd_index","ties","Expected +ve"),
    ]
    st_rows = []
    for m1,m2,hyp in pairs:
        x = [r[m1] for r in good if isinstance(r.get(m1),(int,float)) and isinstance(r.get(m2),(int,float))]
        y = [r[m2] for r in good if isinstance(r.get(m1),(int,float)) and isinstance(r.get(m2),(int,float))]
        if len(x)<5: continue
        r_val,p_r  = plef.pearson_with_p(x,y)
        rho,p_s    = plef.spearman_with_p(x,y)
        exp_pos    = "Expected +ve" in hyp
        direct_ok  = (r_val>0 and exp_pos) or (r_val<0 and not exp_pos)
        st_rows.append({"metric_1":m1,"metric_2":m2,
                        "pearson_r":r_val,"pearson_p":p_r,"pearson_sig":p_star(p_r),
                        "spearman_rho":rho,"spearman_p":p_s,"spearman_sig":p_star(p_s),
                        "direction_correct":"YES" if direct_ok else "NO",
                        "hypothesis":hyp,"n":len(x)})
    save_csv(st_rows, ds_dir/f"statistical_tests{suf}.csv")
    ok(f"statistical_tests{suf}.csv")

    # 5 — Effect size
    pos_s = [r["sentiment"] for r in good if r["gold_sentiment"]=="pos"]
    neg_s = [r["sentiment"] for r in good if r["gold_sentiment"]=="neg"]
    d_val, g_val = plef.cohens_d(pos_s, neg_s) if pos_s and neg_s else (0,0)
    mag = "Large" if abs(d_val)>=0.8 else "Medium" if abs(d_val)>=0.5 else "Small"

    # 6 — Paper Table 1
    t1 = [f"% Table 1: {dataset_name} Corpus Statistics  (N={n:,})  Generated: {now}",
          r"\begin{table}[h]", r"  \centering",
          f"  \\caption{{PLEF Descriptive Statistics — {dataset_name.replace('_',' ').title()} ($N={n:,}$)}}",
          r"  \begin{tabular}{lrrrr}", r"    \toprule",
          r"    Metric & $\mu$ & SD & Min & Max \\", r"    \midrule"]
    for row in sum_rows[:9]:
        t1.append(f"    {row['label']} & {row['mean']:+.4f} & {row['sd']:.4f} & "
                  f"{row['min']:+.4f} & {row['max']:+.4f} \\\\")
    t1 += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    (ds_dir/f"paper_table1{suf}.txt").write_text("\n".join(t1),encoding="utf-8")

    # 7 — Paper Table 2
    t2 = [f"% Table 2: Baseline Comparison — {dataset_name}  (N={n:,})  Generated: {now}",
          r"\begin{table}[h]", r"  \centering",
          f"  \\caption{{Baseline Comparison — {dataset_name.replace('_',' ').title()} ($N={n:,}$)}}",
          r"  \begin{tabular}{lrrrr}", r"    \toprule",
          r"    System & Macro-F1 & Macro-AUC & Pearson $r$ & Sig \\",r"    \midrule"]
    for row in bl_rows:
        sig = p_star(row["pearson_p"])
        t2.append(f"    {row['system']} & {row['macro_f1']:.3f} & "
                  f"{row['macro_auc']:.3f} & {row['pearson_r']:+.3f} & {sig} \\\\")
    t2 += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    (ds_dir/f"paper_table2{suf}.txt").write_text("\n".join(t2),encoding="utf-8")

    # 8 — Paper Table 3
    t3 = [f"% Table 3: Correlation Analysis — {dataset_name}  Generated: {now}",
          r"\begin{table}[h]", r"  \centering",
          f"  \\caption{{Inter-metric Correlations — {dataset_name.replace('_',' ').title()}, Pearson r and Spearman $\\rho$}}",
          r"  \begin{tabular}{llrrrl}", r"    \toprule",
          r"    M1 & M2 & $r$ & Sig & $\rho$ & Dir \\", r"    \midrule"]
    for row in st_rows:
        t3.append(f"    {row['metric_1']} & {row['metric_2']} & "
                  f"{row['pearson_r']:+.3f} & {row['pearson_sig']} & "
                  f"{row['spearman_rho']:+.3f} & {row['direction_correct']} \\\\")
    t3 += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    (ds_dir/f"paper_table3{suf}.txt").write_text("\n".join(t3),encoding="utf-8")
    ok(f"paper_table1/2/3{suf}.txt")

    # 9 — Full report
    dir_rate = sum(1 for r in st_rows if r["direction_correct"]=="YES")
    plef_row = next((r for r in bl_rows if r["system"]=="PLEF"), {})
    report   = [
        "="*62, f"PLEF ANALYSIS REPORT — {dataset_name.upper()}",
        f"Generated: {now}", f"N = {n:,} items",
        "="*62, "",
        "DATASET INFO", "-"*40,
        f"  Source:      {corpus_meta.get('source',dataset_name)}",
        f"  Citation:    {corpus_meta.get('citation','—')}",
        f"  Label type:  {corpus_meta.get('label_type','automatic')}",
        "", "CORPUS STATISTICS", "-"*40,
    ]
    for row in sum_rows[:9]:
        report.append(f"  {row['label']:<35} μ={row['mean']:+.4f}  SD={row['sd']:.4f}")
    report += ["", "BASELINE COMPARISON", "-"*40]
    for row in bl_rows:
        report.append(f"  {row['system']:<8}  F1={row['macro_f1']:.3f}  "
                      f"AUC={row['macro_auc']:.3f}  r={row['pearson_r']:+.3f}")
    report += ["", "CORRELATION ANALYSIS", "-"*40]
    for row in st_rows:
        report.append(f"  {row['metric_1']:<14} x {row['metric_2']:<14}  "
                      f"r={row['pearson_r']:+.3f}{row['pearson_sig']:<4}  "
                      f"dir={row['direction_correct']}")
    report += ["", "EFFECT SIZE", "-"*40,
               f"  Cohen's d (pos vs neg): d={d_val:+.3f}  g={g_val:+.3f}  ({mag})",
               "", "SUMMARY", "-"*40,
               f"  PLEF Macro-F1:   {plef_row.get('macro_f1',0):.3f}",
               f"  PLEF Macro-AUC:  {plef_row.get('macro_auc',0):.3f}",
               f"  Correlations:    {dir_rate}/{len(st_rows)} in predicted direction",
               "="*62]
    (ds_dir/f"full_report{suf}.txt").write_text("\n".join(report),encoding="utf-8")
    ok(f"full_report{suf}.txt")

    return {"dataset":dataset_name, "n":n,
            "plef_f1":plef_row.get("macro_f1",0),
            "plef_auc":plef_row.get("macro_auc",0),
            "plef_r":plef_row.get("pearson_r",0),
            "vader_f1":next((r["macro_f1"] for r in bl_rows if r["system"]=="VADER"),0),
            "direction_rate":f"{dir_rate}/{len(st_rows)}",
            "cohens_d":d_val, "effect_size":mag,
            "citation":corpus_meta.get("citation","—")}

# ═══════════════════════════════════════════════════════════════════════════════
#  COMBINED REPORT
# ═══════════════════════════════════════════════════════════════════════════════
def save_combined_report(all_summaries, now):
    """Generate cross-dataset master comparison."""
    comb_dir = RESULTS_DIR / "COMBINED"
    comb_dir.mkdir(exist_ok=True)

    # Cross-dataset CSV
    save_csv(all_summaries, comb_dir/"cross_dataset_comparison.csv")

    # LaTeX master table
    latex = [
        f"% Cross-dataset comparison — Generated: {now}",
        r"\begin{table*}[t]", r"  \centering",
        r"  \caption{PLEF Performance Across All Evaluation Datasets}",
        r"  \begin{tabular}{llrrrrrl}",
        r"    \toprule",
        r"    Dataset & N & PLEF F1 & PLEF AUC & PLEF $r$ & VADER F1 & Cohen's $d$ & Dir \\",
        r"    \midrule",
    ]
    for s in all_summaries:
        latex.append(
            f"    {s['dataset'].replace('_',' '):<25} & {s['n']:>7,} & "
            f"{s['plef_f1']:.3f} & {s['plef_auc']:.3f} & "
            f"{s['plef_r']:+.3f} & {s['vader_f1']:.3f} & "
            f"{s['cohens_d']:+.3f} & {s['direction_rate']} \\\\"
        )
    latex += [r"    \bottomrule", r"  \end{tabular}", r"\end{table*}"]
    (comb_dir/"paper_table_all_datasets.txt").write_text("\n".join(latex),encoding="utf-8")

    # Master text report
    lines = [
        "="*65, "PLEF MULTI-DATASET MASTER REPORT",
        f"Generated: {now}", f"Datasets analysed: {len(all_summaries)}",
        "="*65, "",
        f"  {'Dataset':<28} {'N':>8} {'F1':>6} {'AUC':>6} {'r':>6} {'d':>6} {'Dir':>7}",
        f"  {'─'*28} {'─'*8} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*7}",
    ]
    for s in all_summaries:
        lines.append(
            f"  {s['dataset']:<28} {s['n']:>8,} {s['plef_f1']:>6.3f} "
            f"{s['plef_auc']:>6.3f} {s['plef_r']:>+6.3f} "
            f"{s['cohens_d']:>+6.3f} {s['direction_rate']:>7}"
        )
    avg_f1  = safe_mean([s["plef_f1"]  for s in all_summaries])
    avg_auc = safe_mean([s["plef_auc"] for s in all_summaries])
    avg_r   = safe_mean([s["plef_r"]   for s in all_summaries])
    lines += [
        f"  {'─'*65}",
        f"  {'AVERAGE ACROSS ALL DATASETS':<28} {'':>8} {avg_f1:>6.3f} "
        f"{avg_auc:>6.3f} {avg_r:>+6.3f}",
        "", "CITATIONS", "-"*40,
    ]
    for s in all_summaries:
        lines.append(f"  [{s['dataset']}] {s['citation']}")
    lines += ["", "FILES SAVED", "-"*40,
              "  results/", "    COMBINED/", "      cross_dataset_comparison.csv",
              "      paper_table_all_datasets.txt", "      master_report.txt"]
    for s in all_summaries:
        lines.append(f"    {s['dataset']}/  ({s['n']:,} items)")
    (comb_dir/"master_report.txt").write_text("\n".join(lines),encoding="utf-8")

# ═══════════════════════════════════════════════════════════════════════════════
#  DATASET REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
DATASETS = [
    {
        "key":      "reddit_relationship",
        "label":    "Reddit r/relationship_advice (local, narrative)",
        "loader":   load_reddit_relationship,
        "meta":     {"source":"r/relationship_advice (your corpus)",
                     "citation":"Reddit public posts (2021–2023)",
                     "label_type":"Auto-generated (keyword), silver standard"},
        "max":      10000,
    },
    {
        "key":      "goemotions",
        "label":    "GoEmotions — Reddit, ACL 2020, Google",
        "loader":   load_goemotions,
        "meta":     {"source":"Google Research GitHub",
                     "citation":"Demszky et al. (2020) GoEmotions. ACL 2020.",
                     "label_type":"Human-annotated (3 raters per item)"},
        "max":      50000,
    },
    {
        "key":      "empathetic",
        "label":    "EmpatheticDialogues — EMNLP 2019, Facebook",
        "loader":   load_empathetic,
        "meta":     {"source":"dl.fbaipublicfiles.com",
                     "citation":"Rashkin et al. (2019) EmpatheticDialogues. EMNLP 2019.",
                     "label_type":"Human-annotated"},
        "max":      30000,
    },
    {
        "key":      "isear",
        "label":    "ISEAR Psychology Dataset — Scherer & Wallbott 1994",
        "loader":   load_isear,
        "meta":     {"source":"GitHub (sinmaniphel/py_isear_dataset)",
                     "citation":"Scherer & Wallbott (1994) JPSP 66(2):310-328.",
                     "label_type":"Human (psychology researchers)"},
        "max":      10000,
    },
    {
        "key":      "semeval2017",
        "label":    "SemEval 2017 Task 4 — Twitter Benchmark",
        "loader":   load_semeval2017,
        "meta":     {"source":"GitHub (cbaziotis/datastories-semeval2017)",
                     "citation":"Rosenthal et al. (2017) SemEval-2017 Task 4. SemEval.",
                     "label_type":"Human-annotated"},
        "max":      10000,
    },
    {
        "key":      "meld",
        "label":    "MELD — Friends TV Dialogues, EMNLP 2019",
        "loader":   load_meld,
        "meta":     {"source":"GitHub (declare-lab/MELD)",
                     "citation":"Poria et al. (2019) MELD. ACL 2019.",
                     "label_type":"Human-annotated"},
        "max":      15000,
    },
    {
        "key":      "tweeteval",
        "label":    "TweetEval — Twitter Benchmark, EMNLP 2020",
        "loader":   load_tweeteval,
        "meta":     {"source":"GitHub (cardiffnlp/tweeteval)",
                     "citation":"Barbieri et al. (2020) TweetEval. EMNLP Findings 2020.",
                     "label_type":"Human-annotated"},
        "max":      15000,
    },
    {
        "key":      "dailydialog",
        "label":    "DailyDialog — Human Dialogues, IJCNLP 2017",
        "loader":   load_dailydialog,
        "meta":     {"source":"yanran.li/ijcnlp_dailydialog",
                     "citation":"Li et al. (2017) DailyDialog. IJCNLP 2017.",
                     "label_type":"Human-annotated"},
        "max":      15000,
    },
    {
        "key":      "consensus",
        "label":    "Cross-system Consensus (silver standard, local)",
        "loader":   load_consensus,
        "meta":     {"source":"Generated from reddit_posts_corpus_original.csv",
                     "citation":"VADER+NRC+LIWC ensemble agreement (silver standard)",
                     "label_type":"Automated consensus (3 systems)"},
        "max":      10000,
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{BLD}{'='*65}")
    print(f"  PLEF Multi-Dataset Analysis Pipeline v2.0")
    print(f"  Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Datasets planned: {len(DATASETS)}")
    print(f"{'='*65}{RST}\n")
    print(f"  Results folder: {RESULTS_DIR}")
    print(f"  Each dataset → own subfolder with dataset-named files\n")

    # Let user choose: all datasets or specific ones
    print(f"  {BLD}Run which datasets?{RST}")
    print(f"  {GRN}A{RST}  All datasets (recommended)")
    print(f"  {YLW}S{RST}  Select specific datasets")
    print(f"  {CYN}L{RST}  Local only (no downloads)")
    choice = input(f"\n  Enter choice [A/S/L]: ").strip().upper()

    if choice == "L":
        selected = [d for d in DATASETS if d["key"] in ("reddit_relationship","consensus")]
    elif choice == "S":
        print()
        for i, d in enumerate(DATASETS):
            print(f"    {i+1}. {d['label']}")
        nums = input("\n  Enter numbers separated by commas (e.g. 1,2,4): ").strip()
        try:
            idxs = [int(x)-1 for x in nums.split(",") if x.strip().isdigit()]
            selected = [DATASETS[i] for i in idxs if 0<=i<len(DATASETS)]
        except:
            selected = DATASETS
    else:
        selected = DATASETS

    print(f"\n  {BLD}Selected {len(selected)} dataset(s):{RST}")
    for d in selected: print(f"    • {d['label']}")
    print()

    pipeline_start = time.time()
    all_summaries  = []
    successful     = []
    failed         = []

    for ds in selected:
        key   = ds["key"]
        label = ds["label"]
        head(f"Dataset: {label}")

        # Load
        try:
            corpus = ds["loader"]()
        except Exception as e:
            err(f"Loader failed for {key}: {e}")
            failed.append(key); continue

        if not corpus:
            warn(f"No data loaded for {key}. Skipping.")
            failed.append(key); continue

        ok(f"Loaded {len(corpus):,} items")

        # Analyse
        subhead("Running PLEF analysis")
        results = run_analysis(corpus, key, max_items=ds.get("max",50000))
        good = [r for r in results if "_error" not in r]
        if not good:
            err(f"No valid results for {key}."); failed.append(key); continue
        ok(f"{len(good):,} items analysed successfully")

        # Save
        summary = save_dataset_results(good, key, ds["meta"])
        all_summaries.append(summary)
        successful.append(key)
        sep()

    # Combined report
    if len(all_summaries) > 1:
        head("Generating Combined Cross-Dataset Report")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        save_combined_report(all_summaries, now)
        ok("COMBINED/master_report.txt")
        ok("COMBINED/cross_dataset_comparison.csv")
        ok("COMBINED/paper_table_all_datasets.txt")

    # Final summary
    total_time = time.time()-pipeline_start
    print(f"\n{BLD}{GRN}{'='*65}")
    print(f"  ALL DONE in {total_time/60:.1f} minutes")
    print(f"{'='*65}{RST}")
    print(f"\n  {BLD}Successful:{RST}  {len(successful)} datasets")
    for s in successful:
        sm = next((x for x in all_summaries if x["dataset"]==s),{})
        print(f"    {GRN}✓{RST}  {s:<30} N={sm.get('n',0):>8,}  F1={sm.get('plef_f1',0):.3f}")
    if failed:
        print(f"\n  {BLD}Failed:{RST}  {len(failed)} datasets")
        for f in failed:
            print(f"    {RED}✗{RST}  {f}  (no data downloaded)")

    print(f"\n  {BLD}Output folders:{RST}")
    for s in successful:
        print(f"    results/{s}/")
    if len(all_summaries)>1:
        print(f"    results/COMBINED/")

    print(f"\n  {BLD}Open these files first:{RST}")
    if len(all_summaries)>1:
        print(f"    results/COMBINED/master_report.txt")
        print(f"    results/COMBINED/paper_table_all_datasets.txt")
    else:
        s = all_summaries[0]["dataset"] if all_summaries else ""
        print(f"    results/{s}/full_report_{s}.txt")

    print()
    input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
