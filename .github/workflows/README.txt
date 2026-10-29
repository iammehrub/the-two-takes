TWO TAKES PODCAST — SCHEDULER SETUP
===================================

Channel: Two Takes Podcast
Hosts: Himel (male) + Niha (female)
Target: one podcast episode daily.

HOW SCHEDULING WORKS
--------------------
There are two intended triggers:
1. GitHub Actions built-in schedule: 08:07 Bangladesh time, with a 09:17 Bangladesh-time recovery trigger.
2. An optional Activepieces schedule at 08:00 Bangladesh time that calls the GitHub workflow_dispatch API.

GitHub Actions builds and publishes the episode in the cloud; your PC does not need to be on.

IMPORTANT FINDING
-----------------
The Activepieces JSON stored in this repository is an export template only. It is marked DRAFT and does not activate a flow in your Activepieces account by itself. The export was repaired to point to the correct repository, but the real flow still needs to be imported, have its token configured securely, and be published/activated in Activepieces. This ChatGPT GitHub connection cannot activate an external Activepieces instance.

ACTIVEPIECES SETUP
------------------
1. In Activepieces, import .github/workflows/Activepieces_The_Two_Takes.json from this repository.
2. Open the HTTP step named “Start GitHub video builder”.
3. The URL should be:
   https://api.github.com/repos/iammehrub/the-two-takes/actions/workflows/daily-podcast.yml/dispatches
4. Replace YOUR_GITHUB_TOKEN inside Activepieces with a fine-grained GitHub token scoped to the iammehrub/the-two-takes repository and with Actions: read/write permission.
5. Do not put the real token in this repository, in a commit, or in chat.
6. Save and PUBLISH/ACTIVATE the flow. A saved draft does not run on schedule.
7. Use the Activepieces test-run feature once and verify the GitHub Actions workflow starts.

GITHUB WORKFLOW
---------------
Workflow file: .github/workflows/daily-podcast.yml
Run page: https://github.com/iammehrub/the-two-takes/actions/workflows/daily-podcast.yml
Schedule: 02:07 UTC (08:07 Bangladesh time), plus 03:17 UTC (09:17 Bangladesh time) as a guarded recovery attempt.
The publish guard avoids publishing twice on the same Bangladesh calendar date.

DEBUGGING HISTORY
-----------------
The 28 October scheduled runs failed in the publish_guard because the old code put the entire GitHub workflow-run response into an environment variable, triggering “Argument list too long.” The current main-branch workflow reads the response from a temporary file instead. A later manual run completed successfully, but the following day's scheduled publication still needs a fresh scheduled-run confirmation.

YOUTUBE UPLOAD SECRETS
----------------------
The repository workflow expects these GitHub Actions secrets:
- GEMINI_API_KEY
- PEXELS_API_KEY
- YOUTUBE_CLIENT_ID
- YOUTUBE_CLIENT_SECRET
- YOUTUBE_REFRESH_TOKEN

Never put secrets in code. If an upload fails with invalid_grant, re-authorize YouTube and update YOUTUBE_REFRESH_TOKEN in GitHub repository secrets.

SAFE TESTING
------------
Run GitHub Actions manually from the Actions tab to test the pipeline. Note that the workflow performs real YouTube publishing when it reaches the upload stage, so use this intentionally and check the generated run/video afterward.

COST NOTES
----------
GitHub Actions availability and provider quotas may change. Monitor the first few runs rather than assuming every scheduled trigger will execute on time.
