# PLEF V1 -- Forensic Defect Record

Generated: 2026-08-28T22:34:01
Script: 01_bootstrap_and_forensics.py v01.1.0
V1 source: `D:\Research\PLEF\Old\PLEF`
Evidence artifacts hashed: 111

This document records defects found in the pipeline that produced the
submitted manuscript. It is the factual basis for the disclosure section
of the response letter. Every statement here is reproducible by re-running
script 01 against the hashed artifacts listed in MANIFEST/.

## F1/F2 -- Gold label integrity

| dataset | N | gold classes | majority label | majority share | degenerate |
|---|---:|---:|---|---:|---|
| consensus | 10,000 | 3 | neu | 86.8% | no |
| dailydialog | 13,118 | 1 | neu | 100.0% | **YES** |
| empathetic | 30,000 | 3 | neu | 39.6% | no |
| goemotions | 50,000 | 3 | pos | 40.0% | no |
| isear | 2,042 | 1 | neu | 100.0% | **YES** |
| meld | 9,881 | 3 | neu | 46.1% | no |
| reddit_relationship | 10,000 | 3 | neu | 39.0% | no |
| semeval2017 | 10,000 | 3 | neu | 46.3% | no |
| tweeteval | 15,000 | 3 | neu | 45.5% | no |

**2 corpora have a single-class gold vector.** On these, macro-AUC
is undefined (reported as 0.500), Cohen's d is 0.000 by construction, and
accuracy measures only the rate at which a system guesses the majority class:

| dataset | PLEF majority-guess rate | VADER majority-guess rate |
|---|---:|---:|
| dailydialog | 80.6% | 30.4% |
| isear | 68.2% | 77.6% |

## F3 -- Baseline authenticity

| named system | embedded entries | published size | ratio |
|---|---:|---:|---:|
| VADER | 100 | ~7,500 | 1.3% |
| NRC | 60 | ~14,182 | 0.4% |
| LIWC | 88 | ~12,000 | 0.7% |

Duplicate dictionary keys found: `{'_NRC_SEEDS': ['happy', 'disgust']}`

Source self-describes these as simplified: **True**

The manuscript (Section 4.3) states VADER was run "using the published
rule-based algorithm". The embedded implementation has no intensifier
handling, no punctuation amplification, no capitalisation handling and no
degree modifiers. That sentence must be corrected.

## F4 -- Ablation validity

The published GASE ablation subtracts a hardcoded constant instead of
removing a component. Located at:

- `experimental_design.py.bak` line 261 (hardcoded_0.5): `removed = [r["gase"] - w*0.5 for r in results]`
- `experimental_design.py.bak` line 337 (rci_x0.7): `rci_no_stop = [r*0.7 for r in rci_vals]  # approx: stop word removal reduces Jaccard ~30%`

Present in shipped (non-backup) code: **False**

Consequence, exactly:

| component | weight | published delta | weight x 0.5 |
|---|---:|---:|---:|
| entropy | 0.25 | -0.1250 | -0.1250 |
| attachment | 0.25 | -0.1250 | -0.1250 |
| horsemen | 0.20 | -0.1000 | -0.1000 |

Reconstructed true entropy+attachment term, computed exactly from the shipped
result files as `gase - 0.30*S - 0.20*(1-G)`:

| dataset | true 0.25(1-H)+0.25(1-A) | assumed by ablation | n |
|---|---:|---:|---:|
| consensus | 0.4644 (sd 0.0869) | 0.2500 | 10,000 |
| dailydialog | 0.4068 (sd 0.1193) | 0.2500 | 13,118 |
| empathetic | 0.4524 (sd 0.0974) | 0.2500 | 30,000 |
| goemotions | 0.4609 (sd 0.0904) | 0.2500 | 50,000 |
| isear | 0.4632 (sd 0.0878) | 0.2500 | 2,042 |
| meld | 0.4795 (sd 0.0685) | 0.2500 | 9,881 |
| reddit_relationship | 0.4444 (sd 0.1034) | 0.2500 | 10,000 |
| semeval2017 | 0.4664 (sd 0.0849) | 0.2500 | 10,000 |
| tweeteval | 0.4679 (sd 0.0831) | 0.2500 | 15,000 |

## F5 -- Table reproducibility from shipped result files

| dataset | PTI mean recomputed | Table 4 | reproduces | Table 7 | reproduces |
|---|---:|---:|---|---:|---|
| consensus | 0.1306 | 0.131 | yes | 0.126 | **NO** |
| dailydialog | 0.0232 | 0.023 | yes | 0.052 | **NO** |
| empathetic | 0.5016 | 0.502 | yes | 0.494 | **NO** |
| goemotions | 0.101 | 0.101 | yes | 0.101 | yes |
| isear | 0.4267 | None | - | 0.427 | yes |
| meld | 0.0622 | 0.062 | yes | 0.064 | **NO** |
| reddit_relationship | 0.1531 | 0.153 | yes | 0.155 | **NO** |
| semeval2017 | 0.0989 | 0.099 | yes | 0.084 | **NO** |
| tweeteval | 0.0889 | 0.089 | yes | 0.082 | **NO** |

Tables 4 and 7 report the same quantity. If one reproduces and the other does
not, the manuscript contains numbers from two different pipeline runs.

## F6 -- Table 5 valid-N filter recovery

Every plausible filter rule was tried against each corpus. A rule 'recovers'
Table 5 only if it reproduces both the published N and the published r.

**consensus** -- paper reports n=70, r=0.832

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 23 | 0.9022 | no | no |
| arc!=short_text | 146 | 0.8006 | no | no |
| n_sents>=4 | 146 | 0.8006 | no | no |
| n_sents>=6 | 2 | None | no | no |
| lewi_drop!=0 | 40 | 0.8103 | no | no |
| nava!=0 & lewi!=0 | 23 | 0.9022 | no | no |
| arc & n>=4 | 146 | 0.8006 | no | no |
| arc & lewi!=0 | 40 | 0.8103 | no | no |
| n>=4 & lewi!=0 | 40 | 0.8103 | no | no |

**dailydialog** -- paper reports n=4671, r=0.742

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 5,676 | 0.7861 | no | no |
| arc!=short_text | 12,519 | 0.7318 | no | no |
| n_sents>=4 | 12,519 | 0.7318 | no | no |
| n_sents>=6 | 10,861 | 0.7151 | no | no |
| lewi_drop!=0 | 7,674 | 0.732 | no | no |
| nava!=0 & lewi!=0 | 5,627 | 0.7879 | no | no |
| arc & n>=4 | 12,519 | 0.7318 | no | no |
| arc & lewi!=0 | 7,674 | 0.732 | no | no |
| n>=4 & lewi!=0 | 7,674 | 0.732 | no | no |

**empathetic** -- paper reports n=334, r=0.725

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 529 | 0.853 | no | no |
| arc!=short_text | 2,412 | 0.7248 | no | yes |
| n_sents>=4 | 2,412 | 0.7248 | no | yes |
| n_sents>=6 | 175 | 0.7137 | no | no |
| lewi_drop!=0 | 1,344 | 0.7287 | no | yes |
| nava!=0 & lewi!=0 | 521 | 0.858 | no | no |
| arc & n>=4 | 2,412 | 0.7248 | no | yes |
| arc & lewi!=0 | 1,344 | 0.7287 | no | yes |
| n>=4 & lewi!=0 | 1,344 | 0.7287 | no | yes |

**goemotions** -- paper reports n=67, r=0.807

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 155 | 0.8827 | no | no |
| arc!=short_text | 645 | 0.807 | no | yes |
| n_sents>=4 | 645 | 0.807 | no | yes |
| n_sents>=6 | 19 | 0.855 | no | no |
| lewi_drop!=0 | 264 | 0.8094 | no | yes |
| nava!=0 & lewi!=0 | 155 | 0.8827 | no | no |
| arc & n>=4 | 645 | 0.807 | no | yes |
| arc & lewi!=0 | 264 | 0.8094 | no | yes |
| n>=4 & lewi!=0 | 264 | 0.8094 | no | yes |

**isear** -- paper reports n=28, r=0.638

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 11 | 0.2261 | no | no |
| arc!=short_text | 28 | 0.6376 | yes | yes |
| n_sents>=4 | 28 | 0.6376 | yes | yes |
| n_sents>=6 | 3 | None | no | no |
| lewi_drop!=0 | 16 | 0.4579 | no | no |
| nava!=0 & lewi!=0 | 11 | 0.2261 | no | no |
| arc & n>=4 | 28 | 0.6376 | yes | yes |
| arc & lewi!=0 | 16 | 0.4579 | no | no |
| n>=4 & lewi!=0 | 16 | 0.4579 | no | no |

**meld** -- paper reports n=176, r=0.835

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 30 | 0.8664 | no | no |
| arc!=short_text | 333 | 0.7831 | no | no |
| n_sents>=4 | 333 | 0.7831 | no | no |
| n_sents>=6 | 32 | 0.8429 | no | no |
| lewi_drop!=0 | 52 | 0.7721 | no | no |
| nava!=0 & lewi!=0 | 30 | 0.8664 | no | no |
| arc & n>=4 | 333 | 0.7831 | no | no |
| arc & lewi!=0 | 52 | 0.7721 | no | no |
| n>=4 & lewi!=0 | 52 | 0.7721 | no | no |

**reddit_relationship** -- paper reports n=163, r=0.779

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 86 | 0.8637 | no | no |
| arc!=short_text | 320 | 0.7786 | no | yes |
| n_sents>=4 | 320 | 0.7786 | no | yes |
| n_sents>=6 | 4 | None | no | no |
| lewi_drop!=0 | 152 | 0.7813 | no | yes |
| nava!=0 & lewi!=0 | 86 | 0.8637 | no | no |
| arc & n>=4 | 320 | 0.7786 | no | yes |
| arc & lewi!=0 | 152 | 0.7813 | no | yes |
| n>=4 & lewi!=0 | 152 | 0.7813 | no | yes |

**semeval2017** -- paper reports n=166, r=0.758

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 70 | 0.8683 | no | no |
| arc!=short_text | 342 | 0.7578 | no | yes |
| n_sents>=4 | 342 | 0.7578 | no | yes |
| n_sents>=6 | 10 | None | no | no |
| lewi_drop!=0 | 115 | 0.7675 | no | no |
| nava!=0 & lewi!=0 | 70 | 0.8683 | no | no |
| arc & n>=4 | 342 | 0.7578 | no | yes |
| arc & lewi!=0 | 115 | 0.7675 | no | no |
| n>=4 & lewi!=0 | 115 | 0.7675 | no | no |

**tweeteval** -- paper reports n=120, r=0.789

| filter | n | r | n matches | r matches |
|---|---:|---:|---|---|
| nava!=0 | 69 | 0.8622 | no | no |
| arc!=short_text | 358 | 0.7894 | no | yes |
| n_sents>=4 | 358 | 0.7894 | no | yes |
| n_sents>=6 | 17 | 0.8787 | no | no |
| lewi_drop!=0 | 123 | 0.7953 | no | no |
| nava!=0 & lewi!=0 | 69 | 0.8622 | no | no |
| arc & n>=4 | 358 | 0.7894 | no | yes |
| arc & lewi!=0 | 123 | 0.7953 | no | no |
| n>=4 & lewi!=0 | 123 | 0.7953 | no | no |

## F7 -- Structural null: NAVA x LEWI

V1's own compute_nava and compute_lewi run on sequences containing no
narrative structure whatsoever.

| noise model | trials | mean r | min | max |
|---|---:|---:|---:|---:|
| iid_uniform | 12 | 0.686 | 0.654 | 0.711 |
| iid_normal_matched | 12 | 0.697 | 0.677 | 0.731 |
| zero_inflated | 12 | 0.705 | 0.664 | 0.762 |
| random_walk | 12 | 0.898 | 0.883 | 0.911 |

The manuscript reports observed r in [0.638, 0.85] and presents it as convergent
validity. Compare against the table above, in particular the autocorrelated
model, which is the appropriate null for real sentence sentiment.

## F8 -- Mechanical null: PTI x PAI

Random pronoun counts. No text. PAI's I_dom term is built from the same
counts as PTI, signed versus absolute.

| regime | trials | mean r | min | max |
|---|---:|---:|---:|---:|
| unrestricted | 12 | 0.146 | 0.135 | 0.163 |
| I_ge_You | 12 | 0.554 | 0.549 | 0.563 |

All nine corpora have positive mean PTI, so all nine sit in the I >= You regime.

## F9 -- Repository hygiene

Distinct version identifiers found: `['3.0', '4.0', '5.0', '6.0', '7.2.0', '7.3.0']` (conflict: **True**)

Reviewer-facing artifacts present in the repository:

| file | marker |
|---|---|
| plef_v7.py | response_language_generator |
| plef_v7.py | verbatim_framing_template |
| plef_v7.py | standard_reply_script |
| plef_v7.py | placeholder_statistic |
| plef_v7.py | latex_paper_generator |
| plef_v7.py | reviewer_summary_module |
| plef_v7_orig.py | response_language_generator |
| plef_v7_orig.py | verbatim_framing_template |
| plef_v7_orig.py | standard_reply_script |
| plef_v7_orig.py | placeholder_statistic |
| plef_v7_orig.py | latex_paper_generator |
| plef_v7_orig.py | reviewer_summary_module |

These must be deleted before the repository is made public. A reviewer
who finds a module that generates reviewer-response prose with
placeholder statistics will not read the rest of the submission charitably.

Backup files shipped in repo: 7 (auto_analysis.py.bak, experimental_design.py.bak, extended_reddit_download.py.bak, get_gold_labels.py.bak, multi_dataset_analysis.py.bak, plef_v7.py.bak ...)

## Disclosure checklist for the response letter

Each item below is a statement in the submitted manuscript that this record
shows to be incorrect. Each must be named explicitly in the response.

1. Two dataset loaders produced single-class gold vectors (dailydialog, isear). All reported F1/AUC/d for these corpora are artifacts, and both are included in the abstract's headline means (macro-F1 0.415, macro-AUC 0.608) and in the 150,041 item total.
2. Section 5.7's 'most striking' McNemar result on DailyDialog reflects majority-class guessing on a single-class label vector, not superior handling of dialogue. Section 6.3's '>83% neutral' figure is also wrong.
3. Section 4.3 states VADER was run 'using the published rule-based algorithm'. The embedded lexicon holds 100 entries against roughly 7,500 in the published system, with no intensifier, punctuation or capitalisation handling. The same applies to the NRC and LIWC baselines. All of Table 3 must be recomputed against real implementations.
4. The Consensus silver standard is defined by agreement among these three simplified reimplementations, which share a tokenizer and overlapping vocabulary. It is not three independent systems, and VADER's 1.000 score on it is definitional.
5. Table 8 is not an ablation. Three of its four rows subtract weight x 0.5, a hardcoded constant; the component values were never read. The conclusions in Sections 3.4 and 5.6 that rest on it are withdrawn.
6. Tables 4 and 7 report the same PTI means but disagree on 7 of 9 corpora. Table 4 reproduces from the shipped result files; Table 7 does not. The manuscript combines two pipeline runs.
7. Table 5's valid-N population cannot be recovered from the shipped result files for 8 of 9 corpora under any tested filter. The Data Availability statement's claim that the pre-computed files allow independent verification of all reported statistics is therefore not correct as written.
8. The NAVA x LEWI correlation reported as the central finding (r = 0.638-0.85) does not exceed its structural null; unstructured sequences reach mean r = 0.898. The metrics are two pre-minus-post mean differences over the same signal. Sections 5.3 and 6.1, the abstract and the conclusion are rewritten accordingly.
9. PAI's I_dom term is built from the same pronoun counts as PTI. With random counts and no text, r reaches 0.554 in the regime all nine corpora occupy. H2 is reported as mechanically confounded, not as construct validation.
10. The abstract states PTI 'correlates significantly with PAI in six of nine datasets'. It is significant in all nine; six exceed an arbitrary r > 0.25 threshold. The wording is corrected.
11. The reported NAVA x LEWI range upper bound of 0.85 does not appear anywhere in Table 5, whose maximum is 0.835.
12. Sections 3 and Contribution 4 claim bootstrap confidence intervals over 500 resamples. No confidence interval appears in the manuscript. Intervals are added throughout.
