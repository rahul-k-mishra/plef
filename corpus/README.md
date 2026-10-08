# corpus

`relationship_post_ids.csv`: the 1,508 relationship posts (1,308 evaluation, 200 annotation-development) by identifier. Columns: `id` as used in the analysis, `subreddit` parsed from the identifier's prefix, `reddit_post_id` (the identifier without the prefix) and `split`. No post text is included.

For the 192 identifiers without a prefix (171 evaluation, 21 annotation-development) the `subreddit` column is empty. These posts carry no prefix and are attributable only through the configuration of a single-subreddit collection script, which is an inference from the code rather than a per-post record.

The posts can be retrieved by identifier through the public Reddit API for as long as they remain available; deleted posts cannot be recovered.
