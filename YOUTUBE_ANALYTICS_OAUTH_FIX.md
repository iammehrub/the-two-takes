# Fix YouTube Analytics OAuth

The analytics workflow was failing because the saved refresh token did not grant both read-only scopes. The upload token and analytics token are separate on purpose.

## 1. Create a correctly scoped analytics refresh token

Do this on your own Windows computer. **Never paste the refresh token or OAuth client secret into chat, commit them to GitHub, or put them in a public file.**

1. Open Google Cloud Console: https://console.cloud.google.com/
2. Select the same Google Cloud project used by Two Takes. Make sure **YouTube Data API v3** and **YouTube Analytics API** are enabled.
3. Under **APIs & Services → Credentials**, download the OAuth client JSON for a **Desktop app** client. If you do not already have a Desktop app OAuth client, create one. Keep this JSON private.
4. Download/clone this repository to your computer, and save that JSON in the repository root as `client_secret.json`. This file is ignored by Git; still, do not commit it.
5. Open a terminal in the repository folder and run:

   ```powershell
   python -m pip install -r requirements.txt
   python scripts/youtube_reauthorize.py --purpose analytics
   ```

6. A browser opens. Sign in to the Google account that owns/manages the correct YouTube channel and approve both requested read-only permissions:
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`
7. Copy the **new analytics refresh token** printed in the terminal. Treat it like a password. Do not share it with anyone or commit it.

If Google shows an OAuth app warning, only continue if you recognize that this is your own Google Cloud project and OAuth client. If the consent screen is in Testing mode, refresh tokens for non-basic scopes may expire after seven days; configure the app appropriately in Google Cloud Console if this keeps happening.

## 2. Replace the GitHub secret

1. Open the repository's [Actions secrets settings](https://github.com/iammehrub/the-two-takes/settings/secrets/actions).
2. Edit or create the repository secret named exactly `YOUTUBE_ANALYTICS_REFRESH_TOKEN`.
3. Paste the new refresh token as its value and save.
4. Do **not** replace `YOUTUBE_REFRESH_TOKEN`; that secret is used by the upload workflow.

The workflow now requires `YOUTUBE_ANALYTICS_REFRESH_TOKEN` explicitly instead of silently falling back to the upload token.

## 3. Verify the repair

1. Open [YouTube 12-Hour Analytics Actions](https://github.com/iammehrub/the-two-takes/actions/workflows/youtube-analytics.yml).
2. Choose **Run workflow** → branch `main` → **Run workflow**.
3. Open the new run. The step **Verify YouTube analytics OAuth** must say that the OAuth check passed and confirm both scopes.
4. If it passes, the workflow can continue to query eligible reports and send due checkpoint reports to Discord. If no video checkpoint is due, it may finish without sending a video report.

## What this fixes—and what it does not

This resolves the missing-permissions problem once the new token is saved. It cannot retroactively recover exact 12-hour/24-hour historical totals that YouTube did not record, and YouTube Analytics data can lag. Never post tokens, OAuth client JSON, or screenshots that reveal secrets when asking for help.
