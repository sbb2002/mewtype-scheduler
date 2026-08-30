"""
YouTube RSS feed collector.
Fetches video IDs from YouTube channel RSS feeds.
"""

import logging
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

# Namespaces used in YouTube RSS feeds
NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}

# Browser-like User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'


def _parse_rss(xml_text: str) -> list[str]:
    """
    Pure function to parse YouTube RSS XML and extract video IDs.

    Args:
        xml_text: XML content as string

    Returns:
        List of video IDs in document order (newest first), max 15
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse RSS XML: {e}")
        return []

    video_ids = []

    # Find all entry elements and extract yt:videoId
    for entry in root.findall('atom:entry', NAMESPACES):
        video_id_elem = entry.find('yt:videoId', NAMESPACES)
        if video_id_elem is not None and video_id_elem.text:
            video_ids.append(video_id_elem.text)

    # Return max 15 videos
    return video_ids[:15]


def fetch_rss_video_ids(
    channel_id: str,
    *,
    timeout: float = 10.0,
    session: Optional[requests.Session] = None
) -> list[str]:
    """
    Fetch video IDs from a YouTube channel's RSS feed.

    Args:
        channel_id: YouTube channel ID
        timeout: Request timeout in seconds
        session: Optional requests.Session for connection pooling

    Returns:
        List of video IDs (newest-first, max 15).
        On any HTTP/parse error: returns [] and logs warning.
    """
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # Use provided session or create a new one
    req_session = session if session is not None else requests.Session()

    try:
        headers = {'User-Agent': USER_AGENT}
        response = req_session.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()

        return _parse_rss(response.text)

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch RSS for channel {channel_id}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Error processing RSS for channel {channel_id}: {e}")
        return []


def fetch_all_rss_video_ids(channel_id_by_key: dict[str, str]) -> dict[str, list[str]]:
    """
    Fetch video IDs for multiple channels using a shared session.

    Args:
        channel_id_by_key: Dict mapping channel key to channel ID

    Returns:
        Dict mapping channel key to list of video IDs.
        Failed channels yield [] for that key.
    """
    result = {}

    # Reuse one session for all requests
    with requests.Session() as session:
        for key, channel_id in channel_id_by_key.items():
            result[key] = fetch_rss_video_ids(channel_id, session=session)

    return result


if __name__ == "__main__":
    # Test with fixture file
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "rss_arale.xml"

    try:
        xml_content = fixture_path.read_text(encoding='utf-8')
        video_ids = _parse_rss(xml_content)

        count = len(video_ids)
        print(f"Total videos: {count}")
        print(f"First 3 IDs: {video_ids[:3]}")

        # Verify count is exactly 15
        assert count == 15, f"Expected 15 videos, got {count}"
        print("SUCCESS: RSS parser test passed")

    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
