## Previous version

The implementation and results of the previous version of this work, which
this evaluation corrects, are preserved at the `pre-revision` tag:
https://github.com/rahul-k-mishra/plef/tree/pre-revision

# PLEF V2 -- analysis release

Generated 2026-09-01T13:38:40 by
`scripts/09_release_assembly.py` v09.4.0.

This release exists so that every provenance claim in the manuscript can be
checked rather than taken on trust.

## Contents

| path | what it is |
|---|---|
| `DECISIONS.md` | analysis choices, each timestamped before the corresponding output |
| `AUDIT_RECONCILIATION.md` | reconciliation of item counts, throughput, chance benchmarks |
| `MANIFEST-RELEASE.txt` | SHA-256 and size for every file in this release |
| `manifest/` | input manifests with source-file checksums |
| `src/` | the framework core, its lexicons, the baseline adapter, the purity test |
| `scripts/` | every pipeline stage, and the annotation tools with their integrity checks |
| `scored/` | one row per document per corpus: the raw outputs behind every table |
| `tables/` | every table in the manuscript, machine-readable |
| `figures/` | the figures |
| `annotation/` | responses for all annotation rounds, including the rejected ones |
| `logs/` | the console log for every pipeline stage |
| `requirements-lock.txt` | the environment that produced these results |

## Reproducing

The framework core (`src/plef_core.py`) imports only the Python standard
library; `src/plef_purity.py` verifies this by importing it in a fresh process
with third-party packages blocked. The evaluation harness does require third
party packages, listed in `requirements-lock.txt`.

The NRC lexicons are distributed by their author under a research licence and
are not redistributed here. The relationship corpus consists of public Reddit
posts; the collection scripts are included and the post text is not
redistributed.

## Verifying this release

    python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" <file>

and compare against `MANIFEST-RELEASE.txt`.

Aggregate release hash: `bdbea69ceaa7d20666207bd2b849ece742fe8d8e6f6e64ba57612dc69483211a`
