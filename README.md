# PLEF: A Neuro-Symbolic Psycholinguistic Framework

**Psycholinguistic Lexical Extraction Framework for Computational Analysis of Relationship Narratives**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![No Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)]()

---

## About

PLEF is a dependency-free, theory-grounded, neuro-symbolic Python framework for extracting psycholinguistic features from relationship narratives. It combines symbolic lexical analysis with Latent Semantic Analysis (LSA) embeddings to compute twelve novel psycholinguistic metrics grounded in validated psychological theory.

This repository contains the source code, analysis scripts, and pre-computed results associated with the manuscript:

> **Mishra, R.K. (2026). PLEF: A Neuro-Symbolic Psycholinguistic Framework for Computational Analysis of Relationship Narratives.** *Scientific Reports, Springer Nature.*

**Author:** Rahul Kumar Mishra  
**Email:** mishra.rahul98@gmail.com  
**Affiliation:** Independent Researcher, Bengaluru, Karnataka, India

---

## Key Features

- **12 psycholinguistic metrics** — each grounded in peer-reviewed psychological theory
- **No external dependencies** — runs on Python standard library only
- **Fully offline** — no API calls, no internet required after setup
- **Per-sentence attribution** — every score traceable to specific tokens and theory
- **Bootstrap confidence intervals** — 500 resamples on all key metrics
- **Clinical risk auditing** — six risk categories flagged with mandatory disclaimers
- **Windows 7 compatible** — tested on Python 3.8.10

---

## The Twelve PLEF Metrics

| Metric | Full Name | Theory |
|--------|-----------|--------|
| LEWI | Linguistic Emotional Watershed Index | Page (1954); Duck (2011) |
| TEG | Temporal Emotional Gradient | Kuppens et al. (2010) |
| NAVA | Narrative Arc Valence Asymmetry | Reagan et al. (2016) |
| GASE | Gottman-Attachment-Sentiment Entropy | Gottman & Silver (2015) |
| PTI | Pronoun Triangulation Index | Pennebaker (2011) |
| RCI | Relational Coherence Index | Turney & Pantel (2010) |
| PAI | Power Asymmetry Index | Gottman & Silver (2015) |
| CD-index | Cognitive Distortion Signature | Burns (2020) |
| VADS | Vulnerability-Authenticity Disclosure Score | Pennebaker (2011) |
| TIES | Temporal Inconsistency Entropy Score | Shannon (1948) |
| NSPL | Neuro-Symbolic Psycholinguistic Layer | Deerwester et al. (1990) |
| RASP | Relationship Arc Story Pattern | McAdams & McLean (2013) |

---

## Repository Structure

```
plef/
│
├── plef_v7.py                          # Main PLEF framework (core file)
├── auto_analysis.py                    # Single corpus analysis pipeline
├── multi_dataset_analysis.py          # Multi-dataset analysis pipeline
├── experimental_design.py             # Hypothesis testing and validation
├── extended_reddit_download.py        # Multi-subreddit data collection
├── reddit_download.py                 # Reddit data downloader
├── get_gold_labels.py                 # Gold label acquisition
├── fix_all.py                         # Bug fix and patch utility
├── run_everything.bat                 # One-click Windows runner
├── lewi_annotations_TEMPLATE.csv     # Human annotation template for LEWI
├── pti_dominance_annotations_TEMPLATE.csv  # Human annotation template for PTI
│
└── results/
    ├── COMBINED/
    │   ├── master_report.txt          # Summary across all 9 datasets
    │   ├── cross_dataset_comparison.csv
    │   └── paper_table_all_datasets.txt
    │
    ├── EXPERIMENTAL/
    │   ├── pre_registered_hypotheses.txt
    │   ├── ablation_all_datasets.csv
    │   ├── mcnemar_all_datasets.csv
    │   ├── pti_dominance_all_datasets.csv
    │   ├── teg_instability_all_datasets.csv
    │   ├── lewi_validation_all_datasets.txt
    │   └── COMBINED_experimental_report.txt
    │
    ├── reddit_relationship/           # Per-dataset results
    ├── goemotions/
    ├── empathetic/
    ├── semeval2017/
    ├── meld/
    ├── tweeteval/
    ├── consensus/
    ├── isear/
    └── dailydialog/
```

---

## Quick Start

**Requirements:** Python 3.8 or higher. No pip installs needed.

**Optional:** Install colorama for coloured terminal output:
```
pip install colorama
```

### Run on a single text

```python
import plef_v7 as plef

text = """
We were so happy together at first. Everything felt perfect and full of hope.
But slowly things began to change. He became distant and cold towards me.
Now I feel completely alone even when we are in the same room together.
I do not know how we got here or how to fix what we have broken.
"""

result = plef.analyse_text(text)
print(result)
```

### Run on your own corpus

1. Place your CSV file in the PLEF folder. It must have a column called `text`.
2. Double-click `run_auto_analysis.bat`
3. Results saved to `results/` folder

### Run on all 9 benchmark datasets

```
python multi_dataset_analysis.py
```

Type `A` when asked and press Enter. Downloads all datasets automatically and runs full analysis.

### Run experimental validation suite

```
python experimental_design.py
```

Type `A` when asked. Runs all hypothesis tests, ablation studies, and McNemar significance tests across all available datasets.

---

## Evaluation Results

PLEF was evaluated on 9 benchmark datasets totalling **150,041 items**.

| Dataset | N | PLEF F1 | PLEF AUC | Cohen's d |
|---------|---|---------|----------|-----------|
| Reddit Relationship | 10,000 | 0.463 | 0.633 | 0.759 |
| GoEmotions | 50,000 | 0.446 | 0.627 | 0.777 |
| EmpatheticDialogues | 30,000 | 0.427 | 0.607 | 0.793 |
| SemEval-2017 Task 4 | 10,000 | 0.468 | 0.628 | 0.747 |
| MELD | 9,881 | 0.330 | 0.537 | 0.313 |
| TweetEval | 15,000 | 0.427 | 0.600 | 0.657 |
| DailyDialog | 13,118 | 0.298 | 0.500 | — |
| ISEAR | 2,042 | 0.270 | 0.500 | — |
| Consensus (silver) | 10,000 | 0.605 | 0.838 | 2.246 |
| **Mean** | **150,041** | **0.415** | **0.608** | |

**Key finding:** NAVA × LEWI structural coherence r = 0.638 to 0.850 across all 9 datasets (all p < 0.001).

Full results are in the `results/` folder. See `results/COMBINED/master_report.txt` for the complete summary.

---

## Datasets

The following publicly available datasets were used for evaluation. They are not included in this repository. Download them from their original sources:

| Dataset | Source |
|---------|--------|
| GoEmotions | https://github.com/google-research/google-research/tree/master/goemotions |
| EmpatheticDialogues | https://github.com/facebookresearch/EmpatheticDialogues |
| SemEval-2017 Task 4 | http://alt.qcri.org/semeval2017/task4 |
| MELD | https://github.com/declare-lab/MELD |
| TweetEval | https://github.com/cardiffnlp/tweeteval |
| DailyDialog | http://yanran.li/dailydialog |
| ISEAR | https://www.unige.ch/cisa/research/materials-and-online-research/research-material |

Reddit data was collected from public posts using the Reddit JSON API in compliance with Reddit's Terms of Service. Raw post content is not redistributed. The collection script `extended_reddit_download.py` is provided so others can reproduce the corpus.

---

## Pre-Registered Hypotheses

Seven hypotheses were registered before data collection to prevent HARKing:

| ID | Metric | Result |
|----|--------|--------|
| H1 | LEWI | Supported (proxy: NAVA×LEWI r = 0.638–0.850) |
| H2 | PTI | Supported (6/9 datasets, all p < 0.001) |
| H3 | TEG | Not supported (TEG×TIES ≈ 0 across datasets) |
| H4 | GASE | Pending (human annotation required) |
| H5 | NAVA | Partial |
| H6 | CD-index | Partial |
| H7 | System | Supported (McNemar p < 0.05 on 8/9 datasets) |

Full details in `results/EXPERIMENTAL/pre_registered_hypotheses.txt`

---

## Ethical Statement

All PLEF outputs are probabilistic linguistic indicators derived from word-level patterns. They are not clinical diagnoses, psychological assessments, or forensic instruments. Six high-risk inference categories are flagged with mandatory exploratory disclaimers aligned with APA Ethical Principles (2017).

Reddit data was collected from public posts in compliance with Reddit's Terms of Service. All usernames were anonymised. No personally identifiable information was retained.

---

## Citation

If you use PLEF in your research, please cite:

```
@article{mishra2026plef,
  title={PLEF: A Neuro-Symbolic Psycholinguistic Framework for 
         Computational Analysis of Relationship Narratives},
  author={Mishra, Rahul Kumar},
  journal={Scientific Reports},
  publisher={Springer Nature},
  year={2026}
}
```

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.

---

## Contact

Rahul Kumar Mishra  
mishra.rahul98@gmail.com  
Bengaluru, Karnataka, India
