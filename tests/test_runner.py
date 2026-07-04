from __future__ import annotations

import json
from unittest.mock import patch

from my_agent.runner import _read_edited_action


class TestReadEditedAction:
    def test_keeps_current_args_on_empty_input(self) -> None:
        action = {"name": "execute", "arguments": {"command": "ls"}}
        with patch("sys.stdin.readline", return_value="\n"):
            edited = _read_edited_action(action)
        assert edited["arguments"] == {"command": "ls"}

    def test_merges_valid_json(self) -> None:
        action = {"name": "execute", "arguments": {"command": "ls"}}
        payload = json.dumps({"command": "pwd"})
        with patch("sys.stdin.readline", return_value=f"{payload}\n"):
            edited = _read_edited_action(action)
        assert edited["arguments"] == {"command": "pwd"}

    def test_retries_on_invalid_json(self) -> None:
        action = {"name": "execute", "arguments": {"command": "ls"}}
        with patch(
            "sys.stdin.readline",
            side_effect=["not-json\n", '{"command": "pwd"}\n'],
        ):
            edited = _read_edited_action(action)
        assert edited["arguments"] == {"command": "pwd"}

    def test_rejects_non_object_json(self) -> None:
        action = {"name": "execute", "arguments": {"command": "ls"}}
        with patch(
            "sys.stdin.readline",
            side_effect=['["not", "an", "object"]\n', "\n"],
        ):
            edited = _read_edited_action(action)
        assert edited["arguments"] == {"command": "ls"}
