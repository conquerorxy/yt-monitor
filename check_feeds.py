"""
YouTube Channel Monitor - checks RSS feeds for new videos.
Runs in GitHub Actions (overseas server), writes results to new_videos.json.
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

CHANNELS_FILE = "channels.json"
STATE_FILE = "state.json"        # tracks last seen video per channel
NEW_VIDEOS_FILE = "new_videos.json"  # output: new videos since last run


def fetch_rss(channel_id: str) -> list[dict]:
    """Fetch latest videos from YouTube RSS feed."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"  [WARN] Failed to fetch RSS for {channel_id}: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }

    root = ET.fromstring(xml_data)
    entries = root.findall("atom:entry", ns)

    videos = []
    for entry in entries[:15]:  # latest 15 per channel
        video_id = entry.find("yt:videoId", ns)
        title = entry.find("atom:title", ns)
        published = entry.find("atom:published", ns)
        if video_id is None or title is None:
            continue
        videos.append({
            "video_id": video_id.text,
            "title": title.text,
            "published": published.text if published is not None else "",
            "url": f"https://www.youtube.com/watch?v={video_id.text}",
        })
    return videos


def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(filepath: str, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    channels_config = load_json(CHANNELS_FILE, {"channels": []})
    channels = channels_config.get("channels", [])
    if not channels:
        print("No channels configured.")
        sys.exit(0)

    # Load previous state (last seen video_id per channel)
    state = load_json(STATE_FILE, {})

    new_videos_all = []
    now = datetime.now(timezone.utc).isoformat()

    for ch in channels:
        name = ch["name"]
        channel_id = ch["channel_id"]
        category = ch.get("category", "")
        print(f"Checking: {name} ({channel_id})...")

        videos = fetch_rss(channel_id)
        if not videos:
            print(f"  No videos found or fetch failed.")
            continue

        # Determine new videos since last check
        last_seen_id = state.get(channel_id, {}).get("last_video_id", "")
        new_for_channel = []

        for v in videos:
            if v["video_id"] == last_seen_id:
                break
            new_for_channel.append(v)

        if new_for_channel:
            print(f"  Found {len(new_for_channel)} new video(s)!")
            for v in new_for_channel:
                new_videos_all.append({
                    "channel_name": name,
                    "category": category,
                    "title": v["title"],
                    "url": v["url"],
                    "published": v["published"],
                })
        else:
            print(f"  No new videos.")

        # Update state with latest video
        if videos:
            state[channel_id] = {
                "channel_name": name,
                "last_video_id": videos[0]["video_id"],
                "last_check": now,
            }

    # Save updated state
    save_json(STATE_FILE, state)

    # Save new videos output
    output = {
        "checked_at": now,
        "new_count": len(new_videos_all),
        "videos": new_videos_all,
    }
    save_json(NEW_VIDEOS_FILE, output)

    print(f"\nDone. {len(new_videos_all)} new video(s) found across all channels.")

    # Also write a summary to stdout for GitHub Actions log
    if new_videos_all:
        print("\n=== NEW VIDEOS ===")
        for v in new_videos_all:
            print(f"[{v['category']}] {v['channel_name']}: {v['title']}")
            print(f"  → {v['url']}")


if __name__ == "__main__":
    main()
