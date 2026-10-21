# Fix YouTube Analytics with OAuth 2.0 Playground

The analytics workflow's old refresh token was missing the required YouTube read scopes. This guide uses Google's browser-based OAuth 2.0 Playground; it does not require running the local reauthorization script.

## 1. Prepare a dedicated OAuth 2.0 client for analytics

Keep the analytics client separate from the existing upload credentials, so repairing analytics does not break the upload workflow.

1. Open Google Cloud Console: https://console.cloud.google.com/
2. Select the Google Cloud project used for Two Takes. Under **APIs & Services → Library**, enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Open **Google Auth Platform** (or **APIs & Services → OAuth consent screen**, depending on the console layout). Configure the consent screen. If the app is External and remains in Testing, add the Google account that owns/manages the YouTube channel as a test user.
4. Under **APIs & Services → Credentials**, create an OAuth client ID of type **Web application**. Name it something clear such as `Two Takes Analytics Playground`.
5. Under **Authorized redirect URIs**, add this exact URL:
   `https://developers.google.com/oauthplayground`
6. Save. Keep the new client ID and client secret private. These credentials are specifically for the analytics flow; do not replace your existing upload client credentials.

**Important for automation:** Google OAuth apps left in **Testing** can have refresh tokens for non-basic scopes expire after seven days. Check the app's publishing status and Google's current requirements if you need long-running automation. Do not ignore an OAuth warning unless you recognize your own project and understand why the warning appears.

## 2. Authorize in Google's OAuth 2.0 Playground

1. Open the official [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/).
2. Click the **settings gear**.
3. Set **OAuth flow** to **Server-side**, **Access type** to **Offline**, and **Force prompt** to **Consent Screen**.
4. Check **Use your own OAuth credentials**. Enter the new Web application client ID and client secret from Step 1. The Playground needs these to issue a refresh token for your own client instead of its temporary default client.
5. In **Step 1 — Select & authorize APIs**, use the custom scopes input and enter these two scopes separated by a space:

   ```text
   https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly
   ```

6. Click **Authorize APIs**. Sign in with the Google account that manages the intended YouTube channel, and review/approve the requested permissions.
7. In **Step 2**, click **Exchange authorization code for tokens**.
8. Copy the **Refresh token** shown in Step 2. Do not use the short-lived access token. Treat the refresh token like a password: do not paste it into chat, email, issues, or repository files.

Google's Playground says that when you supply your own OAuth client, its default 24-hour refresh-token revocation behavior does not apply. The token can still become invalid if access is revoked or Google policy conditions apply.

## 3. Add the three analytics secrets in GitHub

Open the repository's [Actions secrets settings](https://github.com/iammehrub/the-two-takes/settings/secrets/actions). Create or update these repository secrets:

- `YOUTUBE_ANALYTICS_CLIENT_ID` — the new OAuth 2.0 **Web application** client ID.
- `YOUTUBE_ANALYTICS_CLIENT_SECRET` — the matching client secret.
- `YOUTUBE_ANALYTICS_REFRESH_TOKEN` — the refresh token returned by Step 2 in OAuth Playground.

Save each secret. Do **not** change `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, or `YOUTUBE_REFRESH_TOKEN`; those remain for the existing upload integration. The analytics workflow has been updated to use the analytics-specific client credentials when they are present, while retaining fallback compatibility if those dedicated secrets are not set.

## 4. Run a verification

1. Open [YouTube 12-Hour Analytics Actions](https://github.com/iammehrub/the-two-takes/actions/workflows/youtube-analytics.yml).
2. Select **Run workflow**, choose branch `main`, then confirm **Run workflow**.
3. Open the new run. The **Verify YouTube analytics OAuth** step should pass and list both scopes.
4. Once the preflight passes, the workflow can query eligible YouTube Analytics data and send due reports to Discord. If no video checkpoint is due, it may finish without sending an individual video report.

If verification fails, check that all three analytics secrets belong to the same new Web application OAuth client, that both scopes were granted, and that the authorized redirect URI matches exactly. Never share client secrets or tokens when asking for help.

## What this fixes

This lets the automation refresh its analytics access token with both required scopes. It does not recreate exact historical 12-hour or 24-hour totals that were never captured, and YouTube Analytics data can lag.
