# Audit reconciliation

Generated 2026-08-30T16:07:55 by scripts/08_audit_reconciliation.py v08.3.1.

Every figure below is rebuilt from the raw records. The manuscript
quotes these values; none is edited by hand.

## Throughput

- evaluation words scored: 5,501,892
- elapsed: 61.3 minutes
- rate: 1,496 words/s

Per-shard rates differ from the overall rate and must not be
quoted alongside the overall elapsed time.

## Item accounting

- scored documents: 309,833
- after within-corpus deduplication: 288,110 (-21,723)
- after cross-corpus deduplication: 265,452 (-22,658)

Cross-corpus overlaps, unordered pairs:

| corpus A | corpus B | shared items |
|---|---|---:|
| semeval2017 | tweeteval | 22,603 |
| goemotions | meld | 45 |
| goemotions | semeval2017 | 3 |
| dailydialog | goemotions | 2 |
| empathetic | goemotions | 2 |
| empathetic | isear | 1 |
| goemotions | tweeteval | 1 |
| isear | meld | 1 |
| meld | semeval2017 | 1 |

## Coverage by document-length band

| band (words) | corpora | min | max |
|---|---:|---:|---:|
| 1-9 | 7 | 7.2% | 23.8% |
| 10-19 | 7 | 18.1% | 36.2% |
| 20-39 | 7 | 25.8% | 50.5% |
| 40-79 | 5 | 40.0% | 81.8% |
| 80-159 | 3 | 62.5% | 86.3% |
| 160-319 | 1 | 97.6% | 97.6% |
| 320+ | 1 | 99.6% | 99.6% |

## Random three-class benchmark

Mean macro-F1 over 1,000 independent uniform assignments.

| corpus | n | mean | 2.5% | 97.5% |
|---|---:|---:|---:|---:|
| dailydialog | 101,026 | 0.2364 | 0.2341 | 0.2387 |
| goemotions | 54,263 | 0.3268 | 0.3229 | 0.3306 |
| meld | 13,708 | 0.326 | 0.3182 | 0.3331 |
| semeval2017 | 52,806 | 0.3194 | 0.3154 | 0.3234 |
| tweeteval | 59,899 | 0.3234 | 0.3197 | 0.3271 |

## Human turning-point chance rates

- comparison posts: 19
- exact match, mean of 1/N_i: 4.3%
- within one sentence, mean of min(1, 3/N_i): 12.9%

## Archetype resolution

| corpus | n | resolved | % |
|---|---:|---:|---:|
| dailydialog | 101,026 | 6,589 | 6.5% |
| dev_relationship | 200 | 177 | 88.5% |
| empathetic | 19,157 | 2,104 | 11.0% |
| goemotions | 54,263 | 4,454 | 8.2% |
| isear | 7,666 | 981 | 12.8% |
| meld | 13,708 | 541 | 3.9% |
| relationship | 1,308 | 1,153 | 88.1% |
| semeval2017 | 52,806 | 4,573 | 8.7% |
| tweeteval | 59,899 | 5,206 | 8.7% |

