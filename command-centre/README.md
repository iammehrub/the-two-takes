# Personal Command Centre MVP

This directory contains an isolated, no-build dashboard prototype inspired by a personal Command Centre / Warehouse setup.

## Open it
Open [index.html](./index.html) in a current browser. It does not require Node.js or a paid hosting service.

## Working now
- Overview, Focus & Tasks, Content Studio, Sponsor CRM, Research & Memory, and Automation Lab.
- Add/check tasks; create content cards and move them through Idea → Recorded → In Edit → Ready to Publish.
- Add sponsor records and update their stage. No outreach is sent.
- Daily rotating paraphrased book lessons and curated weird-knowledge facts with source links.
- Save local memory notes and export a JSON backup.
- Links to the existing Notion Command Centre and GitHub workflow monitor.

## Limitations — do not mistake this for production deployment
- Records are stored in this browser's localStorage. They do not sync across devices.
- News is not fetched automatically; the source shelf links to official sources.
- OpenRouter / LLM calls, Supabase auth/database, live GitHub/YouTube imports, Telegram, calendar sync, and Hermes Agent are not connected yet.
- This app does not run background or autonomous jobs.
- Never put API keys, passwords, OAuth tokens, or other secrets in this HTML file or browser storage.

## Recommended next implementation steps
1. Move the UI into a dedicated repository and Next.js App Router app.
2. Add Supabase Auth + PostgreSQL, row-level security, backups, and per-user access.
3. Add server-side model routes using protected environment variables, usage caps, and request logging.
4. Add scheduled data ingestion for approved news feeds and read-only GitHub / YouTube reporting.
5. Start Hermes Agent with read-only research and morning-briefing tasks, followed by explicit approval gates for any external actions.
6. Deploy behind HTTPS and authentication, then add Telegram with a private user/chat allowlist.

## Existing systems
- Notion HQ: https://app.notion.com/p/4026d90fa42981199432cc6e5e693bcf
- GitHub monitor: https://github.com/iammehrub/the-two-takes/actions/workflows/notion-command-center-monitor.yml
- Supabase docs: https://supabase.com/docs
- OpenRouter docs: https://openrouter.ai/docs
- Hermes Agent docs: https://hermes-agent.nousresearch.com/docs/
