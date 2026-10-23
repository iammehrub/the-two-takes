# Facebook publishing setup — Two Takes Podcast

This adds Facebook Page publishing to the existing YouTube production pipeline. It does not create a second podcast or render another video.

## What gets published

- The same work/the_two_takes.mp4 full episode that the YouTube pipeline uploads.
- The first eligible file in work/shorts/shorts_manifest.json. This is also the Short selected by the existing YouTube uploader.
- The Facebook Reel caption links to the full episode on the Facebook Page. The YouTube Short continues linking to the YouTube full episode.

The Facebook step runs after the episode build and YouTube upload. If the Facebook secrets are missing, the step records a skipped_not_configured report and does not post anything.

## One-time Facebook setup

1. Create or use the **Two Takes Podcast** Facebook Page. Your Facebook account must have permission to create content on that Page.
2. In Meta for Developers, create or use an app with Facebook Login / Pages access. In the Graph API Explorer, select your app and get a **User Access Token** with these permissions:
   - pages_show_list
   - pages_read_engagement
   - pages_manage_posts
3. Use the User Access Token to call GET /me/accounts?fields=name,id,access_token,tasks. Identify **Two Takes Podcast**, then copy its numeric id and its Page access_token. Check that the returned tasks include content creation. Never put either token in code, commit history, Discord, or a screenshot.
4. In the GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:
   - FACEBOOK_PAGE_ID — the numeric ID for the Two Takes Podcast Page.
   - FACEBOOK_PAGE_ACCESS_TOKEN — the Page access token returned for that Page.
5. Optional repository variable: FACEBOOK_GRAPH_API_VERSION. The code defaults to v26.0; change it only after verifying the currently supported version in Meta's docs.
6. Open **Actions → Podcast Production Tests** and run it once. Then let **Actions → Two Takes — Daily Episode** run on its next schedule. Avoid rerunning a successful episode job because it creates and uploads another episode.

Tokens can expire or be revoked and Meta permissions can change. Keep the token private and renew it if Facebook reports an authentication or permission error.

## Troubleshooting

Open the daily workflow run and inspect **Publish episode and matching Reel to Facebook**. The report is saved in the workflow artifact as facebook_publish.json. It records whether the full episode and Reel were submitted, skipped, or failed. Meta may continue processing a Reel after accepting the publish request, so allow time for it to appear on the Page.

This workflow posts publicly to the configured Facebook Page. Add the secrets only when you are ready for automatic public publishing.
