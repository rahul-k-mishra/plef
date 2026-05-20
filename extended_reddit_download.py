#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extended_reddit_download.py
===========================
Downloads relationship narratives from MULTIPLE subreddits.
Each subreddit saved separately AND merged into one relationship corpus.

Subreddits covered:
  r/relationships          — general relationship issues
  r/relationship_advice    — advice-seeking narratives
  r/BreakUps               — dissolution narratives (Duck 1982 stages)
  r/survivinginfidelity    — betrayal / trust violation narratives
  r/heartbreak             — grief and loss narratives
  r/confession             — emotional disclosure (high VADS)
  r/emotionalsupport       — vulnerability narratives
  r/NarcissisticAbuse      — power dynamics (WARNING: high clinical risk)

Each subreddit → its own CSV file
All combined → relationship_corpus_FULL.csv

Run: python extended_reddit_download.py
"""

import urllib.request, urllib.error, json, csv, ssl, time, re, sys, os
from pathlib import Path

def _safe_input(prompt="", default=""):
    """input() wrapper that handles EOFError in automated/piped mode."""
    try:
        return input(prompt)
    except EOFError:
        return default
from collections import Counter

SCRIPT_DIR = Path(__file__).parent

try:
    import colorama; colorama.init()
    GRN="\033[92m"; YLW="\033[93m"; RED="\033[91m"
    CYN="\033[96m"; BLD="\033[1m"; RST="\033[0m"; DIM="\033[2m"
except ImportError:
    GRN=YLW=RED=CYN=BLD=RST=DIM=""

def head(msg):
    print(f"\n{BLD}{CYN}{'═'*62}{RST}")
    print(f"  {BLD}{CYN}{msg}{RST}")
    print(f"{BLD}{CYN}{'═'*62}{RST}")

def ok(msg):   print(f"  {GRN}✓{RST}  {msg}")
def warn(msg): print(f"  {YLW}!{RST}  {msg}")
def err(msg):  print(f"  {RED}✗{RST}  {msg}")
def info(msg): print(f"     {DIM}{msg}{RST}")

def make_ssl():
    try:    return ssl.create_default_context()
    except: return ssl._create_unverified_context()
SSL_CTX = make_ssl()

# ── Subreddit definitions ─────────────────────────────────────────────────────
SUBREDDITS = [
    {
        "name":       "relationships",
        "domain":     "General relationship issues — conflict, communication, support",
        "plef_focus": ["GASE", "PTI", "NAVA", "Attachment"],
        "risk":       "LOW",
        "min_words":  80,
        "min_score":  20,
        "target":     300,
    },
    {
        "name":       "relationship_advice",
        "domain":     "Advice-seeking relationship narratives",
        "plef_focus": ["PTI", "GASE", "COGS", "Power Dynamics"],
        "risk":       "LOW",
        "min_words":  80,
        "min_score":  10,
        "target":     300,
    },
    {
        "name":       "BreakUps",
        "domain":     "Dissolution narratives — Duck (1982) stages",
        "plef_focus": ["LEWI", "NAVA", "TEG", "Exit Signals"],
        "risk":       "LOW",
        "min_words":  60,
        "min_score":  5,
        "target":     200,
    },
    {
        "name":       "survivinginfidelity",
        "domain":     "Betrayal and trust violation narratives",
        "plef_focus": ["TIES", "GASE", "COGS", "Horsemen"],
        "risk":       "LOW-MEDIUM",
        "min_words":  80,
        "min_score":  10,
        "target":     200,
    },
    {
        "name":       "heartbreak",
        "domain":     "Grief and emotional loss narratives",
        "plef_focus": ["TEG", "NAVA", "LEWI", "Sentiment"],
        "risk":       "LOW",
        "min_words":  50,
        "min_score":  5,
        "target":     150,
    },
    {
        "name":       "confession",
        "domain":     "High emotional disclosure narratives",
        "plef_focus": ["VADS", "CD-index", "PTI"],
        "risk":       "LOW-MEDIUM",
        "min_words":  60,
        "min_score":  10,
        "target":     150,
    },
    {
        "name":       "emotionalsupport",
        "domain":     "Vulnerability and self-disclosure",
        "plef_focus": ["VADS", "Attachment", "GASE"],
        "risk":       "LOW",
        "min_words":  50,
        "min_score":  5,
        "target":     150,
    },
    {
        "name":       "NarcissisticAbuse",
        "domain":     "Power asymmetry and coercive control narratives",
        "plef_focus": ["PAI", "PTI", "Power Dynamics", "TIES"],
        "risk":       "HIGH — clinical risk. Handle ethically. Anonymise completely.",
        "min_words":  80,
        "min_score":  10,
        "target":     100,
    },
]

# ── Auto-labelling ────────────────────────────────────────────────────────────
POS_WORDS = {"love","happy","wonderful","amazing","grateful","thankful","blessed",
             "joy","trust","hope","better","healed","healing","growing","good",
             "great","beautiful","kind","supportive","caring","healthy","safe",
             "progress","moving on","stronger","recovered","grateful","cherish"}
NEG_WORDS = {"hate","angry","hurt","betrayed","broken","destroyed","terrible",
             "awful","horrible","worthless","abandoned","alone","lonely","scared",
             "afraid","anxiety","depressed","toxic","abusive","controlling","sad",
             "devastated","hopeless","helpless","cheated","lied","manipulated",
             "narcissist","gaslight","trauma","ptsd","abuse","coercive","violated"}

def auto_sentiment(text):
    words = re.findall(r"[a-z]+", text.lower())
    p = sum(1 for w in words if w in POS_WORDS)
    n = sum(1 for w in words if w in NEG_WORDS)
    if p > n * 1.5: return "pos"
    if n > p * 1.5: return "neg"
    return "neu"

def auto_emotion(text):
    t = text.lower()
    scores = {
        "anger":   sum(t.count(w) for w in ["angry","furious","rage","hate","irritated"]),
        "sadness": sum(t.count(w) for w in ["sad","grief","devastated","lonely","miss","cry","lost","heartbroken"]),
        "fear":    sum(t.count(w) for w in ["scared","afraid","terrified","anxious","worried","panic"]),
        "joy":     sum(t.count(w) for w in ["happy","excited","grateful","wonderful","love","joy"]),
        "trust":   sum(t.count(w) for w in ["trust","believe","safe","secure","faithful","honest"]),
        "disgust": sum(t.count(w) for w in ["disgusted","repulsed","sick","vile","revolted"]),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "none"

def clean_text(text):
    if not text or text in ("[deleted]","[removed]",""): return ""
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"&amp;","&",text); text = re.sub(r"&lt;","<",text)
    text = re.sub(r"&gt;",">",text)
    text = re.sub(r"\n{3,}","\n\n",text)
    return text.strip()

def word_count(text):
    return len(re.findall(r"\b\w+\b", text))

# ── Reddit API downloader ─────────────────────────────────────────────────────
def fetch_reddit_page(subreddit, after=None, limit=100, sort="top", timeframe="all"):
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={timeframe}"
    if after: url += f"&after={after}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 PLEF-Academic-Research/2.0"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code==429:
            warn("Rate limited. Waiting 30 seconds..."); time.sleep(30); return None
        elif e.code==403:
            return "FORBIDDEN"
        warn(f"HTTP {e.code}"); return None
    except Exception as e:
        warn(f"Error: {e}"); return None

def download_subreddit(subreddit_cfg, test_mode=False):
    """Download posts from one subreddit. Returns list of post dicts."""
    name       = subreddit_cfg["name"]
    target     = 20 if test_mode else subreddit_cfg["target"]
    min_words  = subreddit_cfg["min_words"]
    min_score  = subreddit_cfg["min_score"]

    posts  = []
    after  = None
    pages  = 0
    max_pages = 15

    while len(posts) < target and pages < max_pages:
        data = fetch_reddit_page(name, after=after)
        if data == "FORBIDDEN":
            warn(f"r/{name}: blocked by Reddit. Skipping.")
            return posts, "FORBIDDEN"
        if not data:
            pages += 1; time.sleep(2); continue
        try:
            children = data["data"]["children"]
            after    = data["data"]["after"]
        except (KeyError, TypeError):
            break

        new = 0
        for child in children:
            post = child.get("data",{})
            selftext = clean_text(post.get("selftext",""))
            title    = post.get("title","").strip()
            score    = post.get("score",0)
            post_id  = post.get("id",f"p{len(posts):04d}")
            full_text = f"{title}. {selftext}".strip() if selftext else title
            if word_count(full_text) < min_words: continue
            if score < min_score: continue
            if not selftext: continue
            posts.append({
                "id":         f"{name}_{post_id}",
                "subreddit":  name,
                "text":       full_text,
                "title":      title,
                "sentiment":  auto_sentiment(full_text),
                "emotion":    auto_emotion(full_text),
                "attachment": "none",
                "score":      score,
                "n_words":    word_count(full_text),
            })
            new += 1
            if len(posts) >= target: break

        print(f"\r    r/{name}: {len(posts)}/{target} posts collected "
              f"(page {pages+1}, +{new} this page)  ", end="", flush=True)
        if not after: break
        pages += 1
        time.sleep(2.5)

    print()
    return posts, "OK"

def save_subreddit_csv(posts, subreddit_name):
    """Save individual subreddit CSV."""
    out = SCRIPT_DIR / f"corpus_{subreddit_name}.csv"
    fields = ["id","subreddit","text","sentiment","emotion","attachment","score","n_words","title"]
    with open(out,"w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(posts)
    return out

def print_stats(posts, name):
    if not posts: return
    sents = Counter(p["sentiment"] for p in posts)
    emos  = Counter(p["emotion"] for p in posts)
    words = [p["n_words"] for p in posts]
    avg_w = sum(words)/len(words) if words else 0
    print(f"\n  {BLD}{name} statistics:{RST}")
    print(f"    Total posts:  {len(posts)}")
    print(f"    Avg words:    {avg_w:.0f}")
    print(f"    Sentiment:    ", end="")
    for s,c in sorted(sents.items()):
        print(f"{s}={c}({100*c/len(posts):.0f}%)  ", end="")
    print()
    print(f"    Top emotions: ", end="")
    for e,c in emos.most_common(3):
        print(f"{e}={c}  ", end="")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    head("Extended Reddit Multi-Subreddit Downloader")
    sub_names = ", ".join("r/"+s["name"] for s in SUBREDDITS)
    print(f"  Subreddits: {sub_names}")
    print()

    # Test connection
    info("Testing connection to Reddit...")
    test = fetch_reddit_page("relationship_advice", limit=1)
    if test is None:
        err("Cannot reach Reddit. Check internet connection."); input("\nEnter to exit..."); return
    if test == "FORBIDDEN":
        err("Reddit is blocking this connection."); input("\nEnter to exit..."); return
    ok("Connection successful.")
    print()

    # Options
    print(f"  {BLD}Download options:{RST}")
    print(f"  {CYN}1{RST}  Full download (all 8 subreddits, recommended)")
    print(f"  {CYN}2{RST}  Core only (r/relationships + r/relationship_advice + r/BreakUps)")
    print(f"  {CYN}3{RST}  Quick test (20 posts per subreddit)")
    choice = input(f"\n  Choice [1/2/3]: ").strip()
    if choice=="2":
        selected = [s for s in SUBREDDITS if s["name"] in
                    ("relationships","relationship_advice","BreakUps")]
    elif choice=="3":
        selected = SUBREDDITS; test_mode = True
    else:
        selected = SUBREDDITS
    test_mode = (choice=="3")

    print()
    # High-risk warning
    high_risk = [s for s in selected if "HIGH" in s["risk"]]
    if high_risk:
        print(f"  {YLW}{'─'*60}{RST}")
        print(f"  {YLW}CLINICAL RISK WARNING:{RST}")
        for s in high_risk:
            print(f"  r/{s['name']}: {s['risk']}")
        print(f"  {YLW}These posts will be downloaded and saved locally only.{RST}")
        print(f"  {YLW}Anonymise ALL usernames before sharing or publishing.{RST}")
        print(f"  {YLW}{'─'*60}{RST}")
        confirm = _safe_input("\n  Confirm download of high-risk subreddits? [Y/N]: ", "N").strip().upper()
        if confirm != "Y":
            selected = [s for s in selected if "HIGH" not in s["risk"]]
            warn("High-risk subreddits excluded.")
    print()

    all_posts        = []
    subreddit_counts = {}
    blocked          = []
    failed           = []

    for cfg in selected:
        name = cfg["name"]
        head(f"Downloading r/{name}")
        print(f"  Domain:  {cfg['domain']}")
        print(f"  Focus:   {', '.join(cfg['plef_focus'])}")
        print(f"  Target:  {20 if test_mode else cfg['target']} posts")
        print()

        posts, status = download_subreddit(cfg, test_mode=test_mode)
        if status == "FORBIDDEN":
            blocked.append(name); continue
        if not posts:
            failed.append(name); continue

        # Save individual subreddit CSV
        out = save_subreddit_csv(posts, name)
        ok(f"Saved: {out.name}  ({len(posts)} posts)")
        print_stats(posts, f"r/{name}")
        all_posts.extend(posts)
        subreddit_counts[name] = len(posts)
        time.sleep(1)

    if not all_posts:
        err("No posts downloaded from any subreddit.")
        _safe__safe_input("\nPress Enter to exit..."); return

    # Save merged corpus
    head(f"Saving combined corpus ({len(all_posts):,} posts total)")
    merged_path = SCRIPT_DIR / "relationship_corpus_FULL.csv"
    fields = ["id","subreddit","text","sentiment","emotion","attachment","score","n_words","title"]
    with open(merged_path,"w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(all_posts)
    ok(f"relationship_corpus_FULL.csv  ({len(all_posts):,} posts)")

    # Also save in PLEF format
    plef_path = SCRIPT_DIR / "reddit_posts_corpus.csv"
    backup    = SCRIPT_DIR / "reddit_posts_corpus_original.csv"
    if not backup.exists() and plef_path.exists():
        import shutil; shutil.copy(plef_path, backup)
        ok(f"Backed up original to {backup.name}")
    with open(plef_path,"w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(all_posts)
    ok(f"reddit_posts_corpus.csv updated (PLEF auto-detects this)")

    # Summary
    head("Download Complete")
    print(f"  {BLD}Posts per subreddit:{RST}")
    for name, count in subreddit_counts.items():
        bar = "█" * int(count/max(subreddit_counts.values())*30)
        print(f"    r/{name:<28} {bar} {count}")

    if blocked: warn(f"Blocked by Reddit: {', '.join(f'r/{n}' for n in blocked)}")
    if failed:  warn(f"No posts retrieved: {', '.join(f'r/{n}' for n in failed)}")

    sent_counts = Counter(p["sentiment"] for p in all_posts)
    print(f"\n  {BLD}Combined sentiment:{RST}")
    for s,c in sorted(sent_counts.items()):
        bar = "█" * int(c/len(all_posts)*40)
        print(f"    {s}  {bar}  {c} ({100*c/len(all_posts):.1f}%)")

    print(f"\n  {BLD}Next steps:{RST}")
    print(f"  1. Run:  python multi_dataset_analysis.py")
    print(f"     This will analyse all subreddits in the combined corpus")
    print(f"  2. Run:  python experimental_design.py")
    print(f"     This runs formal hypothesis tests and ablation studies")
    print(f"\n  {BLD}For separate subreddit analysis:{RST}")
    for name in subreddit_counts:
        print(f"    python plef_v7.py --batch reddit_posts\\  (filter by subreddit column)")
    print()
    _safe_input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
