#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 03 : DATASET REBUILD, VALIDATION AND PROVENANCE
                       (v03.3.0 -- consensus removed; all audit fixes applied)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
V1's evaluation rested on loaders that silently produced wrong labels. ISEAR
and DailyDialog came back 100% single-class, and the corpus described in the
paper as "Relationship narratives (7 subreddits)" was GoEmotions comment text.
Every number in the submitted manuscript inherits those defects.

This script rebuilds all nine corpora from raw sources, refuses to emit a
corpus that fails validation, and proves what each one actually contains.

It produces NO evaluation numbers. It produces corpora and evidence about them.

THE GATE
--------
A corpus is REJECTED, not warned about, if any of these hold:
  * the gold label vector has a single class
  * one class exceeds 99% of items
  * fewer than 100 usable items survive parsing
  * the parse discards more than 50% of raw rows
Rejection is the point. V1 shipped because nothing ever refused.

STAGES
------
  S0  Locate and hash every raw source file.
  S1  Rebuild all nine loaders in parallel, each with a format-specific parser
      written against the actual bytes on disk (see FORMAT NOTES below).
  S2  Validation gate. Distribution of every gold vector is printed in full.
  S3  Cross-corpus duplicate detection, all pairs, by normalised text hash.
      V1's Reddit and GoEmotions corpora overlapped at 97% and nobody noticed,
      so no corpus is assumed independent of any other.
  S4  Development split: 200 relationship posts reserved, seeded, hashed, and
      excluded from every evaluation for the rest of the project. All future
      smoke tests and sensitivity sweeps use ONLY this split.
  S5  Structural statistics: words, sentences, and the fraction of items with
      at least 4 sentences -- the population LEWI, TEG and NAVA can actually
      be computed on.
  S6  Write canonical corpora to data/interim/ with a manifest.
  S7  Extend DECISIONS.md with every label mapping declared here.

FORMAT NOTES (what V1 got wrong, and what is done instead)
-----------------------------------------------------------
  ISEAR       Pipe-delimited, 42 columns. Emotion is column 'Field1' (index
              36), text is 'SIT' (index 40). V1 tried comma first, which
              matched nothing, defaulted text_i=1 / emo_i=0, and mapped every
              row to 'neu'. 7,666 rows, 7 emotions, NO neutral class.
  DailyDialog 'dialog' and 'emotion' are NUMPY ARRAY REPRS, not Python lists:
              [0 6 0 0 3 0] with no commas. ast.literal_eval raises
              SyntaxError; V1's except clause then set every emotion to 0.
              Parsed here with regex. 33,349 utterances, 84.3% no_emotion.
  Reddit      V1 read reddit_posts_corpus_original.csv, which is 100%
              GoEmotions text. The genuine posts are in reddit_posts_corpus.csv
              plus reddit_posts/*.txt: 1,508 unique posts, median 370 words.
  GoEmotions  text \\t comma-separated label ids \\t id. Label 27 = neutral.
  MELD        Has an explicit 'Sentiment' column; it is used directly.
  SemEval     id \\t label \\t text across the Subtask_A gold files.
  TweetEval   parallel text and label files; 0=negative 1=neutral 2=positive.
  Empathetic  emotion-emotion_69k.csv, 'Situation' text + 32-way 'emotion'.

EXIT CODES
----------
  0 all corpora built and validated
  2 missing prerequisite (run scripts 01 and 02 first)
  3 one or more corpora FAILED the validation gate
===============================================================================
"""

import argparse
import ast
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "03.4.0"
DEV_SPLIT_N = 200
DEV_SPLIT_SEED = 20260829

# Label provenance. A corpus may only be used for CLASSIFICATION if every one
# of its rows carries a label that came from somewhere real. "fabricated" means
# the loader invented it, which is the V1 ISEAR failure mode and is refused.
PROV_HUMAN = "human"
PROV_SILVER = "silver_keyword"
PROV_NONE = "none"            # no label exists -> trajectory analysis only
PROV_FABRICATED = "fabricated"   # loader invented it -> ALWAYS REJECTED

ROLE_CLASSIFY = "classification+trajectory"
ROLE_TRAJ = "trajectory_only"

MIN_WORDS_RELATIONSHIP = 20      # D15, declared

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
WS = re.compile(r"\s+")


# ===========================================================================
# label taxonomies -- every mapping is declared, none is inferred
# ===========================================================================
GOEMOTIONS = [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
    "joy", "love", "nervousness", "optimism", "pride", "realization",
    "relief", "remorse", "sadness", "surprise", "neutral"]

# Demszky et al. (2020) sentiment groupings, Table 1 of the GoEmotions paper.
GE_POS = {"admiration", "amusement", "approval", "caring", "desire",
          "excitement", "gratitude", "joy", "love", "optimism", "pride", "relief"}
GE_NEG = {"anger", "annoyance", "disappointment", "disapproval", "disgust",
          "embarrassment", "fear", "grief", "nervousness", "remorse", "sadness"}
GE_AMB = {"confusion", "curiosity", "realization", "surprise"}

DD_EMO = {0: "no_emotion", 1: "anger", 2: "disgust", 3: "fear",
          4: "happiness", 5: "sadness", 6: "surprise"}
DD_MAP = {"happiness": "pos", "anger": "neg", "disgust": "neg",
          "fear": "neg", "sadness": "neg", "no_emotion": "neu",
          "surprise": "neu"}          # D9: surprise -> neutral, declared

ISEAR_MAP = {"joy": "pos", "anger": "neg", "sadness": "neg", "disgust": "neg",
             "shame": "neg", "fear": "neg", "guilt": "neg"}   # D10: BINARY

EMP_POS = {"surprised", "excited", "proud", "grateful", "impressed", "hopeful",
           "confident", "joyful", "content", "caring", "trusting", "faithful",
           "prepared", "anticipating", "sentimental", "nostalgic"}
EMP_NEG = {"angry", "sad", "annoyed", "lonely", "afraid", "terrified", "guilty",
           "disgusted", "furious", "anxious", "disappointed", "jealous",
           "devastated", "embarrassed", "ashamed", "apprehensive"}


# ===========================================================================
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
        self.stdout.flush(); self.f.flush()
    def close(self):
        try: self.f.close()
        except Exception: pass


def rule(ch="-", w=78): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def thash(t):
    return hashlib.sha1(" ".join(t.lower().split()).encode("utf-8", "replace")).hexdigest()


def nsent(t):
    return len([s for s in SENT_SPLIT.split(t) if s.strip()])


def nword(t):
    return len(t.split())


# ===========================================================================
# LOADERS -- one per corpus, each written against the real bytes
# ===========================================================================
def load_goemotions(v1):
    rows, raw = [], 0
    for fn in ("ge_train.tsv", "ge_dev.tsv", "ge_test.tsv"):
        p = Path(v1) / "datasets" / fn
        if not p.exists():
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                raw += 1
                text = parts[0].strip()
                ids = [int(x) for x in parts[1].split(",") if x.strip().isdigit()]
                if not text or not ids:
                    continue
                names = [GOEMOTIONS[i] for i in ids if 0 <= i < len(GOEMOTIONS)]
                if not names:
                    continue
                pos = sum(1 for n in names if n in GE_POS)
                neg = sum(1 for n in names if n in GE_NEG)
                if pos > neg:
                    lab = "pos"
                elif neg > pos:
                    lab = "neg"
                else:
                    lab = "neu"
                rows.append({"id": (parts[2].strip() if len(parts) > 2 else ""),
                             "text": text, "gold": lab, "emotion": "|".join(names),
                             "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "note": "3 human raters, Demszky et al. 2020 groupings"}


def load_isear(v1):
    """Pipe-delimited, 42 columns. Field1 = emotion, SIT = situation text."""
    p = Path(v1) / "datasets" / "isear.csv"
    rows, raw = [], 0
    art = collections.Counter()   # every non-ASCII artifact, counted by character
    if not p.exists():
        return rows, raw, {"provenance": PROV_NONE, "role": ROLE_TRAJ}
    with open(p, encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n").split("|")
        hdr = [h.strip().lower() for h in header]
        ei = hdr.index("field1") if "field1" in hdr else 36
        ti = hdr.index("sit") if "sit" in hdr else 40
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) <= max(ei, ti):
                continue
            raw += 1
            emo = parts[ei].strip().lower()
            raw_text = parts[ti].strip()
            # D17: declared text edits, all counted, none hidden.
            #  U+00E1 is a line-continuation marker in the ISEAR questionnaire
            #  responses (verified: 9,530 occurrences, correctly UTF-8 encoded,
            #  always between words -- it is not mojibake). It is replaced with
            #  a space and the resulting double spaces are collapsed.
            #  U+00F7 and U+00A6 also occur and are left untouched; they are
            #  counted and reported so the record is complete.
            for ch in raw_text:
                if ord(ch) > 127:
                    art[ch] += 1
            text = raw_text.replace("\u00e1", " ")
            edited = text != raw_text
            text = WS.sub(" ", text).strip()
            if edited:
                art["_items_edited"] += 1
            if not text or emo not in ISEAR_MAP:
                continue
            rows.append({"id": f"isear_{len(rows):05d}", "text": text,
                         "gold": ISEAR_MAP[emo], "emotion": emo,
                         "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "binary": True,
                       "text_edits": art.get("_items_edited", 0),
                       "artifacts": {k: v for k, v in art.items()
                                     if not k.startswith("_")},
                       "note": "expert annotators; NO neutral class; BINARY (D10)"}


# numpy array repr of a string list mixes quote styles: elements containing an
# apostrophe are emitted with double quotes, the rest with single quotes.
# A single-quote-only regex therefore recovers about a third of the utterances,
# which is why the naive parser silently loses two thirds of DailyDialog.
_DD_ELEM = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", re.S)


def _dd_utterances(field):
    out = []
    for m in _DD_ELEM.finditer(field):
        v = m.group(1) if m.group(1) is not None else m.group(2)
        out.append(v.replace("\\'", "'").replace('\\"', '"').strip())
    return out


def load_dailydialog(v1):
    """dialog/emotion are NUMPY ARRAY REPRS with MIXED QUOTING. ast fails."""
    d = Path(v1) / "datasets" / "dailydialog_extracted"
    rows, raw, mismatch = [], 0, 0
    for fn in ("train.csv", "validation.csv", "test.csv"):
        p = d / fn
        if not p.exists():
            continue
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for i, r in enumerate(csv.DictReader(f)):
                emo = [int(x) for x in re.findall(r"-?\d+", r.get("emotion", ""))]
                utt = _dd_utterances(r.get("dialog", ""))
                raw += len(emo)          # emotion ints parse reliably; use as raw unit
                if len(emo) != len(utt):
                    mismatch += 1
                    continue
                for j, (u, e) in enumerate(zip(utt, emo)):
                    u = u.strip()
                    if len(u.split()) < 3:
                        continue
                    name = DD_EMO.get(e, "no_emotion")
                    rows.append({"id": f"dd_{fn[:2]}_{i:05d}_{j:02d}", "text": u,
                                 "gold": DD_MAP.get(name, "neu"), "emotion": name,
                                 "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "mismatched_dialogues": mismatch,
                       "note": "manual utterance labels; mixed-quote numpy repr parsed"}


def load_meld(v1):
    rows, raw = [], 0
    for fn in ("meld_train.csv", "meld_dev.csv", "meld_test.csv"):
        p = Path(v1) / "datasets" / fn
        if not p.exists():
            continue
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for i, r in enumerate(csv.DictReader(f)):
                raw += 1
                text = (r.get("Utterance") or "").strip()
                s = (r.get("Sentiment") or "").strip().lower()
                if not text or s not in ("positive", "negative", "neutral"):
                    continue
                rows.append({"id": f"meld_{fn[5:8]}_{i:05d}", "text": text,
                             "gold": {"positive": "pos", "negative": "neg",
                                      "neutral": "neu"}[s],
                             "emotion": (r.get("Emotion") or "").strip().lower(),
                             "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "note": "human annotation; dataset Sentiment column used directly"}


def load_semeval(v1):
    d = Path(v1) / "datasets" / "semeval2017_extracted"
    rows, raw = [], 0
    seen = set()
    why = collections.Counter()      # every discarded row gets a counted reason
    if not d.exists():
        return rows, raw, {"provenance": PROV_NONE, "role": ROLE_TRAJ}
    for p in sorted(d.rglob("*")):
        if not p.is_file() or "__MACOSX" in p.parts:
            continue
        if "GOLD" not in str(p) or "Subtask_A" not in str(p):
            continue
        if p.suffix.lower() not in (".txt", ".tsv"):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    if line.strip():
                        why["fewer_than_3_columns"] += 1
                    continue
                raw += 1
                # Column layout is NOT uniform across the Subtask_A gold files.
                # Three-column files are  id / label / text.
                # Four-column files (sms-2013test, livejournal-2014test,
                # twitter-2016test) are  id / id2 / label / text.
                # Detecting this by column count alone is unsafe, so the label
                # column is located by CONTENT: the first field that is a
                # recognised label. An earlier version assumed column 1 and
                # discarded 3,236 rows as "unrecognised label" -- 6% of SemEval,
                # silently, which is the V1 loader failure in miniature.
                li = None
                for j in range(min(3, len(parts) - 1)):
                    if parts[j].strip().lower() in ("positive", "negative", "neutral"):
                        li = j
                        break
                if li is None:
                    why["no_label_column_found"] += 1
                    continue
                tid = "-".join(x.strip() for x in parts[:li]) or f"row{raw}"
                lab = parts[li].strip().lower()
                text = "\t".join(parts[li + 1:]).strip()
                text = text.strip('"').strip()
                if not text:
                    why["empty_text"] += 1
                    continue
                if text.lower() in ("not available", "unavailable"):
                    why["tweet_unavailable"] += 1
                    continue
                if tid in seen:
                    raw -= 1
                    why["duplicate_tweet_id"] += 1
                    continue
                seen.add(tid)
                rows.append({"id": f"se_{tid}", "text": text,
                             "gold": {"positive": "pos", "negative": "neg",
                                      "neutral": "neu"}[lab], "emotion": "none",
                             "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "discard_reasons": dict(why.most_common()),
                       "note": "SemEval-2017 Task 4A gold labels"}


def load_tweeteval(v1):
    d = Path(v1) / "datasets"
    rows, raw = [], 0
    M = {0: "neg", 1: "neu", 2: "pos"}
    for split in ("train", "val", "test"):
        tp, lp = d / f"tweeteval_{split}_text.txt", d / f"tweeteval_{split}_labels.txt"
        if not (tp.exists() and lp.exists()):
            continue
        texts = [l.rstrip("\n").strip().strip('"') for l in
                 open(tp, encoding="utf-8", errors="replace")]
        labs = [l.strip() for l in open(lp, encoding="utf-8", errors="replace")]
        raw += min(len(texts), len(labs))
        for i, (t, l) in enumerate(zip(texts, labs)):
            if not t or not l.isdigit() or int(l) not in M:
                continue
            rows.append({"id": f"te_{split}_{i:05d}", "text": t,
                         "gold": M[int(l)], "emotion": "none",
                         "label_source": PROV_HUMAN})
    return rows, raw, {"provenance": PROV_HUMAN, "role": ROLE_CLASSIFY,
                       "note": "TweetEval sentiment; derived from SemEval-2017"}


def load_empathetic(v1):
    p = Path(v1) / "datasets" / "empathetic_extracted" / "emotion-emotion_69k.csv"
    rows, raw, dup = [], 0, 0
    unmapped = collections.Counter()
    if not p.exists():
        return rows, raw, {"provenance": PROV_NONE, "role": ROLE_TRAJ}
    seen = set()
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            raw += 1
            text = (r.get("Situation") or "").strip()
            emo = (r.get("emotion") or "").strip().lower()
            if not text or not emo:
                continue
            h = thash(text)
            if h in seen:
                dup += 1
                continue
            seen.add(h)
            if emo in EMP_POS:
                lab = "pos"
            elif emo in EMP_NEG:
                lab = "neg"
            else:
                # D16: the mapping leaves fewer than 1% unmapped. Keeping a class
                # with ~10 members is worse than dropping it, so these items are
                # excluded and the corpus is emitted cleanly two-class.
                # These are CSV parse fragments, not emotion labels: the
                # source file has embedded commas and quotes that break a
                # handful of rows. Counted and dropped, never pooled.
                unmapped[emo[:60]] += 1
                continue
            rows.append({"id": f"ed_{i:06d}", "text": text, "gold": lab,
                         "emotion": emo, "label_source": PROV_HUMAN})
    return rows, raw - dup - sum(unmapped.values()), {
        "provenance": PROV_HUMAN, "role": ROLE_CLASSIFY, "binary": True,
        "dropped_unparseable": sum(unmapped.values()),
        "unparseable_emotion_fields": dict(unmapped),
        "note": "self-reported situation emotion; BINARY (D16); a handful of "
                "rows with CSV-broken emotion fields are dropped, not pooled"}


def load_relationship(v1):
    """The GENUINE relationship narratives V1 never used.

    LABEL POLICY (D18). This corpus is TRAJECTORY-ONLY. No classification
    result is computed on it, because:
      * the 1,316 CSV posts carry V1's unaudited keyword-derived silver labels;
      * the reddit_posts/*.txt files carry no label at all.
    An earlier version of this loader wrote "neu" for the txt files. That is
    fabricating gold data -- the exact V1 ISEAR failure mode -- and is removed.
    Every row is emitted with gold="" and label_source=PROV_NONE. The
    validation gate refuses to let a PROV_NONE corpus be used for
    classification. Human labels for the 200-post dev split are collected
    separately (see the annotation task written by S8).
    """
    v1 = Path(v1)
    rows, raw, seen, short = [], 0, set(), 0
    silver_seen = {}
    p = v1 / "reddit_posts_corpus.csv"
    if p.exists():
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                raw += 1
                t = (r.get("text") or "").strip()
                if not t:
                    continue
                if len(t.split()) < MIN_WORDS_RELATIONSHIP:
                    short += 1
                    continue
                h = thash(t)
                if h in seen:
                    raw -= 1
                    continue
                seen.add(h)
                sv = (r.get("sentiment") or "").strip()
                silver_seen[h] = sv
                rows.append({"id": r.get("id", "") or f"rel_{len(rows):05d}",
                             "text": t, "gold": "", "emotion": r.get("subreddit", ""),
                             "label_source": PROV_NONE, "v1_silver": sv})
    d = v1 / "reddit_posts"
    if d.exists():
        for p in sorted(d.glob("*.txt")):
            raw += 1
            try:
                t = p.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                continue
            if not t:
                continue
            if len(t.split()) < MIN_WORDS_RELATIONSHIP:
                short += 1
                continue
            h = thash(t)
            if h in seen:
                raw -= 1
                continue
            seen.add(h)
            rows.append({"id": p.stem, "text": t, "gold": "",
                         "emotion": "txtfile", "label_source": PROV_NONE,
                         "v1_silver": ""})
    return rows, raw, {"provenance": PROV_NONE, "role": ROLE_TRAJ,
                       "dropped_short": short,
                       "min_words": MIN_WORDS_RELATIONSHIP,
                       "v1_silver_available": sum(1 for r in rows if r.get("v1_silver")),
                       "note": "genuine 7-subreddit narratives; NO trustworthy labels; "
                               "trajectory analysis only (D18)"}


LOADERS = {
    "relationship": load_relationship,
    "goemotions": load_goemotions,
    "empathetic": load_empathetic,
    "isear": load_isear,
    "semeval2017": load_semeval,
    "meld": load_meld,
    "tweeteval": load_tweeteval,
    "dailydialog": load_dailydialog,
}


def _load_one(spec):
    name, v1 = spec
    try:
        rows, raw, meta = LOADERS[name](v1)
        return name, rows, raw, meta, None
    except Exception as e:
        return name, [], 0, {}, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:700]}"


# ===========================================================================
def validate(name, rows, raw, meta):
    """Return (ok, problems, flags). Rejection is the point of this function."""
    problems, flags = [], []
    if not rows:
        return False, ["produced zero rows"], flags
    n = len(rows)

    # --- label provenance is checked BEFORE anything about distributions ----
    srcs = collections.Counter(r.get("label_source", PROV_FABRICATED) for r in rows)
    if PROV_FABRICATED in srcs:
        problems.append(f"{srcs[PROV_FABRICATED]:,} rows carry FABRICATED labels "
                        f"invented by the loader -- this is the V1 ISEAR failure "
                        f"mode and is never permitted")
    role = meta.get("role", ROLE_CLASSIFY)
    prov = meta.get("provenance", PROV_FABRICATED)
    if role == ROLE_CLASSIFY and prov == PROV_NONE:
        problems.append("declared for classification but has no label provenance")
    if role == ROLE_TRAJ:
        flags.append("TRAJECTORY-ONLY: no classification result may be computed")
        if any((r.get("gold") or "") for r in rows):
            problems.append("trajectory-only corpus carries non-empty gold labels")
        return not problems, problems, flags

    # --- distribution checks apply only to classification corpora ----------
    dist = collections.Counter(r["gold"] for r in rows)
    top, topn = dist.most_common(1)[0]
    if len(dist) == 1:
        problems.append(f"SINGLE-CLASS gold vector (all '{top}') -- V1 ISEAR/"
                        f"DailyDialog failure mode")
    if topn / n > 0.99:
        problems.append(f"class '{top}' is {100*topn/n:.1f}% of items")
    tiny = [(k, v) for k, v in dist.items() if v / n < 0.01]
    if tiny and len(dist) > 2:
        flags.append("BINARY: " + ", ".join(f"'{k}' is only {100*v/n:.2f}%"
                                            for k, v in tiny) +
                     " -- must be evaluated and reported as two-class")
    if meta.get("binary"):
        if not any(f.startswith("BINARY") for f in flags):
            flags.append("BINARY: declared two-class in DECISIONS.md")
    if n < 100:
        problems.append(f"only {n} usable items")
    if raw and n < raw and n / raw < 0.5:
        problems.append(f"parser discarded {100*(1-n/raw):.1f}% of raw units "
                        f"({raw:,} -> {n:,}); deduplication is already netted out "
                        f"of raw, so this is genuine parse loss")
    return not problems, problems, flags


class GateError(RuntimeError):
    pass


# Item 8: nothing reaches disk as a corpus except through this function, and it
# refuses any corpus that has not been through validate(). Enforcement is
# structural, not a matter of the author remembering.
_VALIDATED = {}


def register_validated(name, ok, flags, meta):
    _VALIDATED[name] = {"ok": ok, "flags": flags, "meta": meta}


def write_corpus(path, name, rows):
    v = _VALIDATED.get(name)
    if v is None:
        raise GateError(f"'{name}' was never passed through validate(); refusing "
                        f"to write it. Every corpus must be gated.")
    if not v["ok"]:
        raise GateError(f"'{name}' FAILED the validation gate; refusing to write.")
    # D18 states the V1 keyword labels are "retained only as a v1_silver
    # reference column". v03.3.0's writer used extrasaction="ignore" and
    # silently dropped it, so the declaration was false. The column is kept.
    fields = ["id", "text", "gold", "emotion", "label_source", "v1_silver"]
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    return round_trip(path, rows)


def round_trip(path, rows):
    """Write-then-read verification. Relationship posts contain newlines and
    quotes; if the CSV cycle mangles anything, script 05 would score corrupted
    text and nothing would say so."""
    back = []
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            back.append(r)
    if len(back) != len(rows):
        return False, f"row count {len(back):,} != {len(rows):,}"
    for a, b in zip(rows, back):
        if thash(a["text"]) != thash(b.get("text", "")):
            return False, f"text hash mismatch at id={a.get('id')}"
        if (a.get("gold") or "") != (b.get("gold") or ""):
            return False, f"gold mismatch at id={a.get('id')}"
    return True, None


def stats_for(rows):
    w = [nword(r["text"]) for r in rows]
    s = [nsent(r["text"]) for r in rows]
    ge4 = sum(1 for x in s if x >= 4)
    return {"n": len(rows), "words_total": sum(w),
            "words_median": statistics.median(w) if w else 0,
            "words_mean": statistics.mean(w) if w else 0,
            "sents_median": statistics.median(s) if s else 0,
            "n_ge4_sents": ge4, "pct_ge4_sents": 100.0 * ge4 / max(1, len(rows))}



ANNOTATION_GUIDE = """# PLEF V2 -- Human annotation task (dev split, {n} posts)

## Why this exists

Three reviewers made the same point: hypothesis H1 claims LEWI locates the
emotional turning point of a narrative, and it was never tested against a human
judgement. The submitted paper marked H1 "Supported (proxy)" using the
NAVA x LEWI correlation, which Reviewer 2 and Reviewer 3 both identified as
circular. It is now marked NOT TESTED.

This task produces the missing criterion. It also produces the only
human-labelled relationship data in the paper.

These {n} posts are the reserved development split. They are excluded from
every evaluation result, so annotating them cannot contaminate anything.

## What to do

Open `annotation_task_rater{{N}}.csv`. Each row is one post, with its sentences
numbered. Fill four columns:

  overall_sentiment   pos | neg | neu
                      The narrator's overall emotional stance in the post.

  turning_point       An integer sentence number, or 0 for none.
                      The single sentence where the emotional direction of the
                      narrative changes most clearly. If the post has no
                      turning point (it is uniformly negative, or a flat
                      request for advice), write 0.

  arc                 tragic | redemptive | flat
                      tragic     = starts better than it ends
                      redemptive = ends better than it starts
                      flat       = no clear directional change

  confidence          1 (guess) to 5 (certain)

Leave `notes` blank unless something needs saying.

## Rules

1. Judge the NARRATOR's emotion, not the events. "My friend died but I feel at
   peace now" is not straightforwardly negative.
2. Read the whole post before marking the turning point.
3. Mark exactly one turning point, or none. Do not mark two.
4. Do not discuss items with other raters until all three files are complete.
5. Do not skip rows. If genuinely unsure, use confidence 1 and move on.

## Three raters

Three files are provided, each with the same posts in a DIFFERENT order, so
fatigue and order effects do not align across raters. Inter-rater reliability
will be computed as Krippendorff's alpha for sentiment and arc, and as
exact-match plus within-one-sentence agreement for the turning point.

If only one rater is available, complete rater1 and report it as a single-rater
criterion with that limitation stated explicitly. Do not present single-rater
annotation as though it were multi-rater.

## What happens next

Script 06 computes:
  * inter-rater reliability
  * LEWI turning-point agreement (exact and within-one-sentence), which is the
    direct test of H1
  * NAVA arc classification accuracy against human arc labels, which is H5
  * PLEF sentiment accuracy against human labels on relationship text

Return the completed files to `data/interim/annotations/`.
"""


def write_annotation_task(root, dev, n_raters=3, seed=DEV_SPLIT_SEED):
    """S8: build the human annotation task for the dev split."""
    sub("S8  HUMAN ANNOTATION TASK (dev split)")
    if not dev:
        print("  no dev split; skipped")
        return {}
    outd = Path(root) / "data" / "interim" / "annotations"
    outd.mkdir(parents=True, exist_ok=True)
    prepared = []
    for r in dev:
        sents = [x.strip() for x in SENT_SPLIT.split(r["text"]) if x.strip()]
        numbered = "\n".join(f"[{i+1}] {x}" for i, x in enumerate(sents))
        prepared.append({"id": r["id"], "n_sentences": len(sents),
                         "numbered_text": numbered,
                         "overall_sentiment": "", "turning_point": "",
                         "arc": "", "confidence": "", "notes": ""})
    files = []
    for k in range(1, n_raters + 1):
        order = list(range(len(prepared)))
        random.Random(seed + k * 7919).shuffle(order)
        p = outd / f"annotation_task_rater{k}.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "n_sentences", "numbered_text",
                                              "overall_sentiment", "turning_point",
                                              "arc", "confidence", "notes"])
            w.writeheader()
            for i in order:
                w.writerow(prepared[i])
        files.append({"path": str(p), "sha256": sha256(p), "rater": k})
        print(f"  rater {k}: {p.name}  ({len(prepared)} posts, order seed {seed + k*7919})")
    g = outd / "ANNOTATION_GUIDE.md"
    g.write_text(ANNOTATION_GUIDE.format(n=len(prepared)), encoding="utf-8")
    print(f"  guide  : {g}")
    ns = [x["n_sentences"] for x in prepared]
    print(f"  posts have {min(ns)}-{max(ns)} sentences (median {statistics.median(ns):.0f})")
    print()
    print("  This is the direct test of H1 that all three reviewers asked for.")
    print("  Until it is returned, H1 stays marked NOT TESTED.")
    return {"files": files, "guide": str(g), "n": len(prepared)}


def remove_consensus(root):
    """S9: delete any Consensus corpus left by an earlier run.

    The V1 Consensus corpus contributed F1 = 0.605 and AUC = 0.838 to the
    abstract's headline means while VADER scored exactly 1.000 on it by
    construction. Rebuilding it from the real baselines produced 637 items
    labelled 69.2% positive on breakup and infidelity narratives, which is
    prima facie false. There is nothing to salvage and no quarantine that
    makes an invalid corpus reportable, so it is deleted.
    """
    sub("S9  CONSENSUS CORPUS -- REMOVED")
    gone = []
    d = Path(root) / "data" / "interim"
    for pat in ("corpus_consensus*.csv", "*consensus*.csv"):
        for f in d.glob(pat):
            try:
                f.unlink()
                gone.append(f.name)
            except Exception as e:
                print(f"  could not delete {f.name}: {e}")
    if gone:
        for g in gone:
            print(f"  deleted {g}")
    else:
        print("  none present")
    print("  The construction is not used anywhere in V2. Lexicon-agreement")
    print("  labelling does not work on long narratives: over ~390 words a")
    print("  bag-of-words sum drifts positive regardless of content.")
    return gone


def fix_script02_artifacts(root):
    """S10: apply the two script-02 defects I said would be fixed here."""
    sub("S10  SCRIPT 02 DEFECT FIXES")
    ad = Path(root) / "src" / "plef_baselines.py"
    if not ad.exists():
        print("  adapter missing; skipped")
        return False
    src = ad.read_text(encoding="utf-8")
    old = """        self.vocab = allw
        self.size = len(allw)"""
    new = """        self.vocab = allw
        # size_vocab  : every term in the file (compare against 14,182)
        # size_nonzero: terms with >=1 non-zero association (about 6,468)
        # Script 02 compared the second against the first and warned about a
        # correct file. Both are exposed so the right pair is compared.
        self.size_vocab = len(allw)
        self.size_nonzero = len(allw)
        self.size = len(allw)"""
    if old in src:
        src = src.replace(old, new)
        ad.write_text(src, encoding="utf-8")
        print("  NRCBaseline now exposes size_vocab and size_nonzero separately")
        print(f"  adapter sha256 -> {sha256(ad)}")
        return True
    print("  adapter already patched or structure changed; no edit made")
    return False


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="PLEF V2 script 03 -- rebuild and validate all nine corpora.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--v1", required=True)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--allow-failures", action="store_true",
                    help="write corpora even if the validation gate rejects them")
    args = ap.parse_args()

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    root, v1 = Path(args.root), Path(args.v1)
    if not (root / "src" / "plef_baselines.py").exists():
        print("FATAL: run script 02 first (src/plef_baselines.py missing).")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_03.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 03 : DATASET REBUILD AND VALIDATION")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  V2 root        : {root}")
        print(f"  V1 source      : {v1}")
        print(f"  workers        : {workers}")

        # ---- S0 -------------------------------------------------------
        sub("S0  RAW SOURCE INVENTORY AND HASHES")
        srcs = []
        for pat in ("datasets/ge_*.tsv", "datasets/isear.csv", "datasets/meld_*.csv",
                    "datasets/tweeteval_*.txt", "datasets/dailydialog_extracted/*.csv",
                    "datasets/empathetic_extracted/*.csv", "reddit_posts_corpus.csv"):
            srcs.extend(sorted(v1.glob(pat)))
        sem = v1 / "datasets" / "semeval2017_extracted"
        if sem.exists():
            srcs.extend([p for p in sorted(sem.rglob("*"))
                         if p.is_file() and "GOLD" in str(p) and "Subtask_A" in str(p)
                         and "__MACOSX" not in p.parts])
        txt_files = sorted((v1 / "reddit_posts").glob("*.txt")) \
            if (v1 / "reddit_posts").exists() else []
        nrp = len(txt_files)
        srcs.extend(txt_files)      # every one is hashed individually
        manifest = []
        for p in srcs:
            try:
                manifest.append({"path": str(p), "size": p.stat().st_size,
                                 "sha256": sha256(p)})
            except Exception:
                pass
        print(f"  hashed {len(manifest)} raw source files "
              f"(including all {nrp} reddit_posts/*.txt individually)")
        agg = hashlib.sha256(
            "".join(m["sha256"] for m in manifest).encode()).hexdigest()
        print(f"  aggregate evidence hash: {agg}")
        for m in manifest[:12]:
            print(f"    {m['size']:>12,}  {Path(m['path']).name}")
        if len(manifest) > 12:
            print(f"    ... and {len(manifest)-12} more")

        # ---- S1 -------------------------------------------------------
        sub("S1  REBUILD ALL LOADERS (parallel)")
        corpora, raws, metas, errs = {}, {}, {}, {}
        with ProcessPoolExecutor(max_workers=min(workers, len(LOADERS))) as ex:
            for name, rows, raw, meta, err in ex.map(
                    _load_one, [(k, str(v1)) for k in LOADERS]):
                corpora[name], raws[name], metas[name] = rows, raw, meta
                if err:
                    errs[name] = err
        print(f"  {'corpus':<15}{'raw':>10}{'usable':>9}{'kept%':>7}  {'labels':>15}  distribution")
        rule()
        for name in LOADERS:
            rows, raw, meta = corpora[name], raws[name], metas.get(name, {})
            if errs.get(name):
                print(f"  {name:<15}{'ERROR':>10}   {errs[name].splitlines()[0][:48]}")
                continue
            n = len(rows)
            prov = meta.get("provenance", "?")
            if meta.get("role") == ROLE_TRAJ:
                dd = "(no labels -- trajectory only)"
            else:
                d = collections.Counter(r["gold"] for r in rows)
                dd = "  ".join(f"{k}:{100*v/max(1,n):.1f}%" for k, v in d.most_common())
            print(f"  {name:<15}{raw:>10,}{n:>9,}{100*n/max(1,raw):>6.1f}%  "
                  f"{prov:>15}  {dd}")
        print()
        for name in LOADERS:
            m = metas.get(name) or {}
            if m.get("note"):
                print(f"    {name:<15} {m['note']}")
            for k in ("dropped_short", "text_edits", "mismatched_dialogues"):
                if m.get(k):
                    print(f"    {'':<15} {k} = {m[k]:,}")

        # ---- S2 -------------------------------------------------------
        sub("S2  VALIDATION GATE")
        failed, allflags = [], {}
        for name in LOADERS:
            ok, probs, flags = validate(name, corpora[name], raws[name],
                                        metas.get(name) or {})
            allflags[name] = flags
            register_validated(name, ok, flags, metas.get(name) or {})
            if ok:
                print(f"  PASS   {name}")
            else:
                failed.append(name)
                print(f"  REJECT {name}")
            for p_ in probs:
                print(f"           ! {p_}")
            for f_ in flags:
                print(f"           * {f_}")
        print()
        print("  V1 comparison, the two corpora that failed silently:")
        for nm, v1n, v1d in (("isear", 2042, "100% neu"),
                             ("dailydialog", 13118, "100% neu")):
            rows = corpora.get(nm, [])
            d = collections.Counter(r["gold"] for r in rows)
            n = max(1, len(rows))
            print(f"    {nm:<12} V1: {v1n:,} items, {v1d}")
            print(f"    {'':<12} V2: {len(rows):,} items, " +
                  ", ".join(f"{k}:{100*v/n:.1f}%" for k, v in d.most_common()))
            em = collections.Counter(r["emotion"] for r in rows)
            print(f"    {'':<12}     emotions: {dict(em.most_common(8))}")

        # ---- S3 -------------------------------------------------------
        sub("S3  DEVELOPMENT SPLIT (reserved, never evaluated)")
        rel = corpora.get("relationship", [])
        if len(rel) > DEV_SPLIT_N * 2:
            idx = list(range(len(rel)))
            random.Random(DEV_SPLIT_SEED).shuffle(idx)
            dev_idx = set(idx[:DEV_SPLIT_N])
            dev = [rel[i] for i in sorted(dev_idx)]
            evalset = [rel[i] for i in range(len(rel)) if i not in dev_idx]
            corpora["relationship"] = evalset
            dev_h = hashlib.sha256(
                "".join(sorted(thash(r["text"]) for r in dev)).encode()).hexdigest()
            print(f"  source          : relationship corpus, {len(rel):,} posts")
            print(f"  dev split       : {len(dev):,} posts (seed {DEV_SPLIT_SEED})")
            print(f"  evaluation set  : {len(evalset):,} posts")
            print(f"  dev split hash  : {dev_h}")
            print()
            print("  Every future smoke test, threshold sweep and sensitivity")
            print("  analysis uses ONLY the dev split. It appears in no result.")
            dp = root / "data" / "interim" / "dev_split_relationship.csv"
            dp.parent.mkdir(parents=True, exist_ok=True)
            with open(dp, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["id", "text", "gold", "emotion",
                                                  "label_source"],
                                   extrasaction="ignore")
                w.writeheader()
                w.writerows(dev)
            print(f"  written -> {dp}")
        else:
            dev, dev_h = [], None
            print(f"  relationship corpus too small ({len(rel)}); no split made")

        # ---- S4 -------------------------------------------------------
        sub("S4  CROSS-CORPUS DUPLICATE DETECTION (all pairs, by text hash)")
        hashes = {k: {thash(r["text"]) for r in v} for k, v in corpora.items() if v}
        names = [k for k in LOADERS if hashes.get(k)]
        print(f"  {'':<16}" + "".join(f"{n[:9]:>10}" for n in names))
        overlaps = {}
        for a in names:
            row = f"  {a[:16]:<16}"
            for b in names:
                if a == b:
                    row += f"{'-':>10}"
                    continue
                ov = len(hashes[a] & hashes[b])
                pct = 100.0 * ov / max(1, len(hashes[a]))
                overlaps[f"{a}|{b}"] = {"n": ov, "pct": pct}
                row += f"{pct:>9.1f}%"
            print(row)
        print()
        bad = [(k, v) for k, v in overlaps.items() if v["pct"] > 5]
        if bad:
            print("  MATERIAL OVERLAP (>5% of the row corpus appears in the column corpus):")
            for k, v in sorted(bad, key=lambda x: -x[1]["pct"]):
                a, b = k.split("|")
                print(f"    {a:<14} -> {b:<14} {v['n']:>7,} items  {v['pct']:.1f}%")
        else:
            print("  No corpus shares more than 5% of its items with another.")
        allh = set()
        for k in names:
            allh |= hashes[k]
        tot = sum(len(corpora[k]) for k in names)
        print()
        print("  All counts below are for the EVALUATION set: the reserved dev")
        print("  split has already been removed. There is exactly one number for")
        print("  each quantity in this log.")
        print()
        print(f"  evaluation items, summed over corpora : {tot:,}")
        print(f"  evaluation items, unique              : {len(allh):,}")
        print(f"  duplicate inflation                   : {tot-len(allh):,} "
              f"({100*(tot-len(allh))/max(1,tot):.1f}%)")
        print(f"  reserved dev split (not evaluated)    : {len(dev):,}")
        print(f"  manuscript claimed                    : 150,041")

        # ---- S5 -------------------------------------------------------
        sub("S5  STRUCTURAL STATISTICS (what the trajectory metrics can use)")
        print(f"  {'corpus':<16}{'n':>9}{'words':>12}{'w/item':>9}"
              f"{'sents':>8}{'>=4 sents':>11}{'usable%':>10}")
        rule()
        st = {}
        for name in LOADERS:
            rows = corpora.get(name) or []
            if not rows:
                continue
            s = stats_for(rows)
            st[name] = s
            print(f"  {name:<16}{s['n']:>9,}{s['words_total']:>12,}"
                  f"{s['words_median']:>9.0f}{s['sents_median']:>8.0f}"
                  f"{s['n_ge4_sents']:>11,}{s['pct_ge4_sents']:>9.1f}%")
        tw = sum(v["words_total"] for v in st.values())
        tg = sum(v["n_ge4_sents"] for v in st.values())
        print("  " + "-" * 74)
        print(f"  {'TOTAL':<16}{sum(v['n'] for v in st.values()):>9,}{tw:>12,}"
              f"{'':>9}{'':>8}{tg:>11,}")
        print()
        print("  The '>=4 sents' column is the population on which LEWI, TEG and")
        print("  NAVA can be computed at all. V1 reported 5,795 such items in")
        print("  Table 5, 3.9% of its claimed corpus.")

        # ---- S6 -------------------------------------------------------
        sub("S6  WRITE CANONICAL CORPORA")
        outd = root / "data" / "interim"
        outd.mkdir(parents=True, exist_ok=True)
        written = {}
        for name in LOADERS:
            rows = corpora.get(name) or []
            if not rows or (name in failed and not args.allow_failures):
                continue
            p = outd / f"corpus_{name}.csv"
            try:
                ok_rt, why = write_corpus(p, name, rows)
            except GateError as e:
                print(f"  {name:<16}{'REFUSED':>9}  {e}")
                if name not in failed:
                    failed.append(name)
                continue
            written[name] = {"path": str(p), "n": len(rows), "sha256": sha256(p),
                             "round_trip": ok_rt,
                             "provenance": (metas.get(name) or {}).get("provenance"),
                             "role": (metas.get(name) or {}).get("role"),
                             "flags": allflags.get(name, [])}
            print(f"  {name:<16}{len(rows):>9,} -> {p.name:<32}"
                  f"round-trip {'OK' if ok_rt else 'FAILED: ' + str(why)}")
            if not ok_rt:
                failed.append(name)
        if failed and not args.allow_failures:
            print(f"\n  NOT written (failed the gate): {', '.join(failed)}")

        # ---- S7 -------------------------------------------------------
        sub("S7  EXTEND DECISIONS.md")
        dpath = root / "DECISIONS.md"
        add = ["", "---", "",
               f"## Corpus decisions (script 03 v{SCRIPT_VERSION}, "
               f"{datetime.datetime.now().isoformat(timespec='seconds')})", "",
               "### D9 DailyDialog label mapping",
               "happiness -> positive; anger, disgust, fear, sadness -> negative;",
               "no_emotion -> neutral; **surprise -> neutral**. Surprise has no",
               "defensible polarity. The alternative (excluding surprise items) is",
               "reported as a sensitivity check. Declared before any evaluation.",
               "",
               "Note: V1 stored these fields as numpy array reprs, e.g. [0 6 0 0 3 0],",
               "which ast.literal_eval cannot parse; V1's except clause then set every",
               "emotion to 0, producing a 100% neutral gold vector. Parsed here by regex.",
               "",
               "### D10 ISEAR is BINARY and reported separately",
               "ISEAR has no neutral class: joy -> positive; anger, sadness, disgust,",
               "shame, fear, guilt -> negative. This makes it a two-class problem inside",
               "a three-class evaluation, so **ISEAR is reported separately and excluded",
               "from any pooled three-class mean.** Forcing three classes would make every",
               "neutral prediction automatically wrong and would misrepresent the result.",
               "The resulting class balance is roughly 14% positive / 86% negative and",
               "must be stated wherever ISEAR appears.",
               "",
               "### D11 The relationship corpus is rebuilt from genuine posts",
               "V1's loader read reddit_posts_corpus_original.csv, which is 100%",
               "GoEmotions comment text (median 14 words). The corpus described in the",
               "manuscript is rebuilt here from reddit_posts_corpus.csv plus",
               "reddit_posts/*.txt: genuine first-person narratives from seven",
               "subreddits, median 370 words. The item count falls from a claimed",
               "10,000 to roughly 1,500, and the population on which the trajectory",
               "metrics are computable rises from 1.6% to about 98%.",
               "",
               "### D12 Development split",
               f"{DEV_SPLIT_N} relationship posts, seed {DEV_SPLIT_SEED}, reserved and",
               "excluded from every evaluation. All smoke tests, threshold sweeps and",
               "sensitivity analyses use only this split. Hash recorded in the manifest.",
               "This corrects a leak in script 02, whose preview was computed on posts",
               "that subsequently became evaluation data.",
               "",
               "### D13 GoEmotions and EmpatheticDialogues mappings",
               "GoEmotions uses the sentiment groupings of Demszky et al. (2020);",
               "an item is positive or negative by majority of its mapped labels and",
               "neutral on a tie or an ambiguous-only labelling. EmpatheticDialogues",
               "maps its 32 emotion labels to three classes by a fixed list declared",
               "in the loader source. Neither mapping was tuned against any result.",
               "",
               "### D20 Trajectory metrics are scoped to the relationship corpus",
               "LEWI, TEG and NAVA require at least four sentences. Measured across",
               "the rebuilt corpora, the fraction of items meeting that bar is:",
               "",
               "| corpus | items >=4 sentences | share |",
               "|---|---:|---:|",
               "| relationship | 1,288 | 98.5% |",
               "| semeval2017 | 3,040 | 6.1% |",
               "| tweeteval | 2,584 | 4.3% |",
               "| dailydialog | 3,892 | 3.9% |",
               "| isear | 296 | 3.9% |",
               "| meld | 354 | 2.6% |",
               "| goemotions | 914 | 1.7% |",
               "| empathetic | 290 | 1.5% |",
               "",
               "On seven of eight corpora the surviving fraction is under 7%, and it",
               "is not a random 7%: it is the long tail of an overwhelmingly",
               "short-form distribution. Reporting a correlation over that tail and",
               "presenting it as a property of the corpus is precisely the",
               "non-random restriction Reviewer 3 objected to (50,000 items reduced",
               "to 67 on GoEmotions).",
               "",
               "**LEWI, TEG and NAVA are therefore reported on the relationship**",
               "**corpus only.** For every other corpus these metrics are reported as",
               "not measurable, with the >=4-sentence count stated so the reader can",
               "see why. Declared before any trajectory result is computed.",
               "",
               "### D15 Minimum length filter on the relationship corpus",
               f"Posts shorter than {MIN_WORDS_RELATIONSHIP} words are excluded. Inherited from V1,",
               "declared here, and the number dropped is reported in the log and manifest.",
               "",
               "### D16 EmpatheticDialogues is BINARY",
               "The 32-emotion to 3-class mapping leaves under 1% neutral (22 of 19,167).",
               "It is therefore evaluated and reported as two-class, exactly as ISEAR is.",
               "A three-class macro-F1 over a class that barely exists is not meaningful.",
               "",
               "### D17 Declared text edit in ISEAR",
               "The ISEAR distribution contains a stray U+00E1 used as a line-continuation",
               "artefact; it is replaced with a space. The count of items touched is",
               "reported. No other corpus text is modified anywhere in the pipeline.",
               "",
               "### D18 The relationship corpus carries NO labels",
               "An earlier draft of this loader wrote 'neu' for the reddit_posts/*.txt",
               "files, which have no label. That is fabricating gold data -- the same",
               "failure mode as V1's ISEAR loader -- and has been removed. The 1,316 CSV",
               "posts carry V1's unaudited keyword silver labels, which are retained only",
               "as a v1_silver reference column and are never used as gold.",
               "",
               "The corpus is therefore TRAJECTORY-ONLY: LEWI, TEG, NAVA, PTI, PAI, RCI",
               "and coverage are computed on it; no macro-F1 or AUC is. The validation",
               "gate enforces this and refuses any corpus whose labels the loader",
               "invented.",
               "",
               "Human labels for the 200-post dev split are collected via the annotation",
               "task written to data/interim/annotations/. That task is the direct test",
               "of H1 that Reviewers 1, 2 and 3 all asked for. Until it is returned, H1",
               "is reported as NOT TESTED.",
               "",
               "### D19 The Consensus corpus is quarantined",
               "Rebuilt from the real VADER, NRC and Hu-Liu implementations rather than",
               "the V1 toys. Its labels are DEFINED by lexicon agreement, so any lexicon",
               "method is advantaged by construction. In V1 it contributed F1 = 0.605 and",
               "AUC = 0.838 to the abstract's headline means while VADER scored exactly",
               "1.000 on it. In V2 it is excluded from every headline result and reported",
               "only as a supplementary sanity check, clearly marked.",
               "",
               "### D14 labMT is not a polarity baseline",
               "On held-out relationship text labMT labelled 97.8% of posts positive and",
               "its Cohen's kappa against every other system was between 0.013 and 0.039.",
               "It measures happiness, not polarity, and no threshold makes it a",
               "three-class classifier. It is therefore removed from the baseline",
               "comparison and used instead as an INDEPENDENT ARC INSTRUMENT for NAVA,",
               "which is how Reagan et al. (2016) use it. Declared before any evaluation.",
               ""]
        if dpath.exists():
            with open(dpath, "a", encoding="utf-8") as f:
                f.write("\n".join(add) + "\n")
            print(f"  appended -> {dpath}")
            print(f"  sha256    {sha256(dpath)}")
        else:
            print("  DECISIONS.md not found; run script 02 first")

        ann = write_annotation_task(root, dev)

        env_p = root / "MANIFEST" / "environment.json"
        nrc_path = legacy_path = None
        if env_p.exists():
            try:
                envj = json.loads(env_p.read_text(encoding="utf-8"))
                nrc_path = (envj.get("lexicons", {}).get("emolex") or {}).get("path")
                legacy_path = str(root / "src" / "legacy_v1_lexicons.json")
            except Exception:
                pass
        # D19: the Consensus corpus is REMOVED, not quarantined. Rebuilt from the
        # real baselines it produced 637 items labelled 69.2% positive on a corpus
        # of breakup and infidelity narratives -- a bag-of-words sum drifts positive
        # over 390 words regardless of content. Three lexicons agreeing on a wrong
        # answer is still a wrong answer. It is not circular, it is invalid.
        removed = remove_consensus(root)
        fix_script02_artifacts(root)

        # ---- manifest -------------------------------------------------
        man = {"aggregate_source_hash": agg, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
               "script_version": SCRIPT_VERSION,
               "raw_sources": manifest, "reddit_txt_files": nrp,
               "corpora": written, "failed_gate": failed,
               "stats": st, "overlaps": overlaps,
               "dev_split": {"n": len(dev) if dev else 0, "seed": DEV_SPLIT_SEED,
                             "hash": dev_h},
               "unique_items": len(allh), "total_items": tot,
               "flags": allflags, "loader_meta": metas,
               "annotation_task": ann, "consensus": None,
               "consensus_removed": removed}
        (root / "MANIFEST" / "corpora.json").write_text(
            json.dumps(man, indent=2, default=str), encoding="utf-8")

        head("DONE")
        print(f"  corpora    : {root / 'data' / 'interim'}")
        print(f"  manifest   : {root / 'MANIFEST' / 'corpora.json'}")
        print(f"  decisions  : {root / 'DECISIONS.md'}")
        print(f"  log        : {root / 'results' / 'forensics' / 'console_log_03.txt'}")
        print()
        print(f"  corpora built  : {len(written)}")
        print(f"  failed gate    : {failed if failed else 'none'}")
        print(f"  unique items   : {len(allh):,}   (manuscript claimed 150,041)")
        print(f"  total words    : {tw:,}")
        print()
        if failed:
            print("  One or more corpora were REJECTED. Do not proceed to script 04")
            print("  until every gate passes or you have decided to drop the corpus.")
            return 3
        print("  NEXT: send me this log. Script 04 rebuilds the PLEF core as a")
        print("  standard-library module with unit tests and the purity check.")
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
