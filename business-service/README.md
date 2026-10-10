# Business Content Studio — Free Starter Kit

An approval-first tool for preparing social-content drafts for small businesses. The core workflow uses Python and GitHub Actions without a paid service or AI API.

## Four included parts

1. **Writing generator:** seven captions and a calendar. It runs with templates at no cost. Optional OpenRouter free-model routing can improve wording if you configure your own free-tier API key; free availability/rate limits can change. No paid model is selected by this project.
2. **Sample pack:** a clearly labeled fictional Dhaka cafe sample in `sample-pack/`. It is a portfolio example, not a real client result.
3. **Customer-acquisition kit:** service offer, intake form, portfolio checklist, pricing worksheet, and outreach drafts. Messages are drafts only; send them manually after reviewing and personalizing.
4. **Business dashboard:** a standalone HTML file at `dashboard.html`. It stores your prospect/client tracker in this browser only and supports JSON export/import. It has no server, paid database, or automatic messaging.

## What the generator does

- Reads a business profile JSON file.
- Creates seven caption drafts, a seven-day calendar, visual directions, and a factual/approval checklist.
- Exports Markdown and JSON.
- Runs in GitHub Actions when manually started; your computer can be off.
- Never publishes posts, messages prospects, or processes payments.

## Quick start — fully free, no API

From the repository root:

```bash
python business-service/generate_demo.py --profile business-service/client_profile.example.json --mode template --start-date 2026-10-12
```

Outputs:
- `work/business_service_demo/content_pack.md`
- `work/business_service_demo/content_pack.json`

### Optional free AI writing

If you choose to use OpenRouter, create a free-tier key in your own account and add it to the repository as the Actions secret `OPENROUTER_API_KEY`. Never paste the key into code or chat. The workflow requests the `openrouter/free` router and falls back to templates if unavailable. Free models may be rate-limited, unavailable, or change. Keep `--mode template` for a no-key/no-network run.

## Run on GitHub

1. Open the [Business Content Studio workflow](../.github/workflows/business-content-studio-demo.yml).
2. Choose **Run workflow** and optionally enter a start date as `YYYY-MM-DD`.
3. Open the completed run and download the `business-content-studio-demo` artifact.
4. Review the Markdown and JSON pack. Artifacts expire after seven days.

## Sample portfolio

See [sample pack](sample-pack/README.md). It is fictional and deliberately avoids unverified prices, hours, testimonials, and performance claims. Replace it with a client-approved example only after receiving permission.

## First pilot offer

Offer seven caption drafts, a one-week calendar, visual suggestions, a factual review checklist, and one revision round. Agree on deliverables, deadline, revisions, fee, and payment terms before work starts. Do not promise sales, virality, reach, or follower growth.

See [service offer](service-offer.md), [client intake](client-intake.md), [prospect message drafts](prospect-message-drafts.md), and [free pricing worksheet](pricing-worksheet.md).

## Dashboard privacy and limitations

Open `dashboard.html` in a browser. Records are saved in that browser's local storage and do not automatically sync to another device. Export backups regularly. Do not store passwords, tokens, bank details, or sensitive customer data. This dashboard does not collect payments or send outreach.

## Tests

```bash
python -m unittest discover -s business-service -p 'test_*.py' -v
```

## Honest limitations

This is a small content-preparation tool, not an autonomous agency. AI output is not fact-checked research. A human must verify and approve every draft. Free-tier service availability can change. All publishing, outreach, pricing agreements, and payment handling remain manual.
