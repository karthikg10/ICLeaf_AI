# backend/app/web_cloud.py
from typing import List, Dict, Optional, Tuple
import base64
import httpx
from bs4 import BeautifulSoup
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

# -------- Web (Tavily) --------
async def tavily_search(query: str, api_key: str, max_results: int = 5) -> List[Dict]:
    if not api_key:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])

async def fetch_url_text(url: str) -> str:
    if not url:
        return ""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = r.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:50_000]

# -------- YouTube --------
async def youtube_search(query: str, api_key: str, max_results: int = 5) -> List[Dict]:
    if not api_key:
        return []
    params = {
        "key": api_key,
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": max_results,
        "safeSearch": "moderate",
    }
    url = "https://www.googleapis.com/youtube/v3/search"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    items: List[Dict] = []
    for it in data.get("items", []):
        vid = it["id"]["videoId"]
        sn = it.get("snippet", {})
        items.append({
            "videoId": vid,
            "title": sn.get("title"),
            "channelTitle": sn.get("channelTitle"),
            "publishedAt": sn.get("publishedAt"),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return items

def youtube_fetch_transcript_text(video_id: str, languages: Optional[List[str]] = None) -> str:
    try:
        if languages is None:
            languages = ["en", "en-US", "en-GB"]
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        txt = " ".join(seg.get("text", "") for seg in transcript)
        return txt[:50_000]
    except (TranscriptsDisabled, NoTranscriptFound, Exception):
        return ""

# -------- GitHub --------
async def github_search_code(query: str, token: Optional[str], max_results: int = 5) -> List[Dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"q": query, "per_page": max_results}
    url = "https://api.github.com/search/code"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    items: List[Dict] = []
    for it in data.get("items", []):
        repo = it.get("repository", {})
        items.append({
            "name": it.get("name"),
            "path": it.get("path"),
            "repository_full_name": repo.get("full_name"),
            "html_url": it.get("html_url"),
            "api_url": it.get("url"),
        })
    return items

async def github_fetch_file_text(api_url: str, token: Optional[str]) -> Tuple[str, str]:
    if not api_url:
        return "", ""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(api_url, headers=headers)
        r.raise_for_status()
        data = r.json()

    content = data.get("content")
    encoding = data.get("encoding")
    download_url = data.get("download_url") or ""
    if content and encoding == "base64":
        try:
            raw = base64.b64decode(content).decode("utf-8", errors="ignore")
            return raw[:50_000], download_url
        except Exception:
            pass

    if download_url:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            rr = await client.get(download_url)
            rr.raise_for_status()
            return rr.text[:50_000], download_url

    return "", download_url
