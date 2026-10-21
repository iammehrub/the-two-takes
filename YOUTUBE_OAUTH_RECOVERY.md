# YouTube OAuth recovery for Two Takes

The daily episode workflow stops before generating a video if Google rejects `YOUTUBE_REFRESH_TOKEN`.
The analytics workflow separately checks that `YOUTUBE_ANALYTICS_REFRESH_TOKEN` grants both read scopes.

## Correct recovery: separate tokens

1. In Google Cloud Console, open **Google Auth Platform -> Audience** for the same project as the YouTube OAuth client. For long-running personal automation, set the app to **In production** where appropriate. External apps left in **Testing** can receive refresh tokens that expire after seven days:
   https://developers.google.com/identity/protocols/oauth2

2. On a computer with Python and Git installed, clone this repository and enter its folder:
   ```powershell
   git clone https://github.com/iammehrub/the-two-takes.git
   cd the-two-takes
   python -m pip install google-auth-oauthlib
   ```

3. Download the OAuth client JSON for the same Google Cloud project used by this repository. Save it as `client_secret.json` in the repository root. This filename is ignored by Git, but do not upload it or share it.

4. Generate the upload token. The script opens Google's consent page; choose the channel used by Two Takes and approve the requested upload permission:
   ```powershell
   python scripts/youtube_reauthorize.py --purpose upload
   ```
   Copy the value printed between the token markers directly into the GitHub secret `YOUTUBE_REFRESH_TOKEN`.

5. Generate the separate analytics token with both read scopes:
   ```powershell
   python scripts/youtube_reauthorize.py --purpose analytics
   ```
   Copy that token directly into the GitHub secret `YOUTUBE_ANALYTICS_REFRESH_TOKEN`.

   The script requests:
   - Upload: `https://www.googleapis.com/auth/youtube.upload`
   - Analytics: `https://www.googleapis.com/auth/youtube.readonly`
   - Analytics: `https://www.googleapis.com/auth/yt-analytics.readonly`

6. In GitHub, open **Settings -> Secrets and variables -> Actions** and update the two secrets separately. Do not paste tokens into chat, issues, workflow files, logs, or commits.

7. Run **Actions -> Two Takes — Daily Episode -> Run workflow**. Confirm **Verify YouTube upload OAuth** passes. Then run **YouTube 12-Hour Analytics** and confirm **Verify YouTube analytics OAuth** passes.

## What the preflight checks do

The upload preflight checks that the upload refresh token is valid and grants the upload scope. Analytics preflight checks that its separate token is valid and grants both required read scopes. The workflows stop before expensive work when those checks fail.

## Important

The refresh token values are private credentials; store them only in GitHub Actions Secrets. If a token works and then expires again after about seven days, check the OAuth app publishing status in Google Cloud Console. Creating repeated tokens without fixing a Testing-status expiry can repeat the same failure.
