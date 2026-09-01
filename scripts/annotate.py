#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- ANNOTATION TOOL  (annotate.py, v1.0.0)
===============================================================================

WHAT THIS IS FOR (plain language)
----------------------------------
Three reviewers said the same thing: hypothesis H1 claims LEWI finds the
emotional turning point of a narrative, and it was never tested against a human
judgement. The submitted paper marked H1 "Supported (proxy)" using the
NAVA x LEWI correlation, which two reviewers identified as circular.

This tool collects the missing human criterion. It runs a local web app on your
own machine -- no internet, no upload, no account. Annotators open a browser,
work through 200 posts, and the answers are written straight to CSV.

It is built to make the annotation FAST and to make it HARD to produce data
that cannot be defended.

THREE MODES
-----------
  serve    (default) run the annotation UI for one rater
  status   progress and quality-control readout for all raters
  merge    combine raters, compute reliability, write the gold file

WHY THE QUALITY-CONTROL PARTS ARE THERE
----------------------------------------
Annotation that cannot be audited is worth about as much as the labels V1
invented. The tool therefore records, for every item:

  * seconds spent on the item, first view to final save
  * how many times the answer was changed
  * whether the annotator scrolled to the end of the post

and it plants REPEAT ITEMS: a sample of posts is shown twice, far apart in the
sequence, without the annotator knowing. Agreement with oneself is intra-rater
reliability. A rater who disagrees with their own earlier judgement half the
time has told you their labels are noise, and you need to know that before it
reaches a reviewer, not after.

None of this is punitive. It is what lets you write "inter-rater alpha = X,
intra-rater agreement = Y, median 34 s per item" in the paper instead of
"three trained raters annotated 200 narratives", which is the kind of sentence
reviewers no longer accept without evidence.

WHAT THE ANNOTATOR NEVER SEES
------------------------------
  * any PLEF output, score, or prediction
  * any other rater's answers
  * their own earlier answer to a repeated item
Blindness is enforced by the tool, not by instruction.

RUNNING IT
----------
  python annotate.py --root <V2_ROOT> --rater 1
      opens http://127.0.0.1:8731 -- annotate, close the tab when done,
      Ctrl+C in the terminal to stop. Progress is saved continuously; you can
      stop and resume any time.

  python annotate.py --root <V2_ROOT> --mode status
  python annotate.py --root <V2_ROOT> --mode merge

KEYBOARD
--------
  1 2 3      sentiment  positive / neutral / negative
  q w e      arc        tragic / flat / redemptive
  1..5 +Shift   confidence
  click a sentence, or type its number, to set the turning point
  0          turning point = none
  Enter      save and advance      Backspace   previous item

DEPENDENCIES
------------
  Python standard library only.
===============================================================================
"""

import argparse
import csv
import datetime
import hashlib
import html
import json
import math
import os
import random
import re
import statistics
import sys
import threading
import traceback
import webbrowser
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
VERSION = "1.6.1"
PORT = 8731
REPEAT_FRACTION = 0.10        # 10% of items shown twice for intra-rater check
REPEAT_MIN_GAP = 40           # items between the two showings
FAST_ITEM_SECONDS = 8         # below this, flag as possibly rushed

SENTIMENTS = ["pos", "neu", "neg"]
ARCS = ["tragic", "flat", "redemptive"]


# ===========================================================================
def rule(ch="-", w=78): print(ch * w)
def head(t): print(); rule("="); print(t); rule("=")
def sub(t): print(); print(t); rule("-")


def ann_dir(root):
    return Path(root) / "data" / "interim" / "annotations"


def task_file(root, rater):
    return ann_dir(root) / f"annotation_task_rater{rater}.csv"


def round_file(root, rater):
    return ann_dir(root) / f"round_meta_rater{rater}.json"


def save_round_meta(root, rater, seq, limit):
    """Persist a limited round's sequence.

    Without this, --mode status and --mode merge rebuild the FULL 220-slot
    sequence and report a completed 40-item round as "40/220 (18%)" with
    "180 remaining, approx 6.2 h" -- alarming and wrong.
    """
    round_file(root, rater).write_text(json.dumps(
        {"limit": limit, "n_slots": len(seq),
         "seq": [{"slot": x["slot"], "idx": x["idx"], "is_repeat": x["is_repeat"]}
                 for x in seq],
         "created": datetime.datetime.now().isoformat(timespec="seconds")},
        indent=1), encoding="utf-8")


def load_round_meta(root, rater):
    p = round_file(root, rater)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def sequence_for(root, rater, rows):
    """The sequence actually in use.

    Prefers the recorded round metadata. If that is absent -- a limited round
    served by a version before the metadata existed -- it is RECONSTRUCTED from
    the saved answers, which carry slot and id for every item completed. Without
    this, a finished 40-item round reports as "40/220 (18%)".
    """
    m = load_round_meta(root, rater)
    if m and m.get("seq"):
        return m["seq"], m.get("limit")
    full = build_sequence(rows, rater)
    saved = load_saved(root, rater)
    if saved:
        slots = sorted(saved)
        contiguous = slots == list(range(len(slots)))
        by_id = {}
        for i, r in enumerate(rows):
            by_id.setdefault(r["id"], i)
        matches_full = all(
            full[s]["slot"] == s and rows[full[s]["idx"]]["id"] == saved[s]["id"]
            for s in slots if s < len(full))
        if contiguous and len(slots) < len(full) and not matches_full:
            seq = [{"slot": s, "idx": by_id.get(saved[s]["id"], 0),
                    "is_repeat": int(saved[s].get("is_repeat") or 0)}
                   for s in slots]
            return seq, len(slots)
    return full, None


def out_file(root, rater):
    return ann_dir(root) / f"annotations_rater{rater}.csv"


def event_file(root, rater):
    return ann_dir(root) / f"events_rater{rater}.jsonl"


FIELDS = ["slot", "id", "is_repeat", "overall_sentiment", "turning_point",
          "arc", "confidence", "notes", "seconds", "wall_seconds", "revisions",
          "scrolled_to_end", "saved_at", "entry_method"]


def load_task(root, rater):
    p = task_file(root, rater)
    if not p.exists():
        return None
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def build_sequence(rows, rater, seed_base=20260829):
    """Insert hidden repeat items. Returns a list of slots."""
    rnd = random.Random(seed_base + rater * 104729)
    n = len(rows)
    k = max(4, int(n * REPEAT_FRACTION))
    # Only items early enough in the sequence can be repeated with a real gap.
    # An earlier version appended late items at the end, producing gaps as small
    # as 20 and weakening the intra-rater check exactly where it is measured.
    eligible = [i for i in range(n) if i + REPEAT_MIN_GAP < n]
    rnd.shuffle(eligible)
    repeats = eligible[:k]
    seq = [{"idx": i, "is_repeat": 0} for i in range(n)]
    for i in repeats:
        lo = seq_index(seq, i) + REPEAT_MIN_GAP
        if lo >= len(seq):
            continue                       # never insert with an undersized gap
        pos = rnd.randint(lo, len(seq))
        seq.insert(pos, {"idx": i, "is_repeat": 1})
    for s, item in enumerate(seq):
        item["slot"] = s
    gaps = {}
    for j, it in enumerate(seq):
        gaps.setdefault(it["idx"], []).append(j)
    bad = [v for v in gaps.values() if len(v) > 1 and max(v) - min(v) < REPEAT_MIN_GAP]
    assert not bad, f"repeat spacing violated: {bad[:3]}"
    return seq


def build_short_sequence(rows, rater, limit, seed_base=20260829):
    """A self-contained sequence of `limit` slots with proportional repeats.

    ~10% of slots are second showings, spaced at least limit//3 apart, so
    intra-rater agreement is measurable inside a short round.
    """
    rnd = random.Random(seed_base + rater * 7717 + limit)
    n_rep = max(2, int(round(limit * 0.10)))
    n_uniq = limit - n_rep
    idx = list(range(len(rows)))
    rnd.shuffle(idx)
    idx = idx[:n_uniq]
    seq = [{"idx": i, "is_repeat": 0} for i in idx]
    gap = max(3, n_uniq // 3)
    eligible = [j for j in range(len(seq)) if j + gap < len(seq)]
    rnd.shuffle(eligible)
    for j in eligible[:n_rep]:
        lo = j + gap
        pos = rnd.randint(lo, len(seq))
        seq.insert(pos, {"idx": seq[j]["idx"], "is_repeat": 1})
    for s_, item in enumerate(seq):
        item["slot"] = s_
    pos = {}
    for j, it in enumerate(seq):
        pos.setdefault(it["idx"], []).append(j)
    bad = [v for v in pos.values() if len(v) > 1 and max(v) - min(v) < gap]
    assert not bad, f"short-sequence repeat spacing violated: {bad[:3]}"
    return seq


def seq_index(seq, idx):
    for j, s in enumerate(seq):
        if s["idx"] == idx:
            return j
    return 0


def load_saved(root, rater):
    p = out_file(root, rater)
    saved = {}
    if p.exists():
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    saved[int(r["slot"])] = r
                except (KeyError, ValueError):
                    continue
    return saved


def write_saved(root, rater, saved):
    p = out_file(root, rater)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for slot in sorted(saved):
            w.writerow(saved[slot])
    os.replace(tmp, p)


def log_event(root, rater, ev):
    ev["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(event_file(root, rater), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


# ===========================================================================
# NOTE: this template is filled by TOKEN REPLACEMENT, never by
# str.format(). v1.1.0 added JavaScript containing single braces to a
# .format() template; every render then raised KeyError and the browser
# hung with no output. Tokens are @@NAME@@ and cannot collide with CSS
# or JS syntax, which removes the entire class of failure.
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>PLEF annotation - rater @@RATER@@</title>
<style>
 :root{--bg:#12141a;--fg:#e8e6e3;--dim:#8b8f9a;--acc:#7aa2f7;--warn:#e0af68;
        --ok:#9ece6a;--bad:#f7768e;--card:#1a1d26;--line:#2a2e3a;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);
       font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);
         padding:10px 20px;display:flex;gap:20px;align-items:center;z-index:10}
 .bar{flex:1;height:6px;background:var(--line);border-radius:3px;overflow:hidden}
 .bar>div{height:100%;background:var(--acc);width:@@PCT@@%}
 main{max-width:900px;margin:0 auto;padding:20px}
 .post{background:var(--card);border:1px solid var(--line);border-radius:8px;
        padding:6px 0;max-height:52vh;overflow-y:auto}
 .s{padding:5px 14px;cursor:pointer;border-left:3px solid transparent;display:flex;gap:10px}
 .s:hover{background:#222634}
 .s.tp{background:#2a2418;border-left-color:var(--warn)}
 .num{color:var(--dim);min-width:34px;text-align:right;user-select:none}
 .panel{margin-top:16px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
 fieldset{border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:0}
 legend{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
 button.opt{background:#222634;color:var(--fg);border:1px solid var(--line);
             border-radius:6px;padding:7px 11px;margin:2px;cursor:pointer;font-size:14px}
 button.opt.on{background:var(--acc);color:#0b0d12;border-color:var(--acc);font-weight:600}
 .row{display:flex;gap:14px;align-items:center;margin-top:16px}
 .go{background:var(--ok);color:#0b0d12;border:0;border-radius:6px;
      padding:11px 22px;font-size:15px;font-weight:700;cursor:pointer}
 .go:disabled{background:#2a2e3a;color:var(--dim);cursor:not-allowed}
 .ghost{background:transparent;color:var(--dim);border:1px solid var(--line);
         border-radius:6px;padding:11px 16px;cursor:pointer}
 input[type=text]{background:#0e1016;color:var(--fg);border:1px solid var(--line);
                   border-radius:6px;padding:9px;width:100%}
 .hint{color:var(--dim);font-size:12px;margin-top:6px}
 kbd{background:#0e1016;border:1px solid var(--line);border-radius:4px;
      padding:1px 6px;font-size:12px}
 .done{text-align:center;padding:60px 20px}
</style></head><body>
<header>
  <b>Rater @@RATER@@</b>
  <div class=bar><div></div></div>
  <span style="color:var(--dim)">@@DONE@@ / @@TOTAL@@</span>
</header>
<main id=app>@@BODY@@</main>
<script>
let TP=@@TP_INIT@@, SENT=@@SENT_INIT@@, ARC=@@ARC_INIT@@, CONF=@@CONF_INIT@@;
let t0=Date.now(), rev=0, scrolled=false;
// ACTIVE time, not wall-clock. An earlier version timed from page load, so a
// tab left open counted idle hours as time-on-item (one item recorded 1,328s).
// The clock now advances only while the tab is visible AND there has been
// interaction within IDLE_MS. Wall time is still recorded, unhidden.
let active=0, lastAct=Date.now(); const IDLE_MS=90000;
['keydown','mousemove','click','scroll'].forEach(e=>
  document.addEventListener(e,()=>{lastAct=Date.now();},{passive:true}));
setInterval(()=>{
  if(document.visibilityState==='visible' && (Date.now()-lastAct)<IDLE_MS) active++;
},1000);
const post=document.querySelector('.post');
if(post){post.addEventListener('scroll',()=>{
  if(post.scrollTop+post.clientHeight>=post.scrollHeight-30) scrolled=true;});
  if(post.scrollHeight<=post.clientHeight) scrolled=true;}
function setTP(n){TP=n;rev++;document.querySelectorAll('.s').forEach(e=>
  e.classList.toggle('tp', parseInt(e.dataset.n)===n));paint();}
function pick(g,v){if(g=='sent')SENT=v;if(g=='arc')ARC=v;if(g=='conf')CONF=v;rev++;paint();}
function paint(){
  document.querySelectorAll('[data-g]').forEach(b=>
    b.classList.toggle('on', (b.dataset.g=='sent'&&b.dataset.v==SENT)||
      (b.dataset.g=='arc'&&b.dataset.v==ARC)||(b.dataset.g=='conf'&&b.dataset.v==CONF)));
  const tpEl=document.getElementById('tpv');
  if(tpEl) tpEl.textContent = (TP===0?'none':('sentence '+TP));
  const ok = SENT && ARC && CONF && TP!==null;
  const g=document.getElementById('go'); if(g) g.disabled=!ok;
}
function save(next){
  fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slot:@@SLOT@@,sentiment:SENT,arc:ARC,confidence:CONF,
      turning_point:TP,notes:document.getElementById('notes').value,
      seconds:active,wall_seconds:Math.round((Date.now()-t0)/1000),revisions:rev,
      scrolled:scrolled?1:0,next:next})})
   .then(r=>r.text()).then(()=>location.href='/?slot='+next);
}
document.addEventListener('keydown',e=>{
  if(e.target.tagName=='INPUT') return;
  const k=e.key.toLowerCase();
  if(e.shiftKey && '12345'.includes(k)){pick('conf',k);e.preventDefault();return;}
  if(k=='1')pick('sent','pos'); else if(k=='2')pick('sent','neu');
  else if(k=='3')pick('sent','neg');
  else if(k=='q')pick('arc','tragic'); else if(k=='w')pick('arc','flat');
  else if(k=='e')pick('arc','redemptive');
  else if(k=='0')setTP(0);
  else if(k=='enter'){const g=document.getElementById('go');if(g&&!g.disabled)g.click();}
  else if(k=='backspace'){e.preventDefault();location.href='/?slot=@@PREV@@';}
});
paint();
</script></body></html>"""


def render_item(root, rater, seq, rows, saved, slot):
    total = len(seq)
    done = len(saved)
    item = seq[slot]
    row = rows[item["idx"]]
    sents = [s for s in row["numbered_text"].split("\n") if s.strip()]
    prev = saved.get(slot, {})
    body = ['<div class=post>']
    for i, s in enumerate(sents, 1):
        txt = re.sub(r"^\[\d+\]\s*", "", s)
        cls = "s tp" if str(prev.get("turning_point", "")) == str(i) else "s"
        body.append(f'<div class="{cls}" data-n="{i}" onclick="setTP({i})">'
                    f'<span class=num>{i}</span><span>{html.escape(txt)}</span></div>')
    body.append("</div>")
    body.append('<div class=panel>')
    body.append('<fieldset><legend>Sentiment of the narrator</legend>' +
                "".join(f'<button class=opt data-g=sent data-v={v} '
                        f'onclick="pick(\'sent\',\'{v}\')">{lab}</button>'
                        for v, lab in zip(SENTIMENTS,
                                          ["1 positive", "2 neutral", "3 negative"])) +
                '</fieldset>')
    body.append('<fieldset><legend>Arc</legend>' +
                "".join(f'<button class=opt data-g=arc data-v={v} '
                        f'onclick="pick(\'arc\',\'{v}\')">{lab}</button>'
                        for v, lab in zip(ARCS,
                                          ["q tragic", "w flat", "e redemptive"])) +
                '<div class=hint>tragic = ends worse than it starts</div></fieldset>')
    body.append('<fieldset><legend>Confidence</legend>' +
                "".join(f'<button class=opt data-g=conf data-v={i} '
                        f'onclick="pick(\'conf\',\'{i}\')">{i}</button>'
                        for i in range(1, 6)) +
                '<div class=hint>Shift+1..5 &nbsp; 1 = guess, 5 = certain</div></fieldset>')
    body.append('</div>')
    body.append('<fieldset style="margin-top:14px"><legend>Turning point</legend>'
                '<div>Currently: <b id=tpv>-</b></div>'
                '<div class=hint>Click the sentence where the emotional direction '
                'changes most clearly. Press <kbd>0</kbd> if there is none. '
                'Mark exactly one, or none.</div></fieldset>')
    body.append(f'<div class=row><input id=notes type=text placeholder="notes (optional)" '
                f'value="{html.escape(prev.get("notes",""))}">'
                f'<button class=go id=go onclick="save({min(slot+1,total-1)})">'
                f'Save &amp; next &nbsp;<kbd>Enter</kbd></button></div>')
    body.append(f'<div class=hint>Item {slot+1} of {total} &nbsp;|&nbsp; '
                f'{len(sents)} sentences &nbsp;|&nbsp; '
                f'progress saves automatically, you can stop any time</div>')
    subs = {
        "@@RATER@@": str(rater), "@@TOTAL@@": str(total), "@@DONE@@": str(done),
        "@@PCT@@": str(round(100 * done / max(1, total), 1)),
        "@@BODY@@": "".join(body), "@@SLOT@@": str(slot),
        "@@PREV@@": str(max(0, slot - 1)),
        "@@TP_INIT@@": str(prev.get("turning_point") or "null"),
        "@@SENT_INIT@@": json.dumps(prev.get("overall_sentiment") or None),
        "@@ARC_INIT@@": json.dumps(prev.get("arc") or None),
        "@@CONF_INIT@@": json.dumps(prev.get("confidence") or None),
    }
    out = PAGE
    for k, v in subs.items():
        out = out.replace(k, v)
    leftover = re.findall(r"@@[A-Z_]+@@", out)
    if leftover:
        raise RuntimeError(f"unfilled template tokens: {sorted(set(leftover))}")
    return out


DONE_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<style>body{background:#12141a;color:#e8e6e3;font:16px/1.7 sans-serif;
text-align:center;padding:80px} b{color:#9ece6a}</style></head><body>
<h2>Rater @@RATER@@: all @@N@@ items complete.</h2>
<p>Answers written to <b>annotations_rater@@RATER@@.csv</b></p>
<p>Press Ctrl+C in the terminal to stop the server.</p>
<p style="color:#8b8f9a">Run <code>python annotate.py --root ... --mode status</code>
to see the quality-control readout.</p></body></html>"""


def serve(root, rater, port, limit=0):
    rows = load_task(root, rater)
    if rows is None:
        print(f"FATAL: {task_file(root, rater)} not found. Run script 03 first.")
        return 2
    seq = build_sequence(rows, rater)
    if limit and limit < len(seq):
        # A short supervised round needs its OWN sequence. Truncating the full
        # one gives zero repeats, because repeats are inserted at least 40 slots
        # after their first showing and a 40-slot prefix contains none -- which
        # silently removes intra-rater reliability, the only QC a single
        # annotator can provide.
        seq = build_short_sequence(rows, rater, limit)
        save_round_meta(root, rater, seq, limit)
        reps = sum(x["is_repeat"] for x in seq)
        print(f"  LIMITED ROUND: {len(seq)} slots = {len(seq) - reps} posts "
              f"+ {reps} hidden repeats")
    saved = load_saved(root, rater)
    reps = sum(x["is_repeat"] for x in seq)
    print(f"  rater {rater}: {len(seq)} slots = {len(seq)-reps} posts + {reps} "
          f"hidden repeats, {len(saved)} already done")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            try:
                self._get()
            except Exception:
                tb = traceback.format_exc()
                print("\n  RENDER ERROR:\n" + tb)
                b = ("<pre style='color:#f7768e;background:#12141a;padding:20px'>"
                     + html.escape(tb) + "</pre>").encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        def _get(self):
            if self.path.startswith("/favicon"):
                self.send_response(204); self.end_headers(); return
            q = parse_qs(urlparse(self.path).query)
            nxt = next((s["slot"] for s in seq if s["slot"] not in saved), None)
            slot = int(q.get("slot", [nxt if nxt is not None else 0])[0])
            slot = max(0, min(slot, len(seq) - 1))
            if len(saved) >= len(seq):
                page = (DONE_PAGE.replace("@@RATER@@", str(rater))
                        .replace("@@N@@", str(len(seq))))
            else:
                page = render_item(root, rater, seq, rows, saved, slot)
            b = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            slot = int(d["slot"])
            item = seq[slot]
            saved[slot] = {
                "slot": slot, "id": rows[item["idx"]]["id"],
                "is_repeat": item["is_repeat"],
                "overall_sentiment": d.get("sentiment") or "",
                "turning_point": d.get("turning_point"),
                "arc": d.get("arc") or "", "confidence": d.get("confidence") or "",
                "notes": (d.get("notes") or "").replace("\n", " "),
                "seconds": d.get("seconds", 0),
                "wall_seconds": d.get("wall_seconds", 0),
                "revisions": d.get("revisions", 0),
                "scrolled_to_end": d.get("scrolled", 0),
                "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "entry_method": "web"}
            write_saved(root, rater, saved)
            log_event(root, rater, {"slot": slot, "id": saved[slot]["id"],
                                    "seconds": saved[slot]["seconds"],
                                    "wall_seconds": saved[slot]["wall_seconds"],
                                    "revisions": saved[slot]["revisions"]})
            done = len(saved)
            print(f"\r  saved {done}/{len(seq)}  "
                  f"({100*done/len(seq):.0f}%)   ", end="", flush=True)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    url = f"http://127.0.0.1:{port}"
    print(f"  open {url}")
    print("  Ctrl+C to stop. Progress saves after every item.")
    try:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    srv = HTTPServer(("127.0.0.1", port), H)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped. Resume with the same command.")
    return 0


# ===========================================================================
def krippendorff_nominal(units):
    """units: list of lists of labels (one list per item, one label per rater)."""
    pairs = []
    for u in units:
        vals = [v for v in u if v]
        if len(vals) < 2:
            continue
        for i in range(len(vals)):
            for j in range(len(vals)):
                if i != j:
                    pairs.append((vals[i], vals[j]))
    if not pairs:
        return None
    n = len(pairs)
    do = sum(1 for a, b in pairs if a != b) / n
    cnt = Counter(v for p in pairs for v in p)
    tot = sum(cnt.values())
    de = 1 - sum((c / tot) ** 2 for c in cnt.values())
    return 1 - do / de if de > 0 else None


def mode_status(root, raters):
    head("ANNOTATION STATUS AND QUALITY CONTROL")
    any_found = False
    for r in raters:
        rows = load_task(root, r)
        if rows is None:
            continue
        seq, lim = sequence_for(root, r, rows)
        saved = load_saved(root, r)
        if not saved:
            print(f"\n  rater {r}: task present, nothing annotated yet "
                  f"({len(seq)} slots{'  [LIMITED]' if lim else ''})")
            continue
        any_found = True
        # Offline rows carry no timing by construction, so including them in the
        # rushed/never-scrolled flags would drown any real signal in noise.
        web = [v for v in saved.values()
               if (v.get("entry_method") or "web") != "offline"]
        offline = [v for v in saved.values()
                   if (v.get("entry_method") or "") == "offline"]
        secs = [int(v.get("seconds") or 0) for v in web]
        fast = [v for v in web if int(v.get("seconds") or 0) < FAST_ITEM_SECONDS]
        noscroll = [v for v in web if str(v.get("scrolled_to_end")) == "0"]
        conf = Counter(v.get("confidence") for v in saved.values())
        sent = Counter(v.get("overall_sentiment") for v in saved.values())
        arc = Counter(v.get("arc") for v in saved.values())
        tp_none = sum(1 for v in saved.values() if str(v.get("turning_point")) == "0")
        sub(f"rater {r}")
        tag = f"   [LIMITED ROUND of {lim}]" if lim else ""
        print(f"  progress        : {len(saved)}/{len(seq)} "
              f"({100*len(saved)/len(seq):.0f}%){tag}")
        if offline:
            print(f"  entry method    : {len(web)} web-tool, {len(offline)} offline")
            print(f"  {'':<16}  offline rows have no timing or engagement data;")
            print(f"  {'':<16}  the paper must state this split")
        wall = [int(v.get("wall_seconds") or 0) for v in web]
        if secs:
            print(f"  ACTIVE s/item   : median {statistics.median(secs):.0f}  "
                  f"mean {statistics.mean(secs):.0f}  "
                  f"total {sum(secs)/3600:.2f} h")
            if any(wall):
                print(f"  wall s/item     : median {statistics.median(wall):.0f}  "
                      f"(includes idle tab time; reported for transparency only)")
            rem = len(seq) - len(saved)
            if rem == 0:
                print("  remaining       : none -- round complete")
            if rem > 0 and statistics.median(secs) > 0:
                eta = rem * statistics.median(secs) / 3600
                print(f"  remaining       : {rem} items, approx {eta:.1f} h "
                      f"at the current median")
        print(f"  sentiment       : {dict(sent)}")
        print(f"  arc             : {dict(arc)}")
        print(f"  confidence      : {dict(sorted(conf.items()))}")
        print(f"  no turning point: {tp_none} ({100*tp_none/len(saved):.0f}%)")
        if fast:
            print(f"  ** {len(fast)} of {len(web)} web-tool items answered in under "
                  f"{FAST_ITEM_SECONDS}s -- possibly rushed")
        if noscroll:
            print(f"  ** {len(noscroll)} of {len(web)} web-tool items where the post "
                  f"was never scrolled to the end")
        # intra-rater: repeats
        byid = defaultdict(list)
        for v in saved.values():
            byid[v["id"]].append(v)
        rep = {k: v for k, v in byid.items() if len(v) > 1}
        if rep:
            s_ag = sum(1 for v in rep.values()
                       if v[0]["overall_sentiment"] == v[1]["overall_sentiment"])
            a_ag = sum(1 for v in rep.values() if v[0]["arc"] == v[1]["arc"])
            t_ex = sum(1 for v in rep.values()
                       if str(v[0]["turning_point"]) == str(v[1]["turning_point"]))
            t_w1 = 0
            for v in rep.values():
                try:
                    if abs(int(v[0]["turning_point"]) - int(v[1]["turning_point"])) <= 1:
                        t_w1 += 1
                except (ValueError, TypeError):
                    pass
            k = len(rep)
            print(f"  INTRA-RATER (hidden repeats, n={k}):")
            print(f"    sentiment agreement with self : {100*s_ag/k:.0f}%")
            print(f"    arc agreement with self       : {100*a_ag/k:.0f}%")
            print(f"    turning point exact           : {100*t_ex/k:.0f}%")
            print(f"    turning point within 1        : {100*t_w1/k:.0f}%")
            if s_ag / k < 0.7:
                print("    ** below 70%: this rater disagrees with their own earlier")
                print("       judgement too often for the labels to carry weight.")
    if not any_found:
        print("\n  No annotations found yet.")
        print(f"  Start with: python annotate.py --root <root> --rater 1")
    return 0


def mode_merge(root, raters, force_gold=False):
    head("MERGE RATERS, RELIABILITY, GOLD FILE")
    per = {}
    for r in raters:
        saved = load_saved(root, r)
        if not saved:
            continue
        first = {}
        for slot in sorted(saved):
            v = saved[slot]
            first.setdefault(v["id"], v)      # first showing only, repeats excluded
        per[r] = first
    if not per:
        print("  no annotations found"); return 2
    print(f"  raters with data: {sorted(per)}")
    ids = set.intersection(*[set(v) for v in per.values()])
    print(f"  items annotated by all: {len(ids):,}")
    if not ids:
        return 2
    sent_units = [[per[r][i]["overall_sentiment"] for r in per] for i in ids]
    arc_units = [[per[r][i]["arc"] for r in per] for i in ids]
    a_s = krippendorff_nominal(sent_units)
    a_a = krippendorff_nominal(arc_units)
    sub("INTER-RATER RELIABILITY")
    if len(per) < 2:
        print("  Only one rater. No inter-rater reliability can be computed.")
        print("  The paper MUST say 'single annotator' and state the limitation.")
    else:
        print(f"  Krippendorff alpha, sentiment : "
              f"{a_s:.3f}" if a_s is not None else "  sentiment alpha: n/a")
        print(f"  Krippendorff alpha, arc       : "
              f"{a_a:.3f}" if a_a is not None else "  arc alpha: n/a")
        print("  Convention: >=0.80 good, 0.67-0.80 tentative, <0.67 not usable.")
        ex = w1 = n = 0
        for i in ids:
            tps = []
            for r in per:
                try:
                    tps.append(int(per[r][i]["turning_point"]))
                except (ValueError, TypeError):
                    pass
            if len(tps) < 2:
                continue
            n += 1
            if len(set(tps)) == 1:
                ex += 1
            if max(tps) - min(tps) <= 1:
                w1 += 1
        if n:
            print(f"  turning point, all raters exact   : {100*ex/n:.0f}%  (n={n})")
            print(f"  turning point, all within 1       : {100*w1/n:.0f}%")
    # A gold file built from unreliable annotation is worse than none: script 06
    # would test H1 and H5 against it and report a number that means nothing.
    # The merge now REFUSES unless the reliability clears the stated convention.
    ALPHA_MIN = 0.67
    worst = min([x for x in (a_s, a_a) if x is not None] or [None])
    if worst is not None and worst < ALPHA_MIN and not force_gold:
        sub("GOLD FILE -- REFUSED")
        print(f"  Krippendorff alpha is {worst:.3f}, below the {ALPHA_MIN} threshold")
        print("  this tool prints as the minimum for usable data.")
        print()
        print("  No gold file is written. Testing LEWI or NAVA against labels this")
        print("  unreliable produces a number that cannot be interpreted, and a")
        print("  reviewer who computes the reliability will find it immediately.")
        print()
        print("  H1 and H5 remain NOT TESTED. Report the alpha values, the")
        print("  intra-rater agreement, and the fact that a reliable criterion")
        print("  could not be established. That is a finding about the construct,")
        print("  not a gap in the study.")
        print()
        print("  If you have a specific reason to override this, pass --force-gold")
        print("  and the file is stamped alpha_below_threshold=1 in every row so")
        print("  the limitation travels with the data.")
        return 0
    sub("GOLD FILE (majority vote; ties dropped)")
    gold, ties = [], 0
    for i in sorted(ids):
        s = Counter(per[r][i]["overall_sentiment"] for r in per)
        a = Counter(per[r][i]["arc"] for r in per)
        tps = []
        for r in per:
            try:
                tps.append(int(per[r][i]["turning_point"]))
            except (ValueError, TypeError):
                pass
        s_top = s.most_common()
        if len(s_top) > 1 and s_top[0][1] == s_top[1][1]:
            ties += 1
            continue
        gold.append({"alpha_below_threshold": int(worst is not None
                                                  and worst < ALPHA_MIN),
                     "id": i, "gold_sentiment": s_top[0][0],
                     "gold_arc": a.most_common(1)[0][0],
                     "gold_turning_point": int(statistics.median(tps)) if tps else "",
                     "n_raters": len(per),
                     "tp_spread": (max(tps) - min(tps)) if len(tps) > 1 else 0})
    p = ann_dir(root) / "gold_dev200.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "gold_sentiment", "gold_arc",
                                          "gold_turning_point", "n_raters",
                                          "tp_spread", "alpha_below_threshold"])
        w.writeheader()
        w.writerows(gold)
    print(f"  {len(gold):,} gold items written -> {p.name}")
    if ties:
        print(f"  {ties} items dropped as unresolvable ties")
    print()
    print("  This file is the human criterion for H1 (turning point) and")
    print("  H5 (arc classification). Script 06 evaluates LEWI and NAVA against it.")
    return 0


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="PLEF V2 annotation tool.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--rater", type=int, default=1)
    ap.add_argument("--mode", choices=["serve", "status", "merge"], default="serve")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--raters", default="1,2,3")
    ap.add_argument("--limit", type=int, default=0,
                    help="serve only the first N slots -- for a short "
                         "supervised single-annotator round")
    ap.add_argument("--force-gold", action="store_true",
                    help="write the gold file even when reliability is below "
                         "threshold; every row is stamped with the limitation")
    args = ap.parse_args()
    root = Path(args.root)
    if not ann_dir(root).exists():
        print(f"FATAL: {ann_dir(root)} not found. Run script 03 first.")
        return 2
    raters = [int(x) for x in args.raters.split(",") if x.strip().isdigit()]
    head(f"PLEF V2 ANNOTATION TOOL v{VERSION}  [{args.mode}]")
    if args.mode == "status":
        return mode_status(root, raters)
    if args.mode == "merge":
        return mode_merge(root, raters, args.force_gold)
    return serve(root, args.rater, args.port, args.limit)


if __name__ == "__main__":
    sys.exit(main())
