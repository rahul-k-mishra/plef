# annotation

One folder per annotation round. Rater indices are assigned within each round, so the same index in different rounds denotes different people; ten people took part in all, three in each of rounds 1 to 3 and one in round 4.

| folder | round | instrument | status |
|---|---|---|---|
| `round1_rejected/` | 1 | spreadsheet | rejected: identical turning points across annotators |
| `round2_rejected/` | 2 | spreadsheet | rejected: all-or-none field matches across 600 comparisons |
| `round3/` | 3 | spreadsheet | retained: source of the reliability estimates |
| `round4/` | 4 | web tool | retained: single annotator, preliminary comparison with the metric |
| `derived/` | not recorded | - | see `derived/README.md` |

Only round 4 recorded active time, revision counts and scroll-to-end; the round-2 and round-3 files carry zeros in those fields and the round-1 spreadsheets have none.

Until 2026-10-08 the round-1 spreadsheets also carried a `numbered_text` column holding the full text of the 200 annotation-development posts as numbered for annotation. That column was removed on that date; every other column is unchanged. The earlier versions remain in the repository's history, which was not rewritten; the reviewed state is preserved at tag `r1-as-reviewed`.
