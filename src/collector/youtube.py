"""
YouTube API v3 client for fetching video metadata and searching for upcoming streams.
"""

import logging
import requests
from dataclasses import dataclass
from typing import Optional, Dict, List


logger = logging.getLogger(__name__)

# Browser-like User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'


@dataclass
class VideoInfo:
    """Holds metadata for a YouTube video."""
    video_id: str
    channel_id: str
    title: str
    thumbnail: str  # URL to best available thumbnail
    live_state: str  # "none" | "upcoming" | "live"
    scheduled_start: Optional[str]  # ISO string with 'Z', or None
    actual_start: Optional[str]  # ISO string with 'Z', or None
    actual_end: Optional[str]  # ISO string with 'Z', or None
    concurrent_viewers: Optional[int]  # Number of current viewers, or None


def _video_from_item(item: dict) -> VideoInfo:
    """
    Convert a YouTube API response item dict to VideoInfo.

    Pure function, no network access.

    Args:
        item: Video item from YouTube API response

    Returns:
        VideoInfo object
    """
    video_id = item.get('id', '')
    snippet = item.get('snippet', {})
    live_details = item.get('liveStreamingDetails', {})

    # Extract channel ID
    channel_id = snippet.get('channelId', '')

    # Extract title
    title = snippet.get('title', '')

    # Extract and select best thumbnail
    thumbnails = snippet.get('thumbnails', {})
    thumbnail = _select_thumbnail(video_id, thumbnails)

    # Extract live broadcast state
    live_state = snippet.get('liveBroadcastContent', 'none')

    # Extract live streaming details
    scheduled_start = live_details.get('scheduledStartTime')
    actual_start = live_details.get('actualStartTime')
    actual_end = live_details.get('actualEndTime')

    # Convert concurrent viewers to int or None
    concurrent_viewers = None
    if 'concurrentViewers' in live_details:
        try:
            concurrent_viewers = int(live_details['concurrentViewers'])
        except (ValueError, TypeError):
            pass

    return VideoInfo(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        thumbnail=thumbnail,
        live_state=live_state,
        scheduled_start=scheduled_start,
        actual_start=actual_start,
        actual_end=actual_end,
        concurrent_viewers=concurrent_viewers,
    )


def _select_thumbnail(video_id: str, thumbnails: dict) -> str:
    """
    Select best thumbnail from available options.

    Preference order: maxres > standard > high > medium > default
    Fallback: https://i.ytimg.com/vi/{video_id}/hqdefault.jpg

    Args:
        video_id: YouTube video ID
        thumbnails: Thumbnails dict from API response

    Returns:
        Thumbnail URL string
    """
    # Try in order of preference
    for key in ['maxres', 'standard', 'high', 'medium', 'default']:
        if key in thumbnails and 'url' in thumbnails[key]:
            return thumbnails[key]['url']

    # Fallback thumbnail
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


class YouTubeClient:
    """Client for YouTube API v3."""

    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 15.0
    ):
        """
        Initialize YouTube client.

        Args:
            api_key: YouTube Data API key
            session: Optional requests.Session for connection pooling
            timeout: Request timeout in seconds

        Raises:
            ValueError: If api_key is falsy
        """
        if not api_key:
            raise ValueError("api_key is required and must be non-empty")

        self.api_key = api_key
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        self.quota_used = 0

    def videos_list(self, video_ids: List[str]) -> Dict[str, VideoInfo]:
        """
        Fetch metadata for multiple videos using YouTube API.

        Automatically chunks requests to 50 videos per request.
        Each request increments quota_used by 1.

        Args:
            video_ids: List of YouTube video IDs

        Returns:
            Dict mapping video_id to VideoInfo.
            Video IDs not in the response are omitted.

        Raises:
            RuntimeError: On HTTP error (non-200 response)
        """
        result = {}

        # Chunk video IDs to 50 per request
        chunk_size = 50
        for i in range(0, len(video_ids), chunk_size):
            chunk = video_ids[i:i + chunk_size]
            video_id_str = ','.join(chunk)

            url = self.BASE + "/videos"
            params = {
                'key': self.api_key,
                'part': 'snippet,liveStreamingDetails',
                'id': video_id_str,
            }

            headers = {'User-Agent': USER_AGENT}

            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise RuntimeError(f"YouTube API error: {e}")

            self.quota_used += 1

            data = response.json()
            items = data.get('items', [])

            for item in items:
                video_info = _video_from_item(item)
                result[video_info.video_id] = video_info

        return result

    def search_upcoming(
        self,
        channel_id: str,
        *,
        max_results: int = 25
    ) -> List[str]:
        """
        Search for upcoming/scheduled streams in a channel.

        Args:
            channel_id: YouTube channel ID
            max_results: Maximum results to return (default 25)

        Returns:
            List of video IDs for upcoming streams.
            On error: returns [] and logs warning.
        """
        url = self.BASE + "/search"
        params = {
            'key': self.api_key,
            'part': 'id',
            'type': 'video',
            'eventType': 'upcoming',
            'order': 'date',
            'channelId': channel_id,
            'maxResults': max_results,
        }

        headers = {'User-Agent': USER_AGENT}

        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to search upcoming streams for {channel_id}: {e}")
            return []

        self.quota_used += 100

        try:
            data = response.json()
            items = data.get('items', [])
            video_ids = [item['id']['videoId'] for item in items if 'id' in item and 'videoId' in item['id']]
            return video_ids
        except Exception as e:
            logger.warning(f"Failed to parse search results for {channel_id}: {e}")
            return []

    def channels_list(self, channel_ids: List[str]) -> Dict[str, str]:
        """
        Fetch channel avatar (profile picture) URLs.

        part=snippet, batched up to 50 ids per request (quota_used += 1 each).
        Returns {channel_id: avatar_url} using the largest available thumbnail
        (high > medium > default). Channels without a thumbnail are omitted.
        On HTTP error: logs warning and returns whatever was gathered so far.
        """
        result: Dict[str, str] = {}
        headers = {'User-Agent': USER_AGENT}
        for i in range(0, len(channel_ids), 50):
            chunk = channel_ids[i:i + 50]
            params = {
                'key': self.api_key,
                'part': 'snippet',
                'id': ','.join(chunk),
            }
            try:
                response = self.session.get(
                    self.BASE + "/channels",
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except requests.RequestException as e:
                logger.warning(f"channels.list failed: {e}")
                return result

            self.quota_used += 1
            for item in response.json().get('items', []):
                cid = item.get('id')
                thumbs = item.get('snippet', {}).get('thumbnails', {})
                for key in ('high', 'medium', 'default'):
                    if key in thumbs and 'url' in thumbs[key]:
                        result[cid] = thumbs[key]['url']
                        break
        return result


if __name__ == "__main__":
    # Test _video_from_item with sample API responses

    # Test case 1: Upcoming stream with scheduledStartTime
    upcoming_item = {
        'id': 'test_upcoming_123',
        'snippet': {
            'channelId': 'UCtest123',
            'title': 'Upcoming Stream Test',
            'liveBroadcastContent': 'upcoming',
            'thumbnails': {
                'maxres': {'url': 'https://i.ytimg.com/vi/test_upcoming_123/maxresdefault.jpg'},
                'high': {'url': 'https://i.ytimg.com/vi/test_upcoming_123/hqdefault.jpg'},
            },
        },
        'liveStreamingDetails': {
            'scheduledStartTime': '2026-08-31T15:00:00Z',
        },
    }

    # Test case 2: Live stream with concurrentViewers
    live_item = {
        'id': 'test_live_456',
        'snippet': {
            'channelId': 'UCtest456',
            'title': 'Live Stream Test',
            'liveBroadcastContent': 'live',
            'thumbnails': {
                'standard': {'url': 'https://i.ytimg.com/vi/test_live_456/sddefault.jpg'},
                'default': {'url': 'https://i.ytimg.com/vi/test_live_456/default.jpg'},
            },
        },
        'liveStreamingDetails': {
            'actualStartTime': '2026-08-30T14:30:00Z',
            'concurrentViewers': '1234',
        },
    }

    # Convert and print
    try:
        upcoming_info = _video_from_item(upcoming_item)
        live_info = _video_from_item(live_item)

        print("Upcoming stream:")
        print(f"  ID: {upcoming_info.video_id}")
        print(f"  Title: {upcoming_info.title}")
        print(f"  State: {upcoming_info.live_state}")
        print(f"  Scheduled start: {upcoming_info.scheduled_start}")
        print(f"  Concurrent viewers: {upcoming_info.concurrent_viewers}")

        print("\nLive stream:")
        print(f"  ID: {live_info.video_id}")
        print(f"  Title: {live_info.title}")
        print(f"  State: {live_info.live_state}")
        print(f"  Actual start: {live_info.actual_start}")
        print(f"  Concurrent viewers: {live_info.concurrent_viewers}")

        print("\nSUCCESS: YouTube client test passed")

    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
