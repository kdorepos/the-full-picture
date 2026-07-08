# Episode templates

An episode is an **envelope** of metadata plus an ordered list of **segments**.
The Big Picture is a segmented show — a review, then a "Plus:" game, then a
mailbag — so each segment is rendered as its own titled block, in order.

`pipeline/enrich_tmdb.py` walks every segment, collects the film titles, and
writes the shared `tmdb` map (title → {id, poster, title, year} | null). The
site resolves posters and TMDb links from that one map, so a film named in two
segments is matched once.

## Envelope

```jsonc
{
  "slug": "the-1988-movie-draft",          // URL + filename
  "title": "The 1988 Movie Draft",
  "show": "The Big Picture",
  "network": "The Ringer",
  "hosts": ["Sean Fennessey", "Amanda Dobbins"],
  "published": "2026-04-14",               // YYYY-MM-DD
  "runtimeMin": 132,
  "spotifyEpisodeId": "…",                 // pipeline/spotify_id.py fills this
  "format": "One-line blurb shown under the title.",
  "segments": [ /* see kinds below */ ],
  "referenced": [                          // episode-level "Also mentioned"
    { "group": "In passing", "films": ["Heat", "Casino"] }
  ],
  "excluded": {                            // episode-level "Not films"
    "TV": ["Andor"], "Ads": ["Mint Mobile"]
  },
  "tmdbOverrides": { "The Naked Gun": 37136 } // pin a same-title collision by id
}
```

## Segments

Every segment has `kind`, `heading`, optional `note` (the gray sub-label), plus
a kind-specific payload. Renderer map (`components/Segment.astro`):

| kind | renderer | payload | live example |
|------|----------|---------|--------------|
| `review` | FilmsBody | `films[]` (usually 1) | matt-damon-…-the-rip |
| `discussion` | FilmsBody | `films[]` | the-star-wars-movie-draft |
| `ranking` | FilmsBody | `subject`, `ranked:true`, `films[]` (ordered) | — |
| `topfive` | FilmsBody | `subject`, `ranked:true`, `films[]` | the-10-best-…-so-far |
| `halloffame` | FilmsBody | `honoree`, `films[]` | — |
| `interview` | FilmsBody | `guest`, `films[]` | the-10-best-…-so-far |
| `list` | ListBody | `picks[]` (`{title,year,by,note}`) | the-10-best-…-so-far |
| `draft` | DraftBody | `draftOf`, `teams[]`, `undrafted[]?`, `categories[]?` | the-1988-movie-draft |
| `auction` | AuctionBody | `slates[]`, `undrafted[]?`, `januarySlate[]?` | 2026-movie-auction-returns |
| `awards` | AwardsBody | `ceremony?`, `categories[]` | — |

`films[]` items are `{title, year?, note?}`. `ranked:true` numbers the cards
top-down (position 1 → "No. 1"), so order `films[]` **best-first (No. 1 first)** —
even when the show reveals worst-to-best on air. `guest` puts a byline on them;
both reuse the pick-card byline slot.

### review / discussion / ranking / topfive / halloffame / interview (FilmsBody)

```jsonc
{ "kind": "ranking", "heading": "The 'Toy Story' Rankings",
  "note": "best to worst", "subject": "Toy Story", "ranked": true,
  "films": [
    { "title": "Toy Story",   "year": 1995, "note": "No. 1 - still the gold standard." },
    { "title": "Toy Story 4", "year": 2019, "note": "Last - the one they'd cut." }
  ] }

{ "kind": "halloffame", "heading": "The Diane Keaton Hall of Fame",
  "honoree": "Diane Keaton",
  "films": [ { "title": "Annie Hall", "year": 1977, "note": "The induction lock." } ] }

{ "kind": "interview", "heading": "In conversation", "guest": "Rian Johnson on",
  "films": [ { "title": "Wake Up Dead Man", "year": 2025, "note": "…" } ] }
```

### list (ListBody) — roundtable, one critic per pick

```jsonc
{ "kind": "list", "heading": "The picks", "note": "one critic, one film",
  "picks": [ { "title": "Sinners", "year": 2025, "by": "Chris Ryan", "note": "…" } ] }
```

### draft (DraftBody)

```jsonc
{ "kind": "draft", "heading": "The teams", "draftOf": "1988 movies",
  "categories": ["Blockbuster", "Wildcard"],          // labels only, decorative
  "teams": [ { "host": "Sean Fennessey", "picks": [
    { "title": "Die Hard", "year": 1988, "category": "Blockbuster", "note": "…" } ] } ],
  "undrafted": ["Beetlejuice", "Big"] }               // year: draft→historical, so no forced year
```

### auction (AuctionBody)

```jsonc
{ "kind": "auction", "heading": "The paddles",
  "saleLabel": "Mid-year sale · 2026",                // sold-stamp fine print (hero)
  "slates": [ { "host": "Amanda", "spent": 950, "budgetLeft": 50, "picks": [
    { "title": "Sinners", "year": 2025, "price": 715, "note": "Top lot." } ] } ],
  "undrafted": ["Whalefall"],                         // "passed in", forced year 2026
  "previousSaleLabel": "January · first-half slate",
  "januarySlate": [ { "host": "Amanda", "picks": [ { "title": "…", "price": 200 } ] } ] }
```

### awards (AwardsBody)

```jsonc
{ "kind": "awards", "heading": "Our Final Oscar Predictions", "ceremony": "98th Academy Awards",
  "categories": [ { "name": "Best Picture",
    "winner": "One Battle After Another",             // marks "Winner"
    "predicted": "Sinners",                           // marks "Their pick"
    "nominees": [
      { "title": "One Battle After Another" },
      { "title": "Sinners" },
      { "title": "Wake Up Dead Man", "person": "Rian Johnson" } // person shown beside film
    ] } ] }
```

## Adding an episode

1. Transcribe (`pipeline/the_full_picture.py`), draft the segments JSON above.
2. `pipeline/spotify_id.py <slug>.json` → fills `spotifyEpisodeId`.
3. `pipeline/enrich_tmdb.py <slug>.json` → fills `tmdb`; **fix any UNMATCHED picks**.
4. Run the **film-title-reviewer** agent (required) before publishing.
5. `npm run build && npx playwright test`.
