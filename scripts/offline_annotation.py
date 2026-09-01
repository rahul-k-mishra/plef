#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- OFFLINE ANNOTATION  (offline_annotation.py, v1.0.0)
===============================================================================

WHAT THIS IS FOR (plain language)
----------------------------------
Some raters would rather work in Excel than in a browser. This script exports
one spreadsheet per rater, and imports the filled spreadsheets back into the
same format the web tool produces, so script 06 cannot tell the difference
except where it should.

WHY YOU CANNOT JUST FILL IN THE TASK FILES
--------------------------------------------
annotation_task_raterN.csv has 200 rows. The real sequence has 220 SLOTS,
because 10% of posts are shown twice, at least 40 slots apart, to measure
whether a rater agrees with their own earlier judgement. Filling the 200-row
task file throws that away, and intra-rater reliability is the only check that
tells you whether the labels carry any weight at all.

The export below contains all 220 slots in the correct order.

WHAT IS HONESTLY WEAKER ABOUT OFFLINE ENTRY
---------------------------------------------
Two things, and both are recorded rather than hidden.

  1. NO TIMING OR ENGAGEMENT DATA. seconds, wall_seconds, revisions and
     scrolled_to_end are all zero for offline rows. You cannot then write
     "median 34 s per item" in the paper for those rows. Every imported row is
     stamped entry_method=offline so the paper can state exactly how many rows
     have instrumentation and how many do not.

  2. BLINDNESS IS WEAKER. In a spreadsheet a rater can scroll back, sort, or
     notice that two rows look alike. The export uses an opaque row_key instead
     of the post id so repeats are not identifiable from the key, and the
     repeats are far apart, but a determined reader could still spot them. The
     web tool prevents this; a spreadsheet cannot. Say so in the paper.

If you can get raters to use the web tool, use the web tool.

USAGE
-----
  python offline_annotation.py --root <V2_ROOT> --mode export
      writes data/interim/annotations/offline/rater{1,2,3}_OFFLINE.csv

  python offline_annotation.py --root <V2_ROOT> --mode import
      validates the filled files and writes annotations_rater{N}.csv

  python offline_annotation.py --root <V2_ROOT> --mode import --rater 2
      import one rater only

The import REFUSES to write anything for a rater whose file has an invalid
value, a changed row_key, or a turning point outside the sentence range. It
prints every problem with its row number. A partially filled file is fine --
only completed rows are imported.
===============================================================================
"""

import argparse
import collections
import csv
import itertools
import random
import datetime
import hashlib
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
VERSION = "1.3.0"

SENTIMENTS = {"pos", "neu", "neg"}
ARCS = {"tragic", "flat", "redemptive"}
CONFS = {"1", "2", "3", "4", "5"}

EXPORT_COLS = ["row_key", "n_sentences", "n_words", "est_read_seconds",
               "numbered_text",
               "overall_sentiment", "turning_point", "arc", "confidence", "notes"]

OUT_COLS = ["slot", "id", "is_repeat", "overall_sentiment", "turning_point",
            "arc", "confidence", "notes", "seconds", "wall_seconds",
            "revisions", "scrolled_to_end", "saved_at", "entry_method"]


def rule(ch="-", w=78): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def ann_dir(root):
    return Path(root) / "data" / "interim" / "annotations"


def row_key(rater, slot):
    """Opaque, stable, and does NOT reveal which slots are repeats."""
    h = hashlib.sha1(f"plefv2|{rater}|{slot}".encode()).hexdigest()
    return f"{h[:10]}"


# Excel on a Windows machine saves CSV in the local ANSI codepage, not UTF-8.
# A curly quote becomes byte 0x93 in cp1252 and UTF-8 decoding dies on it.
# Encodings are tried in order and the one used is REPORTED, because a silent
# fallback to latin-1 turns a curly quote into mojibake without complaint.
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


def read_csv_rows(path):
    """Return (rows, encoding_used, replaced_chars). Never raises on encoding."""
    last = None
    for enc in CSV_ENCODINGS:
        try:
            with open(path, encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            return rows, enc, 0
        except UnicodeDecodeError as e:
            last = e
            continue
    # Nothing decoded cleanly. Fall back with replacement and say how much was lost.
    with open(path, "rb") as f:
        raw = f.read()
    txt = raw.decode("utf-8", errors="replace")
    import io
    rows = list(csv.DictReader(io.StringIO(txt, newline="")))
    return rows, f"utf-8 with replacement (last error: {last})", txt.count("\ufffd")


def _saved_slots(root, rater):
    """Slots already answered, from either the web tool or a previous import."""
    p = ann_dir(root) / f"annotations_rater{rater}.csv"
    out = set()
    if p.exists():
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out.add(int(r["slot"]))
                except (KeyError, ValueError, TypeError):
                    pass
    return out


CORE_N = 60          # posts annotated by ALL raters -> reliability
UNIQUE_N = 40        # posts unique to each rater      -> coverage
DESIGN_SEED = 20260830


def design_assignment(n_posts, n_raters=3):
    """Give each rater a DIFFERENT subset with a designed shared core.

    v1.1.0 gave all three raters the same 200 posts in different orders. That
    made the sheets interchangeable: one completed sheet could be copied into
    the others and only the row order differed. The result was three files with
    identical turning points on 200/200 posts.

    Now each rater receives CORE_N posts shared by everyone plus UNIQUE_N posts
    that only they have. A sheet copied from another rater is wrong on the
    unique portion, so wholesale copying is both harder and immediately visible.
    The shared core still supports inter-rater reliability.
    """
    rnd = random.Random(DESIGN_SEED)
    idx = list(range(n_posts))
    rnd.shuffle(idx)
    core = sorted(idx[:CORE_N])
    rest = idx[CORE_N:]
    out = {}
    for r in range(1, n_raters + 1):
        lo = (r - 1) * UNIQUE_N
        uniq = sorted(rest[lo:lo + UNIQUE_N])
        out[r] = {"core": core, "unique": uniq, "all": sorted(core + uniq)}
    return out


def build(root, rater):
    """Reuse the web tool's sequence builder so both paths are identical."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import annotate
    rows = annotate.load_task(root, rater)
    if rows is None:
        return None, None
    return rows, annotate.build_sequence(rows, rater)


GUIDE = r"""# ANNOTATOR RULES

Read this completely before you open the spreadsheet. It takes five minutes.
Doing so will save you from doing the work twice.

---

## Why these rules are this strict

Two annotation rounds have already been discarded.

**Round 1.** Three annotators returned files in which the turning point was
identical on 200 posts out of 200. Choosing the same sentence out of roughly
twenty-two, by chance, on every post, is about as likely as winning a national
lottery repeatedly. The answers had been shared. All 559 rows were thrown away.

**Round 2.** Three annotators returned files in which, across 600 pairwise
comparisons, sentiment, arc and confidence either **all three matched or all
three differed** — never one, never two. Real people constantly agree about
sentiment while disagreeing about confidence. Zero partial agreement is not
something human judgement produces. All 660 rows were thrown away.

Nobody was accused of anything. The data simply could not be used, and
automated checks caught both rounds.

This is annotation for a scientific paper under peer review. Three reviewers
have already found fabricated statistics in the previous version of this work.
Every number now has to survive someone actively trying to break it.

---

## What you are judging

You are reading real Reddit posts from relationship subreddits: breakups,
infidelity, heartbreak, requests for advice. They are long — a median of about
370 words, roughly 22 sentences.

For each post you answer four questions.

### 1. `overall_sentiment` — the NARRATOR's emotional stance

Choose exactly one: `pos`, `neu`, `neg`

You are judging **how the writer feels as they write**, not how bad the events
are.

- *"He cheated on me for two years. I found out last month. I've moved on and
  I feel free."* → **pos**. Terrible events, settled narrator.
- *"My girlfriend and I had a small argument about dishes and I cannot stop
  crying, I feel like I'm broken."* → **neg**. Minor events, distressed narrator.
- *"My partner wants to move cities for work. I'm listing the pros and cons.
  What would you do?"* → **neu**. Deliberative, not distressed.

Use `neu` when the writer is composed, factual, or asking for advice without
strong feeling. Use it because the post is genuinely neutral, not because you
are unsure. If you are unsure, pick the closer of `pos`/`neg` and mark
confidence 1 or 2.

### 2. `turning_point` — one sentence number, or 0

The sentences are numbered `[1]`, `[2]`, `[3]` in the text. Write the number of
the single sentence where the emotional direction of the narrative **changes
most clearly**.

**Write 0 when there is no turning point.** Many posts have none:

- uniformly miserable from the first sentence to the last
- a flat request for advice with no emotional arc
- a list of facts

**Expect to use 0 on roughly one post in five.** In round 1, zero posts out of
559 were marked 0. That alone made the data worthless, because a turning point
forced onto a post that has none is a guess recorded as a judgement.

Mark exactly one sentence, or none. Never two. Do not mark sentence 1 as a
turning point — the narrative cannot change direction before it has started.

### 3. `arc` — the shape of the whole post

Choose exactly one: `tragic`, `flat`, `redemptive`

- `tragic` — ends worse than it starts
- `redemptive` — ends better than it starts
- `flat` — no clear directional change

Judge start to end, not the worst moment in the middle. A post that describes
a devastating betrayal and ends with *"I'm healing"* is **redemptive**.

If you marked `turning_point = 0`, the arc is almost always `flat`. If it is
not, say why in `notes`.

### 4. `confidence` — 1 to 5

`1` = a guess. `5` = certain.

**Your confidence must vary.** If nearly every row is a 4 or 5, that is a
signal of rapid clicking rather than judgement, and it is checked. Some posts
are genuinely ambiguous. Say so with a 1 or a 2.

---

## Hard rules

1. **Read the whole post before answering.** The `est_read_seconds` column
   shows the minimum reading time for that post at ordinary speed. A 370-word
   post takes about 90 seconds to read before you have judged anything.
   In round 1 the median was 34 seconds per post including idle time. That is
   less than half the time needed to read the text, and it is recorded.

2. **Do not look at another annotator's file. Ever.** Not to compare, not to
   check, not to calibrate. Disagreement between annotators is the measurement.
   If you copy, the measurement is destroyed and nothing tells you which of
   your own answers were real.

3. **Do not fill down, autocomplete, or paste blocks of answers.** Every row is
   a separate judgement. Excel's fill handle is the single most damaging thing
   you can do to this data.

4. **Do not reorder or sort the rows.** Do not edit `row_key`, `numbered_text`,
   `n_sentences`, `n_words` or `est_read_seconds`. The import refuses a file
   whose keys have moved.

5. **Do not skip rows.** If genuinely stuck, answer with confidence 1 and move
   on. A guess marked as a guess is usable. A blank row is not.

6. **Work in sessions.** Twenty to thirty posts at a time. Fatigue after an
   hour is real and it shows in the data.

7. **Answer as yourself.** There is no correct answer being marked. Two
   thoughtful people will disagree on perhaps a third of these posts, and that
   disagreement is exactly what the study measures.

---

## What is checked, and how

You are told this in full, because a check nobody knows about is a trap, and a
check everybody knows about is a deterrent.

| check | what it detects | threshold |
|---|---|---|
| Turning-point identity between annotators | shared answers | above 50% is rejected; chance is about 5% |
| Partial-agreement pattern | answers copied as blocks | zero partial matches is rejected |
| "No turning point" rate | forcing a turning point onto every post | 0% is rejected; expect 15-25% |
| Confidence spread | rapid uniform clicking | over 85% at 4-5 is flagged |
| Hidden repeats | agreement with your own earlier judgement | about 10% of posts appear twice, far apart, unmarked |
| Time per item (web tool only) | answering faster than the post can be read | median under 8 seconds is flagged |
| Row-key integrity | reordered or edited files | any mismatch refuses the whole file |

**About the hidden repeats:** roughly one post in ten appears twice in your
sheet, dozens of rows apart, with no indication. You are not expected to
remember it or to match your earlier answer. Answer it as you find it. If your
self-agreement is low that is useful information about how hard the task is,
not a mark against you.

---

## How long this takes

About 100 posts. At 90 to 120 seconds each, roughly **two and a half to three
hours**, split across sessions.

If you finish 100 posts in under an hour, the data will not pass the checks and
you will be asked to do it again. Slower is genuinely better here.

---

## If something is wrong

Tell the person who gave you the sheet:

- text that is cut off or unreadable
- sentence numbers that do not match the text
- a post in another language, or empty
- anything that makes a row unanswerable

Do not guess around a broken row. Flag it.

---

## The short version

Read every post to the end. Judge the writer, not the events. Use 0 when there
is no turning point, and expect that about one time in five. Let your
confidence vary. Never look at anyone else's file. Never fill down.

Two rounds have already been discarded. This one only counts if it is real.

"""


def do_export(root, raters, skip_done=True, design=True):
    head(f"OFFLINE ANNOTATION EXPORT  v{VERSION}")
    out = ann_dir(root) / "offline"
    out.mkdir(parents=True, exist_ok=True)
    for r in raters:
        rows, seq = build(root, r)
        if rows is None:
            print(f"  rater {r}: annotation_task_rater{r}.csv not found; skipped")
            continue
        done = set(_saved_slots(root, r)) if skip_done else set()
        assign = design_assignment(len(rows)).get(r) if design else None
        allowed = set(assign["all"]) if assign else None
        p = out / f"rater{r}_OFFLINE.csv"
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=EXPORT_COLS)
            w.writeheader()
            written = 0
            for s in seq:
                if skip_done and s["slot"] in done:
                    continue
                if allowed is not None and s["idx"] not in allowed:
                    continue
                src = rows[s["idx"]]
                nw = len(src["numbered_text"].split())
                w.writerow({"row_key": row_key(r, s["slot"]),
                            "n_sentences": src["n_sentences"],
                            "n_words": nw,
                            # 250 wpm is ordinary adult reading speed. Printed so
                            # the annotator can see what the post actually costs.
                            "est_read_seconds": int(round(nw / 250.0 * 60)),
                            "numbered_text": src["numbered_text"],
                            "overall_sentiment": "", "turning_point": "",
                            "arc": "", "confidence": "", "notes": ""})
                written += 1
        reps = sum(s["is_repeat"] for s in seq)
        note = f", {len(done)} already answered and skipped" if skip_done and done else ""
        if assign:
            print(f"  rater {r}: {written} rows -> {p.name}   "
                  f"({len(assign['core'])} shared core + {len(assign['unique'])} "
                  f"unique to this rater{note})")
        else:
            print(f"  rater {r}: {written} rows written of {len(seq)} slots "
                  f"({len(rows)} posts + {reps} hidden repeats{note}) -> {p.name}")
    g = out / "OFFLINE_GUIDE.md"
    g.write_text(GUIDE, encoding="utf-8")
    print(f"\n  guide -> {g}")
    print()
    print("  SAVE LOCATION for the raters:")
    print(f"    {out}")
    print("  Fill only: overall_sentiment, turning_point, arc, confidence")
    print("  Do not reorder rows, sort, or edit row_key / numbered_text.")
    print()
    print("  UTF-8 BOM is written so Excel opens the text correctly. Keep CSV")
    print("  format when saving; decline any offer to convert to .xlsx.")
    return 0


def cross_rater_check(root, raters):
    """Refuse to let duplicated sheets pass as independent annotation.

    Three people cannot pick the same sentence out of ~22 on 200 posts. In the
    previous round they did, on 200 of 200, and nothing in the tooling noticed;
    it took a manual investigation. This check runs automatically.
    """
    sub("CROSS-RATER INDEPENDENCE CHECK")
    data = {}
    for r in raters:
        p = ann_dir(root) / f"annotations_rater{r}.csv"
        if not p.exists():
            continue
        d = {}
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for row in sorted(csv.DictReader(f), key=lambda x: int(x["slot"])):
                d.setdefault(row["id"], row)
        if d:
            data[r] = d
    if len(data) < 2:
        print("  fewer than two raters with data; nothing to compare")
        return True
    ok = True
    print(f"  {'pair':<10}{'shared':>8}{'TP identical':>14}{'sentiment':>11}"
          f"{'arc':>8}   verdict")
    rule()
    for a, b in itertools.combinations(sorted(data), 2):
        ids = set(data[a]) & set(data[b])
        if len(ids) < 10:
            print(f"  {a}v{b:<8}{len(ids):>8}   too few shared items to judge")
            continue
        tp = sum(1 for i in ids
                 if data[a][i].get("turning_point") == data[b][i].get("turning_point"))
        se = sum(1 for i in ids
                 if data[a][i].get("overall_sentiment") == data[b][i].get("overall_sentiment"))
        ar = sum(1 for i in ids if data[a][i].get("arc") == data[b][i].get("arc"))
        n = len(ids)
        # Chance for two raters to pick the same sentence is roughly 1/n_sentences,
        # about 5%. Anything above 50% is not independent judgement.
        bad = tp / n > 0.50
        if bad:
            ok = False
        print(f"  {a}v{b:<8}{n:>8}{100*tp/n:>13.1f}%{100*se/n:>10.1f}%"
              f"{100*ar/n:>7.1f}%   {'** NOT INDEPENDENT **' if bad else 'plausible'}")
    if not ok:
        print()
        print("  ** Turning-point identity above 50% between raters. Chance is about")
        print("     5% (one sentence out of ~22). This is copied data, not")
        print("     independent annotation. Krippendorff alpha computed from it")
        print("     would measure the edits made during copying, not reliability.")
        print("     The gold file must NOT be built from these answers. **")
    else:
        print()
        print("  No pair exceeds the independence threshold.")
    return ok


def do_import(root, raters):
    head(f"OFFLINE ANNOTATION IMPORT  v{VERSION}")
    src_dir = ann_dir(root) / "offline"
    any_ok = False
    for r in raters:
        p = src_dir / f"rater{r}_OFFLINE.csv"
        if not p.exists():
            print(f"\n  rater {r}: {p.name} not found; skipped")
            continue
        rows, seq = build(root, r)
        if rows is None:
            print(f"\n  rater {r}: task file missing; skipped")
            continue
        expected = {row_key(r, s["slot"]): s for s in seq}
        sub(f"rater {r}")
        problems, filled = [], []
        recs, enc_used, replaced = read_csv_rows(p)
        if enc_used != "utf-8-sig":
            print(f"  encoding : file was not UTF-8; read as {enc_used}")
            print(f"             (Excel saves CSV in the local ANSI codepage unless")
            print(f"              'CSV UTF-8' is chosen. Answers are unaffected;")
            print(f"              only accented or curly characters in notes.)")
        if replaced:
            print(f"  ** {replaced} character(s) could not be decoded and were "
                  f"replaced. Check the notes column. **")
        for ln, rec in enumerate(recs, start=2):
                key = (rec.get("row_key") or "").strip()
                s = expected.get(key)
                if s is None:
                    problems.append(f"line {ln}: unknown row_key {key!r} -- the "
                                    f"file was reordered or row_key was edited")
                    continue
                sent = (rec.get("overall_sentiment") or "").strip().lower()
                arc = (rec.get("arc") or "").strip().lower()
                conf = (rec.get("confidence") or "").strip()
                tp = (rec.get("turning_point") or "").strip()
                if not any([sent, arc, conf, tp]):
                    continue                      # untouched row
                if sent not in SENTIMENTS:
                    problems.append(f"line {ln}: overall_sentiment {sent!r} "
                                    f"must be pos, neu or neg")
                if arc not in ARCS:
                    problems.append(f"line {ln}: arc {arc!r} must be tragic, "
                                    f"flat or redemptive")
                if conf.split(".")[0] not in CONFS:
                    problems.append(f"line {ln}: confidence {conf!r} must be 1-5")
                try:
                    tpi = int(float(tp))
                except ValueError:
                    problems.append(f"line {ln}: turning_point {tp!r} must be a "
                                    f"sentence number or 0")
                    continue
                nsent = int(rows[s["idx"]]["n_sentences"])
                if not (0 <= tpi <= nsent):
                    problems.append(f"line {ln}: turning_point {tpi} outside "
                                    f"1..{nsent} (0 means none)")
                filled.append((s, sent, tpi, arc, conf.split(".")[0],
                               (rec.get("notes") or "").replace("\n", " ")))
        print(f"  rows completed : {len(filled)} of {len(seq)}")
        if problems:
            print(f"  REFUSED: {len(problems)} problem(s). Nothing written.")
            for pr in problems[:25]:
                print(f"    - {pr}")
            if len(problems) > 25:
                print(f"    ... and {len(problems)-25} more")
            continue
        if not filled:
            print("  nothing to import")
            continue
        dest = ann_dir(root) / f"annotations_rater{r}.csv"
        existing = {}
        if dest.exists():
            with open(dest, encoding="utf-8", newline="") as f:
                for rec in csv.DictReader(f):
                    try:
                        existing[int(rec["slot"])] = rec
                    except (KeyError, ValueError):
                        pass
            print(f"  existing file has {len(existing)} rows; web-tool rows are "
                  f"kept and offline rows are merged in")
        now = datetime.datetime.now().isoformat(timespec="seconds")
        overwritten = 0
        for s, sent, tpi, arc, conf, notes in filled:
            slot = s["slot"]
            if slot in existing and existing[slot].get("entry_method") != "offline":
                overwritten += 1
            existing[slot] = {"slot": slot, "id": rows[s["idx"]]["id"],
                              "is_repeat": s["is_repeat"],
                              "overall_sentiment": sent, "turning_point": tpi,
                              "arc": arc, "confidence": conf, "notes": notes,
                              "seconds": 0, "wall_seconds": 0, "revisions": 0,
                              "scrolled_to_end": 0, "saved_at": now,
                              "entry_method": "offline"}
        tmp = Path(str(dest) + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLS, extrasaction="ignore")
            w.writeheader()
            for slot in sorted(existing):
                row = dict(existing[slot])
                row.setdefault("entry_method", "web")
                w.writerow(row)
        import os
        os.replace(tmp, dest)
        off = sum(1 for v in existing.values()
                  if v.get("entry_method") == "offline")
        print(f"  written -> {dest.name}   {len(existing)} rows total, "
              f"{off} offline, {len(existing)-off} from the web tool")
        # Offline entry records no timing, so the skim signal is gone. These
        # structural checks are what remains, and they must be printed loudly.
        tp0 = sum(1 for _, _, tpi, _, _, _ in filled if tpi == 0)
        conf = collections.Counter(c for _, _, _, _, c, _ in filled)
        sent = collections.Counter(x for _, x, _, _, _, _ in filled)
        print()
        print("  QUALITY CHECKS (offline entry records no timing; these are what")
        print("  remain, and they are the same checks the web tool applies):")
        print(f"    'no turning point' used : {tp0} of {len(filled)} "
              f"({100*tp0/max(1,len(filled)):.0f}%)")
        if tp0 == 0 and len(filled) >= 30:
            print("    ** ZERO posts marked as having no turning point. Many")
            print("       relationship posts are uniformly negative throughout. A")
            print("       rate of 0% means a turning point was forced onto every")
            print("       post, which makes the H1 criterion meaningless. Ask the")
            print("       annotator to use 0 where there is genuinely no change. **")
        print(f"    sentiment distribution  : {dict(sent)}")
        print(f"    confidence distribution : {dict(sorted(conf.items()))}")
        if conf and sum(conf.get(k, 0) for k in ("4", "5")) / max(1, len(filled)) > 0.85:
            print("    ** over 85% of items rated confidence 4-5. Rapid, uniformly")
            print("       high confidence is a signal of skimming rather than")
            print("       judgement. **")
        if overwritten:
            print(f"  NOTE: {overwritten} web-tool row(s) were replaced by offline "
                  f"answers, losing their timing data")
        reps = [v for v in existing.values() if str(v.get("is_repeat")) == "1"]
        print(f"  hidden repeats captured: {len(reps)} "
              f"(intra-rater reliability is measurable)")
        any_ok = True
    if any_ok:
        cross_rater_check(root, raters)
        print()
        print("  Check the result with:")
        print("    python annotate.py --root <V2_ROOT> --mode status")
        print()
        print("  Offline rows carry entry_method=offline and zero timing data.")
        print("  The paper must state how many rows have instrumentation.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="PLEF V2 offline annotation.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--mode", choices=["export", "import"], required=True)
    ap.add_argument("--rater", type=int, default=0, help="one rater only")
    ap.add_argument("--raters", default="1,2,3")
    ap.add_argument("--no-design", action="store_true",
                    help="give every rater the same full set (the v1.1.0 "
                         "behaviour that allowed sheets to be interchanged)")
    ap.add_argument("--redo-all", action="store_true",
                    help="export EVERY slot, including ones already answered. Use "
                         "this when existing answers are being redone.")
    args = ap.parse_args()
    root = Path(args.root)
    if not ann_dir(root).exists():
        print(f"FATAL: {ann_dir(root)} not found. Run script 03 first.")
        return 2
    raters = [args.rater] if args.rater else [
        int(x) for x in args.raters.split(",") if x.strip().isdigit()]
    if args.mode == "export":
        return do_export(root, raters, not args.redo_all, not args.no_design)
    return do_import(root, raters)


if __name__ == "__main__":
    sys.exit(main())
