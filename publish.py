import json
import os
from datetime import datetime, timezone

import tweepy


def main():
    with open("hadiths.json", "r", encoding="utf-8") as file:
        hadiths = json.load(file)

    if not hadiths:
        raise RuntimeError("hadiths.json is empty; refusing to publish.")

    # One deterministic item per UTC calendar day; no AI-generated or invented text.
    today = datetime.now(timezone.utc).date()
    hadith = hadiths[today.toordinal() % len(hadiths)]
    text = hadith["text"].strip()

    # Keep the post to the requested hadith text only.
    if len(text) > 280:
        raise RuntimeError("Selected hadith exceeds X's 280-character post limit.")

    required = [
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing GitHub Actions secrets: " + ", ".join(missing)
        )

    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    response = client.create_tweet(text=text)
    print(f"Published X post ID: {response.data['id']}")
    print(f"Source for verification (not included in the post): {hadith.get('url', '')}")


if __name__ == "__main__":
    main()
