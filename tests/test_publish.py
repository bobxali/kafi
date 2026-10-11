import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import publish


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_hadiths():
    return [
        {
            "id": "h1",
            "text": "نص قصير",
            "volume": "1",
            "book": "b",
            "chapter": "c",
            "hadith_number": "1",
            "url": "https://example.com/1",
        },
        {
            "id": "h2",
            "text": "نص ثاني",
            "volume": "1",
            "book": "b",
            "chapter": "c",
            "hadith_number": "2",
            "url": "https://example.com/2",
        },
    ]


def test_json_validation_missing_field(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    write_json(hadith_file, [{"id": "h1", "text": "x"}])

    with pytest.raises(RuntimeError):
        publish.load_hadiths(hadith_file)


def test_hadith_selection_cycles_without_repeat_until_exhausted(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    state_file = tmp_path / "state.json"
    write_json(hadith_file, sample_hadiths())
    write_json(state_file, {"next_index": 0, "published_by_date": {}, "published_order": []})

    result1 = publish.publish_hadith(
        hadith_file,
        state_file,
        dry_run=False,
        env={
            "X_API_KEY": "k",
            "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t",
            "X_ACCESS_TOKEN_SECRET": "ts",
        },
        now_utc=datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc),
        client_factory=lambda _env: FakeClient(create_ok=True),
    )
    result2 = publish.publish_hadith(
        hadith_file,
        state_file,
        dry_run=False,
        env={
            "X_API_KEY": "k",
            "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t",
            "X_ACCESS_TOKEN_SECRET": "ts",
        },
        now_utc=datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc),
        client_factory=lambda _env: FakeClient(create_ok=True),
    )

    assert result1["hadith_id"] == "h1"
    assert result2["hadith_id"] == "h2"


def test_duplicate_prevention_by_date(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    state_file = tmp_path / "state.json"
    write_json(hadith_file, sample_hadiths())
    write_json(
        state_file,
        {
            "next_index": 1,
            "published_by_date": {"2026-01-01": "h1"},
            "published_order": ["h1"],
        },
    )

    result = publish.publish_hadith(
        hadith_file,
        state_file,
        dry_run=False,
        env={
            "X_API_KEY": "k",
            "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t",
            "X_ACCESS_TOKEN_SECRET": "ts",
        },
        now_utc=datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc),
        client_factory=lambda _env: (_ for _ in ()).throw(AssertionError("must not call")),
    )

    assert result["status"] == "already_published"
    assert result["hadith_id"] == "h1"


def test_invalid_or_empty_text(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    write_json(
        hadith_file,
        [
            {
                "id": "h1",
                "text": "   ",
                "volume": "1",
                "book": "b",
                "chapter": "c",
                "hadith_number": "1",
                "url": "https://example.com/1",
            }
        ],
    )

    with pytest.raises(RuntimeError):
        publish.load_hadiths(hadith_file)


def test_character_limit_validation():
    with pytest.raises(RuntimeError):
        publish.validate_post_text("x" * 281)


def test_missing_credentials(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    state_file = tmp_path / "state.json"
    write_json(hadith_file, sample_hadiths())
    write_json(state_file, {"next_index": 0, "published_by_date": {}, "published_order": []})

    with pytest.raises(RuntimeError):
        publish.publish_hadith(
            hadith_file,
            state_file,
            dry_run=False,
            env={},
            now_utc=datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc),
        )


def test_dry_run_mode_no_publish_and_no_state_change(tmp_path: Path):
    hadith_file = tmp_path / "hadiths.json"
    state_file = tmp_path / "state.json"
    write_json(hadith_file, sample_hadiths())
    initial_state = {"next_index": 0, "published_by_date": {}, "published_order": []}
    write_json(state_file, initial_state)

    result = publish.publish_hadith(
        hadith_file,
        state_file,
        dry_run=True,
        env={},
        now_utc=datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc),
        client_factory=lambda _env: (_ for _ in ()).throw(AssertionError("must not call")),
    )

    assert result["status"] == "dry_run"
    assert json.loads(state_file.read_text(encoding="utf-8")) == initial_state


def test_network_failure_recovers_when_tweet_detected(tmp_path: Path, monkeypatch):
    hadith_file = tmp_path / "hadiths.json"
    state_file = tmp_path / "state.json"
    write_json(hadith_file, sample_hadiths())
    write_json(state_file, {"next_index": 0, "published_by_date": {}, "published_order": []})

    monkeypatch.setattr(publish, "tweet_already_exists_today", lambda *_args, **_kwargs: True)

    client = FakeClient(create_ok=False)
    result = publish.publish_hadith(
        hadith_file,
        state_file,
        dry_run=False,
        env={
            "X_API_KEY": "k",
            "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t",
            "X_ACCESS_TOKEN_SECRET": "ts",
        },
        now_utc=datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc),
        client_factory=lambda _env: client,
    )

    assert result["status"] == "published"
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["published_by_date"]["2026-01-01"] == "h1"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeClient:
    def __init__(self, create_ok=True):
        self.create_ok = create_ok

    def create_tweet(self, text, user_auth=True):
        if not self.create_ok:
            raise RuntimeError("network")
        return FakeResponse({"id": "12345", "text": text})

    def get_me(self, user_auth=True):
        return FakeResponse(type("Me", (), {"id": "u1"})())

    def get_users_tweets(self, **kwargs):
        return FakeResponse([])
