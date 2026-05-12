"""Download Kaggle Orbit Wars replay JSONs locally.

Local port of `notebooks/api-download-replay-orbit-wars.ipynb` — uses the
official Kaggle SDK for auth (so it works with ~/.kaggle/kaggle.json or
KAGGLE_USERNAME/KAGGLE_KEY env vars), but bypasses the SDK's broken
chunked-download path (`download_file` requires Content-Length but the
replay endpoint sends Transfer-Encoding: chunked).

For the episode listing we still use the internal API endpoint the
notebook discovered (kaggle.com/api/i/competitions.EpisodeService/
ListEpisodes), since the public SDK doesn't expose ListEpisodes by
submission ID.

Usage:
    uv run python -m tools.download_replays --sub-id 52318886 --count 10
    uv run python -m tools.download_replays --sub-id 52318886 --count 5 --out-dir /tmp/replays

Default sub-id 52318886 = bowwowforeach (top player at notebook capture).
Episodes are downloaded into --out-dir (default: replay/, gitignored).
Already-downloaded files are skipped.

Rate-limit with 1 req/sec to avoid 429 RESOURCE_EXHAUSTED.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests


LIST_URL = "https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes"


def _ensure_kaggle_env_vars() -> None:
    """Make sure KAGGLE_USERNAME/KAGGLE_KEY are set in os.environ.

    Order: existing env → .env file → ~/.kaggle/kaggle.json.
    The Kaggle SDK reads the env vars at import time, so this must run
    before any kaggle import.
    """
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        import json

        with kaggle_json.open() as f:
            data = json.load(f)
        if data.get("username") and data.get("key"):
            os.environ["KAGGLE_USERNAME"] = data["username"]
            os.environ["KAGGLE_KEY"] = data["key"]
            return

    sys.exit(
        "ERROR: Kaggle credentials not found. Set KAGGLE_USERNAME/KAGGLE_KEY "
        "env vars or place ~/.kaggle/kaggle.json."
    )


def list_episodes(sub_id: int) -> list[dict]:
    """POST to ListEpisodes for a submission ID; return episodes list."""
    username = os.environ["KAGGLE_USERNAME"]
    key = os.environ["KAGGLE_KEY"]
    response = requests.post(
        LIST_URL,
        auth=(username, key),
        json={"submissionId": sub_id},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        sys.exit(
            f"ListEpisodes failed (status={response.status_code}): "
            f"{response.text[:500]}"
        )
    data = response.json()
    return data.get("episodes", [])


def download_replay(episode_id: int, out_path: Path) -> bool:
    """Use Kaggle SDK auth + raw response.content to download one replay.

    Returns True on success, False on failure (logged to stderr).
    """
    import kaggle
    from kagglesdk.competitions.types.competition_api_service import (
        ApiGetEpisodeReplayRequest,
    )

    api = kaggle.api
    try:
        with api.build_kaggle_client() as client:
            req = ApiGetEpisodeReplayRequest()
            req.episode_id = episode_id
            response = client.competitions.competition_api_client.get_episode_replay(req)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN: SDK call failed for {episode_id}: {e}", file=sys.stderr)
        return False

    if not hasattr(response, "content") or not response.content:
        print(f"  WARN: empty response for {episode_id}", file=sys.stderr)
        return False

    out_path.write_bytes(response.content)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sub-id", type=int, default=52318886,
                    help="Kaggle submission ID (default: 52318886, bowwowforeach)")
    ap.add_argument("--count", type=int, default=5,
                    help="Max number of replays to download (default: 5)")
    ap.add_argument("--out-dir", type=Path, default=Path("replay"),
                    help="Directory for downloaded JSONs (default: ./replay)")
    ap.add_argument("--rate-limit-sec", type=float, default=1.0,
                    help="Seconds to sleep between requests (default: 1.0)")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_kaggle_env_vars()
    print(f"Auth: {os.environ['KAGGLE_USERNAME']}")
    print(f"Listing episodes for submission {args.sub_id}...")

    episodes = list_episodes(args.sub_id)
    print(f"Found {len(episodes)} episodes for this submission")

    # Reverse the list so we start at the last episode and work our way backwards
    episodes.reverse()

    if args.count < len(episodes):
        episodes = episodes[: args.count]
        print(f"Downloading last {args.count} episodes (descending)")
    else:
        print(f"Downloading all {len(episodes)} episodes (descending)")

    downloaded = 0
    skipped = 0
    failed = 0
    for idx, ep in enumerate(episodes, 1):
        episode_id = ep.get("id")
        if not episode_id:
            failed += 1
            continue
        out_path = args.out_dir / f"{episode_id}.json"
        if out_path.exists():
            print(f"[{idx}/{len(episodes)}] skip {episode_id} (exists)")
            skipped += 1
            continue
        print(f"[{idx}/{len(episodes)}] download {episode_id}...")
        if download_replay(episode_id, out_path):
            downloaded += 1
        else:
            failed += 1
        time.sleep(args.rate_limit_sec)

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())