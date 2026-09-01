#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 02 : BASELINE ENVIRONMENT, VERIFICATION, SENSITIVITY
                       (hardened rewrite, v02.2.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
Script 01 proved the submitted paper's "VADER", "NRC" and "LIWC" baselines were
100, 58 and 88 hand-typed words. This script installs the real systems, proves
each one works, measures every arbitrary choice it is forced to make, and
records those choices in a timestamped decision log BEFORE any evaluation
number is produced.

The previous version of this script had six weaknesses. Every one is addressed
here, and none is hidden:

  W1  Empath category mapping was widened AFTER it failed a test.
      FIX: both mappings are kept and BOTH are scored in the sensitivity
      sweep (S9). The provenance ("chosen after observing failure on five
      hand-written sentences") is written verbatim into DECISIONS.md.

  W2  AFINN normalisation constant was invented with no published basis.
      FIX: four normalisations are implemented and all four are reported.

  W3  A single +/-0.05 threshold was applied to systems it does not suit.
      FIX: S9 sweeps thresholds 0.00-0.30 for every system. DECISIONS.md
      instructs downstream analysis to lead with AUC, which is threshold-free.

  W4  Preview used a fabricated NRC stand-in.
      FIX: real archives are extracted and lexicons are identified BY CONTENT.
      The script refuses to proceed on a file it cannot identify.

  W5  No determinism test.
      FIX: S6 scores identical inputs in two separate processes and asserts
      bitwise-identical output.

  W6  No import-purity harness.
      FIX: S7 builds the blocker script 04 will use to prove the PLEF core is
      standard-library only, and self-tests that the blocker actually blocks.

STAGES AND WHAT EACH RESULT MEANS
----------------------------------
  S0  Extract every archive in data/external, recursively; inventory all files.
  S1  Interpreter and packages, exact versions pinned.
  S2  Identify lexicons BY CONTENT (column structure, value ranges), never by
      filename. This is the direct guard against the failure mode that gave
      ISEAR 100% neutral labels: a loader that assumed a format and silently
      fell through to a default.
  S3  Write the unified adapter module.
  S4  Extract the V1 toy lexicons verbatim via AST.
  S5  Known-answer plus adversarial robustness (empty, unicode, emoji, 20k
      chars, HTML, all-caps, non-Latin). A baseline that crashes or silently
      returns 0.0 on these would corrupt part of the corpus invisibly.
  S6  Determinism, cross-process, bitwise.
  S7  Import-purity harness, built and self-tested.
  S8  Coverage and inter-system Cohen's kappa on real relationship text.
      Coverage is the honest measure of how much of the text each system can
      even see; kappa shows which baselines are redundant.
  S9  Sensitivity sweep over thresholds, AFINN normalisations, Empath mappings.
      Quantifies what every arbitrary choice above is worth, in results units.
  S10 DECISIONS.md -- the pre-registration for V2.
  S11 Environment manifest and requirements lock.

EXIT CODES
----------
  0 verified   2 missing prerequisite   3 verification failure
  4 legacy extraction failed            5 lexicon unidentifiable
===============================================================================
"""

import argparse
import ast
import collections
import csv
import datetime
import hashlib
import importlib
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import time
import traceback
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "02.4.0"

PKGS = [("vaderSentiment", "vaderSentiment"), ("afinn", "afinn"),
        ("empath", "empath"), ("nltk", "nltk"), ("labMTsimple", "labMTsimple")]

EXPECT = {"vader_lexicon": 7506, "nrc_unigrams": 14182, "empath_categories": 194,
          "afinn_en165": 3382, "huliu_total": 6789, "labmt_entries": 10222}

# KAT_CORE: unambiguous polarity, no negation. EVERY system must pass these.
KAT_CORE = [("I love this so much!", "pos"),
            ("I hate everything about this.", "neg"),
            ("The book is on the table.", "neu"),
            ("He betrayed me and I feel broken.", "neg"),
            ("She is kind and I am grateful every day.", "pos")]

# KAT_NEGATION: reported for all systems, ASSERTED only for systems that
# implement negation handling. NRC, Empath, Hu-Liu and labMT are pure
# bag-of-words lexicons with no negation logic; requiring them to pass these
# would be asserting a capability they do not claim, and would make this
# script refuse a correctly installed environment. Their failures here are a
# genuine property worth reporting in the paper, not a defect to fix.
KAT_NEGATION = [("This is not good at all.", "neg"),
                ("Nothing bad happened, it was wonderful.", "pos")]

HANDLES_NEGATION = {"vader", "V1_vader_toy"}

KAT = KAT_CORE + KAT_NEGATION

ADVERSARIAL = [
    ("empty", ""),
    ("whitespace", "   \t\n  "),
    ("single_word", "sad"),
    ("punct_only", "!!!???..."),
    ("all_caps", "I AM SO ANGRY RIGHT NOW"),
    ("emoji", "I feel \U0001F62D today but also \U0001F60A"),
    ("unicode", "cafe naive resume \u2014 em dash \u2026 ellipsis"),
    ("html", "<p>I &amp; my partner are <b>happy</b></p>"),
    ("digits", "1234567890 3.14159 -42"),
    ("repeated", "sad " * 2000),
    ("very_long", "The relationship ended badly and I feel terrible. " * 400),
    ("newlines", "line one\n\nline two\r\nline three"),
    ("quotes", "She said \"I'm done\" and I said 'okay'"),
    ("nonlatin", "\u092e\u0948\u0902 \u0926\u0941\u0916\u0940 \u0939\u0942\u0901 \u6211\u5f88\u96be\u8fc7"),
]


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


def label(score, thr=0.05):
    return "pos" if score > thr else ("neg" if score < -thr else "neu")


def kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


# ===========================================================================
def s0_extract(root):
    sub("S0  ARCHIVE EXTRACTION AND INVENTORY")
    ext = Path(root) / "data" / "external"
    ext.mkdir(parents=True, exist_ok=True)
    zips = sorted(ext.glob("*.zip"))
    print(f"  archives in data/external: {len(zips)}")
    for z in zips:
        target = ext / z.stem
        try:
            with zipfile.ZipFile(z) as zf:
                members = zf.namelist()
                bad = [m for m in members if m.startswith("/") or ".." in Path(m).parts]
                if bad:
                    print(f"  REFUSING unsafe archive {z.name}: {bad[:3]}")
                    continue
                if target.exists() and any(target.rglob("*")):
                    print(f"  {z.name:<42} already extracted -> {target.name}/")
                else:
                    zf.extractall(target)
                    print(f"  {z.name:<42} extracted {len(members):>4} entries -> {target.name}/")
        except zipfile.BadZipFile:
            print(f"  {z.name:<42} NOT A VALID ZIP -- skipped")
        except Exception as e:
            print(f"  {z.name:<42} extraction failed: {e}")
    cands = [p for p in sorted(ext.rglob("*"))
             if p.is_file() and p.suffix.lower() in (".txt", ".csv", ".tsv")
             and "__MACOSX" not in p.parts]
    print(f"\n  candidate lexicon files: {len(cands)}")
    for p in cands[:40]:
        try: sz = p.stat().st_size
        except Exception: sz = -1
        print(f"    {sz:>12,}  {p.relative_to(ext)}")
    if len(cands) > 40:
        print(f"    ... and {len(cands)-40} more")
    return ext, cands


# Paths that must never be selection candidates. These are translations,
# per-emotion splits, multi-word-expression files, sense-level variants and
# documentation. Selecting any of them silently produces a lexicon that cannot
# match plain English tokens -- exactly the failure mode that gave ISEAR a
# 100%-neutral label vector in V1.
EXCLUDE_PATH = re.compile(
    r"(OneFilePerLanguage|OneFilePerEmotion|ForVariousLanguages|"
    r"Senselevel|SenseLevel|InManyLanguages|ListOfLanguages|README)", re.I)
EXCLUDE_NAME = re.compile(r"^(mwe-|unigrams-)|-(polar)-", re.I)

EMO_CATS = {"anger", "fear", "joy", "sadness", "disgust", "surprise", "trust",
            "anticipation", "positive", "negative"}


def sniff(path, max_lines=None):
    """Classify a lexicon from full-file structure. Never from its name.

    max_lines=None means read the whole file. An earlier version capped this at
    4,000 lines, which made every candidate report an identical truncated term
    count and turned the selection step into a coin flip.
    """
    header = None
    rows = 0
    ncols = collections.Counter()
    c2n, c3n, c4n = [], [], []
    c2set, words = set(), set()
    sense_markers = 0
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except Exception as e:
        return "unreadable", {"error": str(e)}
    with f:
        for i, line in enumerate(f):
            if max_lines is not None and i > max_lines:
                break
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                parts = [x for x in re.split(r"\s{2,}|,", line) if x != ""]
            low = [c.strip().lower() for c in parts]
            if i == 0 and any(c in ("word", "term", "emotion", "valence", "arousal",
                                    "dominance", "emotion-intensity-score")
                              for c in low):
                header = low
                continue
            ncols[len(parts)] += 1
            rows += 1
            w = parts[0].strip()
            words.add(w)
            if "--" in w:
                sense_markers += 1
            if len(parts) >= 2:
                c2set.add(parts[1].strip())
                try: c2n.append(float(parts[1]))
                except ValueError: pass
            if len(parts) >= 3:
                try: c3n.append(float(parts[2]))
                except ValueError: pass
            if len(parts) >= 4:
                try: c4n.append(float(parts[3]))
                except ValueError: pass
    if rows == 0:
        return "empty", {}
    mode_cols = ncols.most_common(1)[0][0]
    meta = {"rows": rows, "mode_cols": mode_cols, "header": header,
            "unique_col1": len(words), "col2_distinct": len(c2set),
            "sense_pairs": sense_markers}

    def distinct(vals):
        return len(set(round(v, 6) for v in vals))

    # --- sense-level EmoLex: col1 holds word--sense pairs, unusable as tokens
    if sense_markers > rows * 0.5:
        meta["reason"] = "col1 contains word--sense pairs"
        return "emolex_sense", meta

    # --- VAD: needs a header naming V/A/D, or 4 columns of CONTINUOUS values.
    # The old rule accepted any >=4 columns with numeric cols 2-4, which matched
    # the multilingual EmoLex (columns of 0/1 flags).
    hdr_vad = header and all(any(h.startswith(k) for h in header)
                             for k in ("valence", "arousal", "dominance"))
    cont = (len(c2n) > 50 and len(c3n) > 50 and len(c4n) > 50 and
            distinct(c2n) > 20 and distinct(c3n) > 20 and distinct(c4n) > 20)
    if mode_cols == 4 and (hdr_vad or cont):
        meta.update({"valence_range": (min(c2n), max(c2n)),
                     "arousal_range": (min(c3n), max(c3n)),
                     "dominance_range": (min(c4n), max(c4n)),
                     "valence_distinct": distinct(c2n),
                     "reason": "header names V/A/D" if hdr_vad else "4 continuous columns"})
        return "vad", meta
    if mode_cols >= 4:
        meta["reason"] = f"{mode_cols} columns but values not continuous"
        return "wide_binary", meta

    # --- word + emotion + value
    if mode_cols == 3 and len(c2set & EMO_CATS) >= 5:
        if c3n:
            uniq = set(round(v, 6) for v in c3n)
            meta["value_range"] = (min(c3n), max(c3n))
            meta["value_distinct"] = len(uniq)
            if uniq <= {0.0, 1.0}:
                meta["reason"] = "3 cols, emotion names, binary values"
                return "emolex", meta
            meta["reason"] = "3 cols, emotion names, continuous values"
            return "emoint", meta
    if mode_cols == 3:
        meta["col2_sample"] = sorted(list(c2set))[:8]
        meta["reason"] = "3 cols but col2 is not a set of emotion names"
        return "unknown3", meta
    if mode_cols == 2:
        meta["reason"] = "2 columns -- single-emotion or single-dimension split"
        return "two_col", meta
    return "unknown", meta


def s2_lexicons(cands, overrides=None):
    sub("S2  LEXICON IDENTIFICATION BY CONTENT")
    print("  Classified from FULL-FILE column structure and value ranges.")
    print("  Filenames are not trusted for classification; they are used only")
    print("  to exclude translation / per-emotion / sense-level variants.\n")
    overrides = overrides or {}
    kept, excluded = [], []
    for p in cands:
        try: size = p.stat().st_size
        except Exception: size = 0
        if size < 2000:
            continue
        if EXCLUDE_PATH.search(str(p)) or EXCLUDE_NAME.search(p.name):
            excluded.append(p); continue
        kept.append(p)
    print(f"  candidates: {len(kept)} kept, {len(excluded)} excluded by path rule")
    if excluded:
        why = collections.Counter()
        for p in excluded:
            m = EXCLUDE_PATH.search(str(p)) or EXCLUDE_NAME.search(p.name)
            why[m.group(0) if m else "?"] += 1
        print("    excluded by: " + ", ".join(f"{k}={v}" for k, v in why.most_common()))
    print()
    found = collections.defaultdict(list)
    for p in kept:
        kind, meta = sniff(p)
        rec = {"path": str(p), "name": p.name, "kind": kind, "meta": meta,
               "size": p.stat().st_size}
        found[kind].append(rec)
        print(f"  {kind.upper():<14} {meta.get('rows',0):>9,} rows  "
              f"{meta.get('unique_col1',0):>8,} terms  {p.name[:44]}")
        if meta.get("reason"):
            print(f"  {'':<14} -> {meta['reason']}")
    chosen = {}
    for k in ("emolex", "emoint", "vad"):
        if overrides.get(k):
            pth = Path(overrides[k])
            if pth.exists():
                kind, meta = sniff(pth)
                chosen[k] = {"path": str(pth), "name": pth.name, "kind": kind,
                             "meta": meta, "sha256": sha256(pth), "override": True}
                continue
            print(f"  OVERRIDE for {k} not found: {pth}")
        if found.get(k):
            best = max(found[k], key=lambda r: r["meta"].get("unique_col1", 0))
            best["sha256"] = sha256(best["path"])
            chosen[k] = best
    print()
    for k, nm, exp in (("emolex", "NRC Emotion Lexicon (EmoLex)", EXPECT["nrc_unigrams"]),
                       ("emoint", "NRC Emotion Intensity Lexicon", None),
                       ("vad", "NRC Valence-Arousal-Dominance Lexicon", None)):
        if k in chosen:
            c = chosen[k]; m = c["meta"]
            print(f"  SELECTED {nm}{'  (user override)' if c.get('override') else ''}")
            print(f"     file   : {Path(c['path']).name}")
            print(f"     terms  : {m.get('unique_col1',0):,}   rows: {m.get('rows',0):,}")
            if exp:
                d = abs(m.get("unique_col1", 0) - exp)
                print(f"     expect : {exp:,}   deviation {d:,}  "
                      f"{'OK' if d <= 200 else '** CHECK: wrong file or a derivative **'}")
            if k == "vad":
                print(f"     ranges : V{tuple(round(x,3) for x in m.get('valence_range',(0,0)))} "
                      f"A{tuple(round(x,3) for x in m.get('arousal_range',(0,0)))} "
                      f"D{tuple(round(x,3) for x in m.get('dominance_range',(0,0)))}"
                      f"   distinct V={m.get('valence_distinct','?')}")
            if k == "emoint":
                print(f"     scores : {tuple(round(x,3) for x in m.get('value_range',(0,0)))}, "
                      f"{m.get('value_distinct',0):,} distinct")
            print(f"     sha256 : {c['sha256']}")
        else:
            print(f"  MISSING  {nm}")
    print()
    print("  NOT redistributable (NRC non-commercial research licence).")
    print("  Cite Mohammad & Turney (2013) for EmoLex; Mohammad (2018) for EmoInt and VAD.")
    return chosen


ADAPTER_SOURCE = r'''# -*- coding: utf-8 -*-
"""
PLEF V2 -- unified baseline adapter.
AUTOGENERATED by scripts/02_baseline_environment.py. Do not edit by hand.

Every baseline exposes score(text) -> float in [-1, 1].
Scores are comparable in SIGN and ORDER, never in absolute scale.

DECLARED ARBITRARY CHOICES (provenance in DECISIONS.md):
  D1 Empath polarity uses a broad affect-category set; narrow variant retained.
  D2 AFINN normalisation: four variants, primary is 'sqrt'.
  D3 labMT stop band [4.0, 6.0], centre 5.0, scale 4.0. labMT measures
     HAPPINESS, not polarity: its zero point is NOT neutral.
  D4 Threshold +/-0.05 uniformly. AUC (threshold-free) is the primary metric.
"""
import math
import os
import re

_TOK_APOS = re.compile(r"[a-z']+")
_TOK_ALPHA = re.compile(r"[a-z]+")


def _tokens(text):
    return _TOK_APOS.findall(text.lower())


class _Base:
    name = "base"
    size = 0
    def score(self, text):
        raise NotImplementedError
    def coverage(self, text):
        return -1.0


class VaderBaseline(_Base):
    name = "vader"
    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._a = SentimentIntensityAnalyzer()
        self.size = len(self._a.lexicon)
    def score(self, text):
        if not text or not text.strip():
            return 0.0
        return float(self._a.polarity_scores(text)["compound"])
    def coverage(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        return sum(1 for w in t if w in self._a.lexicon) / len(t)


class NRCBaseline(_Base):
    """Real NRC EmoLex v0.92."""
    name = "nrc"
    def __init__(self, path):
        pos, neg, emo = set(), set(), {}
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.rstrip("\n").rstrip("\r").split("\t")
                if len(p) != 3:
                    continue
                w, cat, val = p[0].strip(), p[1].strip().lower(), p[2].strip()
                if val != "1":
                    continue
                if cat == "positive":
                    pos.add(w)
                elif cat == "negative":
                    neg.add(w)
                else:
                    emo.setdefault(cat, set()).add(w)
        self.pos, self.neg, self.emo = pos, neg, emo
        allw = set(pos) | set(neg)
        for s in emo.values():
            allw |= s
        self.vocab = allw
        self.size = len(allw)
    def score(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        p = sum(1 for w in t if w in self.pos)
        n = sum(1 for w in t if w in self.neg)
        return 0.0 if p + n == 0 else (p - n) / float(p + n)
    def coverage(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        return sum(1 for w in t if w in self.vocab) / len(t)
    def emotions(self, text):
        t = _tokens(text)
        d = max(1, len(t))
        return {c: sum(1 for w in t if w in s) / d for c, s in self.emo.items()}


class EmpathBaseline(_Base):
    """LIWC-analogue (Fast, Chen & Bernstein, CHI 2016; mean r=0.906 vs LIWC).

    D1 PROVENANCE, POST HOC: the narrow positive_emotion/negative_emotion pair
    was tried first and returned 0.000 on two of five hand-written known-answer
    sentences. The broad set below was then adopted. Categories were chosen by
    NAME only and never tuned against any evaluation corpus. Both variants are
    scored and reported.
    """
    name = "empath"
    POS_BROAD = ("positive_emotion", "joy", "love", "affection", "optimism",
                 "contentment", "cheerfulness", "trust", "celebration",
                 "achievement", "gain", "fun", "politeness", "sympathy",
                 "friends", "giving", "healing", "beauty", "pride")
    NEG_BROAD = ("negative_emotion", "sadness", "anger", "hate", "disgust",
                 "fear", "suffering", "pain", "shame", "nervousness",
                 "violence", "rage", "envy", "disappointment", "neglect",
                 "deception", "crime", "death", "injury", "weakness",
                 "aggression", "horror", "torment", "exasperation",
                 "irritability", "ridicule")
    POS_NARROW = ("positive_emotion",)
    NEG_NARROW = ("negative_emotion",)
    def __init__(self, mode="broad"):
        from empath import Empath
        self._e = Empath()
        cats = set(self._e.cats)
        p, n = (self.POS_BROAD, self.NEG_BROAD) if mode == "broad" \
            else (self.POS_NARROW, self.NEG_NARROW)
        self.mode = mode
        self.pos = tuple(c for c in p if c in cats)
        self.neg = tuple(c for c in n if c in cats)
        self.size = len(self._e.cats)
    def score(self, text):
        if not text or not text.strip():
            return 0.0
        r = self._e.analyze(text, normalize=True) or {}
        p = sum(float(r.get(c, 0.0)) for c in self.pos)
        n = sum(float(r.get(c, 0.0)) for c in self.neg)
        return 0.0 if p + n == 0 else (p - n) / (p + n)
    def categories(self, text):
        return self._e.analyze(text, normalize=True) or {}
    def coverage(self, text):
        """Fraction of tokens falling in ANY built-in Empath category."""
        t = _tokens(text)
        if not t:
            return 0.0
        r = self._e.analyze(text, normalize=False) or {}
        hits = sum(float(v) for v in r.values())
        return min(1.0, hits / len(t))


class AfinnBaseline(_Base):
    """AFINN-en-165 (Nielsen 2011).

    D2 ARBITRARY: AFINN returns an unbounded integer sum; a normalisation must
    be chosen and there is no published constant. Variants:
      sqrt  sum / (5*sqrt(n_tokens))   [declared primary]
      dens  sum / n_tokens
      mean  sum / (5*n_matched)
      tanh  tanh(sum/5)
    """
    name = "afinn"
    def __init__(self, mode="sqrt"):
        from afinn import Afinn
        self._a = Afinn()
        self.mode = mode
        self.size = 3382
    def _raw(self, text):
        try:
            return float(self._a.score(text))
        except Exception:
            return 0.0
    def _matched(self, text):
        try:
            return len(self._a.find_all(text))
        except Exception:
            return 0
    def score(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        s = self._raw(text)
        if self.mode == "dens":
            return max(-1.0, min(1.0, s / len(t)))
        if self.mode == "mean":
            m = self._matched(text) or 1
            return max(-1.0, min(1.0, s / (5.0 * m)))
        if self.mode == "tanh":
            return math.tanh(s / 5.0)
        return max(-1.0, min(1.0, s / (5.0 * (len(t) ** 0.5))))
    def coverage(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        return min(1.0, self._matched(text) / len(t))


class HuLiuBaseline(_Base):
    name = "huliu"
    def __init__(self):
        from nltk.corpus import opinion_lexicon
        self.pos = set(opinion_lexicon.positive())
        self.neg = set(opinion_lexicon.negative())
        self.size = len(self.pos) + len(self.neg)
    def score(self, text):
        t = _tokens(text)
        p = sum(1 for w in t if w in self.pos)
        n = sum(1 for w in t if w in self.neg)
        return 0.0 if p + n == 0 else (p - n) / float(p + n)
    def coverage(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        return sum(1 for w in t if w in self.pos or w in self.neg) / len(t)


class LabMTBaseline(_Base):
    """labMT happiness lexicon (Dodds & Danforth), as used by Reagan et al. 2016.

    labMTsimple's stopper() raises TypeError in the current release, so the
    standard procedure is implemented directly here.
    D3: labMT measures HAPPINESS, not polarity. Its zero point is not neutral
    and it is strongly positively shifted on ordinary text. This must be stated
    wherever labMT is reported.
    """
    name = "labmt"
    def __init__(self, lo=4.0, hi=6.0, center=5.0, scale=4.0):
        from labMTsimple.storyLab import emotionFileReader
        d, _v, _w = emotionFileReader(stopval=0.0, lang="english", returnVector=True)
        self.h = {}
        for w, row in d.items():
            try:
                self.h[w] = float(row[1])
            except (IndexError, ValueError, TypeError):
                continue
        self.lo, self.hi, self.center, self.scale = lo, hi, center, scale
        self.size = len(self.h)
    def score(self, text):
        vals = [self.h[w] for w in _tokens(text)
                if w in self.h and not (self.lo <= self.h[w] <= self.hi)]
        if not vals:
            return 0.0
        return max(-1.0, min(1.0, (sum(vals) / len(vals) - self.center) / self.scale))
    def coverage(self, text):
        t = _tokens(text)
        if not t:
            return 0.0
        return sum(1 for w in t if w in self.h) / len(t)


# --------------------------------------------------------------------------
# NRC companion lexicons -- VALIDATION INSTRUMENTS, NOT BASELINES.
# --------------------------------------------------------------------------
class VADLexicon:
    """NRC Valence-Arousal-Dominance. External criterion for PAI: dominance is
    annotated independently of any pronoun count, so it is not circular."""
    name = "nrc_vad"
    def __init__(self, path):
        self.v, self.a, self.d = {}, {}, {}
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.rstrip("\n").rstrip("\r").split("\t")
                if len(p) < 4:
                    continue
                w = p[0].strip()
                try:
                    self.v[w] = float(p[1]); self.a[w] = float(p[2]); self.d[w] = float(p[3])
                except ValueError:
                    continue
        self.size = len(self.v)
    def _mean(self, table, text):
        vals = [table[w] for w in _tokens(text) if w in table]
        return sum(vals) / len(vals) if vals else None
    def valence(self, text): return self._mean(self.v, text)
    def arousal(self, text): return self._mean(self.a, text)
    def dominance(self, text): return self._mean(self.d, text)


class EmoIntLexicon:
    """NRC Emotion Intensity. External criterion for TEG: the intensity
    sequence is not derived from PLEF's own compound score."""
    name = "nrc_emoint"
    def __init__(self, path):
        self.t = {}
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.rstrip("\n").rstrip("\r").split("\t")
                if len(p) < 3:
                    continue
                try:
                    s = float(p[2])
                except ValueError:
                    continue
                self.t.setdefault(p[0].strip(), {})[p[1].strip().lower()] = s
        self.size = len(self.t)
    def intensity(self, text):
        vals = []
        for w in _tokens(text):
            d = self.t.get(w)
            if d:
                vals.append(max(d.values()))
        return sum(vals) / len(vals) if vals else 0.0


# --------------------------------------------------------------------------
# LEGACY V1 TOYS -- supplementary error quantification ONLY.
# These must NEVER appear under the names VADER, NRC or LIWC.
# --------------------------------------------------------------------------
class LegacyToy(_Base):
    def __init__(self, name, kind, table):
        self.name, self.kind, self.table = name, kind, table
        self.size = len(table)
    def _toks(self, text):
        low = text.lower()
        return _TOK_ALPHA.findall(low) if self.kind == "nrc" else _TOK_APOS.findall(low)
    def score(self, text):
        toks = self._toks(text)
        if self.kind == "vader":
            total = 0.0
            for i, tok in enumerate(toks):
                if tok in self.table:
                    val = self.table[tok]
                    if any(n in toks[max(0, i - 3):i]
                           for n in ("not", "never", "no", "neither", "nor", "nothing")):
                        val *= -0.74
                    total += val
            return round(total / ((total ** 2 + 15) ** 0.5), 4)
        if self.kind == "nrc":
            c = {}
            for tok in toks:
                if tok in self.table:
                    for e, v in self.table[tok].items():
                        c[e] = c.get(e, 0) + v
            tot = max(1, len(toks))
            return round(c.get("positive", 0) / tot - c.get("negative", 0) / tot, 4)
        if self.kind == "liwc":
            n = max(1, len(toks))
            cnt = {cat: sum(1 for t in toks if t in seeds) * 100.0 / n
                   for cat, seeds in self.table.items()}
            p = cnt.get("Positive Emotion", 0.0)
            g = cnt.get("Negative Emotion", 0.0)
            return round((p - g) / max(1, p + g + 0.001), 4) if p + g > 0 else 0.0
        return 0.0
    def coverage(self, text):
        toks = self._toks(text)
        if not toks:
            return 0.0
        if self.kind == "liwc":
            vocab = set()
            for s in self.table.values():
                vocab |= set(s)
        else:
            vocab = set(self.table)
        return sum(1 for w in toks if w in vocab) / len(toks)


def load_all(nrc_path, legacy_path=None, include_legacy=True,
             empath_mode="broad", afinn_mode="sqrt"):
    out = {}
    out["vader"] = VaderBaseline()
    out["nrc"] = NRCBaseline(nrc_path)
    out["empath"] = EmpathBaseline(empath_mode)
    out["afinn"] = AfinnBaseline(afinn_mode)
    out["huliu"] = HuLiuBaseline()
    out["labmt"] = LabMTBaseline()
    if include_legacy and legacy_path and os.path.exists(legacy_path):
        import json as _json
        with open(legacy_path, encoding="utf-8") as f:
            L = _json.load(f)
        out["V1_vader_toy"] = LegacyToy("V1_vader_toy", "vader", L["_VADER_SEEDS"])
        out["V1_nrc_toy"] = LegacyToy("V1_nrc_toy", "nrc", L["_NRC_SEEDS"])
        out["V1_liwc_toy"] = LegacyToy("V1_liwc_toy", "liwc", L["_LIWC_CATEGORIES"])
    return out
'''

PURITY_SOURCE = r'''# -*- coding: utf-8 -*-
"""
PLEF V2 -- standard-library purity harness.
AUTOGENERATED by scripts/02_baseline_environment.py.

Script 04 uses this to PROVE the PLEF core imports with no third-party package
available.

DESIGN NOTE -- why this runs in a subprocess:
An earlier design installed the blocker in the current process and purged
sys.modules of the blocked packages. That is unsafe. Compiled extension
modules such as numpy raise "ImportError: cannot load module more than once
per process" when removed and re-imported, which poisons the interpreter for
everything that runs afterwards. A purity claim must be tested in a process
that never imported the package in the first place, so the check is always
run in a fresh subprocess.
"""
import builtins
import json
import subprocess
import sys

BLOCKED_DEFAULT = ("numpy", "scipy", "pandas", "matplotlib", "sklearn",
                   "nltk", "torch", "empath", "afinn", "vaderSentiment",
                   "labMTsimple", "seaborn", "statsmodels")

_CHILD = r"""
import sys, json, builtins
blocked = set(json.loads(sys.argv[1]))
target  = sys.argv[2]
for extra in json.loads(sys.argv[3]):
    sys.path.insert(0, extra)
_orig = builtins.__import__
def _guard(name, *a, **kw):
    top = name.split('.')[0]
    if top in blocked:
        raise ImportError("PURITY VIOLATION: attempted import of '%s' "
                          "(blocked package '%s')" % (name, top))
    return _orig(name, *a, **kw)
builtins.__import__ = _guard
try:
    __import__(target)
    print(json.dumps({"ok": True, "error": None}))
except Exception as e:
    print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
"""


def assert_pure(module_name, blocked=BLOCKED_DEFAULT, extra_paths=()):
    """Import module_name in a FRESH subprocess with blocked packages
    unavailable. Returns (ok, error_string_or_None)."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", _CHILD, json.dumps(list(blocked)),
             module_name, json.dumps([str(p) for p in extra_paths])],
            capture_output=True, text=True, timeout=180)
        out = (r.stdout or "").strip().splitlines()
        if not out:
            return False, "no output from purity subprocess: " + (r.stderr or "")[:300]
        d = json.loads(out[-1])
        return bool(d["ok"]), d["error"]
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


class ImportBlocker:
    """In-process blocker. Use ONLY in a process that has not yet imported any
    blocked package. Prefer assert_pure(), which is subprocess-isolated."""
    def __init__(self, blocked=BLOCKED_DEFAULT):
        self.blocked = tuple(blocked)
        self._orig = None
        self.violations = []

    def _guard(self, name, *a, **kw):
        top = name.split(".")[0]
        if top in self.blocked:
            self.violations.append(name)
            raise ImportError("PURITY VIOLATION: attempted import of '%s' "
                              "(blocked package '%s')" % (name, top))
        return self._orig(name, *a, **kw)

    def __enter__(self):
        self._orig = builtins.__import__
        builtins.__import__ = self._guard
        return self

    def __exit__(self, *exc):
        builtins.__import__ = self._orig
        return False
'''


def s3_adapter(root):
    sub("S3  ADAPTER MODULE")
    p = Path(root) / "src" / "plef_baselines.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ADAPTER_SOURCE, encoding="utf-8")
    print(f"  written -> {p}")
    print(f"  sha256   {sha256(p)}")
    return str(p)


def s1_packages(do_install):
    sub("S1  INTERPRETER AND PACKAGE CHECK")
    print(f"  python {sys.version.split()[0]}  ({sys.platform})  cpu_count={os.cpu_count()}")
    if sys.version_info < (3, 8):
        print("  FATAL: Python 3.8+ required")
        return False, {}
    missing, found = [], {}

    def ver(pip_name, mod):
        m = importlib.import_module(mod)
        v = getattr(m, "__version__", None)
        if v is None:
            try:
                from importlib.metadata import version as _v
                v = _v(pip_name)
            except Exception:
                v = "unknown"
        return str(v)

    for pip_name, mod in PKGS:
        try:
            found[pip_name] = ver(pip_name, mod)
            print(f"  OK      {pip_name:<18} {found[pip_name]}")
        except Exception:
            missing.append(pip_name)
            print(f"  MISSING {pip_name}")
    if missing and do_install:
        print(f"\n  installing: {' '.join(missing)}")
        if subprocess.run([sys.executable, "-m", "pip", "install", "--quiet"]
                          + missing).returncode != 0:
            print("  pip install FAILED")
            return False, found
        for pip_name in list(missing):
            try:
                found[pip_name] = ver(pip_name, dict(PKGS)[pip_name])
                print(f"  OK      {pip_name:<18} {found[pip_name]}")
                missing.remove(pip_name)
            except Exception as e:
                print(f"  STILL MISSING {pip_name}: {e}")
    elif missing:
        print(f"\n  Re-run with --install, or: pip install {' '.join(missing)}")
        return False, found
    try:
        import nltk
        try:
            from nltk.corpus import opinion_lexicon
            opinion_lexicon.positive()
            print("  OK      nltk:opinion_lexicon")
        except Exception:
            print("  fetching nltk opinion_lexicon ...")
            nltk.download("opinion_lexicon", quiet=True)
            from nltk.corpus import opinion_lexicon
            opinion_lexicon.positive()
            print("  OK      nltk:opinion_lexicon (downloaded)")
    except Exception as e:
        print(f"  FAILED nltk opinion_lexicon: {e}")
        return False, found
    return not missing, found


def s4_legacy(v1, root):
    sub("S4  LEGACY V1 TOY LEXICON EXTRACTION (verbatim, via AST)")
    src = Path(v1) / "plef_v7.py"
    if not src.exists():
        print(f"  FATAL: {src} not found")
        return None, {}
    tree = ast.parse(src.read_text(encoding="utf-8", errors="replace"))
    want = {"_VADER_SEEDS", "_NRC_SEEDS", "_LIWC_CATEGORIES"}
    got, lit = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in want and isinstance(node.value, ast.Dict):
                    keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
                    lit[t.id] = len(keys)
                    dup = [k for k, c in collections.Counter(keys).items() if c > 1]
                    try:
                        got[t.id] = ast.literal_eval(node.value)
                        if dup:
                            print(f"  NOTE {t.id}: {len(keys)} literal keys, "
                                  f"{len(got[t.id])} unique -- duplicates {dup}")
                    except Exception as e:
                        print(f"  could not evaluate {t.id}: {e}")
    if len(got) != 3:
        print(f"  FATAL: extracted {sorted(got)} -- expected all three")
        return None, {}
    out = Path(root) / "src" / "legacy_v1_lexicons.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(got, indent=1, sort_keys=True), encoding="utf-8")
    liwc_words = sum(len(v) for v in got["_LIWC_CATEGORIES"].values())
    print(f"  _VADER_SEEDS      {len(got['_VADER_SEEDS']):>5} unique "
          f"({lit.get('_VADER_SEEDS')} literal)  vs published ~{EXPECT['vader_lexicon']:,}"
          f"  = {100*len(got['_VADER_SEEDS'])/EXPECT['vader_lexicon']:.2f}%")
    print(f"  _NRC_SEEDS        {len(got['_NRC_SEEDS']):>5} unique "
          f"({lit.get('_NRC_SEEDS')} literal)  vs published {EXPECT['nrc_unigrams']:,}"
          f"  = {100*len(got['_NRC_SEEDS'])/EXPECT['nrc_unigrams']:.2f}%")
    print(f"  _LIWC_CATEGORIES  {len(got['_LIWC_CATEGORIES']):>5} categories, {liwc_words} words")
    print(f"  written -> {out}")
    return str(out), {"vader_unique": len(got["_VADER_SEEDS"]),
                      "vader_literal": lit.get("_VADER_SEEDS"),
                      "nrc_unique": len(got["_NRC_SEEDS"]),
                      "nrc_literal": lit.get("_NRC_SEEDS"),
                      "liwc_categories": len(got["_LIWC_CATEGORIES"]),
                      "liwc_words": liwc_words}


def s5_verify(root, nrc_path, legacy_path):
    sub("S5  KNOWN-ANSWER AND ADVERSARIAL VERIFICATION")
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_baselines as B
    importlib.reload(B)
    try:
        bl = B.load_all(nrc_path, legacy_path, include_legacy=True)
    except Exception as e:
        print(f"  FATAL loading baselines: {e}")
        traceback.print_exc()
        return False, {}, {}
    names = list(bl.keys())
    sizes = {k: getattr(v, "size", None) for k, v in bl.items()}
    print("  lexicon / category sizes:")
    expmap = {"vader": EXPECT["vader_lexicon"], "empath": EXPECT["empath_categories"],
              "afinn": EXPECT["afinn_en165"], "huliu": EXPECT["huliu_total"],
              "labmt": EXPECT["labmt_entries"], "nrc": EXPECT["nrc_unigrams"]}
    for k, v in sizes.items():
        e = expmap.get(k)
        flag = ""
        if e:
            flag = "  OK" if abs(v - e) <= max(50, e * 0.05) else f"  ** expected ~{e:,} **"
        print(f"    {k:<16} {v:>8,}{flag}")
    print()
    failures = []
    negation_notes = []

    def run_block(title, cases, assert_all):
        print(f"  {title:<40}" + "".join(f"{n[:8]:>10}" for n in names))
        rule()
        for text, expect in cases:
            row = f"  {text[:38]:<40}"
            for n in names:
                try:
                    sc = bl[n].score(text)
                except Exception as e:
                    sc = float("nan")
                    failures.append((n, text[:30], f"exception {e}"))
                row += f"{sc:>10.3f}"
                if expect == "neu" or sc != sc:
                    continue
                # labMT: sign-only, its zero point is not neutral
                wrong = ((sc > 0) != (expect == "pos")) if n == "labmt" \
                    else (label(sc) != expect)
                if not wrong:
                    continue
                if assert_all or n in HANDLES_NEGATION:
                    failures.append((n, text[:30],
                                     f"expected {expect}, got {label(sc)} ({sc:+.3f})"))
                else:
                    negation_notes.append((n, text[:34], sc))
            print(row)
        print()

    run_block("core (no negation) -- asserted for all", KAT_CORE, True)
    run_block("negation -- asserted only for VADER-family", KAT_NEGATION, False)
    if negation_notes:
        print("  Bag-of-words systems that mis-handle negation (EXPECTED, not a failure):")
        for n, t, sc in negation_notes:
            print(f"    {n:<14} {sc:+.3f}   [{t}]")
        print("  This is a real limitation of these lexicons and belongs in the paper,")
        print("  not a defect. Only VADER implements negation.")
        print()
    print("  adversarial robustness (crash / NaN / out-of-range):")
    adv_fail = 0
    for tag, text in ADVERSARIAL:
        problems = []
        for n in names:
            try:
                s = bl[n].score(text)
                if s != s:
                    problems.append(f"{n}:NaN")
                elif not (-1.0000001 <= s <= 1.0000001):
                    problems.append(f"{n}:{s:+.3f}")
            except Exception as e:
                problems.append(f"{n}:{type(e).__name__}")
        if problems:
            adv_fail += 1
            failures.append(("adversarial", tag, " ".join(problems[:6])))
        print(f"    {tag:<14} {'OK' if not problems else 'FAIL ' + ' '.join(problems[:4])}")
    print()
    for n in names:
        vals = []
        for text, _ in KAT_CORE:
            try:
                vals.append(bl[n].score(text))
            except Exception:
                vals.append(0.0)
        if all(abs(v) < 1e-9 for v in vals):
            failures.append((n, "<all>", "DEGENERATE: returns 0.0 for every core sentence"))
    if failures:
        print("  VERIFICATION FAILURES:")
        for n, t, why in failures:
            print(f"    {n:<14} {why}   [{t}]")
    else:
        print("  All checks passed: signs correct, no crashes, no NaN, all in range.")
    return not failures, sizes, {"adversarial_failures": adv_fail}


def _det_worker(spec):
    root, nrc, legacy, texts = spec
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_baselines as B
    bl = B.load_all(nrc, legacy, include_legacy=True)
    return {k: [repr(obj.score(t)) for t in texts] for k, obj in bl.items()}


def s6_determinism(root, nrc, legacy, workers):
    sub("S6  DETERMINISM (cross-process, bitwise)")
    texts = [t for t, _ in KAT] + [t for _, t in ADVERSARIAL if t.strip()]
    with ProcessPoolExecutor(max_workers=2) as ex:
        a, b = list(ex.map(_det_worker,
                           [(root, nrc, legacy, texts), (root, nrc, legacy, texts)]))
    bad = [k for k in a if a[k] != b.get(k)]
    print(f"  {len(texts)} inputs scored twice in two separate processes")
    if bad:
        print(f"  NON-DETERMINISTIC: {bad}")
        for k in bad:
            for i, (x, y) in enumerate(zip(a[k], b[k])):
                if x != y:
                    print(f"    {k} input#{i}: {x} vs {y}")
                    break
    else:
        print(f"  all {len(a)} baselines bitwise identical across processes")
    return not bad


def s7_purity(root):
    sub("S7  IMPORT-PURITY HARNESS (build and self-test)")
    p = Path(root) / "src" / "plef_purity.py"
    p.write_text(PURITY_SOURCE, encoding="utf-8")
    print(f"  written -> {p}")
    print("  Checks run in FRESH SUBPROCESSES. Purging compiled extensions such")
    print("  as numpy from a live interpreter raises 'cannot load module more")
    print("  than once per process' and poisons everything after it, so a purity")
    print("  claim must be tested in a process that never imported the package.")
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_purity as P
    importlib.reload(P)
    ok_std, err = P.assert_pure("json")
    print(f"  self-test A: stdlib 'json' under blocker      -> "
          f"{'PASS (allowed)' if ok_std else 'FAIL: ' + str(err)}")
    ok_3p, err2 = P.assert_pure("nltk")
    print(f"  self-test B: third-party 'nltk' under blocker -> "
          f"{'FAIL (blocker did not fire)' if ok_3p else 'PASS (blocked)'}")
    if not ok_3p and err2:
        print(f"     blocker message: {str(err2)[:90]}")
    good = ok_std and not ok_3p
    print(f"  harness {'VERIFIED' if good else 'NOT WORKING'} -- script 04 uses it")
    print(f"  sha256   {sha256(p)}")
    return good


def _cov_worker(spec):
    root, nrc, legacy, texts, empath_mode, afinn_mode = spec
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_baselines as B
    bl = B.load_all(nrc, legacy, include_legacy=True,
                    empath_mode=empath_mode, afinn_mode=afinn_mode)
    sc = {k: [] for k in bl}
    cv = {k: [] for k in bl}
    for t in texts:
        for k, obj in bl.items():
            try:
                sc[k].append(obj.score(t))
            except Exception:
                sc[k].append(0.0)
            try:
                c = obj.coverage(t)
                if c >= 0:
                    cv[k].append(c)
            except Exception:
                pass
    return sc, cv


def _norm_hash(t):
    return hashlib.sha1(" ".join(t.lower().split()).encode("utf-8", "replace")).hexdigest()


def _read_text_col(path, min_words=0):
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                t = (r.get("text") or "").strip()
                if t and len(t.split()) >= min_words:
                    rows.append({"id": r.get("id", ""), "text": t,
                                 "subreddit": r.get("subreddit", "")})
    except Exception:
        pass
    return rows


def s8_provenance_and_pool(v1):
    """Build a smoke-test pool that is PROVABLY disjoint from every evaluation
    corpus, and audit the provenance of V1's 'Reddit relationship' corpus."""
    sub("S8a  PREVIEW SOURCE: PROVENANCE AUDIT AND DISJOINTNESS PROOF")
    v1 = Path(v1)
    prov = {}

    # --- reconstruct the evaluation text universe we can verify locally ------
    eval_hashes = set()
    ge_hashes = set()
    for fn in ("ge_train.tsv", "ge_dev.tsv", "ge_test.tsv"):
        p_ = v1 / "datasets" / fn
        if not p_.exists():
            continue
        try:
            with open(p_, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if parts and parts[0].strip():
                        ge_hashes.add(_norm_hash(parts[0]))
        except Exception:
            pass
    eval_hashes |= ge_hashes

    used_reddit = v1 / "reddit_posts_corpus_original.csv"
    used_rows = _read_text_col(used_reddit) if used_reddit.exists() else []
    used_hashes = {_norm_hash(r["text"]) for r in used_rows}
    eval_hashes |= used_hashes

    if used_rows:
        wl = [len(r["text"].split()) for r in used_rows]
        ov = len(used_hashes & ge_hashes)
        prov = {"file": used_reddit.name, "rows": len(used_rows),
                "unique": len(used_hashes),
                "median_words": statistics.median(wl),
                "id_prefixes": sorted({r["id"][:3] for r in used_rows if r["id"]})[:5],
                "goemotions_overlap": ov,
                "goemotions_overlap_pct": 100.0 * ov / max(1, len(used_hashes))}
        print(f"  V1 loader load_reddit_relationship() reads, in priority order:")
        print(f"    1. {used_reddit.name}   ({len(used_rows):,} rows)")
        print(f"    2. reddit_posts_corpus.csv        (only if the first is absent)")
        print()
        print(f"  Audit of the file actually used ({used_reddit.name}):")
        print(f"    median words per item : {statistics.median(wl):.0f}")
        print(f"    id prefixes           : {prov['id_prefixes']}")
        print(f"    exact-text overlap with GoEmotions raw : {ov:,} "
              f"({prov['goemotions_overlap_pct']:.1f}%)")
        if prov["goemotions_overlap_pct"] > 90:
            print()
            print("    ** The corpus described in Table 2 as 'Relationship narratives")
            print("       (7 subreddits)' is GoEmotions comment text. It is not")
            print("       relationship narratives, and it is not independent of the")
            print("       GoEmotions corpus counted separately. This is a disclosure")
            print("       item for the response letter. Script 03 rebuilds it. **")
        print()

    # --- held-out pool: the genuine relationship posts, never evaluated ------
    pool_rows, pool_src = [], None
    for cand in (v1 / "reddit_posts_corpus.csv", v1 / "relationship_corpus_FULL.csv"):
        if cand.exists():
            rows = _read_text_col(cand, min_words=20)
            if rows:
                pool_rows, pool_src = rows, cand
                break
    if not pool_rows:
        print("  No held-out pool available; preview will be skipped.")
        return [], {"status": "no_pool", "provenance": prov}

    kept = [r for r in pool_rows if _norm_hash(r["text"]) not in eval_hashes]
    dropped = len(pool_rows) - len(kept)
    subs = collections.Counter(r.get("subreddit", "") for r in kept)
    wl = [len(r["text"].split()) for r in kept]
    print(f"  Held-out pool : {pool_src.name}")
    print(f"    rows >=20 words        : {len(pool_rows):,}")
    print(f"    dropped as non-disjoint: {dropped:,}")
    print(f"    HELD-OUT USABLE        : {len(kept):,}")
    if wl:
        print(f"    median words           : {statistics.median(wl):.0f}")
    if any(subs):
        print(f"    subreddits             : {dict(subs.most_common(8))}")
    print()
    print("  Disjointness is proved by normalised-text SHA-1 against every")
    print("  evaluation text reconstructible locally (GoEmotions raw splits and")
    print(f"  the file the V1 Reddit loader actually consumed): {len(eval_hashes):,} hashes.")
    print("  These posts were never scored in any V1 evaluation, so nothing")
    print("  measured here can leak into a decision about evaluation data.")
    return [r["text"] for r in kept], {"status": "ok", "source": pool_src.name,
                                       "n_pool": len(pool_rows), "n_dropped": dropped,
                                       "n_heldout": len(kept),
                                       "eval_hashes": len(eval_hashes),
                                       "provenance": prov}


def s8_coverage(root, v1, nrc, legacy, n_sample, workers, seed=20260828):
    sub("S8b  COVERAGE AND INTER-SYSTEM AGREEMENT (held-out text)")
    pool, meta = s8_provenance_and_pool(v1)
    if not pool:
        print("  no held-out text; skipped")
        return {}, [], None, meta
    random.Random(seed).shuffle(pool)
    texts = pool[:n_sample]
    print(f"  sample {len(texts):,} held-out posts | seed {seed}")
    if len(texts) < n_sample:
        print(f"  NOTE: pool smaller than --preview-n ({n_sample:,}); using all of it.")
    k = max(1, len(texts) // workers)
    chunks = [texts[i:i + k] for i in range(0, len(texts), k)]
    t0 = time.time()
    S, C = collections.defaultdict(list), collections.defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sc, cv in ex.map(_cov_worker,
                             [(root, nrc, legacy, c, "broad", "sqrt") for c in chunks]):
            for kk, vv in sc.items():
                S[kk].extend(vv)
            for kk, vv in cv.items():
                C[kk].extend(vv)
    el = time.time() - t0
    words = sum(len(t.split()) for t in texts)
    print(f"  scored in {el:.1f}s ({len(texts)/max(el,1e-9):.1f} texts/s, "
          f"{words/max(el,1e-9):,.0f} words/s on {workers} workers)")
    print(f"  mean length {words/max(1,len(texts)):.0f} words")
    print()
    print(f"  {'system':<16}{'coverage':>10}{'mean':>10}{'sd':>9}"
          f"{'%pos':>7}{'%neu':>7}{'%neg':>7}{'%nonzero':>10}")
    rule()
    stats = {}
    for name in S:
        vals = S[name]
        n = len(vals)
        lab = collections.Counter(label(v) for v in vals)
        cov = statistics.mean(C[name]) if C.get(name) else float("nan")
        stats[name] = {"n": n, "mean": statistics.mean(vals),
                       "sd": statistics.pstdev(vals) if n > 1 else 0.0,
                       "coverage": cov, "pos": lab["pos"] / n, "neu": lab["neu"] / n,
                       "neg": lab["neg"] / n,
                       "nonzero": sum(1 for v in vals if abs(v) > 1e-9) / n}
        st = stats[name]
        print(f"  {name:<16}{st['coverage']*100:>9.2f}%{st['mean']:>+10.4f}{st['sd']:>9.4f}"
              f"{st['pos']*100:>6.1f}%{st['neu']*100:>6.1f}%{st['neg']*100:>6.1f}%"
              f"{st['nonzero']*100:>9.1f}%")
    print()
    print("  Coverage is the fraction of tokens each lexicon can even see.")
    print()
    labs = {n: [label(v) for v in S[n]] for n in S}
    real = [n for n in S if not n.startswith("V1_")]
    print("  Pairwise Cohen's kappa, 3-class labels (real systems):")
    print(f"  {'':<10}" + "".join(f"{n[:8]:>9}" for n in real))
    for a in real:
        row = f"  {a[:10]:<10}"
        for b in real:
            kv = 1.0 if a == b else kappa(labs[a], labs[b])
            row += f"{kv:>9.3f}" if kv is not None else f"{'-':>9}"
        print(row)
    print()
    print("  Real system vs the V1 toy that carried its name:")
    for rn, toy in (("vader", "V1_vader_toy"), ("nrc", "V1_nrc_toy"),
                    ("empath", "V1_liwc_toy")):
        if rn in labs and toy in labs:
            ag = sum(1 for x, y in zip(labs[rn], labs[toy]) if x == y) / len(labs[rn])
            print(f"    {rn:<8} vs {toy:<16} agreement {ag*100:>5.1f}%   "
                  f"kappa {kappa(labs[rn], labs[toy]):+.3f}")
    return stats, texts, el, meta


def s9_sensitivity(root, nrc, legacy, texts, workers):
    sub("S9  SENSITIVITY: THRESHOLD, AFINN NORMALISATION, EMPATH MAPPING")
    if not texts:
        print("  no sample available; skipped")
        return {}
    sample = texts[:min(len(texts), 2000)]
    k = max(1, len(sample) // workers)
    chunks = [sample[i:i + k] for i in range(0, len(sample), k)]
    out = {}
    print(f"  sample {len(sample):,} posts")
    print()
    print("  (a) variant comparison")
    print(f"    {'variant':<22}{'mean':>10}{'sd':>9}{'%pos':>8}{'%neu':>8}{'%neg':>8}")
    rule()
    for which, mode in ([("afinn", m) for m in ("sqrt", "dens", "mean", "tanh")] +
                        [("empath", m) for m in ("broad", "narrow")]):
        em = mode if which == "empath" else "broad"
        af = mode if which == "afinn" else "sqrt"
        vals = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for sc, _ in ex.map(_cov_worker,
                                [(root, nrc, legacy, c, em, af) for c in chunks]):
                vals.extend(sc[which])
        lab = collections.Counter(label(v) for v in vals)
        n = len(vals)
        o = {"mean": statistics.mean(vals), "sd": statistics.pstdev(vals),
             "pos": lab["pos"] / n, "neu": lab["neu"] / n, "neg": lab["neg"] / n}
        out[f"{which}:{mode}"] = o
        print(f"    {which + ':' + mode:<22}{o['mean']:>+10.4f}{o['sd']:>9.4f}"
              f"{o['pos']*100:>7.1f}%{o['neu']*100:>7.1f}%{o['neg']*100:>7.1f}%")
    print()
    print("  (b) threshold sweep -- percent labelled NEUTRAL at each cut point")
    S = collections.defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sc, _ in ex.map(_cov_worker,
                            [(root, nrc, legacy, c, "broad", "sqrt") for c in chunks]):
            for kk, vv in sc.items():
                S[kk].extend(vv)
    thrs = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30]
    print(f"    {'system':<16}" + "".join(f"{t:>9.2f}" for t in thrs))
    rule()
    sweep = {}
    for name in S:
        row = f"    {name:<16}"
        sweep[name] = {}
        for t in thrs:
            frac = sum(1 for v in S[name] if abs(v) <= t) / len(S[name])
            sweep[name][str(t)] = frac
            row += f"{frac*100:>8.1f}%"
        print(row)
    out["threshold_sweep"] = sweep
    print()
    print("  Reading: a system whose neutral fraction swings sharply across this")
    print("  row is threshold-sensitive, so its macro-F1 is a property of the")
    print("  threshold as much as of the system. AUC is not.")
    return out


def s10_decisions(root, sizes, sens):
    sub("S10  DECISIONS.md  (the pre-registration for V2)")
    p = Path(root) / "DECISIONS.md"
    now = datetime.datetime.now().isoformat(timespec="seconds")
    L = ["# PLEF V2 -- Declared analysis decisions", "",
         f"Written {now} by scripts/02_baseline_environment.py v{SCRIPT_VERSION}.", "",
         "Every arbitrary choice in the evaluation pipeline is recorded here BEFORE",
         "any corpus-level result is computed. Each entry states what was chosen,",
         "why, and whether it was decided before or after observing any output.",
         "This answers Reviewer 2 point 6, which asked for a deviation table",
         "separating confirmatory from post hoc analysis. It cannot retroactively",
         "register the original submission. It registers this one.", "",
         "## Baseline systems", "",
         "| system | source | size | licence |", "|---|---|---:|---|",
         f"| VADER | vaderSentiment reference implementation | {sizes.get('vader','?')} | MIT |",
         f"| NRC EmoLex | Mohammad & Turney 2013 v0.92 | {sizes.get('nrc','?')} | research, non-redistributable |",
         f"| Empath | Fast, Chen & Bernstein CHI 2016 | {sizes.get('empath','?')} categories | open |",
         f"| AFINN | Nielsen 2011, AFINN-en-165 | {sizes.get('afinn','?')} | ODbL |",
         f"| Hu-Liu | Hu & Liu 2004, via NLTK | {sizes.get('huliu','?')} | free |",
         f"| labMT | Dodds & Danforth | {sizes.get('labmt','?')} | free |", "",
         "LIWC-22 is NOT used: it is proprietary and no licence is held. Empath",
         "occupies that role; Fast et al. report mean r = 0.906 with LIWC across a",
         "mixed corpus. The word 'LIWC' must not name a baseline in the manuscript.",
         "", "## Declared choices", "",
         "### D1 Empath polarity category set",
         "Chosen: broad set, 19 positive and 26 negative built-in categories.",
         "",
         "**Provenance: POST HOC.** The narrow set (positive_emotion and",
         "negative_emotion only) was tried first and returned exactly 0.000 on two",
         "of five hand-written known-answer sentences, which would have entered the",
         "results as a degenerate all-neutral baseline. The broad set was then",
         "adopted. Categories were selected by NAME only, judged on five",
         "hand-written sentences, and never tuned against any evaluation corpus.",
         "Both variants are scored; see the sensitivity table below.", "",
         "### D2 AFINN normalisation",
         "Chosen primary: sum / (5 * sqrt(n_tokens)).", "",
         "**Provenance: ARBITRARY, no published basis.** AFINN returns an unbounded",
         "integer sum, so some normalisation is required for comparability. Four",
         "variants (sqrt, dens, mean, tanh) are implemented and all four reported.",
         "", "### D3 labMT scoring",
         "Stop band [4.0, 6.0] discarded as neutral; remainder averaged, centred at",
         "5.0, divided by 4.0. This is the standard labMT procedure. labMTsimple's",
         "own stopper() raises TypeError in the current release and is bypassed.",
         "",
         "**labMT measures happiness, not polarity. Its zero point is not neutral**",
         "**and it is strongly positively shifted on ordinary text.** This must be",
         "stated wherever labMT is reported.", "",
         "### D4 Classification threshold",
         "A single +/-0.05 threshold, inherited from VADER's convention, applied",
         "uniformly to every system. It is not natural for AFINN, Empath, Hu-Liu or",
         "labMT.", "",
         "**Consequence: macro-F1 is threshold-conditional.** Primary reporting is",
         "macro-AUC, which is threshold-free. A full threshold sweep is reported so",
         "the sensitivity is visible rather than buried.", "",
         "### D5 Legacy V1 lexicons",
         "The three simplified lexicons from the original submission are extracted",
         "verbatim from plef_v7.py by AST and scored alongside the real systems.",
         "They appear ONLY in supplementary material, solely to quantify the",
         "magnitude of the error in the submitted Table 3. They must never be",
         "presented under the names VADER, NRC or LIWC.", "",
         "### D6 NRC companion lexicons are instruments, not baselines",
         "NRC-VAD and NRC Emotion Intensity are external criteria, not comparison",
         "systems:", "",
         "- VAD dominance is an independent criterion for PAI, because dominance is",
         "  annotated without reference to any pronoun count. Addresses Reviewer 2",
         "  point 7 (PTI and PAI share their inputs).",
         "- Emotion-intensity sequences are an independent criterion for TEG,",
         "  because they are not derived from PLEF's own compound score. Addresses",
         "  Reviewer 1 point 2 (TEG has no validation target).", "",
         "Neither appears in the baseline comparison table.", "",
         "### D8 Smoke-test text is held out",
         "The verification preview in script 02 is scored on genuine relationship",
         "posts that were never used in any V1 evaluation, proved disjoint by",
         "normalised-text SHA-1 against every evaluation text reconstructible",
         "locally. No decision in this file was derived from an evaluation",
         "corpus. The preview measures throughput, coverage and inter-system",
         "agreement only; it produces no number that appears in the manuscript.",
         "", "### D7 Known-answer test tiering",
         "Core sentences (unambiguous polarity, no negation) are asserted for",
         "every system. Negation sentences are reported for every system but",
         "asserted only for VADER and the V1 VADER toy, which are the only two",
         "that implement negation handling. NRC, Empath, Hu-Liu and labMT are pure",
         "bag-of-words lexicons; asserting negation for them would assert a",
         "capability they do not claim. Their negation failures are reported as a",
         "genuine limitation.", "",
         "## Still to be declared (script 03)", "",
         "- ISEAR label mapping. ISEAR has no neutral class, so joy -> positive and",
         "  fear/anger/sadness/disgust/shame/guilt -> negative makes it a binary",
         "  problem inside a three-class evaluation.",
         "- DailyDialog 'surprise' polarity, which has no defensible mapping.",
         "- NAVA five-class scheme, which the implementation uses and the manuscript",
         "  reports as three.", "",
         "## Sensitivity measured at declaration time", ""]
    if sens:
        L += ["| variant | mean | sd | %pos | %neu | %neg |",
              "|---|---:|---:|---:|---:|---:|"]
        for k, v in sens.items():
            if k == "threshold_sweep":
                continue
            L.append(f"| {k} | {v['mean']:+.4f} | {v['sd']:.4f} | "
                     f"{v['pos']*100:.1f}% | {v['neu']*100:.1f}% | {v['neg']*100:.1f}% |")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  written -> {p}")
    print(f"  sha256   {sha256(p)}")
    print("  Commit this file NOW, before script 04 produces any evaluation number.")
    return str(p)


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="PLEF V2 script 02 -- hardened baseline environment.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--v1", required=True)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--preview-n", type=int, default=3000)
    ap.add_argument("--skip-preview", action="store_true")
    ap.add_argument("--nrc", help="explicit path to the EmoLex word-level .txt")
    ap.add_argument("--vad", help="explicit path to the NRC-VAD .txt")
    ap.add_argument("--emoint", help="explicit path to the EmoInt .txt")
    args = ap.parse_args()

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    root, v1 = Path(args.root), Path(args.v1)
    if not root.exists():
        print(f"FATAL: root does not exist: {root}. Run script 01 first.")
        return 2

    tee = Tee(root / "results" / "forensics" / "console_log_02.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 02 : BASELINE ENVIRONMENT (hardened)")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  V2 root        : {root}")
        print(f"  V1 source      : {v1}")
        print(f"  workers        : {workers}")

        _, cands = s0_extract(root)
        ok, pkgs = s1_packages(args.install)
        if not ok:
            return 2
        chosen = s2_lexicons(cands, {"emolex": args.nrc, "vad": args.vad,
                                     "emoint": args.emoint})
        if "emolex" not in chosen:
            print("\n  FATAL: no NRC Emotion Lexicon identified in data/external.")
            print("  Place the archive or the word-level .txt there and re-run.")
            return 5
        nrc_path = chosen["emolex"]["path"]
        legacy_path, legacy_meta = s4_legacy(v1, root)
        if legacy_path is None:
            return 4
        s3_adapter(root)
        passed, sizes, advmeta = s5_verify(root, nrc_path, legacy_path)
        det = s6_determinism(root, nrc_path, legacy_path, workers)
        pure = s7_purity(root)
        if not passed:
            print("\n  Environment NOT verified. Fix the failures above before script 03.")
            return 3

        stats, texts, elapsed, pool_meta = ({}, [], None, {}) if args.skip_preview else \
            s8_coverage(root, v1, nrc_path, legacy_path, args.preview_n, workers)
        sens = {} if args.skip_preview else \
            s9_sensitivity(root, nrc_path, legacy_path, texts, workers)

        env = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
               "script_version": SCRIPT_VERSION, "python": sys.version.split()[0],
               "platform": sys.platform, "cpu_count": os.cpu_count(),
               "packages": pkgs, "lexicons": chosen, "legacy": legacy_meta,
               "baseline_sizes": sizes, "determinism_ok": det,
               "purity_harness_ok": pure, "adversarial": advmeta,
               "coverage_stats": stats, "sensitivity": sens, "preview_pool": pool_meta,
               "preview_seconds": elapsed}
        (root / "MANIFEST").mkdir(parents=True, exist_ok=True)
        (root / "MANIFEST" / "environment.json").write_text(
            json.dumps(env, indent=2, default=str), encoding="utf-8")
        s10_decisions(root, sizes, sens)

        req = root / "requirements-eval.txt"
        req.write_text("\n".join(
            [f"{k}=={v}" for k, v in sorted(pkgs.items()) if v not in ("?", "unknown")] +
            ["", "# NRC lexicons: obtain separately, non-redistributable",
             "# https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm"]) + "\n",
            encoding="utf-8")

        head("DONE")
        print(f"  adapter      : {root / 'src' / 'plef_baselines.py'}")
        print(f"  purity       : {root / 'src' / 'plef_purity.py'}")
        print(f"  legacy toys  : {legacy_path}")
        print(f"  decisions    : {root / 'DECISIONS.md'}")
        print(f"  environment  : {root / 'MANIFEST' / 'environment.json'}")
        print(f"  log          : {root / 'results' / 'forensics' / 'console_log_02.txt'}")
        print()
        print(f"  determinism verified : {det}")
        print(f"  purity harness works : {pure}")
        print(f"  lexicons identified  : {sorted(chosen)}")
        if elapsed:
            rate = len(texts) / max(elapsed, 1e-9)
            print(f"  throughput           : {rate:.0f} texts/s -> approx "
                  f"{160000/max(rate,1e-9)/60:.1f} min for 160k texts on {workers} workers")
        print()
        print("  NEXT: send me this log. Script 03 rebuilds the nine dataset loaders")
        print("  and wires VAD/EmoInt to the two hypotheses that currently have no")
        print("  external criterion.")
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
