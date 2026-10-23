# My Daily HQ — operations dashboard

The dashboard is the root \`index.html\` in this repository. It combines creator reporting with public GitHub workflow monitoring.

## Publish the dashboard (free)

1. Open https://github.com/iammehrub/the-two-takes/settings/pages
2. Under **Build and deployment**, set **Source** to **GitHub Actions** and save.
3. Open https://github.com/iammehrub/the-two-takes/actions/workflows/pages-dashboard.yml and run **Deploy My Daily HQ** once if it has not started automatically.
4. After the deployment succeeds, open **Settings → Pages** for the exact published URL. The usual project URL is \`https://iammehrub.github.io/the-two-takes/\`.

The \`.github/workflows/pages-dashboard.yml\` workflow publishes only \`index.html\`; it does not copy repository source files or workflow files into the site artifact. Later changes to the dashboard page redeploy it automatically.

## What is connected

- **Public repositories:** loads the owned public repositories from the GitHub public API.
- **Workflow status:** loads recent Actions results for up to the 12 most recently updated active public repositories. The page shows succeeded, failed, queued/running, skipped, cancelled and other statuses; run links open the original GitHub run and logs.
- **Transparent triage:** gives rule-based hints based on a failing workflow's name/type. It does not claim to read private logs or provide an LLM-generated diagnosis.
- **YouTube channel report:** reads \`data/youtube_deep_analytics.json\`, which your existing analytics workflow saves.
- **Video report history:** reads \`data/youtube_analytics_state.json\`, shows per-video snapshots and saved recommendations, and filters records by when the snapshot was stored.
- **Existing daily tools:** routine, Bangladesh/AI/world news and A2–B1 vocabulary remain on the page.

## Data limitations

- The page is public. **Private repositories are intentionally not listed.** Do not put a GitHub personal access token, YouTube OAuth credentials, Discord webhook, API key or private repository metadata into HTML or other public files.
- GitHub's unauthenticated public API has rate limits. If a refresh fails with an HTTP 403, wait and retry rather than repeatedly refreshing.
- The dashboard lists the latest 18 matching workflow rows from the fetched history. Each checked repository contributes up to 8 recent runs. This is a recent monitor, not a complete audit of every historical run.
- The YouTube channel metrics show the saved reporting window displayed on screen; they are not guaranteed real-time. Video views/likes/comments in the history are totals captured at that report time, **not exact views gained during the selected 12-hour/24-hour/7-day period**.
- The current JSON report does not provide impressions or click-through rate, so the dashboard does not invent them.
- If the analytics report is stale, open the **YouTube 12-Hour Analytics** workflow and check its latest run.

## If deployment does not start

Go to **Settings → Pages**, choose **GitHub Actions** as the publishing source, then run the deployment workflow manually. Inspect the deployment run if it fails.

## Security and next stage

The website calls only public GitHub endpoints and downloads public saved analytics JSON. It never asks for or stores tokens. To monitor private repos or get actual AI-written diagnoses from failure logs, use a private authenticated backend or a GitHub Actions job that sends only necessary, sanitized log context to the model using a repository secret. Never put that model key in browser JavaScript.

Routine entries are saved locally in the browser and do not sync between devices. Browser reminders are not reliable when the page/browser is closed or a phone restricts background activity.
