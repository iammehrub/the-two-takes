# YouTube OAuth recovery for Two Takes

The Daily Podcast workflow stops before generating a video when Google rejects the stored
`YOUTUBE_REFRESH_TOKEN`. The latest checked run reported that the refresh token is expired or revoked.
The YouTube Analytics workflow also lacked `YOUTUBE_ANALYTICS_REFRESH_TOKEN`.

## Permanent recovery

1. In Google Cloud Console, open **Google Auth Platform -> Audience** for the same project used by
   `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET`.
2. For a long-running personal automation, change the app publishing status from **Testing** to
   **In production**. Google documents that refresh tokens issued while an external OAuth app is in
   Testing can expire after 7 days:
   https://developers.google.com/identity/protocols/oauth2
3. Generate a fresh token for the **same OAuth client** with all three scopes:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`

   From a local clone, run `python scripts/youtube_reauthorize.py`. The script opens Google's
   consent flow and prints the token locally. Use a client JSON file saved as `client_secret.json`
   in the repository root, or set `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in your local
   environment before running it. Never commit `client_secret.json` or the generated token.

   You can also use Google's OAuth 2.0 Playground with **your own OAuth client credentials** and
   offline access, requesting all three scopes above.
4. In GitHub, open **Settings -> Secrets and variables -> Actions**. Update
   `YOUTUBE_REFRESH_TOKEN` with the newly generated token.
5. The analytics workflow now uses `YOUTUBE_ANALYTICS_REFRESH_TOKEN` when that secret exists, and
   otherwise falls back to `YOUTUBE_REFRESH_TOKEN`. Therefore, one combined-scope token is enough;
   optionally, the same value can also be saved as `YOUTUBE_ANALYTICS_REFRESH_TOKEN`.
6. Run **Actions -> Two Takes — Daily Episode -> Run workflow**. Confirm the
   **Verify YouTube upload OAuth** step passes. Then run **YouTube 12-Hour Analytics** manually and
   confirm **Verify YouTube analytics OAuth** passes.

## What the workflows verify

Before spending time generating audio/video, the upload preflight refreshes the Google credential and
checks the YouTube upload scope. Analytics preflight checks that the token is valid and includes both
read scopes. Both stop early if Google rejects the refresh token or if required scopes are missing.

## Important

Do not paste tokens into chat, issue comments, workflow files, logs, or commits. Put the token only in
GitHub Actions Secrets. If a newly created token expires again after roughly seven days, verify that
the OAuth app is no longer in Testing; creating another token without addressing Testing status may
only repeat the problem.
