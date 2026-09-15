THE TWO TAKES — SIMPLE SETUP
============================

Channel: The Two Takes
Tagline: Two voices. One topic. A fresh perspective.
Hosts: Himel (male) + Niha (female)
Target: one ~10-minute episode every day at 8:00 AM Bangladesh time.

IMPORTANT
---------
This package uses Activepieces as the scheduler and GitHub Actions as the free cloud video builder.
You do NOT need to keep your PC on.

WHY GITHUB?
-----------
Activepieces is excellent for scheduling and API calls, but it is not a good place to render a 10-minute MP4 with FFmpeg.
GitHub Actions does the heavy work in the cloud.
Use a PUBLIC GitHub repository for the workflow so standard GitHub-hosted runner time is free. Do not put API keys in the repository files; use GitHub Secrets.

WHAT THE AUTOMATION DOES
------------------------
1. Fetches current headlines from Google News RSS.
2. Gemini chooses one current topic and writes an original 1,350–1,550 word Himel/Niha conversation.
3. Gemini 2.5 Flash Preview TTS creates a two-speaker voice track.
4. Pexels API supplies topic-related video clips.
5. FFmpeg creates a branded hybrid podcast video with captions.
6. A branded thumbnail is generated automatically.
7. The finished video is uploaded publicly to YouTube.

ONE-TIME SETUP
--------------
A) GitHub
1. Create a PUBLIC repository.
2. Put the contents of the github/ folder into the repository root.
3. The file must end up at .github/workflows/daily-podcast.yml
4. Keep the repo public so standard GitHub-hosted Actions usage is free.

B) GitHub Secrets
Repository → Settings → Secrets and variables → Actions → New repository secret.
Add exactly these names:

GEMINI_API_KEY = your new Gemini API key
PEXELS_API_KEY = your Pexels API key
YOUTUBE_CLIENT_ID = Google OAuth client ID
YOUTUBE_CLIENT_SECRET = Google OAuth client secret
YOUTUBE_REFRESH_TOKEN = YouTube OAuth refresh token

Never paste secrets into code, screenshots, commits, or this chat.

C) Activepieces
1. Import Activepieces_The_Two_Takes.json.
2. Open the HTTP step called “Start GitHub video builder”.
3. Replace YOUR_GITHUB_USERNAME/YOUR_REPO in the URL.
4. Replace YOUR_GITHUB_TOKEN with a GitHub token that can dispatch workflows in your repository.
5. Save/publish the flow.

D) YouTube OAuth
Create a Google Cloud OAuth client for a desktop app, enable YouTube Data API v3, and obtain a refresh token with the youtube.upload scope. Put the resulting values into the three YouTube GitHub secrets above.

E) Pexels
Create a free Pexels API key and add it as PEXELS_API_KEY. The workflow credits Pexels in each YouTube description.

TEST
----
Before relying on the daily schedule, manually run the GitHub workflow once from the Actions tab. If it succeeds, the 8 AM Activepieces trigger can run it automatically.

FREE-COST NOTES
---------------
Gemini 2.5 Flash Preview TTS currently has a documented free tier. Pexels API is free with default limits. GitHub Actions standard runners are free for public repositories. Your actual availability can still depend on provider quotas/changes, so monitor the first few runs.

SAFETY / QUALITY
----------------
The script prompt asks Gemini not to invent facts and uses current Google News RSS headlines as the freshness input. It is still AI-generated content, so review the first few episodes before leaving automatic public publishing enabled.
