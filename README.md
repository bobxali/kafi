# Daily Al-Kafi Hadith Bot (X/Twitter)

This repository posts **exactly one Arabic hadith** from `hadiths.json` to X every day.

- Schedule: **05:00 UTC daily** (08:00 when Lebanon is UTC+3)
- Post content: **hadith text only**
- Duplicate protection: date-based state + retry-safe checks
- Persistent history: `state/publish_state.json` is updated automatically by GitHub Actions

## Files

- `publish.py` — main bot logic
- `hadiths.json` — hadith dataset (Arabic text + metadata + source URL)
- `state/publish_state.json` — persistent publication history/state
- `.github/workflows/daily-hadith.yml` — daily automation workflow
- `tests/test_publish.py` — automated tests

## 1) Create and configure an X Developer app

1. On your Android phone, open a browser and go to: https://developer.x.com/
2. Sign in with your X account.
3. Apply for a developer account if requested.
4. Create a Project/App.
5. Enable permissions that allow posting Tweets (read/write).
6. Generate these credentials from your app:
   - API Key
   - API Secret
   - Access Token
   - Access Token Secret

## 2) API cost and access requirements

X API access is not guaranteed to be free. Posting access may require a paid developer tier, prepaid credits, or both depending on X’s current pricing/policy.

Before enabling automation:

1. Check your plan limits in the X Developer Portal billing/usage pages.
2. Confirm your app has write access for posting.
3. Monitor usage regularly to avoid unexpected charges.

## 3) Add GitHub Secrets (Android)

1. Open your repo on GitHub mobile web.
2. Go to **Settings** → **Secrets and variables** → **Actions**.
3. Tap **New repository secret** and add:
   - `X_API_KEY`
   - `X_API_SECRET`
   - `X_ACCESS_TOKEN`
   - `X_ACCESS_TOKEN_SECRET`

Do not put credentials in code or commits.

## 4) Enable GitHub Actions

1. In your repo, open the **Actions** tab.
2. If prompted, enable workflows.
3. Confirm `Daily Al-Kafi Hadith` workflow is visible.

## 5) Dry-run test (safe, no post)

1. Open **Actions** → `Daily Al-Kafi Hadith`.
2. Tap **Run workflow**.
3. Set `dry_run` to `true`.
4. Run it.
5. Check logs; it should print `status=dry_run` and selected hadith ID.

Dry-run validates data flow and selection without publishing to X or updating state.

## 6) Manual real run

1. Open **Actions** → `Daily Al-Kafi Hadith`.
2. Tap **Run workflow**.
3. Set `dry_run` to `false` (or leave default).
4. Run workflow.
5. Confirm success in logs and check your X profile.

## 7) Automatic daily posting

The workflow runs daily at `0 5 * * *` (05:00 UTC).

Important:

- GitHub scheduled jobs can start late.
- Lebanon timezone can shift with daylight-saving changes, while cron stays UTC.

## 8) Logs and troubleshooting

From Android:

1. Open **Actions**.
2. Open the latest run.
3. Open job logs.

Common issues:

- **Missing secrets**: add all 4 required secrets exactly.
- **X API permission error**: app tier/permissions do not allow posting.
- **No post but run succeeded**: bot may detect it already posted that day and skip duplicate.
- **Hadith too long**: text must be 280 chars or fewer.

## 9) Add new verified hadiths

Edit `hadiths.json` and append entries using this structure:

- `id` (unique)
- `text` (exact Arabic hadith text)
- `volume`
- `book`
- `chapter`
- `hadith_number`
- `url` (reliable verification URL)

Rules:

- Do not paraphrase.
- Do not invent references.
- Keep post text as hadith text only.

## 10) Inspect or restore publication history

History/state is stored in `state/publish_state.json`:

- `published_by_date`: which hadith was posted on each local date
- `published_order`: posting order log
- `next_index`: next hadith index in cycle

If needed, restore an old state file from Git history, then commit.

## Local test command

```bash
pytest
```

## Security notes

- Secrets are read from environment variables only.
- Workflow logs avoid printing credentials.
- Duplicate-prevention logic includes date checks, persistent state, and recent-post detection.
