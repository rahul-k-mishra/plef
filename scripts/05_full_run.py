#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 05 : FULL EVALUATION RUN
                       (v05.3.0)
===============================================================================

WHAT THIS SCRIPT IS FOR (plain language)
----------------------------------------
This is the first script in the project that produces numbers for the paper.
Everything before it built an instrument nobody can dispute. This one uses it.

For every item in all eight corpora it computes:
  * the twelve PLEF metrics from the rebuilt core
  * six REAL baselines: VADER, NRC EmoLex, Empath, AFINN, Hu-Liu, labMT
  * the three V1 toy lexicons, for the supplementary error-quantification table
  * NRC-VAD dominance and NRC Emotion Intensity, as EXTERNAL CRITERIA

It writes one row per item to results/canonical/. It computes no statistics and
draws no conclusions; that is script 06. This script's only job is to produce a
scored dataset that is complete, checkpointed and reproducible.

WHAT THIS SCRIPT WILL NOT DO
-----------------------------
  * It will not compute macro-F1 for the relationship corpus. That corpus has
    no trustworthy labels (D18) and the gate refuses.
  * It will not compute LEWI, TEG or NAVA for corpora outside the declared
    trajectory scope (D20). They are computed and stored, but flagged
    out-of-scope so script 06 cannot silently pool them.
  * It will not include the Consensus corpus. It no longer exists (D19).
  * It will not pick a threshold, a normalisation or a mapping. All of those
    were declared in DECISIONS.md before this script ever ran.

EXTERNAL CRITERIA (D6) -- the answer to two failed hypotheses
--------------------------------------------------------------
  NRC-VAD dominance   is annotated without reference to any pronoun count, so
                      correlating it with PAI is not circular. This is the
                      independent criterion H2 never had (Reviewer 2, point 7).
  NRC EmoInt          gives a per-token emotion intensity that is not derived
                      from PLEF's own compound score, so a sentence-level
                      intensity sequence gives TEG an external criterion. This
                      is what Reviewer 1 asked for on H3.
Both are computed per item here; the correlations are script 06's job.

SHARDING AND CHECKPOINTS
-------------------------
One shard per corpus. Each shard writes its own CSV plus a .done marker
containing the row count and a content hash. A crash costs one corpus, and
re-running skips completed shards unless --force is given.

Windows uses spawn rather than fork, so every worker re-imports the core and
re-reads the lexicons. Chunks are therefore made LARGE and few: the benchmark
showed 3,010 words/s at 7 workers on 200 texts, where startup dominated.

EXIT CODES
----------
  0 all shards complete
  2 missing prerequisite (run scripts 02, 03, 04 first)
  3 a shard failed
===============================================================================
"""

import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
SCRIPT_VERSION = "05.4.0"

# Declared in DECISIONS.md D20, before any result existed.
TRAJECTORY_SCOPE = {"relationship", "dev_relationship"}
# Declared in D18: no classification result may be computed on these.
NO_LABEL_CORPORA = {"relationship", "dev_relationship"}
# Declared in D10 and D16.
BINARY_CORPORA = {"isear", "empathetic"}

BASELINES = ["vader", "nrc", "empath", "afinn", "huliu", "labmt"]
LEGACY = ["V1_vader_toy", "V1_nrc_toy", "V1_liwc_toy"]

METRIC_FIELDS = [
    "n_sents", "n_words", "sentiment_mean",
    "lewi_idx", "lewi_pre", "lewi_post", "lewi_drop",
    "lewi_v1_idx", "lewi_v1_drop",
    "teg", "nava", "nava_arc",
    "gase", "gase_S", "gase_H", "gase_A", "gase_G",
    "pti", "pti_unsmoothed", "pai", "pai_v1", "pai_C_dom", "pai_A_dom",
    "rci", "cd_index", "vads", "ties", "sem_coherence", "nspl",
    "rasp_dominant", "horsemen_total",
]
CRITERION_FIELDS = ["vad_valence", "vad_arousal", "vad_dominance",
                    "emoint_mean", "emoint_teg"]


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


# ===========================================================================
# WORKER -- one call scores a large chunk. Heavy objects are built once per
# worker process and cached, because Windows spawn re-imports for every task.
# ===========================================================================
_CACHE = {}


def _init(root, nrc, legacy, vad, emoint):
    key = (root, nrc, legacy, vad, emoint)
    if key in _CACHE:
        return _CACHE[key]
    sys.path.insert(0, str(Path(root) / "src"))
    import plef_core as C
    import plef_baselines as B
    bl = B.load_all(nrc, legacy, include_legacy=True)
    vadlex = B.VADLexicon(vad) if vad and os.path.exists(vad) else None
    emo = B.EmoIntLexicon(emoint) if emoint and os.path.exists(emoint) else None
    _CACHE[key] = (C, bl, vadlex, emo)
    return _CACHE[key]


def _score_chunk(spec):
    root, nrc, legacy, vad, emoint, rows, in_scope, store_vectors = spec
    try:
        C, bl, vadlex, emo = _init(root, nrc, legacy, vad, emoint)
    except Exception:
        return None, traceback.format_exc()[:900]
    out = []
    for r in rows:
        text = r["text"]
        rec = {"id": r.get("id", ""), "gold": r.get("gold", ""),
               "emotion": r.get("emotion", ""),
               "label_source": r.get("label_source", "")}
        # FIX 2: PLEF's OWN lexicon coverage. v05.1.0 recorded coverage for all
        # six baselines and not for the system the paper is about, which is the
        # one number that explains the entire results table.
        try:
            toks = C.tokenize(text)
            rec["cov_plef"] = (sum(1 for w in toks if w in C.LEXICON) / len(toks)
                               if toks else None)
        except Exception:
            rec["cov_plef"] = None
        # FIX 3: the per-sentence score vector. Without it the WITHIN-DOCUMENT
        # permutation null cannot be computed at all -- shuffling real sentence
        # order preserves each document's marginal distribution and destroys only
        # the temporal structure, which is a strictly stronger test than the
        # synthetic null. Stored only for corpora in trajectory scope, because
        # storing 5.5M vectors to test a null on corpora where NAVA and LEWI are
        # computable on 1.5%-6.4% of items would be pure bloat.
        if store_vectors:
            try:
                rec["sent_scores"] = ";".join(
                    f"{v:.6f}" for v in C.sentence_scores(text))
            except Exception:
                rec["sent_scores"] = ""
        else:
            rec["sent_scores"] = ""
        try:
            m = C.analyse(text)
        except Exception as e:
            m = {k: None for k in METRIC_FIELDS}
            rec["metric_error"] = f"{type(e).__name__}: {e}"[:120]
        for k in METRIC_FIELDS:
            rec[k] = m.get(k)
        # D20: trajectory metrics are computed everywhere but flagged so that
        # script 06 cannot pool them outside the declared scope by accident.
        rec["trajectory_in_scope"] = 1 if in_scope else 0
        for name, obj in bl.items():
            try:
                rec[f"b_{name}"] = obj.score(text)
            except Exception:
                rec[f"b_{name}"] = None
            if name in ("vader", "nrc", "huliu", "afinn", "empath", "labmt"):
                try:
                    cv = obj.coverage(text)
                    rec[f"cov_{name}"] = cv if cv >= 0 else None
                except Exception:
                    rec[f"cov_{name}"] = None
        if vadlex is not None:
            rec["vad_valence"] = vadlex.valence(text)
            rec["vad_arousal"] = vadlex.arousal(text)
            rec["vad_dominance"] = vadlex.dominance(text)
        else:
            rec["vad_valence"] = rec["vad_arousal"] = rec["vad_dominance"] = None
        if emo is not None:
            sents = C.sentences(text)
            seq = [emo.intensity(s) for s in sents]
            rec["emoint_mean"] = round(sum(seq) / len(seq), 6) if seq else None
            if len(seq) >= 2:
                d = [abs(seq[i] - seq[i - 1]) for i in range(1, len(seq))]
                rec["emoint_teg"] = round(sum(d) / len(d), 6)
            else:
                rec["emoint_teg"] = None
        else:
            rec["emoint_mean"] = rec["emoint_teg"] = None
        out.append(rec)
    return out, None


# ===========================================================================
def load_corpus(p):
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def field_order():
    f = ["id", "gold", "emotion", "label_source", "trajectory_in_scope"]
    f += METRIC_FIELDS
    f += [f"b_{n}" for n in BASELINES + LEGACY]
    f += [f"cov_{n}" for n in BASELINES]
    f += CRITERION_FIELDS + ["cov_plef", "sent_scores", "metric_error"]
    return f


def run_shard(name, path, root, paths, workers, chunk_target,
              store_vectors=False):
    rows = load_corpus(path)
    n = len(rows)
    in_scope = name in TRAJECTORY_SCOPE
    words = sum(len(r["text"].split()) for r in rows)
    # Few, large chunks: Windows spawn re-imports the core per task, so many
    # small chunks spend most of their time on startup. But v05.1.0 used
    # max(chunk_target, n/workers), which gave ONE chunk for any corpus smaller
    # than chunk_target -- the relationship shard ran 857s on a single core
    # while five idled. Take the MINIMUM of the two so every worker gets work.
    per = max(1, min(chunk_target, (n + workers - 1) // workers))
    chunks = [rows[i:i + per] for i in range(0, n, per)]
    print(f"  {name:<15} {n:>8,} items  {words:>10,} words  "
          f"{len(chunks)} chunk(s) of ~{per:,}   "
          f"{'trajectory IN scope' if in_scope else 'trajectory out of scope'}"
          f"{'  +sentence vectors' if store_vectors else ''}")
    t0 = time.time()
    out, errs = [], []
    specs = [(str(root), paths["nrc"], paths["legacy"], paths["vad"],
              paths["emoint"], c, in_scope, store_vectors) for c in chunks]
    with ProcessPoolExecutor(max_workers=min(workers, len(chunks))) as ex:
        for res, err in ex.map(_score_chunk, specs):
            if err:
                errs.append(err)
            else:
                out.extend(res)
    el = time.time() - t0
    if errs:
        print(f"  {'':<15} SHARD FAILED: {errs[0].splitlines()[-1][:70]}")
        return None
    dest = Path(root) / "results" / "canonical" / f"scored_{name}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(dest) + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=field_order(), extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    os.replace(tmp, dest)
    h = sha256(dest)
    marker = dest.with_suffix(".done")
    marker.write_text(json.dumps(
        {"corpus": name, "rows": len(out), "sha256": h,
         "seconds": round(el, 1), "words": words,
         "trajectory_in_scope": in_scope,
         "at": datetime.datetime.now().isoformat(timespec="seconds")},
        indent=1), encoding="utf-8")
    print(f"  {'':<15} {len(out):>8,} rows in {el:>6.1f}s "
          f"({words/max(el,1e-9):>7,.0f} w/s) -> {dest.name}")
    return {"rows": len(out), "seconds": el, "words": words, "sha256": h,
            "path": str(dest)}


def coverage_report(root, names):
    sub("COMPLETENESS AUDIT")
    print("  Every metric, per corpus: how many items produced a value rather")
    print("  than None. A metric that is mostly None is not a weak metric, it is")
    print("  an inapplicable one, and the paper must say which it is.")
    print()
    key = ["lewi_drop", "nava", "teg", "rci", "ties", "sem_coherence", "nspl",
           "pti", "pai", "gase", "cd_index", "vads"]
    print(f"  {'corpus':<15}" + "".join(f"{k[:7]:>9}" for k in key))
    rule()
    table = {}
    for name in names:
        p = Path(root) / "results" / "canonical" / f"scored_{name}.csv"
        if not p.exists():
            continue
        cnt = collections.Counter()
        n = 0
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                n += 1
                for k in key:
                    v = (r.get(k) or "").strip()
                    if v != "":
                        cnt[k] += 1
        table[name] = {k: (100.0 * cnt[k] / max(1, n)) for k in key}
        print(f"  {name:<15}" + "".join(f"{table[name][k]:>8.1f}%" for k in key))
    return table


def sanity_checks(root, names):
    sub("SANITY CHECKS")
    ok = True
    for name in names:
        p = Path(root) / "results" / "canonical" / f"scored_{name}.csv"
        if not p.exists():
            continue
        n = 0
        gold_present = 0
        const = collections.defaultdict(set)
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                n += 1
                if (r.get("gold") or "").strip():
                    gold_present += 1
                for b in BASELINES:
                    v = (r.get(f"b_{b}") or "").strip()
                    if v and len(const[b]) < 5:
                        const[b].add(v)
        problems = []
        if name in NO_LABEL_CORPORA and gold_present:
            problems.append(f"{gold_present} rows carry gold labels on a "
                            f"no-label corpus (D18 violated)")
        for b in BASELINES:
            if len(const[b]) <= 1 and n > 50:
                problems.append(f"baseline '{b}' produced a constant value")
        if problems:
            ok = False
            print(f"  FAIL  {name}")
            for pr in problems:
                print(f"          - {pr}")
        else:
            print(f"  PASS  {name}   ({n:,} rows"
                  f"{', no gold labels as declared' if name in NO_LABEL_CORPORA else ''})")
    return ok


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 05 -- full run.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=2000,
                    help="minimum items per chunk (large is better on Windows)")
    ap.add_argument("--force", action="store_true",
                    help="rescore corpora that already have a .done marker")
    ap.add_argument("--only", default="", help="comma-separated corpus names")
    ap.add_argument("--store-vectors", action="store_true",
                    help="store per-sentence score vectors for EVERY corpus "
                         "(default: only corpora in trajectory scope)")
    args = ap.parse_args()
    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    root = Path(args.root)

    for req in ("src/plef_core.py", "src/plef_baselines.py",
                "MANIFEST/environment.json", "MANIFEST/corpora.json"):
        if not (root / req).exists():
            print(f"FATAL: {req} missing. Run scripts 02, 03 and 04 first.")
            return 2

    tee = Tee(root / "results" / "forensics" / "console_log_05.txt")
    sys.stdout = tee
    try:
        head("PLEF V2 -- SCRIPT 05 : FULL EVALUATION RUN")
        print(f"  script version : {SCRIPT_VERSION}")
        print(f"  started        : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  V2 root        : {root}")
        print(f"  workers        : {workers}   chunk target: {args.chunk:,}")

        env = json.loads((root / "MANIFEST" / "environment.json").read_text(
            encoding="utf-8"))
        lex = env.get("lexicons", {})
        paths = {
            "nrc": (lex.get("emolex") or {}).get("path"),
            "vad": (lex.get("vad") or {}).get("path"),
            "emoint": (lex.get("emoint") or {}).get("path"),
            "legacy": str(root / "src" / "legacy_v1_lexicons.json"),
        }
        sub("INPUTS")
        for k in ("nrc", "vad", "emoint", "legacy"):
            v = paths[k]
            print(f"  {k:<8} {'MISSING' if not v else Path(v).name}")
        if not paths["nrc"]:
            print("  FATAL: NRC EmoLex path not in the environment manifest.")
            return 2
        if not paths["vad"]:
            print("  NOTE: NRC-VAD absent. PAI will have no external criterion,")
            print("        so H2 cannot be re-tested (D6). Continuing.")
        if not paths["emoint"]:
            print("  NOTE: NRC EmoInt absent. TEG will have no external criterion,")
            print("        so H3 cannot be re-tested (D6). Continuing.")

        man = json.loads((root / "MANIFEST" / "corpora.json").read_text(
            encoding="utf-8"))
        available = sorted((man.get("corpora") or {}).keys())
        wanted = [x.strip() for x in args.only.split(",") if x.strip()] or available
        names = [n for n in wanted if n in available]
        missing = [n for n in wanted if n not in available]
        if missing:
            print(f"  unknown corpora ignored: {missing}")

        sub("SCORING SHARDS")
        print(f"  Declared scope (D20): trajectory metrics IN SCOPE only for "
              f"{sorted(TRAJECTORY_SCOPE)}")
        print(f"  Declared (D18): no classification on {sorted(NO_LABEL_CORPORA)}")
        print(f"  Declared (D10, D16): binary corpora {sorted(BINARY_CORPORA)}")
        print()
        # The dev split is excluded from every classification result, but the
        # human annotation was collected on it -- so H1 and H5 cannot be tested
        # unless it is scored. v05.3.1 scored only the evaluation set, which made
        # the gold file match zero scored posts. Scored here as its own shard,
        # in trajectory scope, and NEVER pooled with the evaluation corpora.
        dev = root / "data" / "interim" / "dev_split_relationship.csv"
        if dev.exists() and "dev_relationship" not in (man.get("corpora") or {}):
            man.setdefault("corpora", {})["dev_relationship"] = {"path": str(dev)}
            if "dev_relationship" not in names:
                names.append("dev_relationship")
            print("  dev_relationship added: the annotated split, scored so that")
            print("  H1 and H5 can be evaluated. Excluded from all pooled results.")
            print()

        results, failed, skipped = {}, [], []
        t_all = time.time()
        for name in names:
            info = (man["corpora"] or {}).get(name) or {}
            src = info.get("path")
            if not src or not Path(src).exists():
                print(f"  {name:<15} corpus file missing; skipped")
                failed.append(name)
                continue
            done = (root / "results" / "canonical" / f"scored_{name}.done")
            if done.exists() and not args.force:
                d = json.loads(done.read_text(encoding="utf-8"))
                print(f"  {name:<15} already done ({d['rows']:,} rows) -- skipped "
                      f"(use --force to rescore)")
                skipped.append(name)
                results[name] = d
                continue
            store_vec = (name in TRAJECTORY_SCOPE) or args.store_vectors
            r = run_shard(name, src, root, paths, workers, args.chunk, store_vec)
            if r is None:
                failed.append(name)
            else:
                results[name] = r
        el_all = time.time() - t_all

        # FIX 4: v05.2.0 wrote the manifest WHOLESALE from this run's results,
        # so "--only relationship" erased the other seven shards from the record
        # while their CSVs and .done markers sat untouched on disk. The manifest
        # is the record of what exists, not of what this invocation happened to
        # touch. Every .done marker present is now folded back in, and any shard
        # on disk but absent from this run is reported.
        canon = root / "results" / "canonical"
        recovered = []
        for d in sorted(canon.glob("scored_*.done")):
            nm = d.stem.replace("scored_", "")
            if nm in results:
                continue
            try:
                results[nm] = json.loads(d.read_text(encoding="utf-8"))
                recovered.append(nm)
            except Exception:
                pass
        if recovered:
            print()
            print(f"  manifest: folded back {len(recovered)} shard(s) present on disk "
                  f"but not scored in this run:")
            print(f"    {', '.join(recovered)}")
        orphan = [n for n in results
                  if not (canon / f"scored_{n}.csv").exists()]
        if orphan:
            print(f"  WARNING: manifest entries with no CSV on disk: {orphan}")

        scored = [n for n in names if n not in failed]
        cov = coverage_report(root, sorted(results))
        ok = sanity_checks(root, sorted(results))

        prev = {}
        mp = root / "MANIFEST" / "scored.json"
        if mp.exists():
            try:
                prev = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        tot_rows = sum(results[n]["rows"] for n in results)
        tot_words = sum(results[n].get("words", 0) for n in results)
        manifest = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                    "script_version": SCRIPT_VERSION, "workers": workers,
                    "shards": results, "failed": failed, "skipped": skipped,
                    "total_rows": tot_rows, "total_words": tot_words,
                    "elapsed_seconds": round(el_all, 1),
                    "completeness": cov, "sanity_ok": ok,
                    "trajectory_scope": sorted(TRAJECTORY_SCOPE),
                    "no_label_corpora": sorted(NO_LABEL_CORPORA),
                    "binary_corpora": sorted(BINARY_CORPORA),
                    "baselines": BASELINES, "legacy": LEGACY}
        (root / "MANIFEST" / "scored.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8")

        head("DONE")
        print(f"  scored     : {root / 'results' / 'canonical'}")
        print(f"  manifest   : {root / 'MANIFEST' / 'scored.json'}")
        print(f"  log        : {root / 'results' / 'forensics' / 'console_log_05.txt'}")
        print()
        # v05.3.0 counted every non-failed corpus as "scored this run", which
        # printed 8 when all 8 had been skipped. Skipped is not scored.
        n_scored = len([n for n in names if n not in failed and n not in skipped])
        print(f"  corpora in manifest : {len(results)}   "
              f"scored this run: {n_scored}   skipped: {len(skipped)}   "
              f"failed: {failed or 'none'}")
        print(f"  rows           : {tot_rows:,}")
        print(f"  words          : {tot_words:,}")
        if el_all > 0 and n_scored:
            print(f"  elapsed        : {el_all/60:.1f} min "
                  f"({tot_words/max(el_all,1e-9):,.0f} words/s overall)")
        print(f"  sanity checks  : {'PASSED' if ok else 'FAILED'}")
        print()
        if failed or not ok:
            print("  Do not proceed to script 06 until every shard is present and")
            print("  the sanity checks pass.")
            return 3
        print("  NEXT: send me this log. Script 06 computes the statistics:")
        print("  Table 3 against real baselines, bootstrap confidence intervals,")
        print("  the NAVA x LEWI structural null, PAI against VAD dominance, TEG")
        print("  against EmoInt, and the honest hypothesis scoreboard.")
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
