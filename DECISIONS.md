# PLEF V2 -- Declared analysis decisions

Written 2026-08-29T00:03:34 by scripts/02_baseline_environment.py v02.4.0.

Every arbitrary choice in the evaluation pipeline is recorded here BEFORE
any corpus-level result is computed. Each entry states what was chosen,
why, and whether it was decided before or after observing any output.
This answers Reviewer 2 point 6, which asked for a deviation table
separating confirmatory from post hoc analysis. It cannot retroactively
register the original submission. It registers this one.

## Baseline systems

| system | source | size | licence |
|---|---|---:|---|
| VADER | vaderSentiment reference implementation | 7506 | MIT |
| NRC EmoLex | Mohammad & Turney 2013 v0.92 | 6453 | research, non-redistributable |
| Empath | Fast, Chen & Bernstein CHI 2016 | 194 categories | open |
| AFINN | Nielsen 2011, AFINN-en-165 | 3382 | ODbL |
| Hu-Liu | Hu & Liu 2004, via NLTK | 6789 | free |
| labMT | Dodds & Danforth | 10222 | free |

LIWC-22 is NOT used: it is proprietary and no licence is held. Empath
occupies that role; Fast et al. report mean r = 0.906 with LIWC across a
mixed corpus. The word 'LIWC' must not name a baseline in the manuscript.

## Declared choices

### D1 Empath polarity category set
Chosen: broad set, 19 positive and 26 negative built-in categories.

**Provenance: POST HOC.** The narrow set (positive_emotion and
negative_emotion only) was tried first and returned exactly 0.000 on two
of five hand-written known-answer sentences, which would have entered the
results as a degenerate all-neutral baseline. The broad set was then
adopted. Categories were selected by NAME only, judged on five
hand-written sentences, and never tuned against any evaluation corpus.
Both variants are scored; see the sensitivity table below.

### D2 AFINN normalisation
Chosen primary: sum / (5 * sqrt(n_tokens)).

**Provenance: ARBITRARY, no published basis.** AFINN returns an unbounded
integer sum, so some normalisation is required for comparability. Four
variants (sqrt, dens, mean, tanh) are implemented and all four reported.

### D3 labMT scoring
Stop band [4.0, 6.0] discarded as neutral; remainder averaged, centred at
5.0, divided by 4.0. This is the standard labMT procedure. labMTsimple's
own stopper() raises TypeError in the current release and is bypassed.

**labMT measures happiness, not polarity. Its zero point is not neutral**
**and it is strongly positively shifted on ordinary text.** This must be
stated wherever labMT is reported.

### D4 Classification threshold
A single +/-0.05 threshold, inherited from VADER's convention, applied
uniformly to every system. It is not natural for AFINN, Empath, Hu-Liu or
labMT.

**Consequence: macro-F1 is threshold-conditional.** Primary reporting is
macro-AUC, which is threshold-free. A full threshold sweep is reported so
the sensitivity is visible rather than buried.

### D5 Legacy V1 lexicons
The three simplified lexicons from the original submission are extracted
verbatim from plef_v7.py by AST and scored alongside the real systems.
They appear ONLY in supplementary material, solely to quantify the
magnitude of the error in the submitted Table 3. They must never be
presented under the names VADER, NRC or LIWC.

### D6 NRC companion lexicons are instruments, not baselines
NRC-VAD and NRC Emotion Intensity are external criteria, not comparison
systems:

- VAD dominance is an independent criterion for PAI, because dominance is
  annotated without reference to any pronoun count. Addresses Reviewer 2
  point 7 (PTI and PAI share their inputs).
- Emotion-intensity sequences are an independent criterion for TEG,
  because they are not derived from PLEF's own compound score. Addresses
  Reviewer 1 point 2 (TEG has no validation target).

Neither appears in the baseline comparison table.

### D8 Smoke-test text is held out
The verification preview in script 02 is scored on genuine relationship
posts that were never used in any V1 evaluation, proved disjoint by
normalised-text SHA-1 against every evaluation text reconstructible
locally. No decision in this file was derived from an evaluation
corpus. The preview measures throughput, coverage and inter-system
agreement only; it produces no number that appears in the manuscript.

### D7 Known-answer test tiering
Core sentences (unambiguous polarity, no negation) are asserted for
every system. Negation sentences are reported for every system but
asserted only for VADER and the V1 VADER toy, which are the only two
that implement negation handling. NRC, Empath, Hu-Liu and labMT are pure
bag-of-words lexicons; asserting negation for them would assert a
capability they do not claim. Their negation failures are reported as a
genuine limitation.

## Still to be declared (script 03)

- ISEAR label mapping. ISEAR has no neutral class, so joy -> positive and
  fear/anger/sadness/disgust/shame/guilt -> negative makes it a binary
  problem inside a three-class evaluation.
- DailyDialog 'surprise' polarity, which has no defensible mapping.
- NAVA five-class scheme, which the implementation uses and the manuscript
  reports as three.

## Sensitivity measured at declaration time

| variant | mean | sd | %pos | %neu | %neg |
|---|---:|---:|---:|---:|---:|
| afinn:sqrt | +0.0187 | 0.2145 | 43.4% | 19.9% | 36.8% |
| afinn:dens | +0.0036 | 0.0618 | 17.9% | 67.7% | 14.4% |
| afinn:mean | +0.0108 | 0.1528 | 39.2% | 28.0% | 32.8% |
| afinn:tanh | +0.0703 | 0.8748 | 52.7% | 2.0% | 45.3% |
| empath:broad | -0.0030 | 0.3582 | 42.0% | 13.5% | 44.5% |
| empath:narrow | -0.1641 | 0.4797 | 28.2% | 15.0% | 56.7% |

---

## Corpus decisions (script 03 v03.2.0, 2026-08-29T00:26:37)

### D9 DailyDialog label mapping
happiness -> positive; anger, disgust, fear, sadness -> negative;
no_emotion -> neutral; **surprise -> neutral**. Surprise has no
defensible polarity. The alternative (excluding surprise items) is
reported as a sensitivity check. Declared before any evaluation.

Note: V1 stored these fields as numpy array reprs, e.g. [0 6 0 0 3 0],
which ast.literal_eval cannot parse; V1's except clause then set every
emotion to 0, producing a 100% neutral gold vector. Parsed here by regex.

### D10 ISEAR is BINARY and reported separately
ISEAR has no neutral class: joy -> positive; anger, sadness, disgust,
shame, fear, guilt -> negative. This makes it a two-class problem inside
a three-class evaluation, so **ISEAR is reported separately and excluded
from any pooled three-class mean.** Forcing three classes would make every
neutral prediction automatically wrong and would misrepresent the result.
The resulting class balance is roughly 14% positive / 86% negative and
must be stated wherever ISEAR appears.

### D11 The relationship corpus is rebuilt from genuine posts
V1's loader read reddit_posts_corpus_original.csv, which is 100%
GoEmotions comment text (median 14 words). The corpus described in the
manuscript is rebuilt here from reddit_posts_corpus.csv plus
reddit_posts/*.txt: genuine first-person narratives from seven
subreddits, median 370 words. The item count falls from a claimed
10,000 to roughly 1,500, and the population on which the trajectory
metrics are computable rises from 1.6% to about 98%.

### D12 Development split
200 relationship posts, seed 20260829, reserved and
excluded from every evaluation. All smoke tests, threshold sweeps and
sensitivity analyses use only this split. Hash recorded in the manifest.
This corrects a leak in script 02, whose preview was computed on posts
that subsequently became evaluation data.

### D13 GoEmotions and EmpatheticDialogues mappings
GoEmotions uses the sentiment groupings of Demszky et al. (2020);
an item is positive or negative by majority of its mapped labels and
neutral on a tie or an ambiguous-only labelling. EmpatheticDialogues
maps its 32 emotion labels to three classes by a fixed list declared
in the loader source. Neither mapping was tuned against any result.

### D15 Minimum length filter on the relationship corpus
Posts shorter than 20 words are excluded. Inherited from V1,
declared here, and the number dropped is reported in the log and manifest.

### D16 EmpatheticDialogues is BINARY
The 32-emotion to 3-class mapping leaves under 1% neutral (22 of 19,167).
It is therefore evaluated and reported as two-class, exactly as ISEAR is.
A three-class macro-F1 over a class that barely exists is not meaningful.

### D17 Declared text edit in ISEAR
The ISEAR distribution contains a stray U+00E1 used as a line-continuation
artefact; it is replaced with a space. The count of items touched is
reported. No other corpus text is modified anywhere in the pipeline.

### D18 The relationship corpus carries NO labels
An earlier draft of this loader wrote 'neu' for the reddit_posts/*.txt
files, which have no label. That is fabricating gold data -- the same
failure mode as V1's ISEAR loader -- and has been removed. The 1,316 CSV
posts carry V1's unaudited keyword silver labels, which are retained only
as a v1_silver reference column and are never used as gold.

The corpus is therefore TRAJECTORY-ONLY: LEWI, TEG, NAVA, PTI, PAI, RCI
and coverage are computed on it; no macro-F1 or AUC is. The validation
gate enforces this and refuses any corpus whose labels the loader
invented.

Human labels for the 200-post dev split are collected via the annotation
task written to data/interim/annotations/. That task is the direct test
of H1 that Reviewers 1, 2 and 3 all asked for. Until it is returned, H1
is reported as NOT TESTED.

### D19 The Consensus corpus is quarantined
Rebuilt from the real VADER, NRC and Hu-Liu implementations rather than
the V1 toys. Its labels are DEFINED by lexicon agreement, so any lexicon
method is advantaged by construction. In V1 it contributed F1 = 0.605 and
AUC = 0.838 to the abstract's headline means while VADER scored exactly
1.000 on it. In V2 it is excluded from every headline result and reported
only as a supplementary sanity check, clearly marked.

### D14 labMT is not a polarity baseline
On held-out relationship text labMT labelled 97.8% of posts positive and
its Cohen's kappa against every other system was between 0.013 and 0.039.
It measures happiness, not polarity, and no threshold makes it a
three-class classifier. It is therefore removed from the baseline
comparison and used instead as an INDEPENDENT ARC INSTRUMENT for NAVA,
which is how Reagan et al. (2016) use it. Declared before any evaluation.


---

## Corpus decisions (script 03 v03.3.0, 2026-08-29T01:05:43)

### D9 DailyDialog label mapping
happiness -> positive; anger, disgust, fear, sadness -> negative;
no_emotion -> neutral; **surprise -> neutral**. Surprise has no
defensible polarity. The alternative (excluding surprise items) is
reported as a sensitivity check. Declared before any evaluation.

Note: V1 stored these fields as numpy array reprs, e.g. [0 6 0 0 3 0],
which ast.literal_eval cannot parse; V1's except clause then set every
emotion to 0, producing a 100% neutral gold vector. Parsed here by regex.

### D10 ISEAR is BINARY and reported separately
ISEAR has no neutral class: joy -> positive; anger, sadness, disgust,
shame, fear, guilt -> negative. This makes it a two-class problem inside
a three-class evaluation, so **ISEAR is reported separately and excluded
from any pooled three-class mean.** Forcing three classes would make every
neutral prediction automatically wrong and would misrepresent the result.
The resulting class balance is roughly 14% positive / 86% negative and
must be stated wherever ISEAR appears.

### D11 The relationship corpus is rebuilt from genuine posts
V1's loader read reddit_posts_corpus_original.csv, which is 100%
GoEmotions comment text (median 14 words). The corpus described in the
manuscript is rebuilt here from reddit_posts_corpus.csv plus
reddit_posts/*.txt: genuine first-person narratives from seven
subreddits, median 370 words. The item count falls from a claimed
10,000 to roughly 1,500, and the population on which the trajectory
metrics are computable rises from 1.6% to about 98%.

### D12 Development split
200 relationship posts, seed 20260829, reserved and
excluded from every evaluation. All smoke tests, threshold sweeps and
sensitivity analyses use only this split. Hash recorded in the manifest.
This corrects a leak in script 02, whose preview was computed on posts
that subsequently became evaluation data.

### D13 GoEmotions and EmpatheticDialogues mappings
GoEmotions uses the sentiment groupings of Demszky et al. (2020);
an item is positive or negative by majority of its mapped labels and
neutral on a tie or an ambiguous-only labelling. EmpatheticDialogues
maps its 32 emotion labels to three classes by a fixed list declared
in the loader source. Neither mapping was tuned against any result.

### D20 Trajectory metrics are scoped to the relationship corpus
LEWI, TEG and NAVA require at least four sentences. Measured across
the rebuilt corpora, the fraction of items meeting that bar is:

| corpus | items >=4 sentences | share |
|---|---:|---:|
| relationship | 1,288 | 98.5% |
| semeval2017 | 3,040 | 6.1% |
| tweeteval | 2,584 | 4.3% |
| dailydialog | 3,892 | 3.9% |
| isear | 296 | 3.9% |
| meld | 354 | 2.6% |
| goemotions | 914 | 1.7% |
| empathetic | 290 | 1.5% |

On seven of eight corpora the surviving fraction is under 7%, and it
is not a random 7%: it is the long tail of an overwhelmingly
short-form distribution. Reporting a correlation over that tail and
presenting it as a property of the corpus is precisely the
non-random restriction Reviewer 3 objected to (50,000 items reduced
to 67 on GoEmotions).

**LEWI, TEG and NAVA are therefore reported on the relationship**
**corpus only.** For every other corpus these metrics are reported as
not measurable, with the >=4-sentence count stated so the reader can
see why. Declared before any trajectory result is computed.

### D15 Minimum length filter on the relationship corpus
Posts shorter than 20 words are excluded. Inherited from V1,
declared here, and the number dropped is reported in the log and manifest.

### D16 EmpatheticDialogues is BINARY
The 32-emotion to 3-class mapping leaves under 1% neutral (22 of 19,167).
It is therefore evaluated and reported as two-class, exactly as ISEAR is.
A three-class macro-F1 over a class that barely exists is not meaningful.

### D17 Declared text edit in ISEAR
The ISEAR distribution contains a stray U+00E1 used as a line-continuation
artefact; it is replaced with a space. The count of items touched is
reported. No other corpus text is modified anywhere in the pipeline.

### D18 The relationship corpus carries NO labels
An earlier draft of this loader wrote 'neu' for the reddit_posts/*.txt
files, which have no label. That is fabricating gold data -- the same
failure mode as V1's ISEAR loader -- and has been removed. The 1,316 CSV
posts carry V1's unaudited keyword silver labels, which are retained only
as a v1_silver reference column and are never used as gold.

The corpus is therefore TRAJECTORY-ONLY: LEWI, TEG, NAVA, PTI, PAI, RCI
and coverage are computed on it; no macro-F1 or AUC is. The validation
gate enforces this and refuses any corpus whose labels the loader
invented.

Human labels for the 200-post dev split are collected via the annotation
task written to data/interim/annotations/. That task is the direct test
of H1 that Reviewers 1, 2 and 3 all asked for. Until it is returned, H1
is reported as NOT TESTED.

### D19 The Consensus corpus is quarantined
Rebuilt from the real VADER, NRC and Hu-Liu implementations rather than
the V1 toys. Its labels are DEFINED by lexicon agreement, so any lexicon
method is advantaged by construction. In V1 it contributed F1 = 0.605 and
AUC = 0.838 to the abstract's headline means while VADER scored exactly
1.000 on it. In V2 it is excluded from every headline result and reported
only as a supplementary sanity check, clearly marked.

### D14 labMT is not a polarity baseline
On held-out relationship text labMT labelled 97.8% of posts positive and
its Cohen's kappa against every other system was between 0.013 and 0.039.
It measures happiness, not polarity, and no threshold makes it a
three-class classifier. It is therefore removed from the baseline
comparison and used instead as an INDEPENDENT ARC INSTRUMENT for NAVA,
which is how Reagan et al. (2016) use it. Declared before any evaluation.


---

## Core decisions (script 04 v04.2.0, 2026-08-29T01:14:35)

### D21 LEWI implements its published definition
The manuscript defines LEWI as the argmax of the absolute second
difference of the smoothed sentiment signal. V1's code searched for
first-derivative sign changes, fell back to maximum absolute slope, and
defaulted to the midpoint (Reviewer 2, point 3). V2 implements the
published definition exactly, with disjoint pre/post segments, and
retains the V1 algorithm as compute_lewi_v1 so the discrepancy is
reported as a measurement rather than a description.

Measured on the 198 dev-split posts with at least four
sentences: the two algorithms select the same watershed sentence in
76.3% of texts, agree within one sentence in
82.3%, and the median absolute difference in
the reported drop is 0.0000.

### D22 TEG divides by N-1 and is not described as novel
TEG is the mean absolute successive difference over N-1 differences.
The manuscript printed 1/N (Reviewer 2, point 4). MASD is a standard
affect-dynamics statistic (Kuppens et al. 2010; Houben et al. 2015);
V2 describes TEG as that statistic applied to sentence-level narrative
sentiment, not as a new metric.

### D23 NAVA publishes five classes and one sign convention
Positive NAVA means the narrative ENDS WORSE than it starts, which is
the tragic direction. Manuscript section 6.1 contradicted section 3.2.3
on this. Five classes are published (tragic, mildly_declining, flat,
mildly_improving, redemptive); the implementation always had five while
the manuscript reported three and left 0.05 < |NAVA| < 0.15 undefined.

### D24 PAI drops the pronoun term
V1's PAI averaged in I_dom = |I-You|/(I+You), built from the same counts
as PTI, so their correlation was partly an identity (Reviewer 2, point
7); a null with random counts and no text reaches r = 0.554 in the
regime every corpus occupies. V2's PAI is (C_dom + A_dom)/2 -- control
verb density and apology asymmetry -- and is invariant to swapping I for
You, which is asserted in the unit tests. pai_v1 is retained so the
original coupling is reportable. H2 will be evaluated against the V2
form and against NRC-VAD dominance as an external criterion.

### D25 GASE ablation is genuine and renormalised
V1's published ablation subtracted weight x 0.5, a hardcoded constant;
component values were never read, which is why removing Entropy and
removing Attachment produced identical numbers to four decimals. V2
computes real components and renormalises the remaining weights on
leave-one-out, so removing a component does not lower the score by its
weight by construction. A unit test fails the build if any delta equals
weight x 0.5.

### D26 Undefined is None, never zero; and the layer is not neural
Every metric returns None when it is undefined (fewer than four
sentences for LEWI and NAVA, fewer than two segments for RCI and TIES).
V1 returned 0.0, which entered correlations as a real value and
inflated them. Semantic coherence uses one deterministic code path with
a fixed initial vector; V1 switched between NumPy SVD and stochastic
power iteration depending on the environment and never stated which
produced the published numbers (Reviewer 2, point 8). LSA is a linear
matrix factorisation: the manuscript must not call PLEF neuro-symbolic
on the strength of it (Reviewer 2, point 1).

Benchmark at declaration time: 3,010 words/s on 7 workers.


---

## Corpus decisions (script 03 v03.4.0, 2026-08-29T22:48:54)

### D9 DailyDialog label mapping
happiness -> positive; anger, disgust, fear, sadness -> negative;
no_emotion -> neutral; **surprise -> neutral**. Surprise has no
defensible polarity. The alternative (excluding surprise items) is
reported as a sensitivity check. Declared before any evaluation.

Note: V1 stored these fields as numpy array reprs, e.g. [0 6 0 0 3 0],
which ast.literal_eval cannot parse; V1's except clause then set every
emotion to 0, producing a 100% neutral gold vector. Parsed here by regex.

### D10 ISEAR is BINARY and reported separately
ISEAR has no neutral class: joy -> positive; anger, sadness, disgust,
shame, fear, guilt -> negative. This makes it a two-class problem inside
a three-class evaluation, so **ISEAR is reported separately and excluded
from any pooled three-class mean.** Forcing three classes would make every
neutral prediction automatically wrong and would misrepresent the result.
The resulting class balance is roughly 14% positive / 86% negative and
must be stated wherever ISEAR appears.

### D11 The relationship corpus is rebuilt from genuine posts
V1's loader read reddit_posts_corpus_original.csv, which is 100%
GoEmotions comment text (median 14 words). The corpus described in the
manuscript is rebuilt here from reddit_posts_corpus.csv plus
reddit_posts/*.txt: genuine first-person narratives from seven
subreddits, median 370 words. The item count falls from a claimed
10,000 to roughly 1,500, and the population on which the trajectory
metrics are computable rises from 1.6% to about 98%.

### D12 Development split
200 relationship posts, seed 20260829, reserved and
excluded from every evaluation. All smoke tests, threshold sweeps and
sensitivity analyses use only this split. Hash recorded in the manifest.
This corrects a leak in script 02, whose preview was computed on posts
that subsequently became evaluation data.

### D13 GoEmotions and EmpatheticDialogues mappings
GoEmotions uses the sentiment groupings of Demszky et al. (2020);
an item is positive or negative by majority of its mapped labels and
neutral on a tie or an ambiguous-only labelling. EmpatheticDialogues
maps its 32 emotion labels to three classes by a fixed list declared
in the loader source. Neither mapping was tuned against any result.

### D20 Trajectory metrics are scoped to the relationship corpus
LEWI, TEG and NAVA require at least four sentences. Measured across
the rebuilt corpora, the fraction of items meeting that bar is:

| corpus | items >=4 sentences | share |
|---|---:|---:|
| relationship | 1,288 | 98.5% |
| semeval2017 | 3,040 | 6.1% |
| tweeteval | 2,584 | 4.3% |
| dailydialog | 3,892 | 3.9% |
| isear | 296 | 3.9% |
| meld | 354 | 2.6% |
| goemotions | 914 | 1.7% |
| empathetic | 290 | 1.5% |

On seven of eight corpora the surviving fraction is under 7%, and it
is not a random 7%: it is the long tail of an overwhelmingly
short-form distribution. Reporting a correlation over that tail and
presenting it as a property of the corpus is precisely the
non-random restriction Reviewer 3 objected to (50,000 items reduced
to 67 on GoEmotions).

**LEWI, TEG and NAVA are therefore reported on the relationship**
**corpus only.** For every other corpus these metrics are reported as
not measurable, with the >=4-sentence count stated so the reader can
see why. Declared before any trajectory result is computed.

### D15 Minimum length filter on the relationship corpus
Posts shorter than 20 words are excluded. Inherited from V1,
declared here, and the number dropped is reported in the log and manifest.

### D16 EmpatheticDialogues is BINARY
The 32-emotion to 3-class mapping leaves under 1% neutral (22 of 19,167).
It is therefore evaluated and reported as two-class, exactly as ISEAR is.
A three-class macro-F1 over a class that barely exists is not meaningful.

### D17 Declared text edit in ISEAR
The ISEAR distribution contains a stray U+00E1 used as a line-continuation
artefact; it is replaced with a space. The count of items touched is
reported. No other corpus text is modified anywhere in the pipeline.

### D18 The relationship corpus carries NO labels
An earlier draft of this loader wrote 'neu' for the reddit_posts/*.txt
files, which have no label. That is fabricating gold data -- the same
failure mode as V1's ISEAR loader -- and has been removed. The 1,316 CSV
posts carry V1's unaudited keyword silver labels, which are retained only
as a v1_silver reference column and are never used as gold.

The corpus is therefore TRAJECTORY-ONLY: LEWI, TEG, NAVA, PTI, PAI, RCI
and coverage are computed on it; no macro-F1 or AUC is. The validation
gate enforces this and refuses any corpus whose labels the loader
invented.

Human labels for the 200-post dev split are collected via the annotation
task written to data/interim/annotations/. That task is the direct test
of H1 that Reviewers 1, 2 and 3 all asked for. Until it is returned, H1
is reported as NOT TESTED.

### D19 The Consensus corpus is quarantined
Rebuilt from the real VADER, NRC and Hu-Liu implementations rather than
the V1 toys. Its labels are DEFINED by lexicon agreement, so any lexicon
method is advantaged by construction. In V1 it contributed F1 = 0.605 and
AUC = 0.838 to the abstract's headline means while VADER scored exactly
1.000 on it. In V2 it is excluded from every headline result and reported
only as a supplementary sanity check, clearly marked.

### D14 labMT is not a polarity baseline
On held-out relationship text labMT labelled 97.8% of posts positive and
its Cohen's kappa against every other system was between 0.013 and 0.039.
It measures happiness, not polarity, and no threshold makes it a
three-class classifier. It is therefore removed from the baseline
comparison and used instead as an INDEPENDENT ARC INSTRUMENT for NAVA,
which is how Reagan et al. (2016) use it. Declared before any evaluation.

