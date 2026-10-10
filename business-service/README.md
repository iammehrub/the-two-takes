# Business Content Studio — Zero-Cost Starter Kit

A small, approval-first demo for offering content-planning and social-post preparation to local businesses. This is a service starter, not a claim of completed client work or guaranteed income.

## What it does now

- Reads a business profile JSON file.
- Generates a 7-day content plan with caption drafts and a clear approval status.
- Saves the pack to `work/business_service_demo/`.
- Uses only Python's standard library; no API key or paid service is required for the demo.
- Does not publish, message customers, or spend money.

## Quick start

From the repository root:

```bash
python business-service/generate_demo.py --profile business-service/client_profile.example.json
```

Output: `work/business_service_demo/content_pack.md` and `work/business_service_demo/content_pack.json`.

## Make a prospect-specific demo

1. Copy `client_profile.example.json` and edit the copy with a business's public-facing details.
2. Run the command above with your copied profile path.
3. Review every draft for accuracy and brand fit.
4. Share only after you approve it. Do not put private customer data or credentials in the profile.

## What a paid service could include

- Weekly content calendar and caption drafts.
- Brand voice and FAQ setup.
- Human-approved scheduling/publishing integration as a separate phase.
- Monthly performance report, if the customer connects suitable analytics.

Start with a narrow promise: "I prepare a week's worth of reviewed social content drafts." Do not promise sales growth, virality, or guaranteed results. Ask the client what success metric matters and establish a baseline before claiming impact.

## Client approval boundary

Every generated item is marked `DRAFT — HUMAN APPROVAL REQUIRED`. The demo intentionally has no publishing or outbound-messaging capability. Add integrations only after the client authorizes them and a review step is tested.

## Free workflow demo

The GitHub Actions workflow `Business Content Studio — Demo Pack` can be run manually to generate an artifact. It does not publish externally. The artifact is for internal review only.

## Next implementation steps

1. Replace the sample profile with a clearly fictional demo or a prospect's public business information.
2. Collect feedback and refine the template.
3. Add an optional AI provider only if the service has authorized credentials and the cost is understood.
4. Add client-specific publishing only behind an explicit approval gate.
