#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reddit_download.py
==================
Downloads posts from r/relationship_advice using Reddit's public JSON API.
Converts them into the CSV format that PLEF expects.

NO API KEY NEEDED. NO SIGN-UP. Pure Python stdlib only.
Works on Python 3.8 and Windows 7.

Output files created in the same folder as this script:
  reddit_raw.json              - raw downloaded data (backup)
  reddit_posts_corpus.csv     - ready for PLEF (name it: yourfile_corpus.csv)
  reddit_posts\               - folder of individual .txt files for --batch mode

Usage:
  python reddit_download.py

Then follow the on-screen instructions.
"""

import urllib.request
import urllib.error
import urllib.parse
import json
import csv
import ssl
import time
import os
import sys
import re
from pathlib import Path

def _safe_input(prompt="", default=""):
    """input() wrapper that handles EOFError in automated/piped mode."""
    try:
        return input(prompt)
    except EOFError:
        return default

# ── Configuration ─────────────────────────────────────────────────────────────
SUBREDDIT      = "relationship_advice"   # which subreddit to download from
HOW_MANY_POSTS = 500                     # how many posts to try to download
MIN_WORDS      = 50                      # skip posts shorter than this
MIN_SCORE      = 10                      # skip posts with fewer upvotes
OUTPUT_FOLDER  = Path(__file__).parent   # save files next to this script

# ── Colours for Windows (safe fallback) ──────────────────────────────────────
try:
    import colorama; colorama.init()
    GRN = "\033[92m"; YLW = "\033[93m"; RED = "\033[91m"
    CYN = "\033[96m"; BLD = "\033[1m";  RST = "\033[0m"
except ImportError:
    GRN = YLW = RED = CYN = BLD = RST = ""

def p(msg, color=""):
    print(f"  {color}{msg}{RST}")

def heading(msg):
    print(f"\n{BLD}{CYN}{'─'*60}{RST}")
    print(f"  {BLD}{CYN}{msg}{RST}")
    print(f"{BLD}{CYN}{'─'*60}{RST}")

# ── SSL fix for Windows 7 (old certificates) ─────────────────────────────────
def make_ssl_context():
    """Create SSL context that works on Windows 7 with old certificates."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        pass
    try:
        ctx = ssl._create_unverified_context()
        p("Warning: SSL verification disabled (Windows 7 certificate issue).", YLW)
        p("Data is still downloaded correctly — this is a known Windows 7 limitation.", YLW)
        return ctx
    except Exception:
        return None

# ── Auto-label sentiment from text ───────────────────────────────────────────
# Simple word-count labelling so PLEF has something to compare against.
# You can manually correct these labels later for higher accuracy.
POS_WORDS = {"love","happy","wonderful","amazing","grateful","thankful","blessed",
             "joy","trust","hope","better","healed","healing","growing","good",
             "great","beautiful","kind","supportive","caring","healthy","safe"}
NEG_WORDS = {"hate","angry","hurt","betrayed","broken","destroyed","terrible",
             "awful","horrible","worthless","abandoned","alone","lonely","scared",
             "afraid","anxiety","depressed","toxic","abusive","controlling","sad",
             "devastated","hopeless","helpless","cheated","lied","manipulated"}

def auto_label_sentiment(text):
    """Quick word-count sentiment label. Rough but usable as starting point."""
    words = re.findall(r"[a-z]+", text.lower())
    pos = sum(1 for w in words if w in POS_WORDS)
    neg = sum(1 for w in words if w in NEG_WORDS)
    if pos > neg * 1.5:   return "pos"
    if neg > pos * 1.5:   return "neg"
    return "neu"

def auto_label_emotion(text):
    """Rough primary emotion label based on keyword frequency."""
    text_l = text.lower()
    emotions = {
        "anger":        ["angry","furious","rage","hate","irritated","frustrated"],
        "sadness":      ["sad","grief","devastated","heartbroken","lonely","miss","cry","lost"],
        "fear":         ["scared","afraid","terrified","anxious","worried","panic","dread"],
        "joy":          ["happy","excited","grateful","wonderful","amazing","love","joy"],
        "trust":        ["trust","believe","reliable","honest","safe","secure","faithful"],
        "disgust":      ["disgusted","repulsed","sick","gross","vile","revolted"],
        "surprise":     ["shocked","surprised","unexpected","sudden","disbelief"],
        "anticipation": ["hope","waiting","expect","planning","looking forward"],
    }
    scores = {}
    for emo, words in emotions.items():
        scores[emo] = sum(text_l.count(w) for w in words)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "none"

# ── Reddit API downloader ─────────────────────────────────────────────────────
def build_url(subreddit, after=None, limit=100):
    base = f"https://www.reddit.com/r/{subreddit}/top.json?limit={limit}&t=all"
    if after:
        base += f"&after={after}"
    return base

def fetch_page(url, ssl_ctx):
    """Fetch one page of Reddit JSON. Returns parsed dict or None."""
    headers = {
        "User-Agent": "Mozilla/5.0 PLEF-Research-Downloader/1.0 (academic research)"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        if ssl_ctx:
            response = urllib.request.urlopen(req, context=ssl_ctx, timeout=15)
        else:
            response = urllib.request.urlopen(req, timeout=15)
        raw = response.read().decode("utf-8")
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            p(f"Rate limited by Reddit (429). Waiting 30 seconds...", YLW)
            time.sleep(30)
            return None
        elif e.code == 403:
            p(f"Reddit returned 403 Forbidden. See alternative instructions below.", RED)
            return "FORBIDDEN"
        else:
            p(f"HTTP error {e.code}: {e.reason}", RED)
            return None
    except Exception as e:
        p(f"Download error: {e}", RED)
        return None

def clean_text(text):
    """Remove Reddit formatting, links, and junk."""
    if not text or text in ("[deleted]", "[removed]", ""):
        return ""
    # Remove URLs
    text = re.sub(r"http\S+", "", text)
    # Remove Reddit markdown
    text = re.sub(r"\*+([^*]+)\*+", r"\1", text)     # bold/italic
    text = re.sub(r"#+\s*", "", text)                  # headers
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text

def count_words(text):
    return len(re.findall(r"\b\w+\b", text))

# ── Main download function ────────────────────────────────────────────────────
def download_posts(subreddit, target_count, min_words, min_score, ssl_ctx):
    posts = []
    after = None
    attempts = 0
    max_attempts = 20   # stop after 20 pages (= 2000 raw posts tried)

    p(f"Downloading from r/{subreddit}...", GRN)
    p(f"Target: {target_count} posts with ≥{min_words} words and ≥{min_score} upvotes", GRN)
    print()

    while len(posts) < target_count and attempts < max_attempts:
        url = build_url(subreddit, after=after, limit=100)
        p(f"Page {attempts+1}: downloading... ({len(posts)}/{target_count} collected so far)", CYN)

        data = fetch_page(url, ssl_ctx)

        if data == "FORBIDDEN":
            return posts, "FORBIDDEN"

        if data is None:
            p("Skipping page due to error. Trying next...", YLW)
            attempts += 1
            time.sleep(3)
            continue

        try:
            children = data["data"]["children"]
            after    = data["data"]["after"]
        except (KeyError, TypeError):
            p("Unexpected response format. Stopping.", RED)
            break

        new_this_page = 0
        for child in children:
            post = child.get("data", {})
            title    = post.get("title", "").strip()
            selftext = clean_text(post.get("selftext", ""))
            score    = post.get("score", 0)
            post_id  = post.get("id", f"p{len(posts):04d}")

            # Combine title and body
            full_text = f"{title}. {selftext}".strip() if selftext else title

            # Filter
            if count_words(full_text) < min_words:
                continue
            if score < min_score:
                continue
            if not selftext:   # title-only posts
                continue

            sentiment  = auto_label_sentiment(full_text)
            emotion    = auto_label_emotion(full_text)

            posts.append({
                "id":         post_id,
                "text":       full_text,
                "sentiment":  sentiment,
                "emotion":    emotion,
                "attachment": "none",   # to be filled manually or by PLEF
                "score":      score,
                "title":      title,
            })
            new_this_page += 1

            if len(posts) >= target_count:
                break

        p(f"  → {new_this_page} posts kept from this page. Total: {len(posts)}", GRN)

        if not after:
            p("No more pages available from Reddit.", YLW)
            break

        attempts += 1
        # Be polite — Reddit asks for 1 request per 2 seconds
        time.sleep(2.5)

    return posts, "OK"

# ── Save files ────────────────────────────────────────────────────────────────
def save_raw_json(posts, output_folder):
    path = output_folder / "reddit_raw.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    return path

def save_corpus_csv(posts, output_folder):
    """Save as PLEF-compatible CSV. Name matches what PLEF auto-detects."""
    path = output_folder / "reddit_posts_corpus.csv"
    fieldnames = ["id","text","sentiment","emotion","attachment","score","title"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(posts)
    return path

def save_individual_txt_files(posts, output_folder):
    """Save each post as a separate .txt file for PLEF --batch mode."""
    txt_folder = output_folder / "reddit_posts"
    txt_folder.mkdir(exist_ok=True)
    for post in posts:
        fname = txt_folder / f"{post['id']}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(post["text"])
    return txt_folder

# ── Print alternative instructions if Reddit blocks ──────────────────────────
def print_alternative_instructions():
    print(f"""
{RED}Reddit blocked the automatic download.{RST}
This sometimes happens. Here are two alternatives:

{BLD}ALTERNATIVE 1 — Download manually from Reddit{RST}
  1. Open your web browser
  2. Go to: https://www.reddit.com/r/relationship_advice/top/?t=all
  3. You will see posts. Open each one, copy the text, paste into Notepad.
  4. Save each as a .txt file in C:\\PLEF\\reddit_posts\\
  5. Run PLEF batch mode:
     python plef_v7.py --batch C:\\PLEF\\reddit_posts\\

{BLD}ALTERNATIVE 2 — Download a pre-packaged dataset from Kaggle{RST}
  1. Create a free account at: https://www.kaggle.com
  2. Search for: "reddit relationship advice"
  3. Download the CSV file
  4. Rename it to: reddit_posts_corpus.csv
  5. Place it in C:\\PLEF\\
  6. Run PLEF and type CORP in the menu

{BLD}ALTERNATIVE 3 — Use a smaller manual test right now{RST}
  Copy 5-10 posts from Reddit manually into one text file.
  Run PLEF on it to see results immediately.
  Scale up later with a proper dataset.
""")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    heading("PLEF Reddit Dataset Downloader")
    p("Downloads r/relationship_advice posts and converts to PLEF format.")
    p("No API key required. No sign-up. Fully automatic.")
    print()

    # Check internet
    p("Checking internet connection...", CYN)
    ssl_ctx = make_ssl_context()

    test_result = fetch_page("https://www.reddit.com/r/relationship_advice/top.json?limit=1&t=all", ssl_ctx)
    if test_result is None:
        p("Cannot reach Reddit. Check your internet connection.", RED)
        p("If you are behind a firewall or proxy, use Alternative 2 (Kaggle) below.", YLW)
        print_alternative_instructions()
        _safe_input("\n  Press Enter to exit...")
        return
    if test_result == "FORBIDDEN":
        print_alternative_instructions()
        _safe_input("\n  Press Enter to exit...")
        return

    p("Connection successful.", GRN)
    print()

    # Ask user how many posts
    print(f"  {BLD}How many posts to download?{RST}")
    print(f"  {YLW}  100{RST}  = Quick test  (~3 minutes)   Good for checking everything works")
    print(f"  {YLW}  300{RST}  = Medium       (~8 minutes)   Enough for a pilot study")
    print(f"  {YLW}  500{RST}  = Full         (~15 minutes)  Recommended for paper")
    print()
    try:
        choice = _safe_input("  Type a number (or press Enter for 300): ", "300").strip()
        target = int(choice) if choice else 300
        target = max(10, min(1000, target))
    except ValueError:
        target = 300
    p(f"Will collect up to {target} posts.", GRN)
    print()

    # Download
    posts, status = download_posts(
        subreddit  = SUBREDDIT,
        target_count = target,
        min_words  = MIN_WORDS,
        min_score  = MIN_SCORE,
        ssl_ctx    = ssl_ctx,
    )

    if status == "FORBIDDEN":
        print_alternative_instructions()
        _safe_input("\n  Press Enter to exit...")
        return

    if not posts:
        p("No posts downloaded. Try the alternatives below.", RED)
        print_alternative_instructions()
        _safe_input("\n  Press Enter to exit...")
        return

    # Save files
    heading(f"Download complete — {len(posts)} posts collected")

    raw_path = save_raw_json(posts, OUTPUT_FOLDER)
    csv_path = save_corpus_csv(posts, OUTPUT_FOLDER)
    txt_path = save_individual_txt_files(posts, OUTPUT_FOLDER)

    p(f"Raw JSON backup:     {raw_path}", GRN)
    p(f"PLEF corpus CSV:     {csv_path}", GRN)
    p(f"Individual txt files:{txt_path}", GRN)
    print()

    # Show sentiment breakdown
    heading("Dataset Summary")
    from collections import Counter
    sent_counts = Counter(p["sentiment"] for p in posts)
    emo_counts  = Counter(p["emotion"]   for p in posts)
    p(f"Total posts:   {len(posts)}", BLD)
    p(f"Sentiment labels (auto-generated, can be corrected):")
    for label, count in sorted(sent_counts.items()):
        bar = "█" * int(count/len(posts)*40)
        print(f"    {label:5}  {bar}  {count}")
    p(f"\nTop emotions detected:")
    for emo, count in emo_counts.most_common(5):
        print(f"    {emo:15}  {count}")
    print()

    # Next steps
    heading("NEXT STEPS — How to Run PLEF on This Dataset")
    print(f"""
  {BLD}STEP 1 — Run the full PLEF analysis on ALL posts at once:{RST}
  {YLW}  cd C:\\PLEF
  python plef_v7.py --batch reddit_posts{RST}
  This analyses every post and shows a ranked table of GASE, PTI, sentiment.

  {BLD}STEP 2 — Run the benchmark evaluation (F1, AUC, comparisons):{RST}
  {YLW}  python plef_v7.py reddit_posts_corpus.csv{RST}
  Then type {BLD}CORP{RST} in the menu.
  This compares PLEF vs VADER vs NRC vs LIWC with P/R/F1 scores.

  {BLD}STEP 3 — Run statistical validation:{RST}
  Type {BLD}STAT{RST} in the menu — Pearson, Spearman, Wilcoxon, ICC, Cohen's d.

  {BLD}STEP 4 — Run ROC curve analysis:{RST}
  Type {BLD}ROC{RST} in the menu — multi-class AUC vs all baselines.

  {BLD}STEP 5 — Generate your paper tables:{RST}
  Type {BLD}BASE{RST} for the comparison table.
  Type {BLD}P123{RST} for all three LaTeX paper skeletons pre-filled with results.

  {BLD}NOTE on sentiment labels:{RST}
  The labels in the CSV were auto-generated by keyword counting.
  For a published paper, manually check 50-100 of them for accuracy.
  Or use the {BLD}ANN{RST} command in PLEF to export an annotation template.
""")

    _safe_input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
