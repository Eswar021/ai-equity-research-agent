"""YouTube scraper — discovers recent channel videos and saves transcripts."""

import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import requests
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from youtube_transcript_api._errors import IpBlocked

from src.config.settings import IST

_API_KEY    = os.getenv("YOUTUBE_API_KEY", "")
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_LANG_PREF  = ["en", "te", "hi", "ta", "kn", "ml", "bn", "mr", "gu", "pa"]
_SLEEP      = 1.5

_proxy_url = os.getenv("YOUTUBE_PROXY", "").strip()
if _proxy_url:
    from youtube_transcript_api.proxies import GenericProxyConfig
    _yt_api = YouTubeTranscriptApi(
        proxy_config=GenericProxyConfig(http_url=_proxy_url, https_url=_proxy_url)
    )
else:
    _yt_api = YouTubeTranscriptApi()


def _extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query)["v"][0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[1]
    raise ValueError(f"Cannot extract video ID from: {url}")


def _fetch_transcript(video_id: str) -> str:
    try:
        fetched = _yt_api.fetch(video_id, languages=_LANG_PREF)
    except NoTranscriptFound:
        transcript_list = _yt_api.list(video_id)
        fetched = next(iter(transcript_list)).fetch()
    snippets = list(fetched)
    return " ".join(s.text for s in snippets)


def _search_channel(channel_id: str, duration: str, max_results: int,
                    published_after: str) -> list[dict]:
    params = {
        "part":          "snippet",
        "channelId":     channel_id,
        "maxResults":    max_results,
        "order":         "date",
        "type":          "video",
        "videoDuration": duration,
        "publishedAfter": published_after,
        "key":           _API_KEY,
    }
    resp = requests.get(_SEARCH_URL, params=params, timeout=15)
    resp.raise_for_status()
    videos = []
    for item in resp.json().get("items", []):
        vid_id = item["id"].get("videoId")
        if vid_id:
            videos.append({
                "video_id":       vid_id,
                "title":          item["snippet"].get("title", ""),
                "published_at":   item["snippet"].get("publishedAt", ""),
                "duration_class": duration,
            })
    return videos


def collect(cfg: dict) -> list[dict]:
    if not _API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY env var not set")

    days_back  = cfg.get("days_back", 3)
    max_medium = cfg.get("max_medium", 3)
    max_long   = cfg.get("max_long", 2)
    channels   = [c for c in cfg.get("channels", []) if c.get("enabled", True)]
    if not channels:
        return []

    published_after = (datetime.now(IST) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = []

    for ch in channels:
        name = ch["name"]
        cid  = ch["channel_id"]
        videos = []

        try:
            if max_medium > 0:
                videos += _search_channel(cid, "medium", max_medium, published_after)
            if max_long > 0:
                videos += _search_channel(cid, "long", max_long, published_after)
        except Exception as e:
            print(f"  [youtube] {name} search failed: {e}")
            continue

        for v in videos:
            url = f"https://www.youtube.com/watch?v={v['video_id']}"
            try:
                transcript = _fetch_transcript(v["video_id"])
                records.append({
                    "source":       "youtube",
                    "source_type":  "video_transcript",
                    "title":        v["title"],
                    "url":          url,
                    "published_at": v["published_at"] or None,
                    "content":      transcript,
                    "metadata": {
                        "channel_name":   name,
                        "video_id":       v["video_id"],
                        "duration_class": v["duration_class"],
                    },
                })
                time.sleep(_SLEEP)
            except IpBlocked:
                print(f"  [youtube] IP blocked — stopping transcript fetches")
                return records
            except Exception:
                print(f"  [youtube] no transcript: {v['video_id']} {v['title'][:50]}")
                time.sleep(_SLEEP)

    return records
