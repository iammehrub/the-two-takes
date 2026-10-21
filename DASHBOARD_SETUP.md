# My Daily HQ dashboard setup

The dashboard is the root `index.html` in this repository. It is a static, mobile-friendly starter.

## Publish it with GitHub Pages

1. Open https://github.com/iammehrub/the-two-takes/settings/pages
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **main** and folder **/(root)**, then save.
4. Wait for the Pages deployment to finish. GitHub will show the published website URL in the Pages settings.

The URL is not guaranteed to be live until Pages is enabled and its first deployment succeeds.

## What works in this starter

- Shows the current date and time in Asia/Dhaka.
- Lets you add, complete, and delete routine items.
- Saves routine items in local browser storage on that device.
- Requests browser notification permission and can show reminders while the page/browser is able to run.
- Tries to load Bangladesh, AI/technology, and world headlines from GDELT, with a fallback news-search link.
- Includes an A2–B1 English vocabulary card.
- Provides 12-hour, 24-hour, and 7-day analytics range controls.

## Not connected yet

The website does not yet receive live YouTube Analytics numbers or upload status from GitHub Actions. The metric values intentionally remain blank rather than displaying invented data. Connect the existing YouTube analytics and notification workflows through a small JSON data feed or authenticated backend before showing real channel data.

**Security:** Never put YouTube OAuth refresh tokens, client secrets, Discord webhook URLs, or other secrets into `index.html` or any file downloaded by the browser. Keep secrets in GitHub Actions Secrets and publish only the minimum non-sensitive metrics needed by the dashboard.

## Important limitations

- Browser-local routine data does not sync to other devices or browsers.
- Browser notifications are not a reliable alarm when the page is closed or the phone restricts background activity.
- News availability depends on the external feed and network.
