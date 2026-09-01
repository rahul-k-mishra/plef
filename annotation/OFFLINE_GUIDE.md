# Offline annotation -- how to fill this file

Open rater{N}_OFFLINE.csv in Excel or LibreOffice.

Fill FOUR columns. Leave everything else exactly as it is. Do NOT reorder the
rows, do NOT sort, and do NOT edit row_key or numbered_text.

  overall_sentiment   pos | neu | neg
                      The narrator's overall emotional stance.

  turning_point       a sentence number from the [n] markers, or 0 for none.
                      The single sentence where the emotional direction of the
                      narrative changes most clearly. If there is no turning
                      point, write 0. Mark exactly one, or none. Never two.

  arc                 tragic | flat | redemptive
                      tragic     = ends worse than it starts
                      redemptive = ends better than it starts
                      flat       = no clear directional change

  confidence          1 to 5.  1 = guess, 5 = certain.

  notes               optional, and no line breaks.

Rules
  1. Judge the NARRATOR's emotion, not the events. "My friend died but I feel
     at peace now" is not straightforwardly negative.
  2. Read the whole post before marking the turning point.
  3. Do not skip rows. If genuinely unsure, use confidence 1 and move on.
  4. Do not discuss items with the other raters until all files are done.
  5. Save as CSV (UTF-8). Excel may offer to change the format -- decline.

When finished, save the file in place and tell the project owner to run:

    python offline_annotation.py --root <V2_ROOT> --mode import

The importer checks every value and refuses the file if anything is wrong,
naming the row. Partially filled files are fine; only completed rows import.
