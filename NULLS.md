# Null distributions and formal tests

Generated 2026-08-31T23:31:04 by scripts/10_null_analysis.py v10.5.0.

RNG: Python `random.Random`, seed 20260830 for the permutation null, 20260831 for the i.i.d. null, 20260832 for the random walk.

Observed NAVA x LEWI on 1,288 documents: r = +0.5979

| null | draws | mean r | SD | 95% interval | p |
|---|---:|---:|---:|---|---:|
| within-document permutation | 1000 | +0.6070 | 0.0267 | [+0.5542, +0.6605] | 0.6304 |
| synthetic i.i.d. normal | 1000 | +0.5948 | 0.0232 | [+0.5480, +0.6387] | 0.4655 |
| synthetic random walk | 1000 | +0.8494 | 0.0090 | [+0.8313, +0.8662] | 1.0000 |

Empirical p is the proportion of null draws at least as large as the observed correlation, with the usual +1 correction:
p = (1 + #[null r >= observed r]) / (draws + 1).

## Generating processes

- **Within-document permutation.** Each document's observed sentence-level values are randomly reordered; the multiset is preserved exactly and only the order changes.
- **Synthetic i.i.d.** N values per document from Normal(0, 0.2488), where the scale is the pooled SD of the observed sentence scores; lengths matched.
- **Synthetic random walk.** s_1 = 0; s_t = clip(s_(t-1) + e_t, -1, +1), e_t ~ Normal(0, 0.2678), where the step scale is the SD of the observed absolute successive differences; lengths matched.

## Smoothing

The centred moving average uses half-width w = max(1, floor(N/4)); the window at position i is [max(0, i-w), min(N, i+w+1)), truncated at the boundaries and never padded. The window is 2w+1 wide in the interior, so the parity of w does not arise.

