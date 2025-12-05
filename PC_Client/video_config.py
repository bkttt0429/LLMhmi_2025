"""Shared helpers for building video process configuration payloads."""

from typing import Any, Mapping


def build_initial_video_config(state: Any) -> Mapping[str, Any]:
    """Construct the video process configuration payload.

    The video process expects the stream URL under the ``url`` key. Using a
    different key (for example ``video_url``) causes the video process to clear
    its last known URL when the command queue is processed, preventing the
    stream from starting. This helper centralizes the correct key names.
    """

    return {
        'url': getattr(state, 'video_url', ''),
        'camera_ip': getattr(state, 'camera_ip', None),
        'camera_net_ip': getattr(state, 'camera_net_ip', None),
        'ai_enabled': getattr(state, 'ai_enabled', False),
    }
