# Business Content Studio — Zero-Cost Starter Kit

A lightweight, approval-first tool for preparing social-content drafts for small businesses. It helps you test a service offer without paying for an AI API or connecting a client's social account.

## What it does
- Reads a business profile JSON file.
- Creates seven distinct caption drafts, a seven-day calendar, visual directions, and a review checklist.
- Uses the business name, industry, location, audience, offer, channel, tone, confirmed facts, and claims to avoid.
- Exports Markdown (easy to review/share) and JSON (structured for future tools).
- Runs in GitHub Actions when manually started; your computer can be off.
- Keeps every item in draft status. It does not publish posts, message prospects, or spend money.

**Important limitation:** this is template-assisted copy, not an AI model. It does not browse the web, verify business details, or guarantee custom marketing quality. A human must edit and approve every draft.

## Quick start
From the repository root:

```bash
python business-service/generate_demo.py --profile business-service/client_profile.example.json --start-date 2026-10-12
```

Outputs:
- `work/business_service_demo/content_pack.md`
- `work/business_service_demo/content_pack.json`

Omit `--start-date` to start from today.

## Make a prospect-specific profile
1. Copy `client_profile.example.json` to a new JSON file.
2. Replace fictional sample details with public information or facts the business explicitly confirmed.
3. Keep `brand_facts` limited to verified details and list unsupported claims in `avoid_claims`.
4. Run the generator with your copied profile.
5. Review and customize every caption before sharing. Never add passwords, access tokens, private customer lists, or sensitive personal data.

## Run it on GitHub
1. Open the [Business Content Studio workflow](../.github/workflows/business-content-studio-demo.yml).
2. Choose **Run workflow** and optionally enter a start date as `YYYY-MM-DD`.
3. Open the completed run and download the `business-content-studio-demo` artifact.
4. Review the Markdown and JSON pack before using it. Artifacts expire after seven days.

## Suggested first service
Offer a small pilot: seven caption drafts, a one-week calendar, visual suggestions, a factual review checklist, and one revision round. Agree on price, deadline, revisions, and payment terms before work starts. Do not promise sales, virality, reach, or follower growth. This repo does not process payments or automatically acquire customers.

See [service offer](service-offer.md), [client intake](client-intake.md), and [prospect message drafts](prospect-message-drafts.md). Personalize any outreach and send it yourself only after reviewing it; do not mass-message businesses.

## Tests
```bash
python -m unittest discover -s business-service -p 'test_*.py' -v
```

## Later upgrades
An optional AI provider could improve originality, but requires an authorized API key and may have limits or costs. Add it only after the free workflow proves useful. Any publishing integration should require explicit client authorization and a tested approval gate.
