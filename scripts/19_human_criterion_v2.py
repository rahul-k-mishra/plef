#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 19 : HUMAN CRITERION, VERSION 2   (19_human_criterion_v2.py, v1.1.0)
===============================================================================

CHANGES IN v1.1.0
-----------------
  The pooled key gap_all_rounds_under41 collected every key ending in
  "_presented", which included r4_items_presented (the round-4 item count,
  40) and counted it as one more repeat gap: 20 of 31 instead of 19 of 30.
  It now collects only the per-rater gap lists, keys of the form
  gap_round<r>_rater<n>_presented. No other key or value changes.

WHAT WE CHECK (plain language)
------------------------------
Every number the manuscript reports about the human annotation -- Sections
2.6, 3.5 and 3.6, Tables 8, 9 and 12 -- recomputed from the annotation records
with nothing typed in by hand. It replaces the human-criterion part of
06_statistics.py (lines 1548-1677), 10_null_analysis.py stage I and
11_response_space.py, and productionises the round-2 audit helpers
round2_audit/r2a_indexing.py and r2c_annotation.py.

Three alignments of the watershed index against the human turning point:

  impl   as implemented in 06_statistics.py line 1593: the stored human number
         compared with the stored lewi_idx, no conversion.
  plus1  lewi_idx + 1 (lewi_idx is a zero-based Python index, plef_core.py
         line 162), human number as stored. This is Reviewer 3's correction.
  full   lewi_idx + 1 against the human's SENTENCE. Round 4 was entered in the
         web tool, which numbers displayed lines, not sentences: it splits
         numbered_text on newlines and renumbers (annotate.py lines 409-415).
         A sentence containing a paragraph break becomes several lines. The
         line number is mapped back to the sentence that contains it.

For each alignment: exact / within-one / within-two agreement with Wilson 95%
intervals; the support-aware chance model (metric uniform on sentences
2..N-1, independent of the human), with exact Poisson-binomial P(X >= observed)
and P(X <= observed). The homogeneous Binomial(n, mean p) values that the
submitted paper reported are printed as well, labelled as such.

Round 3 (three raters, offline sheets): raw, existence and location agreement;
location chance under 1/(N-2) (published), 1/N (the support the raters were
permitted: the importer accepts 0..N, offline_annotation.py line 542) and each
rater's own empirical distribution of relative positions; Krippendorff's alpha;
three-way unanimity and majority. Rounds 3 and 4: intra-rater repeat agreement
for every rater, and repeat spacing AS PRESENTED to each rater (round 3 from the
row order of the returned sheet, round 4 from the web slot order) beside the
spacing in the full 220-slot sequence. Rounds 1 and 2: the integrity patterns
that rejected them. Every round: entry method and which web-tool
instrumentation fields are populated.

Also: arc agreement, Cohen's kappa, total variation distance; the constant-
signal tie rule of compute_lewi against Equation (1); Table 8 accounting.

WHAT THE RESULT MEANS
---------------------
Every value is written with a key to results/tables/human_criterion_v2.csv
(key, value, k, n, wilson_lo, wilson_hi, note). The manuscript placeholders
<<19:human_criterion_v2:KEY>> refer to those keys. The per-post table for the
19 round-4 comparison posts is results/tables/annotation_audit_v2.csv.
If a value here differs from the submitted paper, this script is the source.

Standard library only; worker pool for the per-post recomputation and the
pairwise comparisons; deterministic. Imports the released core from src/ and
annotate.py (for its sequence builder) from the folder above --root, without
writing bytecode. Writes only the two tables and
results/forensics/console_log_19.txt.

USAGE
-----
  python 19_human_criterion_v2.py --root <path to PLEF_V2>   [--workers N]
"""
import argparse
import collections
import csv
import datetime
import hashlib
import importlib.util
import io
import itertools
import math
import re
import statistics
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

sys.dont_write_bytecode = True
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

VERSION = "1.1.0"
LEXICON_SHA256 = "18294c6727f66003df67c0c01ab9e66073dca34d3c60541878c35ba84825165c"
ARC = {"tragic": "tragic", "mildly_declining": "tragic", "flat": "flat",
       "mildly_improving": "redemptive", "redemptive": "redemptive"}  # 06 line 1630
CONV = ("impl", "plus1", "full")


# --------------------------------------------------------------------------
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
        self.stdout.flush()
        self.f.flush()

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


def rule(ch="-", w=94):
    print(ch * w)


def head(t):
    print()
    rule("=")
    print(t)
    rule("=")


def sub(t):
    print()
    print(t)
    rule()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_csv(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        return list(csv.DictReader(io.StringIO(txt, newline=""))), enc
    raise RuntimeError(f"cannot decode {p}")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_core(src):
    if sha256(Path(src) / "plef_lexicons.json") != LEXICON_SHA256:
        raise RuntimeError("lexicon hash mismatch")
    return load_module(Path(src) / "plef_core.py", "plef_core_released")


# ------------------------------------------------------------- statistics
def wilson(k, n, z=1.96):
    """Identical in form to 06_statistics._prop_ci."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def poisson_binomial(ps):
    dist = [1.0]
    for p in ps:
        new = [0.0] * (len(dist) + 1)
        for k, v in enumerate(dist):
            new[k] += v * (1 - p)
            new[k + 1] += v * p
        dist = new
    return dist


def kappa_pairs(a, b):
    """06_statistics.kappa_pairs, copied."""
    n = len(a)
    if not n:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def krippendorff_nominal(units):
    """annotate.krippendorff_nominal, copied."""
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
    cnt = collections.Counter(v for p in pairs for v in p)
    tot = sum(cnt.values())
    de = 1 - sum((c / tot) ** 2 for c in cnt.values())
    return 1 - do / de if de > 0 else None


def chance_near(h, n, k):
    """P(|metric - h| <= k) for a metric uniform on sentences 2..N-1."""
    adm = set(range(2, n))
    return len(set(range(h - k, h + k + 1)) & adm) / max(1, len(adm))


# ------------------------------------------------------------------ output
OUT = []


def put(key, value=None, k=None, n=None, note=""):
    lo = hi = None
    if k is not None and n:
        value = k / n
        lo, hi = wilson(k, n)

    def s(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.6f}"
        return str(v)
    OUT.append({"key": key, "value": s(value), "k": s(k), "n": s(n),
                "wilson_lo": s(lo), "wilson_hi": s(hi), "note": note})
    return value


def kn(k, n):
    lo, hi = wilson(k, n)
    return f"{k:>3}/{n:<3} {100*k/n:5.1f}%  [{100*lo:5.1f}%, {100*hi:5.1f}%]"


# ----------------------------------------------------------------- workers
CORE = None


def _init(src):
    global CORE
    sys.dont_write_bytecode = True
    CORE = load_core(src)


def _post(args):
    pid, text, numbered = args
    s = CORE.sentences(text)
    rebuilt = "\n".join(f"[{i + 1}] {x}" for i, x in enumerate(s))
    line2sent = []
    for k, x in enumerate(s, 1):
        for ln in f"[{k}] {x}".split("\n"):
            if ln.strip():
                line2sent.append(k)
    disp = [x for x in numbered.split("\n") if x.strip()]          # annotate.py 409
    lewi = CORE.compute_lewi(CORE.sentence_scores(text))[0]
    return {"id": pid, "n": len(s), "rebuilt_ok": rebuilt == numbered,
            "n_disp": len(disp), "map_ok": len(line2sent) == len(disp),
            "line2sent": line2sent, "lewi": lewi}


def tp(r):
    try:
        return int(float(r["turning_point"]))
    except (TypeError, ValueError, KeyError):
        return None


def first_showings(rows):
    d = {}
    for r in sorted(rows, key=lambda x: int(x["slot"])):
        d.setdefault(r["id"], r)
    return d


def emp_dist(us, n):
    p = [0.0] * (n + 1)
    for u in us:
        p[min(n, int(u * n) + 1)] += 1.0 / len(us)
    return p


def _pair(args):
    a, b, A, B, N, U = args
    ids = sorted(i for i in set(A) & set(B) if i in N
                 and tp(A[i]) is not None and tp(B[i]) is not None)
    ea = {i: tp(A[i]) > 0 for i in ids}
    eb = {i: tp(B[i]) > 0 for i in ids}
    pa = sum(ea.values()) / len(ids)
    pb = sum(eb.values()) / len(ids)
    both = [i for i in ids if ea[i] and eb[i]]
    emp_loo, emp_all = [], []
    for i in both:
        for store, excl in ((emp_loo, True), (emp_all, False)):
            ua = [u for j, u in U[a] if not (excl and j == i)]
            ub = [u for j, u in U[b] if not (excl and j == i)]
            x, y = emp_dist(ua, N[i]), emp_dist(ub, N[i])
            store.append(sum(p * q for p, q in zip(x, y)))
    return {"pair": f"{a}v{b}", "n": len(ids),
            "raw": sum(1 for i in ids if tp(A[i]) == tp(B[i])),
            "exist": sum(1 for i in ids if ea[i] == eb[i]),
            "exist_chance": pa * pb + (1 - pa) * (1 - pb),
            "nl": len(both), "loc": sum(1 for i in both if tp(A[i]) == tp(B[i])),
            "ch_n2": statistics.mean(1.0 / max(1, N[i] - 2) for i in both),
            "ch_n": statistics.mean(1.0 / N[i] for i in both),
            "ch_emp_loo": statistics.mean(emp_loo), "ch_emp_all": statistics.mean(emp_all),
            "bnd": sum(1 for i in both for t in (tp(A[i]), tp(B[i])) if t in (1, N[i]))}


def gaps(order):
    pos = collections.defaultdict(list)
    for k, i in enumerate(order):
        pos[i].append(k)
    return sorted(v[1] - v[0] for v in pos.values() if len(v) > 1)


def row_key(rater, slot):
    """offline_annotation.row_key, copied (lines 96-99)."""
    return hashlib.sha1(f"plefv2|{rater}|{slot}".encode()).hexdigest()[:10]


# =========================================================================
def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 19 -- human criterion v2.")
    ap.add_argument("--root", required=True, help="path to PLEF_V2")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count()))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    src = root / "src"
    ad = root / "data" / "interim" / "annotations"
    canon = root / "results" / "canonical"
    tables = root / "results" / "tables"

    tee = Tee(root / "results" / "forensics" / "console_log_19.txt")
    sys.stdout = tee
    try:
        head(f"PLEF V2 -- SCRIPT 19 : HUMAN CRITERION, VERSION 2   v{VERSION}")
        print(f"  root      : {root}")
        print(f"  started   : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  python    : {sys.version.split()[0]}   workers {a.workers}")
        print(f"  core      : sha256 {sha256(src / 'plef_core.py')}")
        core = load_core(src)
        annotate = load_module(root.parent / "annotate.py", "annotate_tool")
        print(f"  annotate  : {root.parent / 'annotate.py'}  v{annotate.VERSION}  "
              f"sha256 {sha256(root.parent / 'annotate.py')[:16]}...")

        sc, _ = read_csv(canon / "scored_dev_relationship.csv")
        S = {r["id"]: r for r in sc}
        N = {r["id"]: int(r["n_sents"]) for r in sc}
        dev, _ = read_csv(root / "data" / "interim" / "dev_split_relationship.csv")
        task, _ = read_csv(ad / "annotation_task_rater1.csv")
        T = {r["id"]: r for r in task}

        # ============================================================ 0 rounds
        sub("0  ROUNDS: FILES, ENTRY METHOD, INSTRUMENTATION")
        print("  The submitted text (Sections 2.6, 2.7) describes active time, revision")
        print("  counts and scroll-to-end as recorded for each item. Those fields exist")
        print("  only where entry_method is 'web'. Offline rows carry zeros.")
        files = [(1, r, ad / "round1_compromised" / f"rater{r}_OFFLINE.csv") for r in (1, 2, 3)] + \
                [(2, r, ad / "round1_compromised" / f"annotations_rater{r}.csv") for r in (1, 2, 3)] + \
                [(3, r, ad / "round3_low_reliability" / f"annotations_rater{r}.csv") for r in (1, 2, 3)] + \
                [(4, 1, ad / "annotations_rater1.csv")]
        print(f"  {'round':<6}{'rater':<6}{'rows':>6}  {'entry method':<30}"
              f"{'secs>0':>8}{'wall>0':>8}{'rev>0':>7}{'scroll':>8}  file")
        for rnd, r, p in files:
            rows, _ = read_csv(p)
            if "entry_method" in (rows[0] if rows else {}):
                em = dict(collections.Counter(x["entry_method"] for x in rows))
                method = ",".join(f"{k}:{v}" for k, v in sorted(em.items()))
            else:
                method = "offline sheet (returned spreadsheet)"
            def cnt(fld, test):
                if not rows or fld not in rows[0]:
                    return None
                return sum(1 for x in rows if test(x.get(fld) or "0"))
            pos = lambda v: float(v) > 0
            secs, wall = cnt("seconds", pos), cnt("wall_seconds", pos)
            rev, scr = cnt("revisions", pos), cnt("scrolled_to_end", pos)
            put(f"round{rnd}_rater{r}_rows", len(rows))
            put(f"round{rnd}_rater{r}_entry_method", method)
            for nm, v in (("seconds_nonzero", secs), ("wall_seconds_nonzero", wall),
                          ("revisions_nonzero", rev), ("scrolled_nonzero", scr)):
                put(f"round{rnd}_rater{r}_{nm}", "not recorded" if v is None else v)
            sh = lambda v: "-" if v is None else str(v)
            print(f"  {rnd:<6}{r:<6}{len(rows):>6}  {method:<30}{sh(secs):>8}{sh(wall):>8}"
                  f"{sh(rev):>7}{sh(scr):>8}  {p.relative_to(root)}")

        # ============================================================ 1 index
        sub("1  SPLITTERS, DISPLAY NUMBERING, WATERSHED INDEX BASE")
        jobs = [(r["id"], r["text"], T[r["id"]]["numbered_text"]) for r in dev]
        with Pool(a.workers, initializer=_init, initargs=(str(src),)) as pool:
            res = pool.map(_post, jobs, chunksize=8)
        R = {x["id"]: x for x in res}
        put("dev_posts", len(res))
        put("dev_numbered_text_matches_core_split", sum(x["rebuilt_ok"] for x in res))
        put("dev_display_lines_differ_from_sentences", sum(1 for x in res if x["n_disp"] != x["n"]))
        put("dev_texts_with_newline", sum(1 for r in dev if "\n" in r["text"]))
        put("dev_lewi_stored_equals_recomputed",
            sum(1 for x in res if (S[x["id"]]["lewi_idx"] or "") == ("" if x["lewi"] is None else str(x["lewi"]))))
        for k in ("dev_posts", "dev_numbered_text_matches_core_split",
                  "dev_display_lines_differ_from_sentences", "dev_texts_with_newline",
                  "dev_lewi_stored_equals_recomputed"):
            print(f"  {k:<46}: {[o['value'] for o in OUT if o['key'] == k][0]}")
        print(f"  display map verified on {sum(x['map_ok'] for x in res)}/{len(res)} posts")

        print()
        print("  Tie rule. Equation (1) text (ms lines 81-84): a constant smoothed signal")
        print("  gives i* = floor(N/2) + 1. compute_lewi starts best_v at -1.0")
        print("  (plef_core.py line 161), so the first interior index always wins.")
        for n in range(4, 13):
            got = core.compute_lewi([0.0] * n)[0]
            put(f"tie_rule_N{n}_implemented_onebased", got + 1)
            put(f"tie_rule_N{n}_equation_onebased", n // 2 + 1)
            print(f"    N={n:<3} implemented sentence {got + 1:<3} Equation (1) text {n // 2 + 1}")
        for name in ("relationship", "dev_relationship"):
            rows, _ = read_csv(canon / f"scored_{name}.csv")
            const = 0
            elig = 0
            for r in rows:
                v = [x for x in (r.get("sent_scores") or "").split(";") if x != ""]
                if len(v) >= 4:
                    elig += 1
                    if len(set(v)) == 1:
                        const += 1
            put(f"tie_rule_constant_signal_posts_{name}", const, note=f"of {elig} with >= 4 sentences")
            print(f"    {name}: {const} of {elig} posts with >= 4 sentences have a constant signal")

        # ============================================================ 2 round 4
        sub("2  ROUND 4: ACCOUNTING (TABLE 8)")
        r4, _ = read_csv(ad / "annotations_rater1.csv")
        gold, _ = read_csv(ad / "gold_dev200.csv")
        f4 = first_showings(r4)
        put("r4_items_presented", len(r4))
        put("r4_repeat_showings", sum(1 for x in r4 if x["is_repeat"] == "1"))
        put("r4_unique_posts", len(f4))
        put("r4_gold_equals_first_showing",
            sum(1 for g in gold if g["id"] in f4 and tp(f4[g["id"]]) == int(float(g["gold_turning_point"]))))
        put("r4_matched_scored", sum(1 for i in f4 if i in S))
        defined = [i for i in f4 if i in S and (S[i]["lewi_idx"] or "").strip()]
        put("r4_lewi_defined", len(defined))
        put("r4_lewi_undefined", sum(1 for i in f4 if i in S) - len(defined))
        none_ = [i for i in defined if tp(f4[i]) == 0]
        put("r4_no_tp", len(none_))
        put("r4_no_tp_prop", k=len(none_), n=len(defined))
        put("r4_tp_marked", len(defined) - len(none_))
        secs_all = [float(x["seconds"]) for x in r4]
        secs_first = [float(f4[i]["seconds"]) for i in f4]
        put("r4_median_active_seconds_all_items", statistics.median(secs_all))
        put("r4_median_active_seconds_first_showings", statistics.median(secs_first))
        put("r4_scrolled_to_end", k=sum(1 for x in r4 if x["scrolled_to_end"] == "1"), n=len(r4))
        for o in OUT:
            if o["key"].startswith("r4_"):
                print(f"  {o['key']:<44}: {o['value']}" + (f"  ({o['k']}/{o['n']})" if o["k"] else ""))

        # ============================================================ 3 per post
        sub("3  ROUND 4: THE COMPARISON POSTS UNDER THREE ALIGNMENTS (TABLE 9)")
        rows = []
        for i in sorted(defined):
            h = tp(f4[i])
            if h <= 0:
                continue
            l2s = R[i]["line2sent"]
            if h > len(l2s):
                print(f"  STOP: {i} human line {h} exceeds the {len(l2s)} displayed lines")
                return 3
            hs = l2s[h - 1]
            li = int(S[i]["lewi_idx"])
            n = N[i]
            rows.append({"id": i, "N": n, "N_disp": R[i]["n_disp"], "h_disp": h,
                         "h_sent": hs, "lewi_zero_based": li, "lewi_one_based": li + 1,
                         "boundary_disp": int(h in (1, n)), "boundary_sent": int(hs in (1, n))})
        pairs = {"impl": [(x["h_disp"], x["lewi_zero_based"]) for x in rows],
                 "plus1": [(x["h_disp"], x["lewi_one_based"]) for x in rows],
                 "full": [(x["h_sent"], x["lewi_one_based"]) for x in rows]}
        human = {"impl": [x["h_disp"] for x in rows], "plus1": [x["h_disp"] for x in rows],
                 "full": [x["h_sent"] for x in rows]}

        def mtype(h, m):
            d = abs(h - m)
            return "exact" if d == 0 else ("within1" if d == 1 else ("within2" if d == 2 else f"off{d}"))
        for c in CONV:
            for x, (h, m) in zip(rows, pairs[c]):
                x[f"match_{c}"] = mtype(h, m)
        for c in ("plus1", "full"):
            for x, h in zip(rows, human[c]):
                x[f"p_exact_{c}"] = f"{chance_near(h, x['N'], 0):.6f}" if 2 <= h <= x["N"] - 1 else "0.000000"
                x[f"p_within1_{c}"] = f"{chance_near(h, x['N'], 1):.6f}"
        n19 = len(rows)
        Ns = [x["N"] for x in rows]
        put("cmp_n", n19)
        put("cmp_N_min", min(Ns))
        put("cmp_N_max", max(Ns))
        put("cmp_N_median", statistics.median(Ns))
        put("cmp_display_differs_from_sentence", sum(1 for x in rows if x["h_disp"] != x["h_sent"]))
        put("cmp_boundary_disp", sum(x["boundary_disp"] for x in rows))
        put("cmp_boundary_sent", sum(x["boundary_sent"] for x in rows))
        print(f"  {'id':<29}{'N':>4}{'Ndisp':>6}{'h_disp':>7}{'h_sent':>7}{'lewi0':>6}{'lewi1':>6}"
              f"{'bnd':>4}  {'impl':<9}{'plus1':<9}{'full':<9}")
        rule()
        for x in rows:
            print(f"  {x['id']:<29}{x['N']:>4}{x['N_disp']:>6}{x['h_disp']:>7}{x['h_sent']:>7}"
                  f"{x['lewi_zero_based']:>6}{x['lewi_one_based']:>6}{x['boundary_sent']:>4}  "
                  f"{x['match_impl']:<9}{x['match_plus1']:<9}{x['match_full']:<9}")
        print(f"  N range {min(Ns)}-{max(Ns)}, median {statistics.median(Ns)}; displayed line != "
              f"sentence on {sum(1 for x in rows if x['h_disp'] != x['h_sent'])} posts")

        sub("4  AGREEMENT AND SUPPORT-AWARE CHANCE, PER ALIGNMENT")
        print("  chance: metric uniform on sentences 2..N-1; impl uses the published")
        print("  model (human number as stored against support 2..N-1).")
        for c in CONV:
            hc = human[c]
            print(f"  [{c}]")
            for k, lab in ((0, "exact"), (1, "within1"), (2, "within2")):
                obs = sum(1 for h, m in pairs[c] if abs(h - m) <= k)
                put(f"{lab}_{c}", k=obs, n=n19)
                if k == 0:
                    ps = [chance_near(h, n, 0) if 2 <= h <= n - 1 else 0.0 for h, n in zip(hc, Ns)]
                else:
                    ps = [chance_near(h, n, k) for h, n in zip(hc, Ns)]
                d = poisson_binomial(ps)
                pge, ple = sum(d[obs:]), sum(d[:obs + 1])
                put(f"chance_{lab}_mean_{c}", statistics.mean(ps))
                put(f"expected_{lab}_{c}", sum(ps))
                put(f"p_ge_{lab}_{c}", pge, note="Poisson-binomial P(X >= observed)")
                put(f"p_le_{lab}_{c}", ple, note="Poisson-binomial P(X <= observed)")
                put(f"p0_{lab}_{c}", d[0])
                put(f"p_le2_{lab}_{c}", sum(d[:3]))
                print(f"    {lab:<8} {kn(obs, n19)}   chance mean {100*statistics.mean(ps):5.2f}%  "
                      f"E[X] {sum(ps):.3f}  P(X>={obs}) {pge:.3f}  P(X<={obs}) {ple:.3f}")
        ps0 = [chance_near(h, n, 0) if 2 <= h <= n - 1 else 0.0 for h, n in zip(human["impl"], Ns)]
        ps1 = [chance_near(h, n, 1) for h, n in zip(human["impl"], Ns)]
        b0 = poisson_binomial([statistics.mean(ps0)] * n19)
        b1 = poisson_binomial([statistics.mean(ps1)] * n19)
        put("submitted_binomial_p0_exact", b0[0],
            note="homogeneous Binomial(n, mean p) as in the submitted paper, NOT the per-post model")
        put("submitted_binomial_ple2_within1", sum(b1[:3]),
            note="homogeneous Binomial(n, mean p) as in the submitted paper, NOT the per-post model")
        put("chance_exact_naive_1overN", statistics.mean(1.0 / n for n in Ns))
        put("chance_within1_naive_3overN", statistics.mean(min(1.0, 3.0 / n) for n in Ns))
        print(f"  submitted paper's values, homogeneous binomial (labelled, not the model it names):"
              f" P(0) exact {b0[0]:.3f}, P(<=2) within-one {sum(b1[:3]):.3f}")
        print(f"  naive 1/N and 3/N benchmarks: {100*statistics.mean(1.0/n for n in Ns):.1f}%, "
              f"{100*statistics.mean(min(1.0, 3.0/n) for n in Ns):.1f}%")

        sub("5  ARC (TABLE 9)")
        arcs = [(g["gold_arc"], ARC.get((S[g["id"]].get("nava_arc") or "").strip()))
                for g in gold if g["id"] in S and (S[g["id"]].get("nava_arc") or "").strip()]
        arcs = [(x, y) for x, y in arcs if y]
        ag = sum(1 for x, y in arcs if x == y)
        hd = collections.Counter(x for x, _ in arcs)
        nd = collections.Counter(y for _, y in arcs)
        maj = hd.most_common(1)[0]
        put("arc_agreement", k=ag, n=len(arcs))
        put("arc_majority_baseline", k=maj[1], n=len(arcs), note=f"always '{maj[0]}'")
        put("arc_kappa", kappa_pairs([x for x, _ in arcs], [y for _, y in arcs]))
        put("arc_tvd", 0.5 * sum(abs(hd[x] - nd[x]) for x in set(hd) | set(nd)) / len(arcs))
        put("arc_human_distribution", dict(sorted(hd.items())))
        put("arc_nava_distribution", dict(sorted(nd.items())))
        for o in OUT:
            if o["key"].startswith("arc_"):
                print(f"  {o['key']:<26}: {o['value']}" + (f"  ({o['k']}/{o['n']}, Wilson "
                      f"{o['wilson_lo']}-{o['wilson_hi']})" if o["k"] else ""))

        # ============================================================ 6 round 3
        sub("6  ROUND 3: PERMITTED SUPPORT, DESIGN, RELIABILITY")
        R3 = {r: read_csv(ad / "round3_low_reliability" / f"annotations_rater{r}.csv")[0] for r in (1, 2, 3)}
        A = {r: first_showings(v) for r, v in R3.items()}
        print("  offline import accepts 0 <= tp <= n_sentences (offline_annotation.py 542);")
        print("  the shipped OFFLINE_GUIDE.md places no restriction on sentence 1 or N.")
        for r in (1, 2, 3):
            sel = [(i, tp(x)) for i, x in A[r].items() if tp(x) and i in N]
            put(f"r3_rater{r}_nonzero_selections", len(sel))
            put(f"r3_rater{r}_selected_sentence_1", sum(1 for _, t in sel if t == 1))
            put(f"r3_rater{r}_selected_sentence_N", sum(1 for i, t in sel if t == N[i]))
            print(f"  rater{r}: {len(sel)} selections; sentence 1: "
                  f"{sum(1 for _, t in sel if t == 1)}; sentence N: {sum(1 for i, t in sel if t == N[i])}")
        allids = set(A[1]) | set(A[2]) | set(A[3])
        cover = collections.Counter(i for r in (1, 2, 3) for i in A[r])
        three = sorted(i for i in allids if cover[i] == 3)
        put("r3_distinct_posts", len(allids))
        put("r3_posts_by_three", len(three))
        put("r3_posts_by_two", sum(1 for i in allids if cover[i] == 2))
        put("r3_posts_by_one", sum(1 for i in allids if cover[i] == 1))
        for x, y in itertools.combinations((1, 2, 3), 2):
            sh = set(A[x]) & set(A[y])
            put(f"r3_shared_{x}v{y}", len(sh))
            put(f"r3_pair_only_{x}v{y}", len(sh) - len(three))
        put("r3_alpha_sentiment_3way", krippendorff_nominal([[A[r][i]["overall_sentiment"] for r in (1, 2, 3)] for i in three]))
        put("r3_alpha_arc_3way", krippendorff_nominal([[A[r][i]["arc"] for r in (1, 2, 3)] for i in three]))
        unan = sum(1 for i in three if tp(A[1][i]) == tp(A[2][i]) == tp(A[3][i]))
        majc = collections.Counter()
        for i in three:
            v, c_ = collections.Counter(tp(A[r][i]) for r in (1, 2, 3)).most_common(1)[0]
            if c_ >= 2:
                majc["none" if v == 0 else "sentence"] += 1
        put("r3_unanimous_tp_3way", k=unan, n=len(three))
        put("r3_majority_tp_3way", k=majc["none"] + majc["sentence"], n=len(three))
        put("r3_majority_none", majc["none"])
        put("r3_majority_sentence", majc["sentence"])
        for o in OUT:
            if o["key"].startswith(("r3_distinct", "r3_posts", "r3_shared", "r3_pair_only",
                                    "r3_alpha", "r3_unan", "r3_maj")):
                print(f"  {o['key']:<30}: {o['value']}" + (f"  ({o['k']}/{o['n']}, Wilson "
                      f"{o['wilson_lo']}-{o['wilson_hi']})" if o["k"] else ""))

        sub("7  ROUND 3: PAIRWISE RAW, EXISTENCE AND LOCATION AGREEMENT")
        U = {r: [(i, (tp(x) - 0.5) / N[i]) for i, x in A[r].items() if tp(x) and i in N] for r in (1, 2, 3)}
        with Pool(min(3, a.workers)) as pool:
            P = pool.map(_pair, [(x, y, A[x], A[y], N, U) for x, y in itertools.combinations((1, 2, 3), 2)])
        ratios = collections.defaultdict(list)
        for p in P:
            pr = p["pair"]
            put(f"r3_raw_{pr}", k=p["raw"], n=p["n"])
            put(f"r3_existence_{pr}", k=p["exist"], n=p["n"])
            put(f"r3_existence_chance_{pr}", p["exist_chance"])
            put(f"r3_location_{pr}", k=p["loc"], n=p["nl"])
            obs = p["loc"] / p["nl"]
            for ck in ("ch_n2", "ch_n", "ch_emp_loo", "ch_emp_all"):
                put(f"r3_location_chance_{ck[3:]}_{pr}", p[ck])
                put(f"r3_location_ratio_{ck[3:]}_{pr}", obs / p[ck])
                ratios[ck[3:]].append(obs / p[ck])
            put(f"r3_location_boundary_picks_{pr}", p["bnd"])
            print(f"  {pr}  raw {kn(p['raw'], p['n'])}  existence {kn(p['exist'], p['n'])} "
                  f"chance {100*p['exist_chance']:.1f}%")
            print(f"       location {kn(p['loc'], p['nl'])}  chance 1/(N-2) {100*p['ch_n2']:.2f}%  "
                  f"1/N {100*p['ch_n']:.2f}%  empirical LOO {100*p['ch_emp_loo']:.2f}%  "
                  f"all {100*p['ch_emp_all']:.2f}%  boundary picks {p['bnd']}")
        for ck, v in ratios.items():
            put(f"r3_location_ratio_{ck}_min", min(v))
            put(f"r3_location_ratio_{ck}_max", max(v))
            print(f"  location / chance ratio, {ck:<8}: {min(v):.1f} to {max(v):.1f}")
        print("  empirical: each rater's own choices as relative position (h-0.5)/N binned")
        print("  onto the post's N sentences; LOO excludes the post itself.")

        # ============================================================ 8 repeats
        sub("8  INTRA-RATER REPEAT AGREEMENT, ROUNDS 3 AND 4")
        rep_sets = [(3, r, R3[r]) for r in (1, 2, 3)] + [(4, 1, r4)]
        rng = collections.defaultdict(list)
        for rnd, r, rows_ in rep_sets:
            by = collections.defaultdict(list)
            for x in sorted(rows_, key=lambda z: int(z["slot"])):
                by[x["id"]].append(x)
            reps = [v for v in by.values() if len(v) > 1]
            line = f"  round {rnd} rater {r}:"
            for fld, lab in (("overall_sentiment", "sentiment"), ("arc", "arc"), ("turning_point", "tp")):
                k = sum(1 for v in reps if str(v[0][fld]).strip() == str(v[1][fld]).strip())
                put(f"rep_round{rnd}_rater{r}_{lab}", k=k, n=len(reps))
                rng[(rnd, lab)].append(k / len(reps))
                line += f"  {lab} {kn(k, len(reps))}"
            w1 = sum(1 for v in reps if tp(v[0]) is not None and tp(v[1]) is not None
                     and abs(tp(v[0]) - tp(v[1])) <= 1)
            put(f"rep_round{rnd}_rater{r}_tp_within1", k=w1, n=len(reps))
            print(line)
        for (rnd, lab), v in sorted(rng.items()):
            put(f"rep_round{rnd}_{lab}_min", min(v))
            put(f"rep_round{rnd}_{lab}_max", max(v))
            print(f"  round {rnd} {lab:<9} range {100*min(v):.0f}-{100*max(v):.0f}%")

        # ============================================================ 9 spacing
        sub("9  REPEAT SPACING AS PRESENTED (gap = second position - first position)")
        print(f"  full sequence: annotate.REPEAT_MIN_GAP = {annotate.REPEAT_MIN_GAP} slots;")
        print("  short rounds: gap = max(3, n_uniq // 3) (annotate.py line 246).")
        for r in (1, 2, 3):
            sheet, _ = read_csv(ad / "offline" / f"rater{r}_OFFLINE.csv")
            k2s = {row_key(r, s): s for s in range(1000)}
            s2row = {int(x["slot"]): x for x in R3[r]}
            order = [s2row[k2s[x["row_key"]]]["id"] for x in sheet]
            g = gaps(order)
            slot_g = sorted(
                (lambda v: v[1] - v[0])(sorted(int(x["slot"]) for x in R3[r] if x["id"] == i))
                for i in {x["id"] for x in R3[r] if x["is_repeat"] == "1"})
            put(f"gap_round3_rater{r}_n", len(g))
            put(f"gap_round3_rater{r}_min", min(g))
            put(f"gap_round3_rater{r}_median", statistics.median(g))
            put(f"gap_round3_rater{r}_max", max(g))
            put(f"gap_round3_rater{r}_under41", sum(1 for x in g if x < 41))
            put(f"gap_round3_rater{r}_presented", " ".join(map(str, g)))
            put(f"gap_round3_rater{r}_slots", " ".join(map(str, slot_g)))
            put(f"gap_round3_rater{r}_sheet_rows", len(sheet))
            print(f"  round 3 rater {r}: {len(g)} repeats, presented min {min(g)} median "
                  f"{statistics.median(g)} max {max(g)}, under 41: {sum(1 for x in g if x < 41)}")
            print(f"      presented {g}")
            print(f"      slots     {slot_g}")
        g4 = gaps([x["id"] for x in sorted(r4, key=lambda z: int(z["slot"]))])
        put("gap_round4_rater1_n", len(g4))
        put("gap_round4_rater1_min", min(g4))
        put("gap_round4_rater1_median", statistics.median(g4))
        put("gap_round4_rater1_max", max(g4))
        put("gap_round4_rater1_under41", sum(1 for x in g4 if x < 41))
        put("gap_round4_rater1_presented", " ".join(map(str, g4)))
        put("gap_round4_rater1_slots", " ".join(map(str, g4)))
        print(f"  round 4 rater 1: {len(g4)} repeats, min {min(g4)} median {statistics.median(g4)} "
              f"max {max(g4)}, under 41: {sum(1 for x in g4 if x < 41)}; {g4}")
        gap_key = re.compile(r"^gap_round\d+_rater\d+_presented$")
        allg = [int(v) for o in OUT if gap_key.match(o["key"]) for v in o["value"].split()]
        put("gap_all_rounds_under41", k=sum(1 for x in allg if x < 41), n=len(allg))
        for rnd, rows_ in ((3, [x for r in (1, 2, 3) for x in R3[r]]), (4, r4)):
            put(f"repeat_fraction_round{rnd}", k=sum(1 for x in rows_ if x["is_repeat"] == "1"), n=len(rows_))

        # ============================================================ 10 rounds 1-2
        sub("10  REJECTED ROUNDS: THE PATTERNS THAT REJECTED THEM")
        r2 = {r: first_showings(read_csv(ad / "round1_compromised" / f"annotations_rater{r}.csv")[0]) for r in (1, 2, 3)}
        tot = part = 0
        for x, y in itertools.combinations((1, 2, 3), 2):
            sh = set(r2[x]) & set(r2[y])
            pat = collections.Counter(sum(r2[x][i][k] == r2[y][i][k] for k in
                                          ("overall_sentiment", "arc", "confidence")) for i in sh)
            tot += len(sh)
            part += pat[1] + pat[2]
            put(f"round2_{x}v{y}_comparisons", len(sh))
            put(f"round2_{x}v{y}_all_three_match", pat[3])
            put(f"round2_{x}v{y}_none_match", pat[0])
            print(f"  round 2 {x}v{y}: {len(sh)} comparisons, fields matching {dict(sorted(pat.items()))}")
        put("round2_comparisons_total", tot)
        put("round2_partial_matches", part)
        print(f"  round 2: {tot} comparisons, {part} with exactly one or two matching fields")
        r1 = {}
        for r in (1, 2, 3):
            trows = annotate.load_task(str(root), r)
            seq = annotate.build_sequence(trows, r)
            k2 = {row_key(r, s["slot"]): (trows[s["idx"]]["id"], s["is_repeat"]) for s in seq}
            sheet, _ = read_csv(ad / "round1_compromised" / f"rater{r}_OFFLINE.csv")
            r1[r] = {k2[x["row_key"]][0]: x for x in sheet if not k2[x["row_key"]][1]}
            put(f"round1_rater{r}_first_showings", len(r1[r]))
        for x, y in itertools.combinations((1, 2, 3), 2):
            sh = set(r1[x]) & set(r1[y])
            same = sum(1 for i in sh if r1[x][i]["turning_point"] == r1[y][i]["turning_point"])
            put(f"round1_tp_identical_{x}v{y}", k=same, n=len(sh))
            print(f"  round 1 {x}v{y}: identical turning point {same}/{len(sh)}")
        r1ids = sorted(set(r1[1]) | set(r1[2]) | set(r1[3]))
        r1N = [N[i] for i in r1ids if i in N]
        put("round1_posts", len(r1N))
        put("round1_chance_same_sentence_n2", statistics.mean(1.0 / max(1, n - 2) for n in r1N))
        put("round1_chance_same_sentence_n", statistics.mean(1.0 / n for n in r1N))
        print(f"  round 1 chance of the same sentence over {len(r1N)} posts: "
              f"1/(N-2) {100*statistics.mean(1.0/max(1, n-2) for n in r1N):.2f}%  "
              f"1/N {100*statistics.mean(1.0/n for n in r1N):.2f}%")

        # ============================================================ write
        sub("WRITING")
        tables.mkdir(parents=True, exist_ok=True)
        p = tables / "human_criterion_v2.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["key", "value", "k", "n", "wilson_lo", "wilson_hi", "note"])
            w.writeheader()
            w.writerows(OUT)
        print(f"  {p}  ({len(OUT)} keys)")
        cols = ["id", "N", "N_disp", "h_disp", "h_sent", "lewi_zero_based", "lewi_one_based",
                "boundary_disp", "boundary_sent", "match_impl", "match_plus1", "match_full",
                "p_exact_plus1", "p_within1_plus1", "p_exact_full", "p_within1_full"]
        p = tables / "annotation_audit_v2.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"  {p}  ({len(rows)} rows)")
        print("  no figure caption in the submitted text carries an annotation number;")
        print("  Tables 8, 9 and 12 and Sections 2.6, 3.5, 3.6, 4.3, 4.6 draw on the keys above.")
        head("DONE")
        return 0
    finally:
        print(f"  finished  : {datetime.datetime.now().isoformat(timespec='seconds')}")
        sys.stdout = tee.stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(main())
