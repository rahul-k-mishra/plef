#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
PLEF V2 -- SCRIPT 21 : RELEASE CORRECTION, SECOND REVISION
                       (21_release_correction_r2.py, v1.1.1)
===============================================================================

CHANGE HISTORY
--------------
  v1.1.1  The plan-step-0 precondition on console_log_15_before_r2.txt required
          the line after "FILES NEEDING A HUMAN LOOK" to be exactly "none", but
          script 15 writes "none -- every mismatch is a line-ending form", so a
          clean audit failed the check. The section (up to its blank line) must
          now hold a single line beginning with "none"; any listed file path
          still stops the script.
  v1.1.0  Commit A carries its own manifest amendment; commit B refers to it and
          is untagged; commit C adds the console logs after the push and carries
          r2-corrected; the manifest is re-read before each amendment.
  v1.0.0  First version.

WHAT THIS DOES (plain language)
-------------------------------
Carries out paper/round2/RELEASE_PLAN_ROUND2.md on the public release working
copy (PLEF_V2/release, repository rahul-k-mishra/plef). The public history is
NOT rewritten: everything here is new commits and new annotated tags, pushed
by name, never forced. 09_release_assembly.py is never run.

Three commits are made, in this order:

  COMMIT A (plan step 6) on top of a6c5fc7, containing ONLY first_revision/
      and a dated amendment block appended to MANIFEST-RELEASE.txt that lists
      the first_revision/ files with their hashes and sizes: the first-revision
      manuscript source, the PDF exactly as uploaded to the journal, and the
      first-revision SUPPLEMENTARY.md (optionally also the class file and four
      figures, with --first-revision-compilable). Tagged r1-as-reviewed. That
      tag is the repository as the reviewers saw it plus the paper they read,
      and it verifies against its own manifest.

  COMMIT B (plan steps 2-5, 7, 8) on top of commit A:
      step 2  drop the numbered_text column from the three round-1 sheets,
              keeping every other column, the UTF-8 BOM and CRLF record ends
      step 3  one folder per round; round 2's records added from the workspace
      step 4  corpus/relationship_post_ids.csv and its README
      step 5  collection scripts recovered byte-exact from the pre-revision tag
      step 7  scripts 15-21, their console logs, the new tables and figures;
              release README corrected
      step 8  a dated amendment block appended to MANIFEST-RELEASE.txt; no
              existing manifest line is touched. first_revision/ is not listed
              again: the block refers to commit A's block
      Not tagged.

  COMMIT C after verification and after main and the tags are pushed (only in
      a --push run): logs/console_log_21.txt (this log, copied up to that
      point) and, if it exists, logs/console_log_15_after_r2.txt, with a one-line
      manifest amendment and the entries for those files. Tagged r2-corrected
      and pushed in the same run, so the tag the paper cites ships scripts
      15-21 with logs 15-21. If console_log_15_after_r2.txt does not exist,
      commit C carries console_log_21.txt alone and the output says so.

DEPARTURES FROM THE PLAN, as instructed by the author on 2026-10-08
  a. gold_dev200.csv (was annotation/rejected/) and
     gold_dev200_UNUSABLE_alpha0.177.csv (was annotation/) go to
     annotation/derived/, with a README giving each file's row count and
     columns and stating that the round it was produced from is not recorded.
     The 24-rows-against-26-three-way-posts discrepancy is noted there.
  b. The notes column of the round-2 records and of the retained round-1
     sheets is scanned for post text BEFORE commit B. A note containing post
     text is blanked and the removal is logged (row and column only).
  c. After the text column is dropped, every retained field longer than 200
     characters is listed in the log (file, row key, column, length) for
     inspection. Contents are not printed.
  d. corpus/README.md uses the manuscript's Section 2.2 wording for the
     unprefixed identifiers; the script checks that the phrase occurs verbatim
     in Version_3/paper/manuscript.tex.
  e. Script 20, console_log_20.txt, the four supp_*.csv tables and the two v2
     figures are added in step 7.

POST-TEXT TESTS
  file scan  : a relationship post is "in" a file if any of its fingerprints,
               the first 12 words ([a-z0-9']+, lower case) of up to three
               sentences of >= 12 words (released core's splitter), occurs as a
               contiguous word sequence in the file (as script 20, stage 5)
  note test  : a note "contains post text" if any 8 consecutive words of it
               occur consecutively in any of the 1,508 posts; notes are short,
               so the stricter 8-word window is used

IDEMPOTENCE
  If tag r1-as-reviewed exists and verifies (parent a6c5fc7; only
  first_revision/ and the manifest changed; the tagged manifest lists the
  first_revision/ files with their hashes), commit A is skipped. If HEAD is an
  untagged commit B (parent r1-as-reviewed, carrying the corrected layout),
  commit B is skipped. If tag r2-corrected exists and verifies (a commit C on
  top of such a commit B, adding only the logs and the manifest), commits A, B
  and C are all skipped and a --push run only re-pushes, which is a no-op when
  the remote is up to date. Any other state (HEAD elsewhere, uncommitted
  changes, a tag that does not verify) stops the script with a message.

PRECONDITIONS (all checked before anything is written; any failure stops)
  * release is a git work tree on branch main, remote origin is
    rahul-k-mishra/plef, the work tree is clean, core.autocrlf is false and
    .gitattributes is exactly "* -text"
  * for a fresh start, HEAD is a6c5fc7 and origin/main points at a6c5fc7
  * every MANIFEST-RELEASE.txt entry hashes raw on disk
  * results/forensics/console_log_15_before_r2.txt exists (plan step 0, script
    15 on a fresh clone) and reports no file needing a human look
  * every source file exists; the first-revision files and the pre-revision
    collection-script blobs have the hashes recorded in the plan; the release
    round-1 sheets and round-3 records are byte-identical to their workspace
    originals
  * the release README contains the sentence it is to replace

USAGE
  python 21_release_correction_r2.py --root <PLEF_V2>                 dry run
  python 21_release_correction_r2.py --root <PLEF_V2> --apply         commits A and B (+ tag r1-as-reviewed)
  python 21_release_correction_r2.py --root <PLEF_V2> --apply --push  and push, then commit C + tag r2-corrected
  options: --tag-pushed-states (also create r1-pushed at 04bdc4f and
           r1-byte-fixed at a6c5fc7), --first-revision-compilable, --workers N

AFTER IT HAS RUN (not done by this script)
  * run 15_release_byte_audit.py on a fresh clone and save
    results/forensics/console_log_15_after_r2.txt (plan step 9.2)
  * the DATE printed at the end is the <<DATE:correction>> of the manuscript
  * console_log_15_after_r2.txt can only be in commit C if script 15 was run on
    a fresh clone of the pushed commit B before the --push run that makes C

Standard library only; worker pool for the scans; deterministic. Writes only
inside the release work tree and results/forensics/console_log_21.txt.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

sys.dont_write_bytecode = True
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

VERSION = "1.1.1"
A6C = "a6c5fc7e32c5116c6f9bfe9e1d3a2247885f1851"
P04 = "04bdc4f44638e703017fdb249007cc17daf962c1"
LEXICON_SHA256 = "18294c6727f66003df67c0c01ab9e66073dca34d3c60541878c35ba84825165c"
REMOTE_RE = re.compile(r"github\.com[:/]rahul-k-mishra/plef(\.git)?$")
TAG_A, TAG_C = "r1-as-reviewed", "r2-corrected"
B_MARKERS = ("annotation/round1_rejected/rater1_OFFLINE.csv", "corpus/relationship_post_ids.csv",
             "annotation/derived/README.md")
C_FILES = ("logs/console_log_21.txt", "logs/console_log_15_after_r2.txt")
FIRST_REVISION = [   # (release path, workspace path relative to repo root, sha256)
    ("first_revision/manuscript_revised.tex", "Version_2/PLEF_revision/manuscript_revised.tex",
     "cfcbd815c2dfd656990254361f9343cd89dbb877d37245f9aeee4fd2ff0b0f2b"),
    ("first_revision/PLEF_revision_as_submitted.pdf", "submitted_round1/PLEF_revision_as_submitted.pdf",
     "93100088ac750508b3f5f85a6ec9c4ad2fadfb0e90c45ddfd554a8ddd2761ddf"),
    ("first_revision/SUPPLEMENTARY.md", "Version_2/PLEF_revision/SUPPLEMENTARY.md",
     "e57eb3280ad4f4a42d33263bdfc59c71eca5f46ce41c2c2be307a564d4488683"),
]
FIRST_REVISION_COMPILE = ["wlscirep.cls", "fig1_coverage_scope.png", "fig2_benchmark.png",
                          "fig3_nulls_moderator.png", "fig4_gase_abstention.png"]
COLLECTION = {"reddit_download.py": "5624c2477f2b54812db1e2e263ce7562cdc2f23f",
              "extended_reddit_download.py": "755a6f56c10d28e7e7585d1280caaa1eff4598a7"}
OLD_README = ("The relationship corpus consists of public Reddit\n"
              "posts; the collection scripts are included and the post text is not\n"
              "redistributed.")
UNPREFIXED_PHRASE = ("carry no prefix and are attributable only through the configuration of a "
                     "single-subreddit collection script, which is an inference from the code "
                     "rather than a per-post record")
KEEP_COLS = ["row_key", "n_sentences", "n_words", "est_read_seconds", "overall_sentiment",
             "turning_point", "arc", "confidence", "notes"]
LONG_FIELD = 200
K_FILE, K_NOTE = 12, 8


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


class Stop(Exception):
    """A precondition failed. Nothing further is done."""


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


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def read_csv_bytes(b):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            txt = b.decode(enc)
        except UnicodeDecodeError:
            continue
        rd = csv.DictReader(io.StringIO(txt, newline=""))
        return list(rd), rd.fieldnames, enc
    raise Stop("undecodable CSV")


class Git:
    def __init__(self, repo):
        self.repo = str(repo)

    def run(self, *args, check=True, inp=None, write=False):
        cmd = ["git", "-C", self.repo] + ([] if write else ["--no-optional-locks"]) + list(args)
        if write:
            cmd = ["git", "-C", self.repo] + list(args)
        r = subprocess.run(cmd, capture_output=True, input=inp)
        if check and r.returncode != 0:
            raise Stop(f"git {' '.join(args)} failed:\n{r.stderr.decode(errors='replace')}")
        return r.stdout.decode("utf-8", errors="replace")

    def raw(self, *args, inp=None):
        r = subprocess.run(["git", "-C", self.repo, "--no-optional-locks"] + list(args),
                           capture_output=True, input=inp)
        if r.returncode != 0:
            raise Stop(f"git {' '.join(args)} failed:\n{r.stderr.decode(errors='replace')}")
        return r.stdout

    def rev(self, ref):
        r = subprocess.run(["git", "-C", self.repo, "--no-optional-locks", "rev-parse", "-q",
                            "--verify", ref + "^{commit}"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None


def parse_manifest(b):
    out = {}
    for ln in b.decode("utf-8").replace("\r\n", "\n").split("\n"):
        if ln and not ln.startswith("#"):
            p_ = ln.split()
            if len(p_) >= 3:
                out[" ".join(p_[2:])] = (p_[0], int(p_[1]))
    return out


def amend(man_bytes, lines):
    """Append lines to the manifest with its own line ending; existing bytes untouched."""
    eol = "\r\n" if b"\r\n" in man_bytes else "\n"
    tail = "" if man_bytes.endswith(eol.encode()) else eol
    return man_bytes + (tail + eol.join(lines) + eol).encode("utf-8")


def load_core(src):
    if sha256_file(Path(src) / "plef_lexicons.json") != LEXICON_SHA256:
        raise Stop("lexicon hash mismatch in src/")
    spec = importlib.util.spec_from_file_location("plef_core_released", str(Path(src) / "plef_core.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------- scan workers
WORD = re.compile(r"[a-z0-9']+")
FP = None


def _init_fp(fp):
    global FP
    FP = collections.defaultdict(lambda: collections.defaultdict(set))
    for pid, words in fp:
        FP[words[0]][tuple(words)].add(pid)


def _scan(job):
    label, data = job
    try:
        t = data.decode("utf-8")
    except UnicodeDecodeError:
        t = data.decode("latin-1")
    w = WORD.findall(t.lower())
    found = set()
    for i, x in enumerate(w):
        d = FP.get(x)
        if d:
            found.update(d.get(tuple(w[i:i + K_FILE]), ()))
    return label, sorted(found)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="PLEF V2 script 21 -- release correction, round 2.")
    ap.add_argument("--root", required=True, help="path to PLEF_V2")
    ap.add_argument("--release", help="release work tree (default: <root>/release)")
    ap.add_argument("--apply", action="store_true", help="make the changes, commits and tags")
    ap.add_argument("--push", action="store_true", help="push main and the tags by name (needs --apply)")
    ap.add_argument("--tag-pushed-states", action="store_true",
                    help="also create r1-pushed at 04bdc4f and r1-byte-fixed at a6c5fc7")
    ap.add_argument("--first-revision-compilable", action="store_true",
                    help="also add wlscirep.cls and the four first-revision figures to first_revision/")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count()))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    repo_root = root.parent.parent                       # workspace repository root
    rel = Path(a.release).resolve() if a.release else root / "release"
    ann_ws = root / "data" / "interim" / "annotations"
    tables, figs, fx = root / "results" / "tables", root / "results" / "figures", root / "results" / "forensics"
    mode = "APPLY" + (" + PUSH" if a.push else "") if a.apply else "DRY RUN"
    tee = Tee(fx / "console_log_21.txt")
    sys.stdout = tee
    today = datetime.date.today().isoformat()
    try:
        head(f"PLEF V2 -- SCRIPT 21 : RELEASE CORRECTION, SECOND REVISION   v{VERSION}   [{mode}]")
        print(f"  root      : {root}")
        print(f"  release   : {rel}")
        print(f"  started   : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"  python    : {sys.version.split()[0]}   workers {a.workers}")
        if a.push and not a.apply:
            raise Stop("--push requires --apply")
        g = Git(rel)

        # ================================================================ checks
        sub("0  PRECONDITIONS")
        if not (rel / ".git").exists():
            raise Stop(f"{rel} is not a git work tree")
        branch = g.run("rev-parse", "--abbrev-ref", "HEAD").strip()
        if branch != "main":
            raise Stop(f"release is on branch {branch!r}, not main")
        url = g.run("remote", "get-url", "origin").strip()
        if not REMOTE_RE.search(url):
            raise Stop(f"origin is {url!r}, not rahul-k-mishra/plef")
        if g.run("status", "--porcelain").strip():
            raise Stop("release work tree is not clean; commit or remove the changes by hand first")
        if g.run("config", "--get", "core.autocrlf", check=False).strip() != "false":
            raise Stop("core.autocrlf is not false in the release repository (script 17 sets it)")
        if (rel / ".gitattributes").read_bytes() != b"* -text\n":
            raise Stop(".gitattributes is not exactly '* -text'")
        headc = g.rev("HEAD")
        tag_a, tag_c = g.rev(TAG_A), g.rev(TAG_C)
        print(f"  branch main, origin {url}, clean, autocrlf false, .gitattributes '* -text'")
        print(f"  HEAD {headc}; {TAG_A} {tag_a or '-'}; {TAG_C} {tag_c or '-'}")

        # manifest: every entry raw on disk
        man_path = rel / "MANIFEST-RELEASE.txt"
        man_raw = man_path.read_bytes()
        man_lines = man_raw.decode("utf-8").split("\n")
        entries = []
        for ln in man_lines:
            if ln and not ln.startswith("#"):
                p_ = ln.split()
                if len(p_) >= 3:
                    entries.append((p_[0], int(p_[1]), " ".join(p_[2:])))
        man_paths = {e[2] for e in entries}
        bad = [e[2] for e in entries if not (rel / e[2]).exists() or sha256_file(rel / e[2]) != e[0]]
        if bad:
            raise Stop(f"{len(bad)} manifest entries do not hash raw on disk, e.g. {bad[:3]}")
        print(f"  manifest: {len(entries)} entries, all hash raw on disk")

        # plan step 0: script 15 on a fresh clone
        l15 = fx / "console_log_15_before_r2.txt"
        if not l15.exists():
            raise Stop(f"{l15} missing: run 15_release_byte_audit.py on a fresh clone first (plan step 0)")
        t15 = l15.read_text(encoding="utf-8").split("\n")
        i15 = next((i for i, x in enumerate(t15) if x.startswith("FILES NEEDING A HUMAN LOOK")), None)
        if i15 is None:
            raise Stop(f"{l15} has no 'FILES NEEDING A HUMAN LOOK' section")
        sec = []                                  # the section's lines, up to its blank line
        for x in t15[i15 + 1:]:
            if not x.strip():
                break
            if set(x.strip()) <= {"-", "="}:
                continue
            sec.append(x.strip())
        # script 15 prints "none -- every mismatch is a line-ending form" when clean,
        # and one line per file otherwise
        if len(sec) != 1 or not sec[0].startswith("none"):
            raise Stop(f"{l15} lists files needing a human look; resolve them first: {sec[:5]}")
        print(f"  {l15.name}: no file needs a human look")

        # sources
        for relp, wsp, h in FIRST_REVISION:
            src = repo_root / wsp
            if not src.exists() or sha256_file(src) != h:
                raise Stop(f"first-revision source {wsp} missing or not sha256 {h[:12]}...")
        if a.first_revision_compilable:
            for fn in FIRST_REVISION_COMPILE:
                if not (repo_root / "Version_2" / "PLEF_revision" / fn).exists():
                    raise Stop(f"Version_2/PLEF_revision/{fn} missing")
        print("  first-revision sources present with the planned hashes")
        for fn, blob in COLLECTION.items():
            got = g.run("rev-parse", f"pre-revision:{fn}").strip()
            if got != blob:
                raise Stop(f"pre-revision:{fn} is blob {got}, plan says {blob}")
        print("  pre-revision collection-script blobs as planned")
        need_files = []
        for r in (1, 2, 3):
            need_files += [ann_ws / "round1_compromised" / f"rater{r}_OFFLINE.csv",
                           ann_ws / "round1_compromised" / f"annotations_rater{r}.csv",
                           ann_ws / "round3_low_reliability" / f"annotations_rater{r}.csv"]
        scripts = ["15_release_byte_audit.py", "16_offline_csv_probe.py", "17_release_byte_fix.py",
                   "18_match_counts.py", "19_human_criterion_v2.py", "20_round2_assets.py",
                   "21_release_correction_r2.py"]
        logs = ["console_log_15.txt", "console_log_15_fresh_clone.txt", "console_log_15_after_fix.txt",
                "console_log_15_before_r2.txt", "console_log_16.txt", "console_log_17.txt",
                "console_log_18.txt", "console_log_19.txt", "console_log_20.txt"]
        corpora = [c for c in ("dailydialog", "empathetic", "goemotions", "isear", "meld", "relationship",
                               "semeval2017", "tweeteval", "dev_relationship")]
        tabs = (["abstention_v2.csv", "human_criterion_v2.csv", "annotation_audit_v2.csv",
                 "release_byte_audit.csv", "release_byte_audit_after_fix.csv",
                 "supp_annotation_intervals.csv", "supp_alignment_comparison.csv",
                 "supp_corpus_sources.csv", "supp_released_text_overlap.csv"]
                + [f"match_counts_{c}.csv" for c in corpora])
        tab_src = {t: (fx / t if t.startswith("release_byte_audit") else tables / t) for t in tabs}
        figs_v2 = ["fig1_coverage_scope_v2.png", "fig4_gase_abstention_v2.png"]
        need_files += [repo_root / "Version_2" / s_ for s_ in scripts] + [fx / l_ for l_ in logs]
        need_files += list(tab_src.values()) + [figs / f_ for f_ in figs_v2]
        need_files += [root / "data" / "interim" / "corpus_relationship.csv",
                       root / "data" / "interim" / "dev_split_relationship.csv",
                       repo_root / "Version_3" / "paper" / "manuscript.tex"]
        miss = [str(p_) for p_ in need_files if not p_.exists()]
        if miss:
            raise Stop("missing source files:\n    " + "\n    ".join(miss))
        ms = (repo_root / "Version_3" / "paper" / "manuscript.tex").read_text(encoding="utf-8")
        if UNPREFIXED_PHRASE not in ms:
            raise Stop("the Section 2.2 wording for unprefixed identifiers is not in Version_3/paper/manuscript.tex")
        print(f"  all {len(need_files)} source files present; Section 2.2 wording found in the manuscript")

        # ============================================================= fingerprints
        sub("1  FINGERPRINTS OF THE 1,508 RELATIONSHIP POSTS")
        core = load_core(root / "src")
        posts = {}
        split_of = {}
        for sp, f_ in (("evaluation", "corpus_relationship.csv"),
                       ("annotation_development", "dev_split_relationship.csv")):
            rows, _, _ = read_csv_bytes((root / "data" / "interim" / f_).read_bytes())
            for r in rows:
                posts[r["id"]] = r["text"]
                split_of[r["id"]] = sp
        fp, grams8 = [], set()
        for pid, text in posts.items():
            ws_ = [WORD.findall(s_.lower()) for s_ in core.sentences(text)]
            for x in [w for w in ws_ if len(w) >= K_FILE][:3]:
                fp.append((pid, x[:K_FILE]))
            allw = WORD.findall(text.lower())
            for i in range(len(allw) - K_NOTE + 1):
                grams8.add(tuple(allw[i:i + K_NOTE]))
        print(f"  posts {len(posts)} (evaluation {sum(1 for v in split_of.values() if v == 'evaluation')}, "
              f"annotation-development {sum(1 for v in split_of.values() if v != 'evaluation')}); "
              f"12-word fingerprints {len(fp)}; distinct 8-word windows {len(grams8)}")

        def note_has_text(note):
            w = WORD.findall((note or "").lower())
            return any(tuple(w[i:i + K_NOTE]) in grams8 for i in range(len(w) - K_NOTE + 1))

        def scan(jobs):
            with Pool(a.workers, initializer=_init_fp, initargs=(fp,)) as pool:
                return pool.map(_scan, jobs, chunksize=1)

        # ================================================================ tags (step 1)
        sub("2  OPTIONAL TAGS OF THE PUSHED STATES (plan step 1)")
        if a.tag_pushed_states:
            for name, target in (("r1-pushed", P04), ("r1-byte-fixed", A6C)):
                cur = g.rev(name)
                if cur == target:
                    print(f"  {name} already at {target[:7]}")
                elif cur is not None:
                    raise Stop(f"tag {name} exists at {cur[:7]}, not {target[:7]}")
                elif a.apply:
                    g.run("tag", "-a", name, target, "-m", f"PLEF release state {target[:7]}", write=True)
                    print(f"  created {name} at {target[:7]}")
                else:
                    print(f"  would create {name} at {target[:7]}")
        else:
            print("  not requested (--tag-pushed-states)")

        # ================================================================ commit A (step 6)
        sub("3  COMMIT A: first_revision/ ALONE ON TOP OF a6c5fc7 (plan step 6)")
        fr_files = [(relp, repo_root / wsp) for relp, wsp, _ in FIRST_REVISION]
        if a.first_revision_compilable:
            fr_files += [(f"first_revision/{fn}", repo_root / "Version_2" / "PLEF_revision" / fn)
                         for fn in FIRST_REVISION_COMPILE]
        if tag_a:
            parent = g.run("rev-parse", f"{tag_a}^").strip()
            if parent != A6C:
                raise Stop(f"{TAG_A} exists but its parent is {parent[:7]}, not a6c5fc7")
            changed = sorted(g.run("diff", "--name-only", A6C, tag_a).split())
            frp = [x for x in changed if x.startswith("first_revision/")]
            if sorted(changed) != sorted(frp + ["MANIFEST-RELEASE.txt"]) or \
                    not set(p_ for p_, _ in fr_files[:3]) <= set(frp):
                raise Stop(f"{TAG_A} changes {changed}, not just first_revision/ and the manifest")
            man_a = parse_manifest(g.raw("show", f"{tag_a}:MANIFEST-RELEASE.txt"))
            for f_ in frp:
                b_ = g.raw("show", f"{tag_a}:{f_}")
                if man_a.get(f_) != (sha256_bytes(b_), len(b_)):
                    raise Stop(f"the manifest at {TAG_A} does not list {f_} with its hash and size")
            for relp, wsp, h in FIRST_REVISION:
                if sha256_bytes(g.raw("show", f"{tag_a}:{relp}")) != h:
                    raise Stop(f"{TAG_A}:{relp} does not have sha256 {h[:12]}...")
            print(f"  {TAG_A} exists at {tag_a[:7]} and verifies against its own manifest; commit A skipped")
        else:
            if headc != A6C:
                raise Stop(f"HEAD is {headc[:7]}, not a6c5fc7, and {TAG_A} does not exist")
            om = g.rev("refs/remotes/origin/main")
            if om != A6C:
                raise Stop(f"origin/main is {om and om[:7]}, not a6c5fc7; fetch and inspect first")
            res = scan([(p_, src.read_bytes()) for p_, src in fr_files if not p_.endswith(".png")])
            hits = [(l_, h_) for l_, h_ in res if h_]
            for l_, h_ in res:
                print(f"  scan {l_:<46} posts found {len(h_)}")
            if hits:
                raise Stop(f"post text found in first-revision files: {[(l_, len(h_)) for l_, h_ in hits]}")
            if a.apply:
                for p_, src in fr_files:
                    dst = rel / p_
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                blk_a = ["# ---------------------------------------------------------------------------",
                         f"# AMENDMENT {today} (commit A, tag {TAG_A}; script 21 v{VERSION})",
                         "# Added folder first_revision/: the manuscript source, the PDF exactly as uploaded",
                         "#   to the journal, and the supplementary (SUPPLEMENTARY.md) of the first revision,",
                         f"#   so that tag {TAG_A} preserves the paper the reviewers read together with the",
                         "#   repository they examined. Nothing else in the repository changes in this commit.",
                         "# Added entries:"]
                for p_, src in sorted(fr_files):
                    b_ = (rel / p_).read_bytes()
                    blk_a.append(f"{sha256_bytes(b_)}  {len(b_)}  {p_}")
                blk_a.append(f"# AMENDMENT {today} (commit A) ends; {len(fr_files)} entries added.")
                man_path.write_bytes(amend(man_path.read_bytes(), blk_a))
                g.run("add", "--", "first_revision", "MANIFEST-RELEASE.txt", write=True)
                staged = g.run("diff", "--cached", "--name-only").split()
                if sorted(staged) != sorted([p_ for p_, _ in fr_files] + ["MANIFEST-RELEASE.txt"]):
                    raise Stop(f"staged {staged}, expected only first_revision/ and the manifest")
                g.run("commit", "-m", "Add the first-revision manuscript, the PDF as uploaded and the "
                      "first-revision supplementary (second-revision release correction, step 6)", write=True)
                tag_a = g.rev("HEAD")
                g.run("tag", "-a", TAG_A, tag_a, "-m",
                      "Repository as reviewed in the first revision, with the paper the reviewers read", write=True)
                print(f"  commit A {tag_a[:7]}; tagged {TAG_A}")
            else:
                print(f"  would copy {len(fr_files)} files, append a manifest block listing them, "
                      f"commit them alone and tag {TAG_A}")

        # ================================================================ commit B
        sub("4  COMMIT B: THE CORRECTION (plan steps 2-5, 7, 8)")

        def is_commit_b(c):
            if not c or not tag_a or g.run("rev-parse", f"{c}^", check=False).strip() != tag_a:
                return False
            return all(subprocess.run(["git", "-C", str(rel), "--no-optional-locks", "cat-file", "-e",
                                       f"{c}:{m_}"], capture_output=True).returncode == 0 for m_ in B_MARKERS)

        commit_b = None
        if tag_c:
            cb = g.run("rev-parse", f"{tag_c}^").strip()
            if not is_commit_b(cb):
                raise Stop(f"{TAG_C} exists but its parent is not a commit B on top of {TAG_A}")
            changed = sorted(g.run("diff", "--name-only", cb, tag_c).split())
            if "logs/console_log_21.txt" not in changed or "MANIFEST-RELEASE.txt" not in changed or \
                    not set(changed) <= set(C_FILES) | {"MANIFEST-RELEASE.txt"}:
                raise Stop(f"{TAG_C} changes {changed}, not just the logs and the manifest")
            man_c = parse_manifest(g.raw("show", f"{tag_c}:MANIFEST-RELEASE.txt"))
            for f_ in changed:
                if f_ != "MANIFEST-RELEASE.txt":
                    b_ = g.raw("show", f"{tag_c}:{f_}")
                    if man_c.get(f_) != (sha256_bytes(b_), len(b_)):
                        raise Stop(f"the manifest at {TAG_C} does not list {f_} with its hash and size")
            commit_b = cb
            print(f"  {TAG_C} exists at {tag_c[:7]} on commit B {cb[:7]} and verifies; commits B and C skipped")
        elif is_commit_b(g.rev("HEAD")):
            commit_b = g.rev("HEAD")
            print(f"  HEAD {commit_b[:7]} is commit B (untagged, parent {TAG_A}); commit B skipped")
        else:
            if a.apply and g.rev("HEAD") != tag_a:
                raise Stop(f"HEAD is not {TAG_A}; commit B must sit directly on commit A")
            readme = (rel / "README.md").read_text(encoding="utf-8")
            if OLD_README not in readme:
                raise Stop("release README.md does not contain the sentence to be replaced")
            # source identities
            for r in (1, 2, 3):
                if sha256_file(rel / "annotation" / "rejected" / f"rater{r}_OFFLINE.csv") != \
                        sha256_file(ann_ws / "round1_compromised" / f"rater{r}_OFFLINE.csv"):
                    raise Stop(f"release rater{r}_OFFLINE.csv is not the round-1 original")
                if sha256_file(rel / "annotation" / "rejected" / f"annotations_rater{r}.csv") != \
                        sha256_file(ann_ws / "round3_low_reliability" / f"annotations_rater{r}.csv"):
                    raise Stop(f"release rejected/annotations_rater{r}.csv is not the round-3 record")
            print("  release round-1 sheets and round-3 records are byte-identical to the workspace originals")
            new = {}          # release path -> bytes
            moves = []        # (old path, new path)
            removed_notes = []

            # ---- step 2: drop numbered_text; (b) notes scan; (c) long fields
            sub("4.2  ROUND-1 SHEETS: DROP numbered_text (step 2)")
            long_fields = []
            for r in (1, 2, 3):
                src = rel / "annotation" / "rejected" / f"rater{r}_OFFLINE.csv"
                b = src.read_bytes()
                if not b.startswith(b"\xef\xbb\xbf"):
                    raise Stop(f"{src.name} has no UTF-8 BOM")
                rows, cols, _ = read_csv_bytes(b)
                if cols != KEEP_COLS[:4] + ["numbered_text"] + KEEP_COLS[4:]:
                    raise Stop(f"{src.name} columns are {cols}")
                for row in rows:
                    if note_has_text(row["notes"]):
                        removed_notes.append((f"rater{r}_OFFLINE.csv", row["row_key"]))
                        row["notes"] = ""
                out = io.StringIO()
                w = csv.writer(out, lineterminator="\r\n")
                w.writerow(KEEP_COLS)
                for row in rows:
                    w.writerow([row[c] for c in KEEP_COLS])
                nb = b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")
                back, bcols, _ = read_csv_bytes(nb)
                if bcols != KEEP_COLS or len(back) != len(rows):
                    raise Stop(f"{src.name}: re-read check failed")
                orig, _, _ = read_csv_bytes(b)
                for o, n_ in zip(orig, back):
                    for c in KEEP_COLS:
                        if c == "notes" and (f"rater{r}_OFFLINE.csv", o["row_key"]) in removed_notes:
                            continue
                        if o[c] != n_[c]:
                            raise Stop(f"{src.name}: field {c} of {o['row_key']} changed")
                    for c in KEEP_COLS:
                        if len(n_[c]) > LONG_FIELD:
                            long_fields.append((src.name, n_["row_key"], c, len(n_[c])))
                new[f"annotation/round1_rejected/rater{r}_OFFLINE.csv"] = nb
                moves.append((f"annotation/rejected/rater{r}_OFFLINE.csv",
                              f"annotation/round1_rejected/rater{r}_OFFLINE.csv"))
                print(f"  rater{r}_OFFLINE.csv: {len(rows)} rows, {len(b):,} -> {len(nb):,} bytes; "
                      f"every kept field identical; columns {', '.join(KEEP_COLS)}")
            print(f"  retained fields longer than {LONG_FIELD} characters: {len(long_fields)}")
            for x in long_fields:
                print(f"    INSPECT {x[0]} row_key {x[1]} column {x[2]} length {x[3]}")

            # ---- step 3 (+a, b): rounds
            sub("4.3  ONE FOLDER PER ROUND (step 3; departures a, b)")
            for r in (1, 2, 3):
                moves.append((f"annotation/rejected/annotations_rater{r}.csv",
                              f"annotation/round3/annotations_rater{r}.csv"))
            moves += [("annotation/annotations_rater1.csv", "annotation/round4/annotations_rater1.csv"),
                      ("annotation/gold_dev200.csv", "annotation/round4/gold_dev200.csv"),
                      ("annotation/rejected/gold_dev200.csv", "annotation/derived/gold_dev200_rejected_folder.csv"),
                      ("annotation/gold_dev200_UNUSABLE_alpha0.177.csv",
                       "annotation/derived/gold_dev200_UNUSABLE_alpha0.177.csv")]
            for old, _ in moves:
                if not (rel / old).exists():
                    raise Stop(f"{old} not in the release work tree")
            r2_rows = {}
            for r in (1, 2, 3):
                b = (ann_ws / "round1_compromised" / f"annotations_rater{r}.csv").read_bytes()
                rows, cols, enc = read_csv_bytes(b)
                if "notes" not in cols:
                    raise Stop(f"round-2 annotations_rater{r}.csv has no notes column")
                hit = [row for row in rows if note_has_text(row["notes"])]
                for row in hit:
                    removed_notes.append((f"round2 annotations_rater{r}.csv", f"slot {row['slot']}"))
                    row["notes"] = ""
                if hit:
                    out = io.StringIO()
                    w = csv.DictWriter(out, fieldnames=cols, lineterminator="\r\n" if b"\r\n" in b[:4096] else "\n")
                    w.writeheader()
                    w.writerows(rows)
                    b = (b"\xef\xbb\xbf" if b.startswith(b"\xef\xbb\xbf") else b"") + out.getvalue().encode("utf-8")
                new[f"annotation/round2_rejected/annotations_rater{r}.csv"] = b
                r2_rows[r] = len(rows)
                print(f"  round 2 rater {r}: {len(rows)} rows; notes with post text: {len(hit)}")
            print(f"  notes blanked because they contain post text (8-word test): {len(removed_notes)}")
            for f_, k_ in removed_notes:
                print(f"    REMOVED note: {f_} {k_}")
            # derived/ README (a)
            hc = {x["key"]: x for x in read_csv_bytes((tables / "human_criterion_v2.csv").read_bytes())[0]}
            three = hc["r3_posts_by_three"]["value"]
            dl = ["# annotation/derived", "",
                  "Two gold files whose round of origin is not recorded. They were kept by the annotation tooling "
                  "under the paths given below; file times suggest a round, but file times are not a record, so "
                  "no round is assigned. Neither file enters any result in the paper.", ""]
            for newp, oldp in (("gold_dev200_rejected_folder.csv", "annotation/rejected/gold_dev200.csv"),
                               ("gold_dev200_UNUSABLE_alpha0.177.csv", "annotation/gold_dev200_UNUSABLE_alpha0.177.csv")):
                rows, cols, _ = read_csv_bytes((rel / oldp).read_bytes())
                dl.append(f"- `{newp}` (formerly `{oldp}`): {len(rows)} rows; columns {', '.join(cols)}. "
                          "The round it was produced from is not recorded.")
                if "UNUSABLE" in newp:
                    dl.append(f"  Its name refers to an alpha of 0.177, the round-3 sentiment value, but it has "
                              f"{len(rows)} rows while {three} posts were labelled by all three round-3 "
                              "annotators; the discrepancy is unexplained and is stated here rather than resolved.")
            new["annotation/derived/README.md"] = ("\n".join(dl) + "\n").encode("utf-8")
            al = ["# annotation", "",
                  "One folder per annotation round. Rater indices are assigned within each round, so the same "
                  "index in different rounds denotes different people; ten people took part in all, three in each "
                  "of rounds 1 to 3 and one in round 4.", "",
                  "| folder | round | instrument | status |", "|---|---|---|---|",
                  "| `round1_rejected/` | 1 | spreadsheet | rejected: identical turning points across annotators |",
                  "| `round2_rejected/` | 2 | spreadsheet | rejected: all-or-none field matches across 600 comparisons |",
                  "| `round3/` | 3 | spreadsheet | retained: source of the reliability estimates |",
                  "| `round4/` | 4 | web tool | retained: single annotator, preliminary comparison with the metric |",
                  "| `derived/` | not recorded | - | see `derived/README.md` |", "",
                  "Only round 4 recorded active time, revision counts and scroll-to-end; the round-2 and round-3 "
                  "files carry zeros in those fields and the round-1 spreadsheets have none.", "",
                  f"Until {today} the round-1 spreadsheets also carried a `numbered_text` column holding the full "
                  "text of the 200 annotation-development posts as numbered for annotation. That column was removed "
                  "on that date; every other column is unchanged. The earlier versions remain in the repository's "
                  f"history, which was not rewritten; the reviewed state is preserved at tag `{TAG_A}`.", ""]
            if removed_notes:
                al += [f"{len(removed_notes)} annotator notes were blanked because they contained post text; "
                       "the rows are listed in console_log_21.txt.", ""]
            new["annotation/README.md"] = ("\n".join(al)).encode("utf-8")

            # ---- step 4 (+d): identifier list
            sub("4.4  IDENTIFIER LIST (step 4; departure d)")
            known = ["relationship_advice", "relationships", "survivinginfidelity", "emotionalsupport",
                     "confession", "heartbreak", "BreakUps", "NarcissisticAbuse"]
            out = io.StringIO()
            w = csv.writer(out, lineterminator="\n")
            w.writerow(["id", "subreddit", "reddit_post_id", "split"])
            cnt = collections.Counter()
            for pid in sorted(posts, key=lambda x: (split_of[x] != "evaluation", x)):
                s_ = next((k for k in sorted(known, key=len, reverse=True) if pid.startswith(k + "_")), "")
                rid = pid[len(s_) + 1:] if s_ else pid
                w.writerow([pid, s_, rid, split_of[pid]])
                cnt[(split_of[pid], s_ or "(none)")] += 1
            new["corpus/relationship_post_ids.csv"] = out.getvalue().encode("utf-8")
            ne = sum(v for (sp, _), v in cnt.items() if sp == "evaluation")
            nd = sum(v for (sp, _), v in cnt.items() if sp != "evaluation")
            ue, ud = cnt[("evaluation", "(none)")], cnt[("annotation_development", "(none)")]
            if cnt[("evaluation", "NarcissisticAbuse")] or cnt[("annotation_development", "NarcissisticAbuse")]:
                raise Stop("an identifier carries a NarcissisticAbuse prefix; the README wording would be wrong")
            for k_, v_ in sorted(cnt.items()):
                print(f"  {k_[0]:<24}{k_[1]:<22}{v_:>6}")
            cr = ["# corpus", "",
                  f"`relationship_post_ids.csv`: the {ne + nd:,} relationship posts ({ne:,} evaluation, {nd} "
                  "annotation-development) by identifier. Columns: `id` as used in the analysis, `subreddit` "
                  "parsed from the identifier's prefix, `reddit_post_id` (the identifier without the prefix) and "
                  "`split`. No post text is included.", "",
                  f"For the {ue + ud} identifiers without a prefix ({ue} evaluation, {ud} annotation-development) "
                  "the `subreddit` column is empty. These posts " + UNPREFIXED_PHRASE + ".", "",
                  "The posts can be retrieved by identifier through the public Reddit API for as long as they "
                  "remain available; deleted posts cannot be recovered.", ""]
            new["corpus/README.md"] = ("\n".join(cr)).encode("utf-8")

            # ---- step 5: collection scripts
            sub("4.5  COLLECTION SCRIPTS (step 5)")
            for fn, blob in COLLECTION.items():
                b = g.raw("show", f"pre-revision:{fn}")
                h = g.run("hash-object", "--stdin", inp=b).strip()
                if h != blob:
                    raise Stop(f"{fn}: recovered bytes hash to blob {h}, not {blob}")
                new[f"collection/{fn}"] = b
                print(f"  collection/{fn}: {len(b):,} bytes, blob {blob[:10]} verified")
            ext = new["collection/extended_reddit_download.py"].decode("utf-8")
            subs8 = re.findall(r'"name"\s*:\s*"([^"]+)"', ext)
            cl = ["# collection", "",
                  "The two collection scripts, recovered byte-exact from the `pre-revision` tag.", "",
                  "- These are the scripts as they stood on 2026-05-20.",
                  f"- `extended_reddit_download.py` queries {len(subs8)} subreddits ({', '.join(subs8)}); the corpus "
                  "contains posts carrying the prefixes of seven of them, and none carries a NarcissisticAbuse "
                  "prefix. `reddit_download.py` queries r/relationship_advice and writes bare identifiers.",
                  "- The exact settings and date of the collection run that produced the 1,508-post file are not "
                  "recorded beyond the corpus file date, 10 May 2026.", ""]
            new["collection/README.md"] = ("\n".join(cl)).encode("utf-8")

            # ---- step 7 (+e): scripts, logs, tables, figures, README
            sub("4.7  SCRIPTS, LOGS, TABLES, FIGURES, README (step 7; departure e)")
            for s_ in scripts:
                new[f"scripts/{s_}"] = (repo_root / "Version_2" / s_).read_bytes()
            for l_ in logs:
                new[f"logs/{l_}"] = (fx / l_).read_bytes()
            for t_, src in tab_src.items():
                new[f"tables/{t_}"] = src.read_bytes()
            for f_ in figs_v2:
                new[f"figures/{f_}"] = (figs / f_).read_bytes()
            readme_new = readme.replace(OLD_README,
                "The relationship corpus consists of public Reddit\n"
                "posts. The post text is not part of this release: `corpus/` lists the\n"
                "posts by identifier and `collection/` holds the collection scripts. Until\n"
                f"{today} the round-1 annotation spreadsheets carried the text of the 200\n"
                "annotation-development posts; see `annotation/README.md`. The first-revision\n"
                f"manuscript and supplementary are in `first_revision/` (tag `{TAG_A}`).")
            readme_new = readme_new.replace("Aggregate release hash:",
                "The aggregate hash below describes the release as generated on 2026-09-01; the dated amendment\n"
                "block at the end of `MANIFEST-RELEASE.txt` lists every file added or changed since.\n\n"
                "Aggregate release hash:")
            new["README.md"] = readme_new.encode("utf-8")
            print(f"  {len(scripts)} scripts, {len(logs)} logs, {len(tab_src)} tables, {len(figs_v2)} figures; README corrected")

            # ---- pre-commit scan of every new or changed file (step 9.1, done before commit)
            sub("4.9  POST-TEXT SCAN OF EVERY NEW OR CHANGED FILE, BEFORE COMMIT")
            res = scan([(p_, b_) for p_, b_ in sorted(new.items()) if not p_.endswith(".png")])
            hits = [(l_, h_) for l_, h_ in res if h_]
            print(f"  {len(res)} files scanned; files with post text: {len(hits)}")
            for l_, h_ in hits:
                print(f"    {l_}: {len(h_)} posts")
            if hits:
                raise Stop("post text found in files to be committed; nothing written")

            # ---- step 8: manifest amendment
            sub("4.8  MANIFEST AMENDMENT (step 8)")
            man_raw = man_path.read_bytes()            # re-read: commit A may have amended it in this run
            man_paths = set(parse_manifest(man_raw))
            superseded = [(o, n_) for o, n_ in moves if o in man_paths]
            added = {}
            for p_, b_ in new.items():
                added[p_] = (sha256_bytes(b_), len(b_))
            for o, n_ in moves:
                if n_ not in new:
                    b_ = (rel / o).read_bytes()
                    added[n_] = (sha256_bytes(b_), len(b_))
            blk = ["# ---------------------------------------------------------------------------",
                   f"# AMENDMENT {today} (second revision, reviewer 3 point 5; script 21 v{VERSION})",
                   "# Removed column numbered_text from the three round-1 annotation sheets (post",
                   f"#   text; public from 2026-09-01 13:47:41 IST until {today}; commits 9cd1c08,",
                   "#   a956c9c, 04bdc4f, a6c5fc7; history not rewritten).",
                   f"# first_revision/ was added in commit A (tag {TAG_A}) and is listed in that",
                   "#   commit's amendment block above; it is not repeated here.",
                   "# Two gold files of unrecorded round moved to annotation/derived/.",
                   "# README.md, LICENSE.txt and MANIFEST-RELEASE.txt are not manifest entries.",
                   "# Superseded entries (paths moved or changed; the lines above are kept as the",
                   "# record of the reviewed state):"]
            blk += [f"#   {o}  ->  {n_}" for o, n_ in superseded]
            blk.append("# Added entries:")
            blk += [f"{h}  {nb}  {p_}" for p_, (h, nb) in sorted(added.items()) if p_ != "README.md"]
            blk.append(f"# AMENDMENT {today} ends; {sum(1 for p_ in added if p_ != 'README.md')} entries added, "
                       f"{len(superseded)} superseded.")
            man_new = amend(man_raw, blk)
            print(f"  {len(superseded)} superseded, {len(added) - ('README.md' in added)} added; existing lines untouched")

            if not a.apply:
                print()
                print("  DRY RUN: nothing written. Planned moves:")
                for o, n_ in moves:
                    print(f"    git mv {o} {n_}")
                print(f"  planned new or changed files: {len(new)}")
            else:
                for o, n_ in moves:
                    (rel / n_).parent.mkdir(parents=True, exist_ok=True)
                    g.run("mv", o, n_, write=True)
                for p_, b_ in new.items():
                    dst = rel / p_
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(b_)
                man_path.write_bytes(man_new)
                # verify every amended entry on disk before committing
                for p_, (h, nb) in added.items():
                    if p_ != "README.md" and sha256_file(rel / p_) != h:
                        raise Stop(f"{p_} on disk does not match its amendment entry")
                if (rel / "annotation" / "rejected").exists() and any((rel / "annotation" / "rejected").iterdir()):
                    raise Stop("annotation/rejected/ is not empty after the moves")
                g.run("add", "-A", write=True)
                g.run("commit", "-m", "Second-revision release correction: post text removed from the "
                      "round-1 sheets, one folder per round, identifier list and collection scripts, scripts "
                      "15-21 with logs, tables and figures, manifest amendment (script 21)", write=True)
                commit_b = g.rev("HEAD")
                print(f"  commit B {commit_b[:7]} (untagged; {TAG_C} goes on commit C)")

        # ================================================================ verification
        sub("5  VERIFICATION (plan step 9.1)")
        target = tag_c or commit_b
        if target:
            files = g.run("ls-tree", "-r", "--name-only", target).split("\n")
            files = [f_ for f_ in files if f_ and not f_.endswith(".png") and not f_.endswith(".pdf")]
            res = scan([(f_, g.raw("show", f"{target}:{f_}")) for f_ in files])
            hits = [(l_, h_) for l_, h_ in res if h_]
            print(f"  tree of {target[:7]}: {len(res)} text files scanned; files with post text: {len(hits)}")
            if hits:
                raise Stop(f"post text in the corrected tree: {[(l_, len(h_)) for l_, h_ in hits]}")
            objs = g.run("rev-list", "--objects", target).split("\n")
            shas = sorted({o.split()[0] for o in objs if " " in o and not o.endswith((".png", ".pdf"))})
            types = g.run("cat-file", "--batch-check", inp=("\n".join(shas) + "\n").encode()).split("\n")
            blobs = [t_.split()[0] for t_ in types if t_ and t_.split()[1] == "blob"]
            res = scan([(b_, g.raw("cat-file", "blob", b_)) for b_ in blobs])
            hist = [(l_, h_) for l_, h_ in res if h_]
            evp = sorted({p_ for _, h_ in hist for p_ in h_ if split_of.get(p_) == "evaluation"})
            dvp = sorted({p_ for _, h_ in hist for p_ in h_ if split_of.get(p_) != "evaluation"})
            print(f"  history reachable from {target[:7]}: {len(blobs)} blobs; blobs with post text: {len(hist)} "
                  f"(expected: the six earlier versions of the round-1 sheets)")
            for l_, h_ in hist:
                print(f"    blob {l_[:10]}: {len(h_)} posts")
            print(f"  posts found in history: {len(dvp)} annotation-development, {len(evp)} evaluation "
                  f"(evaluation posts quoted inside annotation-development posts)")
        else:
            print("  nothing committed yet (dry run); verification runs after commit B")

        # ================================================================ push
        sub("6  PUSH (plan step 10)")
        def push(ref):
            r = subprocess.run(["git", "-C", str(rel), "push", "origin", ref], capture_output=True, text=True)
            if r.returncode != 0:
                raise Stop(f"git push origin {ref} was rejected; not forcing:\n{r.stderr}")

        if a.push:
            if commit_b is None:
                raise Stop("no commit B to push")
            push("main")
            for name in ("r1-pushed", "r1-byte-fixed", TAG_A):
                if g.rev(name):
                    push(f"refs/tags/{name}")
                    print(f"  pushed tag {name}")
            refl = g.run("reflog", "show", "--date=iso-strict", "-1", "refs/remotes/origin/main").strip()
            print(f"  pushed main: {refl}")
            if not tag_c:
                m = re.search(r"@\{([^}]+)\}", refl)
                print(f"  <<DATE:correction>> = {m.group(1) if m else 'read it from the line above'}"
                      "  (the push that removed the post text from the current version)")

            # ======================================================== commit C
            sub("7  COMMIT C: THE CONSOLE LOGS, THEN TAG r2-corrected (after verification and push)")
            if tag_c:
                push(f"refs/tags/{TAG_C}")
                print(f"  {TAG_C} exists and verifies; commit C skipped; tag pushed by name (no-op if up to date)")
            else:
                if g.rev("HEAD") != commit_b or g.run("status", "--porcelain").strip():
                    raise Stop("HEAD is not commit B or the work tree is not clean; commit C not made")
                l15a = fx / "console_log_15_after_r2.txt"
                if l15a.exists():
                    print("  console_log_15_after_r2.txt exists and is added")
                else:
                    print("  console_log_15_after_r2.txt does not exist: commit C carries console_log_21.txt "
                          "alone; run script 15 on a fresh clone and add its log in a later commit")
                print(f"  the copy of this log in commit C ends with this line "
                      f"({datetime.datetime.now().isoformat(timespec='seconds')})")
                tee.flush()
                c_new = {"logs/console_log_21.txt": (fx / "console_log_21.txt").read_bytes()}
                if l15a.exists():
                    c_new["logs/console_log_15_after_r2.txt"] = l15a.read_bytes()
                res = scan(sorted(c_new.items()))
                if any(h_ for _, h_ in res):
                    raise Stop("post text found in the logs for commit C; nothing written")
                for p_, b_ in c_new.items():
                    (rel / p_).parent.mkdir(parents=True, exist_ok=True)
                    (rel / p_).write_bytes(b_)
                blk_c = [f"# AMENDMENT {today} (commit C, tag {TAG_C}): console logs added after verification "
                         f"and push: {', '.join(sorted(c_new))}."]
                blk_c += [f"{sha256_bytes(b_)}  {len(b_)}  {p_}" for p_, b_ in sorted(c_new.items())]
                man_path.write_bytes(amend(man_path.read_bytes(), blk_c))
                g.run("add", "--", *sorted(c_new), "MANIFEST-RELEASE.txt", write=True)
                staged = g.run("diff", "--cached", "--name-only").split()
                if sorted(staged) != sorted(list(c_new) + ["MANIFEST-RELEASE.txt"]):
                    raise Stop(f"staged {staged}, expected only the logs and the manifest")
                g.run("commit", "-m", "Add the console logs of the release correction (script 21"
                      + (" and script 15 after it" if l15a.exists() else "") + ")", write=True)
                tag_c = g.rev("HEAD")
                g.run("tag", "-a", TAG_C, tag_c, "-m", "State cited by the second revision", write=True)
                push("main")
                push(f"refs/tags/{TAG_C}")
                print(f"  commit C {tag_c[:7]}; tagged {TAG_C}; main and {TAG_C} pushed")
            print("  next: run 15_release_byte_audit.py on a fresh clone of the pushed state (plan step 9.2)")
        else:
            print("  not pushed. Commit C and tag r2-corrected are made only by a --push run, after main and the")
            print("  tags are pushed. To push: rerun with --apply --push (by name; never forces)")
        head("DONE")
        return 0
    except Stop as e:
        print()
        print(f"  STOPPED: {e}")
        head("STOPPED -- nothing further was done")
        return 2
    finally:
        print(f"  finished  : {datetime.datetime.now().isoformat(timespec='seconds')}")
        sys.stdout = tee.stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(main())
