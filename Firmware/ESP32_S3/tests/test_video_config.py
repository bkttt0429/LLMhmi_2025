import sys
from pathlib import Path

# Ensure the PC_Client directory is on the import path without pulling heavy dependencies
sys.path.append(str(Path(__file__).resolve().parents[1] / "PC_Client"))

from video_config import build_initial_video_config


class DummyState:
    def __init__(self):
        self.video_url = "http://10.0.0.5:81/stream"
        self.camera_ip = "10.0.0.5"
        self.camera_net_ip = "10.0.0.1"
        self.ai_enabled = True


def test_build_initial_video_config_uses_expected_keys():
    config = build_initial_video_config(DummyState())

    assert config["url"] == "http://10.0.0.5:81/stream"
    assert config["camera_ip"] == "10.0.0.5"
    assert config["camera_net_ip"] == "10.0.0.1"
    assert config["ai_enabled"] is True
