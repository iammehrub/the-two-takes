# Two Takes Podcast: 30-day growth system

This is a free-first operating plan for the existing channel. It does not change the
channel niche, copy another creator, alter thumbnails, or publish videos automatically.

## Weekly review loop

1. Export video-level analytics from YouTube Studio as CSV.
2. Include title, views, impressions, impressions click-through rate, average view
   duration, watch time, subscribers gained, and intro/0:30 retention where available.
3. Run:
   `python scripts/weekly_growth_report.py studio-export.csv --output weekly-growth-report.md`
4. Review the three category leaders and the individual videos before choosing next week's
   topics. Keep Shorts and long-form in separate exports/reviews.
5. Use CTR to diagnose packaging, 0:30 retention to diagnose the cold open, average view
   duration to diagnose episode engagement, and subscribers gained to identify topics
   that attract returning learners.

The report accepts YouTube Studio CSV exports with localized/renamed headers only when
they match one of the supported header aliases in the script. Missing metrics are clearly
reported as unavailable; the script never invents them.

## Content categories

- Real-life English: specific everyday situations and practical dialogue.
- Speaking Confidence: getting unstuck, fluency, pronunciation, and speaking anxiety.
- Vocabulary in Context: phrases and expressions taught through examples.

The categories are a starting taxonomy, not a claim that these are already proven winners.
The weekly report ranks only the videos present in the supplied CSV.

## Production standard

- One concrete learner promise per episode.
- Hook immediately; avoid generic welcome/introduction padding.
- Himel and Niha should sound like two people having a useful, natural conversation.
- Teach phrases in context, then include actual repeat-after-us pauses.
- Keep the existing single wide two-host composition.
- Accurate, readable, keyword-emphasized subtitles.
- Run dialogue quality checks before rendering; listen to the finished episode before publishing.

## 30-day operating targets

- 25–30 quality long-form episodes, only if quality remains stable.
- 30–45 Shorts selected from useful moments in the long-form episodes.
- Four weekly compilations, only when there is enough coherent material.
- Identify three categories that repeatedly produce strong retention and subscriber gains.
- Improve subscriber conversion and average view duration against the channel's own baseline.

These are production and learning targets, not guaranteed audience outcomes.

## Roadmap status

- Dialogue quality scoring: available in the separate draft upgrade PR #8.
- Vocabulary-highlighted captions: available in PR #8.
- Repeat-after-us timing: available in PR #8.
- Weekly CSV analytics report and category-based topic directions: added in this branch.
- Smart Shorts scoring: next implementation; current clip selection should not be called
  performance-predictive until it is validated against actual Shorts analytics.
- Automatic comment intelligence: requires a supported comments data source and privacy-
  preserving aggregation; keep it read-only.
- Thumbnail/title experimentation: use YouTube Studio's actual impressions and CTR data.
  Do not auto-change packaging based on tiny samples.
- Compilation automation: should assemble only approved, coherent segments and avoid
  duplicate uploads.

## Explicit boundaries

- No paid API is required for the CSV report.
- CTR and first-30-second retention are not reliably available from every standard CSV
  export; export those fields from Studio or leave them marked unavailable.
- This script is read-only with respect to YouTube. It writes a local Markdown report only.
- Nothing in this branch changes the scheduled publishing workflow.
