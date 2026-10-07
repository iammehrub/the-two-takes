# YouTube OAuth recovery for Two Takes

The Daily Podcast workflow is blocked before video generation when Google rejects the stored
YOUTUBE_REFRESH_TOKEN.

## Permanent recovery

1. In Google Cloud Console, open the OAuth consent screen for the same project used by
   YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET.
2. Change the app publishing status from **Testing** to **In production** when this is a
   long-running personal automation. Google documents that refresh tokens issued while an
   external OAuth app is in Testing can expire after 7 days.
3. Create a fresh refresh token for the same OAuth client with this scope:

   https://www.googleapis.com/auth/youtube.upload

   The repository also contains scripts/youtube_reauthorize.py for a local browser-based
   authorization flow. It requires the OAuth client credentials locally and never writes the
   token to the repository.

   Another option is Google's OAuth 2.0 Playground using the custom OAuth credentials for
   this same client. Use offline access and consent, authorize the YouTube upload scope,
   exchange the authorization code, and copy the new refresh token.
4. In GitHub:
   Settings -> Secrets and variables -> Actions -> YOUTUBE_REFRESH_TOKEN -> Update secret
   with the new token.
5. Do not paste the token into chat or commit it to Git.
6. Run Actions -> Two Takes - Daily Episode -> Run workflow.

## What the workflow verifies

Before spending time generating audio/video, youtube_upload_preflight.py refreshes the
Google credential and calls the YouTube Data API. The workflow stops immediately when the
refresh token is missing, expired, revoked, or lacks the upload scope.

Once the preflight passes, the existing build -> render -> upload -> Discord -> repository
recording pipeline can proceed.

## Important

The workflow's YOUTUBE_REFRESH_TOKEN secret is the credential that failed in Run #110.
Changing Python scopes alone cannot repair a revoked/expired refresh token; Google requires
reauthorization and a newly issued token.
