import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import tweepy

# Use a conservative limit so the complete hadith fits comfortably within X's post limit.
X_CHARACTER_LIMIT = 250
REQUIRED_SECRETS = [
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]


@dataclass(frozen=True)
class Hadith:
    hadith_id: str
    text: str
    volume: str
    book: str
    chapter: str
    hadith_number: str
    url: str


def load_hadiths(path: Path) -> List[Hadith]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list) or not data:
        raise RuntimeError("hadiths.json must contain a non-empty JSON array.")

    hadiths: List[Hadith] = []
    seen_ids = set()
    required_fields = {
        "id",
        "text",
        "volume",
        "book",
        "chapter",
        "hadith_number",
        "url",
    }

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise RuntimeError(f"Hadith entry at index {index} must be a JSON object.")

        missing = required_fields - set(item)
        if missing:
            raise RuntimeError(
                f"Hadith entry at index {index} is missing fields: {', '.join(sorted(missing))}."
            )

        hadith_id = str(item["id"]).strip()
        if not hadith_id:
            raise RuntimeError(f"Hadith entry at index {index} has an empty id.")
        if hadith_id in seen_ids:
            raise RuntimeError(f"Duplicate hadith id found: {hadith_id}")
        seen_ids.add(hadith_id)

        text = str(item["text"]).strip()
        if not text:
            raise RuntimeError(f"Hadith '{hadith_id}' has empty text.")

        hadiths.append(
            Hadith(
                hadith_id=hadith_id,
                text=text,
                volume=str(item["volume"]).strip(),
                book=str(item["book"]).strip(),
                chapter=str(item["chapter"]).strip(),
                hadith_number=str(item["hadith_number"]).strip(),
                url=str(item["url"]).strip(),
            )
        )

    return hadiths


def load_state(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"next_index": 0, "published_by_date": {}, "published_order": []}

    with path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise RuntimeError("State file must contain a JSON object.")

    next_index = state.get("next_index", 0)
    published_by_date = state.get("published_by_date", {})
    published_order = state.get("published_order", [])

    if not isinstance(next_index, int) or next_index < 0:
        raise RuntimeError("State field 'next_index' must be a non-negative integer.")
    if not isinstance(published_by_date, dict):
        raise RuntimeError("State field 'published_by_date' must be an object.")
    if not isinstance(published_order, list):
        raise RuntimeError("State field 'published_order' must be an array.")

    return {
        "next_index": next_index,
        "published_by_date": published_by_date,
        "published_order": published_order,
    }


def save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_lebanon_date(now_utc: datetime) -> str:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(ZoneInfo("Asia/Beirut")).date().isoformat()


def validate_post_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise RuntimeError("Selected hadith text is empty.")
    if len(normalized) > X_CHARACTER_LIMIT:
        raise RuntimeError(
            f"Selected hadith exceeds X character limit ({X_CHARACTER_LIMIT})."
        )
    return normalized


def get_missing_secrets(env: Dict[str, str]) -> List[str]:
    return [name for name in REQUIRED_SECRETS if not env.get(name)]


def format_post_text(hadith: Hadith) -> str:
    """Format the complete hadith with its source and hadith number."""
    source = (
        f"المصدر: الكافي، ج {hadith.volume}، "
        f"{hadith.book}، ح {hadith.hadith_number}"
    )
    return f"{hadith.text.strip()}\n\n{source}"


def select_hadith(hadiths: List[Hadith], state: Dict[str, object]) -> Hadith:
    """Select the next complete formatted hadith that fits in one X post."""
    start_index = int(state.get("next_index", 0)) % len(hadiths)

    for offset in range(len(hadiths)):
        candidate = hadiths[(start_index + offset) % len(hadiths)]
        if len(format_post_text(candidate)) <= X_CHARACTER_LIMIT:
            return candidate

    raise RuntimeError(
        "No complete hadith with its source and number fits "
        f"within {X_CHARACTER_LIMIT} characters."
    )


def _create_client(env: Dict[str, str]) -> tweepy.Client:
    return tweepy.Client(
        consumer_key=env["X_API_KEY"],
        consumer_secret=env["X_API_SECRET"],
        access_token=env["X_ACCESS_TOKEN"],
        access_token_secret=env["X_ACCESS_TOKEN_SECRET"],
    )


def _same_local_day(created_at: datetime, target_local_date: str) -> bool:
    return created_at.astimezone(ZoneInfo("Asia/Beirut")).date().isoformat() == target_local_date


def tweet_already_exists_today(
    client: tweepy.Client, expected_text: str, target_local_date: str
) -> Optional[bool]:
    """Return None if X cannot be checked; callers must fail closed in that case."""
    try:
        me = client.get_me(user_auth=True)
        user_id = getattr(getattr(me, "data", None), "id", None)
        if not user_id:
            return None

        tweets_response = client.get_users_tweets(
            id=user_id,
            max_results=10,
            tweet_fields=["created_at"],
            exclude=["replies", "retweets"],
            user_auth=True,
        )

        tweets = getattr(tweets_response, "data", None) or []
        for tweet in tweets:
            text = (getattr(tweet, "text", "") or "").strip()
            created_at = getattr(tweet, "created_at", None)
            if text == expected_text and isinstance(created_at, datetime):
                if _same_local_day(created_at, target_local_date):
                    return True
    except Exception:
        return None

    return False


def publish_hadith(
    hadith_path: Path,
    state_path: Path,
    *,
    dry_run: bool,
    env: Dict[str, str],
    now_utc: Optional[datetime] = None,
    client_factory: Callable[[Dict[str, str]], tweepy.Client] = _create_client,
) -> Dict[str, str]:
    hadiths = load_hadiths(hadith_path)
    state = load_state(state_path)

    now_utc = now_utc or datetime.now(timezone.utc)
    local_date = get_lebanon_date(now_utc)

    published_by_date = state["published_by_date"]
    if local_date in published_by_date:
        return {
            "status": "already_published",
            "date": local_date,
            "hadith_id": str(published_by_date[local_date]),
        }

    selected = select_hadith(hadiths, state)
    text = validate_post_text(format_post_text(selected))

    if dry_run:
        return {
            "status": "dry_run",
            "date": local_date,
            "hadith_id": selected.hadith_id,
            "text": text,
        }

    missing = get_missing_secrets(env)
    if missing:
        raise RuntimeError(
            "Missing required credentials in environment: " + ", ".join(missing)
        )

    client = client_factory(env)

    posted = False
    tweet_id = ""
    duplicate_check = tweet_already_exists_today(client, text, local_date)
    if duplicate_check is None:
        raise RuntimeError(
            "Could not verify whether today's hadith was already published; "
            "refusing to post to avoid a duplicate. Check X API read access and retry."
        )
    if duplicate_check:
        posted = True
    else:
        try:
            response = client.create_tweet(text=text, user_auth=True)
            tweet_data = getattr(response, "data", {}) or {}
            if isinstance(tweet_data, dict):
                tweet_id = str(tweet_data.get("id", ""))
            posted = True
        except Exception as error:
            duplicate_check_after_error = tweet_already_exists_today(
                client, text, local_date
            )
            if duplicate_check_after_error is True:
                posted = True
            elif duplicate_check_after_error is None:
                raise RuntimeError(
                    "X returned an error while posting, and the follow-up check also "
                    "failed. The post may or may not have been published; inspect the "
                    "X profile before retrying to avoid a duplicate."
                ) from error
            else:
                raise RuntimeError(f"Failed to publish hadith to X: {error}") from error

    if posted:
        state["published_by_date"][local_date] = selected.hadith_id
        state["published_order"].append(selected.hadith_id)
        # Resume after the hadith actually published, skipping any long entries.
        state["next_index"] = (hadiths.index(selected) + 1) % len(hadiths)
        save_state(state_path, state)

    return {
        "status": "published",
        "date": local_date,
        "hadith_id": selected.hadith_id,
        "tweet_id": tweet_id,
        "url": selected.url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish one daily Al-Kafi hadith to X.")
    parser.add_argument(
        "--hadiths-file",
        default="hadiths.json",
        help="Path to hadith JSON file.",
    )
    parser.add_argument(
        "--state-file",
        default="state/publish_state.json",
        help="Path to publication state JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and select without posting to X or changing state.",
    )

    args = parser.parse_args()
    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() in {
        "1",
        "true",
        "yes",
    }

    result = publish_hadith(
        Path(args.hadiths_file),
        Path(args.state_file),
        dry_run=dry_run,
        env=dict(os.environ),
    )

    print(f"status={result['status']}")
    print(f"date={result['date']}")
    print(f"hadith_id={result['hadith_id']}")
    if "text" in result:
        print("post_text_begin")
        print(result["text"])
        print("post_text_end")
    if "tweet_id" in result and result["tweet_id"]:
        print(f"tweet_id={result['tweet_id']}")


if __name__ == "__main__":
    main()
