# How to Read OpenCast

OpenCast is a release dashboard for chess-opening behavior. It shows where human play is drifting away from engine expectation, and whether those openings are strengthening or weakening over time.

## Dashboard Views

The overview page is the entry point. It shows the broadest signals: the forecast panel, the engine-vs-human delta panel, and the ECO-family summary. Use it when you want the release-level picture.

The openings table is for comparison work. It is the fastest way to scan all tracked ECOs, sort by forecast direction, and jump into a single opening.

The family view aggregates openings by ECO family. It is useful when you care about structural shifts across A, B, C, D, and E families rather than a single line.

The opening detail page combines the trend chart with the interactive board. Read it top-to-bottom as: what is this opening, what has the win-rate trend done, and what does the curated main line look like?

## What The Charts Mean

The forecast chart shows the historical white win rate and the next three projected months. The shaded interval is the model’s uncertainty band; a narrow band means the model is more confident, not that the line is guaranteed.

The engine-delta chart compares Stockfish evaluation to the observed human win rate at 2000-rated blitz. Positive delta means humans are outperforming the engine expectation; negative delta means the engine is more optimistic than real play.

The family chart is a summary view only. It is good for spotting balance across families, but it should not be used to infer detailed opening quality without drilling into the opening detail page.

## Interactive Board

The board is a curated line preview, not a full repertoire explorer. It exists to orient the reader before the forecast chart, so the page answers both "what is this opening?" and "where is it heading?".

On desktop, the board and move list sit side-by-side. On mobile, they stack vertically before the forecast chart.

## Tier Meaning

Tier 1 openings are the highest-priority analytical set. They have enough monthly volume for model-selected forecasting and engine delta analysis.

Tier 2 openings are lower-volume trend openings. They still receive forecasting, but the system prefers simpler, more stable models.

Tier 3 openings are descriptive only. They are useful for context and coverage, but they do not carry the same forecasting guarantees as Tier 1 or Tier 2.

## Limitations

- Small sample sizes can move forecasts sharply from month to month.
- Sparse openings can look stable even when they are mostly data-poor.
- Confidence intervals are empirical guides, not hard guarantees.
- The interactive board only exists when a curated line has been provided for that ECO.
