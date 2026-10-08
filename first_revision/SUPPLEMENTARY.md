# Supplementary material

Generated from the analysis outputs. Every value is produced by the released
scripts from a single run; none is transcribed by hand.

## S1  Archetype resolution

The framework includes an exploratory archetype metric that matches a document
against six narrative templates by keyword signal and reports the dominant
match, or none if no template exceeds its threshold. It has **no external
criterion and no validation is claimed for it.** It is reported here rather
than in the main text because its resolution rate separates the corpora
sharply, which bears on scope, while the assignments themselves are untested.

| Corpus | n | Resolved | % | Three most frequent archetypes |
|---|---:|---:|---:|---|
| relationship | 1,308 | 1,153 | 88.1 | Mirror Dynamic 27.6, Tragic Hero 15.4, Rescuer–Victim 13.0 |
| isear | 7,666 | 981 | 12.8 | Tragic Hero 4.2, Push-Pull 2.3, Rescuer–Victim 2.2 |
| empathetic | 19,157 | 2,104 | 11.0 | Tragic Hero 3.5, Rescuer–Victim 2.8, Slow Fade 1.6 |
| semeval2017 | 52,806 | 4,573 | 8.7 | Push-Pull 2.5, Mirror Dynamic 2.1, Rescuer–Victim 1.5 |
| tweeteval | 59,899 | 5,206 | 8.7 | Push-Pull 2.5, Mirror Dynamic 2.0, Tragic Hero 1.5 |
| goemotions | 54,263 | 4,454 | 8.2 | Mirror Dynamic 2.5, Rescuer–Victim 1.8, Tragic Hero 1.3 |
| dailydialog | 101,026 | 6,589 | 6.5 | Rescuer–Victim 2.8, Mirror Dynamic 1.2, Push-Pull 1.0 |
| meld | 13,708 | 541 | 3.9 | Push-Pull 1.1, Rescuer–Victim 0.8, Tragic Hero 0.8 |

On the reserved 200-post development split the rate is 177/200 = 88.5%,
consistent with the evaluation portion of the same corpus.

**Interpretation.** This describes where the metric returns any output, not
whether the output is correct. The most likely mechanism is keyword density:
the templates were written for relationship discourse, and the corpora on
which resolution is low are short-form and mostly not about relationships. No
claim is made that the assignments correspond to distinctions a reader would
draw, and given the annotator-reliability results in the main text such a
correspondence should not be assumed.

## S2  Annotation integrity checks

Four annotation rounds were conducted. Two were rejected before analysis by
automated checks that are part of the released tooling. The rejection rules
are stated here so the decisions are auditable rather than assertions.

**Protocol.** Each annotator receives an ordered sequence of items. Roughly
10% of items are second showings of an earlier item in the same sequence,
placed at least a fixed minimum number of positions later and not marked as
repeats. Each item records the response, elapsed active time, revision count,
and whether the document was scrolled to its end.

**Check 1 — cross-annotator turning-point identity.** For each pair of
annotators, the proportion of shared items on which both selected the same
sentence. Under independent selection this is approximately the mean of
1/N_i over the shared items, about 5% for these documents. **Rejection rule:
above 50%.**

**Check 2 — partial-agreement pattern.** For each pair, the joint distribution
over how many of the three categorical fields (sentiment, arc, confidence)
match: 0, 1, 2 or 3. Random pairing of the same responses, holding each
annotator's marginals fixed, produces partial matches (exactly 1 or exactly 2)
on a substantial majority of items. **Rejection rule: zero items with partial
agreement.**

**Check 3 — turning-point abstention rate.** The proportion of items marked as
having no turning point. **Flag: exactly 0%.**

**Check 4 — confidence spread.** **Flag: more than 85% of items at the top two
confidence levels.**

**Response formats.** Sentiment, arc and turning point are as described in the
main text. Confidence is a five-point scale, presented as buttons 1 to 5 with the
interface hint "1 = guess, 5 = certain". The turning point accepts one integer
sentence index or zero; no ranges or free text.

**Timing.** Two measures are recorded per item. `seconds` is active time: a
counter advancing once per second only while the browser tab is visible and a
keystroke, mouse movement, click or scroll occurred within the previous ninety
seconds. `wall_seconds` is total elapsed time from first display to submission.
All timing figures in the paper are the active measure. Both fields are in the
released response files. An earlier version of the tool timed from page load
alone, which recorded idle tab time as time on task; the active measure replaced
it.

**Round 3 overlap design.** Computed from the released response files. Three
annotators, 100 unique posts each, 174 distinct posts in total.

| set | posts |
|---|---:|
| labelled by all three | 26 |
| shared by raters 1 and 2 | 53 (26 three-way + 27 pair-only) |
| shared by raters 1 and 3 | 51 (26 three-way + 25 pair-only) |
| shared by raters 2 and 3 | 48 (26 three-way + 22 pair-only) |
| seen by exactly one rater | 74 (22 / 25 / 27) |
| hidden repeat slots | 8 / 7 / 11 |

Krippendorff's alpha and the unanimity figure use the 26 three-way posts. The
pairwise existence and location figures use each pair's own shared set, which is
why their denominators are 53, 51 and 48 rather than 26.

**What "identical" meant in the rejected first round.** The check compares the
raw recorded turning-point response between each pair of annotators over their
shared items. Two annotators who both recorded "no turning point" count as
identical, as do two who selected the same sentence. The rejection threshold is
above 50% pairwise identity; the observed value was 100% on all 200 shared items.
The 8.44% figure quoted in the main text is the expected rate of selecting the
same *sentence* under an independent-response null over the admissible positions,
and is reported for scale rather than as the quantity the check tests.

**What the second rejected round showed.** Across 600 pairwise comparisons
(three pairs over 200 items), the three categorical fields — sentiment, arc and
confidence — either all matched or all differed. Not one comparison showed
exactly one or exactly two matching fields. No chance rate is computed for this;
the rejection rests on the absence of any partial agreement across 600
comparisons.

**Check 5 — intra-annotator agreement** on the hidden repeats, reported but
not used as a rejection rule.

### Outcomes

| Round | Annotators | Items each | Outcome | Statistic |
|---|---|---|---|---|
| 1 | 3 | 220 slots | Rejected | Check 1: identical turning-point selection on 200 of 200 shared items against ~5% expected |
| 2 | 3 | 220 slots | Rejected | Check 2: zero partial matches across 600 pairwise comparisons |
| 3 | 3 | ~100 slots | Retained | All checks passed; used for the reliability estimates |
| 4 | 1 | 40 slots | Retained | Single annotator; used for the preliminary human comparison |

Round 3 gave Krippendorff's alpha of 0.177 for sentiment and 0.002 for arc on
the 26 items annotated by all three, and intra-annotator turning-point
agreement of 18–29% on the hidden repeats.

**Unanimous versus pairwise turning-point agreement.** These are different
quantities and were conflated in an earlier draft. Both are computed by stage H
of `10_null_analysis.py` from the raw response files, for every round.

Round 3, the retained multi-annotator round:

| measure | value |
|---|---|
| posts annotated by all three | 26 |
| unanimous three-way exact agreement | 0 of 26 (0.0%) |
| pairwise, raters 1 and 2 | 8 of 53 (15.1%) |
| pairwise, raters 1 and 3 | 15 of 51 (29.4%) |
| pairwise, raters 2 and 3 | 12 of 48 (25.0%) |

Pairwise sets are larger than the three-way set because the overlap design
gives each pair more shared posts than all three share. Against a chance rate
computed per pair on the admissible support, pairwise agreement exceeds chance
by factors of 1.7 to 4.0 while unanimity never occurred. The main text reports
both; neither alone describes the data.

| pair | shared posts | observed | chance, mean of 1/(N_i−2) | ratio |
|---|---:|---:|---:|---:|
| 1 and 2 | 53 | 15.1% | 8.65% | 1.7 |
| 1 and 3 | 51 | 29.4% | 7.41% | 4.0 |
| 2 and 3 | 48 | 25.0% | 7.09% | 3.5 |

For the rejected first round the pair-specific chance rate is 8.44% on all
three pairs over 200 shared posts, against observed identity of 100%, which is
the basis on which that round was rejected.

**Majority-resolved items.** A two-of-three majority resolves an item when at
least two annotators select the same value. Computed directly by stage H of
`10_null_analysis.py`:

| round | annotated by all three | unanimous | majority-resolved | of which "no turning point" |
|---|---:|---:|---:|---:|
| round 3 (retained) | 26 | 0 | 18 (69.2%) | 8 |
| round 1 (rejected) | 200 | 3 (1.5%) | 70 (35.0%) | 21 |

The retained round would therefore have yielded a majority-resolved value for
most items. The decision not to construct a gold standard does not rest on a
shortage of resolved items: it rests on the fact that only 10 of the 26 would
name a specific sentence, that a majority among annotators who never agreed
unanimously and whose repeat agreement was 18–29% inherits that unreliability,
and that the sentiment and arc coefficients on the same items are 0.177 and
0.002. Reporting the count is what makes that distinction visible; an inference
from the pairwise rates would have suggested the opposite and would have been
wrong.

**Keyword-label contingency.** The 25.0% agreement and Cohen's kappa of −0.028
between the keyword-derived labels and the human annotation are computed on the
36 posts carrying both. The contingency table and the keyword rule are included
in the release under `tables/`; they are not reproduced here because the rule is
not used for any reported result and is retained only to document why it was
rejected.

The raw response files for all four rounds, including both rejected rounds,
are released.

## S2b  Exact chance benchmarks for turning-point agreement

The watershed metric of Equation (1) can return only the interior positions
2 ... N-1, so a chance benchmark computed as 1/N uses the wrong support. Stage I
of `10_null_analysis.py` recomputes both benchmarks exactly, per post:

- exact match: mean over posts of 1/(N_i - 2)  →  5.0% on the 19 comparison
  posts, against 4.3% under the naive 1/N_i
- within one sentence: mean over posts of the number of admissible positions
  within one sentence of the annotator's selection, divided by (N_i - 2),
  using each post's own sentence count rather than the approximation 3/N_i
  →  14.2%, against 12.9% under the naive form

The same stage reports pair-specific chance rates for every annotator pair in
every round, computed over that pair's own shared posts rather than from a
single median sentence count. The rejected rounds are included, so the chance
rate against which their integrity checks were judged is auditable.

**Per-post audit.** So that neither benchmark has to be taken on trust, the
release contains `tables/chance_per_post.csv`, one row per comparison post:

| column | meaning |
|---|---|
| `id` | post identifier |
| `N_i` | sentence count |
| `human_selection_h_i` | the annotator's selected sentence |
| `boundary` | whether the selection lies outside {2,…,N_i−1} |
| `exact_contribution_1_over_N_minus_2` | 1/(N_i−2), or 0 for a boundary selection |
| `within1_admissible_neighbours` | \|{h_i−1, h_i, h_i+1} ∩ {2,…,N_i−1}\| |
| `within1_contribution` | that count divided by (N_i−2) |

Nineteen posts, sentence counts 7 to 114. Exactly one selection is on the
boundary — post `1707opw`, sentence 17 of 17 — and contributes zero. Averaging
the two contribution columns gives 4.67% and 14.21%, the values reported in
Table 9. Treating the boundary post as interior would give 5.02% instead.

## S2b2  Existence and location agreement, separated

The turning-point response space contains a null category alongside the
sentence positions, so a single agreement percentage mixes two questions and
cannot be compared against a chance rate defined over sentences alone. Stage B
of `11_response_space.py` separates them. Round 3, the retained round:

| pair | n | existence agree | existence chance | location n | location agree | location chance | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 and 2 | 53 | 58.5% | 65.0% | 30 | 23.3% | 7.8% | 3.0 |
| 1 and 3 | 51 | 62.7% | 54.4% | 26 | 34.6% | 5.6% | 6.2 |
| 2 and 3 | 48 | 52.1% | 52.1% | 18 | 27.8% | 8.2% | 3.4 |

Existence chance is the agreement rate implied by each annotator's own rate of
recording "no turning point", so the null respects their observed tendencies.
Location chance is the mean of 1/(N_i − 2) over exactly the posts where both
selected a sentence.

The pattern is consistent across all three pairs: existence agreement at or
below chance, location agreement three to six times chance. The earlier mixed
figures of 15.1%, 29.4% and 25.0% conflated the two and were compared against a
sentence-only benchmark; they are superseded by this table.

## S2c  Treatment of the zero response in reliability calculations

The turning-point response space is {0, 2, 3, …, N−1}, where 0 means "no
turning point". Two treatments are possible and they answer different
questions.

**Categorical agreement (reported in the main text).** The zero response is one
admissible category. Two annotators who both record 0 are counted as agreeing,
because agreeing that a narrative does not turn is agreement on the task as
posed. This is the basis for the pairwise figures of 15.1%, 29.4% and 25.0%.

**Sentence-location agreement.** Restricting to posts where both annotators
selected a sentence answers the separate question of whether they localise the
same turn. This conditional figure is emitted by stage H of
`10_null_analysis.py` alongside the categorical one.

Reporting only one would conflate whether a turn exists with where it is. The
main text uses the categorical figure and states the distinction.

## S2d  Exact nulls for the rejected rounds

The first rejected round showed identical turning-point selection on 200 of 200
items across all three annotator pairs. Under an independent-response null
respecting the metric's admissible support, computed from that round's own posts
as the mean of 1/(N_i − 2), the expected pairwise exact-agreement rate is 8.44%
on all three pairs. The observed 100% is the basis on which the round was
rejected. The corresponding rates for the retained round are 8.65%, 7.41% and
7.09%.

## S2e  Lexicon provenance

| item | value |
|---|---|
| entries | 348 |
| authored | 18 April 2026 |
| relationship corpus file assembled | 10 May 2026 |
| gap | 22 days, lexicon first |
| corpus text consulted during authoring | none |
| labels consulted during authoring | none |
| modified during the analysis reported here | no |
| released file | `src/plef_lexicons.json` |
| SHA-256 | 18294c6727f66003df67c0c01ab9e66073dca34d3c60541878c35ba84825165c |

The lexicon predates the evaluation corpus and is therefore independent of it.
This does not claim unfamiliarity with relationship discourse in general, which
is the domain the lexicon targets.

## S2f  Arc-window sensitivity

The arc window is piecewise, k = max(1, floor(N/4)) for N < 9 and
max(1, floor(N/3)) otherwise, and the threshold at nine sentences is a property
of the implementation rather than a derived optimum. Since the arc metric is one
half of the primary null analysis, the whole analysis was repeated under three
rules. The watershed metric is identical in all three, so any difference is
attributable to k alone. 1,288 documents, 1,000 permutation replicates per rule,
seed 20260830.

| arc window rule | observed r | null mean | null SD | null 95% | null ≥ obs | p |
|---|---:|---:|---:|---|---:|---:|
| k = ⌊N/4⌋ throughout | +0.6107 | +0.6144 | 0.0249 | [+0.5670, +0.6615] | 560/1000 | 0.5604 |
| k = ⌊N/3⌋ throughout | +0.6349 | +0.6331 | 0.0258 | [+0.5824, +0.6846] | 472/1000 | 0.4725 |
| piecewise (used) | +0.5979 | +0.6070 | 0.0267 | [+0.5542, +0.6605] | 630/1000 | 0.6304 |

Under every rule the observed correlation sits at or below its own null mean and
p ranges from 0.47 to 0.63. The conclusion is not an artefact of the window
choice.

A wider window raises both the observed correlation and the null by almost the
same amount. That is the behaviour expected if the association is generated by
the signal the two metrics share rather than by sentence ordering, so the
sensitivity analysis independently supports the mechanism proposed in the main
text.

**Window disjointness, checked on the data.** Across the 125 distinct document
lengths in this corpus, N from 4 to 526, there is no length at which 2k exceeds
N. The tightest case is N = 327, where the two windows cover two thirds of the
document. The opening and closing windows are therefore disjoint on every
document analysed.

**Cross-check.** The piecewise row was produced by a separate implementation
from the one used for the main null analysis, with the same seed, and reproduces
it exactly: observed +0.5979, null mean +0.6070, SD 0.0267, 630 of 1,000 draws at
or above the observed value, p = 0.6304.

## S2g  Metric definitions

Transcribed from the released `src/plef_core.py`, which is the authoritative
specification. Tokenisation is the same lowercase alphabetic-with-apostrophe
regex throughout. Every metric returns a missing value rather than zero when it
is undefined, so an undefined value never enters a correlation as a real one.

**Sentence sentiment.** Lexicon sum over matched tokens with negation and
intensity modifiers, normalised as C(s) = sigma / sqrt(sigma^2 + 15).

**LEWI.** Defined in the main text, Equation (1). Output: the watershed index
i* is an integer in {2,…,N−1}; the drop is a real number, missing for N < 4.

**LEWI drop.** mean(s_1 … s_{i*−1}) − mean(s_{i*} … s_N), the two segments
disjoint and exhaustive.

**NAVA.** Defined in the main text, Equation (2). Real-valued, missing for
N < 4. Positive means the narrative ends worse than it begins.

**NAVA five-class label.** Derived from the NAVA value by fixed thresholds:
NAVA > 0.15 tragic; 0.05 < NAVA ≤ 0.15 mildly declining; |NAVA| ≤ 0.05 flat;
−0.15 ≤ NAVA < −0.05 mildly improving; NAVA < −0.15 redemptive. For the
comparison against human arcs these five are collapsed to three by mapping
mildly declining to tragic and mildly improving to redemptive.

**TEG.** Mean absolute successive difference, (N−1)^-1 sum |s_i − s_{i−1}|.
Non-negative, missing for N < 2.

**PTI, pronoun triangulation.** (I − You) / (I + You + We + 1) over first- and
second-person pronoun counts. Range [−1, 1]; defined for every document.

**PAI, power asymmetry.** Mean of a control-verb density and an apology
asymmetry. The pronoun term of the earlier definition is excluded; when it is
included for the comparison in Table 11 it is |I − You| / (I + You), set to zero
when a document contains neither pronoun.

**RCI, relational coherence.** Mean pairwise Jaccard similarity over content
words between segments. Segments are paragraphs when at least two exist,
otherwise sentences longer than 15 characters. Content words are alphabetic,
at least three characters, and not stopwords. Returns missing for fewer than two
segments.

**Cognitive distortion index.** Twelve distortion categories, each a regular
expression set. For each category the match count is divided by a cap of
max(1, n_words/200) and clipped to 1; the index is the mean of the twelve capped
densities.

**VADS, vulnerability-authenticity disclosure.** Weighted density over
disclosure tiers: sum over tiers of (tier weight x match count), divided by the
token count, multiplied by 10 and clipped to 1.

**TIES, inconsistency.** Normalised emotion entropy multiplied by the density of
segments containing a contradictory absolute-term pair. Entropy is Shannon
entropy over the non-zero emotion totals, normalised by log2 of the number of
non-zero categories. Returns missing for fewer than two segments. This is an
inconsistency measure and is not a gaslighting detector.

**GASE components.** S is the mean sentence sentiment. H is normalised emotion
entropy as above. A is min(1, (1.2 x anxious + 0.8 x avoidant) / (10 + secure +
1)) over attachment-lexicon counts. G is min(1, horsemen total / (0.5 x n_sents
+ 1)).

**GASE.** 0.30 S + 0.25 (1 − H) + 0.25 (1 − A) + 0.20 (1 − G), clipped to
[−1, 1]. The leave-one-out ablation renormalises the remaining weights.

**Semantic coherence.** Mean off-diagonal cosine similarity of LSA sentence
vectors. At most 60 sentences. Documents are the sentences; terms are tokens of
at least three characters that are not stopwords; the vocabulary is the sorted
set of those terms. TF is the within-sentence count divided by the sentence
length; IDF is log((1 + N)/(1 + df) + 1) with N the sentence count. The
truncated SVD takes 3 components by deterministic power iteration, 60 iterations
per component, from the fixed initial vector (1/sqrt(V), …, 1/sqrt(V)) rather
than a random one, with deflation between components. Sentence vectors with norm
below 1e-12 are excluded from the similarity average. Returns missing for fewer
than two sentences or an empty vocabulary.

**NSPL, semantic fusion.** 0.35 x (GASE + 1)/2 + 0.30 x semantic coherence +
0.20 x (1 − min(1, TEG)) + 0.15 x (1 − |PTI|), clipped to [0, 1]. Returns
missing if any input is missing. This layer is latent semantic analysis, a
linear matrix factorisation; it is not neural.

**Baseline score conversions.** Transcribed from `src/plef_baselines.py`. Each
system produces one signed document score before thresholding.

| system | conversion | zero-match behaviour |
|---|---|---|
| VADER | its own compound score | package-native |
| AFINN | sum of integer valences / (5 x sqrt(total tokens)), clipped to [-1, 1] | 0.0 when the document has no tokens |
| Hu-Liu | (p - n)/(p + n) over matched tokens | 0.0 when p + n = 0 |
| NRC | (p - n)/(p + n) over positive/negative association flags only; the eight emotion categories are ignored | 0.0 when p + n = 0 |
| Empath | (p - n)/(p + n) over normalised category scores summed across 19 positive and 26 negative categories | 0.0 when p + n = 0 |

Two points require disclosure. AFINN's normalisation is a choice: the resource
returns an unbounded integer sum and no constant is published. Four variants are
implemented in the released adapter (root-total-tokens, density,
per-matched-token mean, and tanh); the root-total-tokens form is the declared
primary and is used throughout.

Empath's category set is also a choice, and it was made after observing
behaviour. The narrow positive-emotion/negative-emotion pair was tried first and
returned exactly 0.000 on two of five hand-written known-answer sentences; the
broader 19/26 set was then adopted. Categories were selected by name and never
tuned against any evaluation corpus, and both variants are scored in the released
code. This is a post-hoc selection and is reported as such.

Because every baseline returns 0.0 rather than a missing value when nothing
matches, and 0.0 falls in the neutral band, baseline zero-match cases are
labelled neutral and enter both the macro-F1 and the AUC computations. They are
not abstentions and are not dropped. The abstention analysis in the main text
concerns the interpretation of that mapping, not a difference in how the systems
are scored.

## S2h  Label mappings

From the rebuild log. Distributions are of the retained items.

| corpus | classes | distribution | note |
|---|---|---|---|
| goemotions | 3 | neu 40.7%, pos 38.3%, neg 21.0% | Demszky et al. groupings |
| semeval2017 | 3 | neu 45.1%, pos 38.9%, neg 16.0% | Task 4A gold labels |
| meld | 3 | neu 47.0%, neg 30.5%, pos 22.5% | dataset Sentiment column used directly |
| tweeteval | 3 | neu 45.9%, pos 35.1%, neg 19.0% | TweetEval sentiment |
| dailydialog | 3 | neu 84.9%, pos 12.5%, neg 2.7% | manual utterance labels |
| isear | 2 | neg 85.7%, pos 14.3% | no neutral class in the resource |
| empathetic | 2 | pos 50.5%, neg 49.5% | self-reported situation emotion |

**ISEAR**, two-class. The resource has no neutral category. The mapping is
joy → positive; anger, sadness, disgust, shame, fear and guilt → negative. The
seven emotions occur in near-equal numbers (anger 1,096, sadness 1,096, disgust
1,096, shame 1,096, fear 1,095, joy 1,094, guilt 1,093), so a single positive
emotion against six negative ones produces the 14.3/85.7 split. ISEAR required
5,337 character-level text repairs.

**EmpatheticDialogues**, two-class. The scored unit is the situation
description. Sixteen emotion labels map to positive — surprised, excited, proud,
grateful, impressed, hopeful, confident, joyful, content, caring, trusting,
faithful, prepared, anticipating, sentimental, nostalgic — and sixteen to
negative — angry, sad, annoyed, lonely, afraid, terrified, guilty, disgusted,
furious, anxious, disappointed, jealous, devastated, embarrassed, ashamed,
apprehensive. There is no neutral class and none is created. Four rows carried an
emotion field that matched neither set; inspection showed these are CSV parse
fragments produced by embedded commas and quotes in the source file rather than
emotion labels, and they were counted and dropped rather than pooled into either
class or into a residual category. Exact-duplicate situation texts were removed
before labelling.

**DailyDialog**, three-class. Seven labels — no_emotion 84,061, happiness 12,580,
surprise 1,706, sadness 1,140, anger 1,016, disgust 350, fear 173 — with
no_emotion → neutral, happiness → positive, and the remainder → negative.
Surprise is treated as negative, which is a choice rather than a necessity and
affects 1.7% of that corpus.

## S2i  Ten-thousand-draw null run

The null analysis reported in the main text was repeated at 10,000 draws per
null using a parallel implementation whose output is a deterministic function
of the draw count and the seed, verified independent of worker count.

| null | draws | mean r | SD | 95% interval | p | MC SE |
|---|---:|---:|---:|---|---:|---:|
| within-document permutation | 10,000 | +0.6074 | 0.0264 | [+0.5544, +0.6583] | 0.643 | 0.005 |
| synthetic i.i.d. normal | 10,000 | +0.5945 | 0.0231 | [+0.5486, +0.6388] | 0.440 | 0.005 |
| synthetic bounded random walk | 10,000 | +0.8497 | 0.0091 | [+0.8314, +0.8671] | 1.000 | 0.000 |

**Change from the earlier 1,000-draw run.** The permutation p moves from 0.630
to 0.643, a shift of 0.012 against a combined two-standard-error band of 0.032,
so the two runs agree. The Monte Carlo standard error falls from 0.015 to 0.005.
The i.i.d. and random-walk means differ from the earlier run by 0.0004. The
inferential conclusion is unchanged; the larger run is reported because it is
more precise, and the change is stated rather than silently substituted.

**Verification of the larger run.** Before drawing any null, the implementation
recomputed the watershed drop and arc asymmetry for all 1,288 documents and
confirmed they reproduce the values stored in the scored file. It confirmed the
observed correlation, the i.i.d. scale, the random-walk step scale and the
document count against the values reported here. It recomputed 100 draws per
null serially, including indices straddling every parallel chunk boundary, and
found no disagreement with the parallel result. All draws are released as
`tables/null_draws_parallel.csv`.

## S3  Random-number generation

All simulation-based results use Python's `random.Random`. The seeds are fixed
in the released analysis configuration: the within-document permutation null
uses seed 20260830, the synthetic i.i.d. null 20260831, and the bounded
Gaussian random-walk null 20260832. The Monte Carlo random-classification
benchmark uses seed 20260830. Re-running the released scripts with the
released configuration reproduces every simulated value reported.

## S4  The twelve metrics

The framework computes: sentence-level compound sentiment; the watershed index
(LEWI) and its drop; the arc asymmetry (NAVA) and its five-class label; the
volatility index (TEG); the pronoun triangulation index (PTI); the power
asymmetry index (PAI); the relational coherence index (RCI); the cognitive
distortion index; the vulnerability-disclosure score (VADS); the inconsistency
index (TIES); the semantic coherence measure; and the composite
relationship-health metric (GASE), together with a semantic-fusion metric
(NSPL) combining the composite, semantic coherence, volatility and pronoun
terms with weights 0.35, 0.30, 0.20 and 0.15. Full definitions are in the
released `plef_core.py`, which is the authoritative specification.

## S5  Threshold sweep

macro-F1 for every system at classification thresholds from 0.00 to 0.30. The
headline results use ±0.05, which is VADER's convention and is not native to the
other four systems, so this sweep tests whether the reported ranking depends on
that choice. Values are rounded half-up to three decimals; three cells
(goemotions NRC and Hu-Liu at the wider thresholds, semeval2017 VADER at 0.15)
fall exactly on a rounding tie, and the released
`results/tables/threshold_sweep.csv` carries the unrounded values.

| corpus | system | 0.00 | 0.02 | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| goemotions | PLEF | .450 | .449 | .447 | .442 | .428 | .399 | .352 |
| goemotions | VADER | .578 | .579 | .581 | .585 | .588 | .589 | .602 |
| goemotions | NRC | .479 | .479 | .479 | .479 | .479 | .479 | .479 |
| goemotions | Empath | .469 | .469 | .469 | .469 | .468 | .467 | .465 |
| goemotions | AFINN | .594 | .594 | .604 | .608 | .575 | .505 | .370 |
| goemotions | Hu-Liu | .555 | .555 | .555 | .555 | .555 | .554 | .554 |
| semeval2017 | PLEF | .426 | .426 | .423 | .411 | .387 | .351 | .304 |
| semeval2017 | VADER | .540 | .540 | .541 | .547 | .551 | .554 | .560 |
| semeval2017 | NRC | .450 | .450 | .450 | .450 | .449 | .448 | .448 |
| semeval2017 | Empath | .461 | .460 | .460 | .460 | .459 | .458 | .458 |
| semeval2017 | AFINN | .543 | .543 | .556 | .541 | .468 | .387 | .284 |
| semeval2017 | Hu-Liu | .525 | .525 | .525 | .525 | .525 | .524 | .524 |
| meld | PLEF | .323 | .323 | .321 | .318 | .306 | .293 | .278 |
| meld | VADER | .404 | .404 | .404 | .403 | .403 | .399 | .422 |
| meld | NRC | .373 | .373 | .373 | .373 | .372 | .372 | .372 |
| meld | Empath | .335 | .335 | .335 | .335 | .335 | .335 | .334 |
| meld | AFINN | .432 | .432 | .431 | .416 | .393 | .346 | .289 |
| meld | Hu-Liu | .405 | .405 | .405 | .405 | .405 | .405 | .405 |
| tweeteval | PLEF | .424 | .424 | .421 | .413 | .392 | .361 | .314 |
| tweeteval | VADER | .541 | .540 | .541 | .547 | .551 | .554 | .561 |
| tweeteval | NRC | .456 | .456 | .456 | .456 | .456 | .454 | .454 |
| tweeteval | Empath | .463 | .463 | .463 | .463 | .462 | .462 | .461 |
| tweeteval | AFINN | .547 | .547 | .556 | .545 | .481 | .403 | .298 |
| tweeteval | Hu-Liu | .525 | .525 | .525 | .525 | .525 | .524 | .524 |
| dailydialog | PLEF | .418 | .418 | .420 | .421 | .420 | .400 | .380 |
| dailydialog | VADER | .346 | .347 | .350 | .363 | .370 | .376 | .412 |
| dailydialog | NRC | .359 | .359 | .359 | .359 | .359 | .359 | .359 |
| dailydialog | Empath | .392 | .392 | .392 | .393 | .394 | .394 | .395 |
| dailydialog | AFINN | .378 | .378 | .395 | .459 | .488 | .484 | .414 |
| dailydialog | Hu-Liu | .411 | .411 | .411 | .411 | .411 | .411 | .411 |

**Does the ranking depend on the common threshold?** Comparing each system at
its own best threshold rather than at a shared one:

| corpus | PLEF best | at | best baseline | at | difference |
|---|---:|---:|---|---:|---:|
| goemotions | .450 | 0.00 | AFINN .608 | 0.10 | −0.158 |
| semeval2017 | .426 | 0.00 | VADER .560 | 0.30 | −0.134 |
| meld | .323 | 0.00 | AFINN .432 | 0.00 | −0.109 |
| tweeteval | .424 | 0.00 | VADER .561 | 0.30 | −0.137 |
| dailydialog | .421 | 0.10 | AFINN .488 | 0.15 | −0.067 |

The framework does not lead on any three-class corpus at any threshold, and
would not lead even if every system were tuned to its own optimum. The reported
ranking is therefore not an artefact of applying VADER's convention to all five
systems.

One threshold-dependent detail is worth stating. On DailyDialog the framework
has the highest macro-F1 of the six at thresholds 0.00 to 0.10, and loses that
position at 0.15 once AFINN reaches .488. This is the abstention effect
described in the main text, and the sweep shows it is threshold-dependent as
well as decision-rule dependent.

## S6  Released artifacts

- input manifests with SHA-256 checksums for every source file
- the decision file, 26 entries, each machine-timestamped before the
  corresponding evaluation output
- annotation response files for all four rounds and the integrity-check code
- dataset filtering logs and the deduplication report
- the environment lock file
- the raw numerical outputs from which every table and figure is generated,
  and the script that generates each
