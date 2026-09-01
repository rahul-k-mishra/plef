# PLEF V2 -- Human annotation task (dev split, 200 posts)

## Why this exists

Three reviewers made the same point: hypothesis H1 claims LEWI locates the
emotional turning point of a narrative, and it was never tested against a human
judgement. The submitted paper marked H1 "Supported (proxy)" using the
NAVA x LEWI correlation, which Reviewer 2 and Reviewer 3 both identified as
circular. It is now marked NOT TESTED.

This task produces the missing criterion. It also produces the only
human-labelled relationship data in the paper.

These 200 posts are the reserved development split. They are excluded from
every evaluation result, so annotating them cannot contaminate anything.

## What to do

Open `annotation_task_rater{N}.csv`. Each row is one post, with its sentences
numbered. Fill four columns:

  overall_sentiment   pos | neg | neu
                      The narrator's overall emotional stance in the post.

  turning_point       An integer sentence number, or 0 for none.
                      The single sentence where the emotional direction of the
                      narrative changes most clearly. If the post has no
                      turning point (it is uniformly negative, or a flat
                      request for advice), write 0.

  arc                 tragic | redemptive | flat
                      tragic     = starts better than it ends
                      redemptive = ends better than it starts
                      flat       = no clear directional change

  confidence          1 (guess) to 5 (certain)

Leave `notes` blank unless something needs saying.

## Rules

1. Judge the NARRATOR's emotion, not the events. "My friend died but I feel at
   peace now" is not straightforwardly negative.
2. Read the whole post before marking the turning point.
3. Mark exactly one turning point, or none. Do not mark two.
4. Do not discuss items with other raters until all three files are complete.
5. Do not skip rows. If genuinely unsure, use confidence 1 and move on.

## Three raters

Three files are provided, each with the same posts in a DIFFERENT order, so
fatigue and order effects do not align across raters. Inter-rater reliability
will be computed as Krippendorff's alpha for sentiment and arc, and as
exact-match plus within-one-sentence agreement for the turning point.

If only one rater is available, complete rater1 and report it as a single-rater
criterion with that limitation stated explicitly. Do not present single-rater
annotation as though it were multi-rater.

## What happens next

Script 06 computes:
  * inter-rater reliability
  * LEWI turning-point agreement (exact and within-one-sentence), which is the
    direct test of H1
  * NAVA arc classification accuracy against human arc labels, which is H5
  * PLEF sentiment accuracy against human labels on relationship text

Return the completed files to `data/interim/annotations/`.
