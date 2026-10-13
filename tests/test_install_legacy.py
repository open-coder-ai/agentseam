"""A vendor's legacy hook config: install moves off it, never shadows the user's, uninstall cleans it."""

from __future__ import annotations

import json

import pytest

from agentseam import install as I

_LEGACY = ".windsurf/hooks.json"
_CURRENT = ".devin/hooks.json"


def _write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(root, rel):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def test_windsurf_wires_devin_hooks_json_and_cleans_the_legacy_file(tmp_path):
    """docs.devin.ai/desktop/cascade/hooks: .windsurf/hooks.json is read only while .devin/hooks.json defines none."""
    _write(tmp_path, _LEGACY, {"hooks": {"pre_run_command": [{"command": "old", "_agentseam": "agentseam"}]}})
    path = I.install("windsurf", ["pre_tool"], "g", str(tmp_path))
    assert path == str(tmp_path / _CURRENT)
    assert _read(tmp_path, _CURRENT)["hooks"]["pre_run_command"][0]["command"] == "g"
    assert _read(tmp_path, _LEGACY) == {}
    assert I.uninstall("windsurf", str(tmp_path))
    assert _read(tmp_path, _CURRENT) == {}


def test_windsurf_refuses_to_shadow_the_users_own_legacy_hooks(tmp_path):
    _write(tmp_path, _LEGACY, {"hooks": {"pre_run_command": [{"command": "theirs"}]}})
    with pytest.raises(ValueError, match="switch off the hooks already in"):
        I.install("windsurf", ["pre_tool"], "g", str(tmp_path))
    assert not (tmp_path / _CURRENT).exists()
    assert _read(tmp_path, _LEGACY)["hooks"]["pre_run_command"] == [{"command": "theirs"}]


def test_windsurf_wires_beside_the_users_own_devin_hooks_whatever_the_legacy_file_holds(tmp_path):
    _write(tmp_path, _CURRENT, {"hooks": {"pre_user_prompt": [{"command": "mine"}]}})
    _write(tmp_path, _LEGACY, {"hooks": {"pre_run_command": [{"command": "unread"}]}})
    I.install("windsurf", ["pre_tool"], "g", str(tmp_path))
    hooks = _read(tmp_path, _CURRENT)["hooks"]
    assert hooks["pre_user_prompt"] == [{"command": "mine"}]
    assert hooks["pre_run_command"][0]["command"] == "g"


def test_uninstall_cleans_a_legacy_install_when_the_current_file_is_absent(tmp_path):
    _write(
        tmp_path,
        _LEGACY,
        {"hooks": {"pre_run_command": [{"command": "g", "_agentseam": "agentseam"}, {"command": "theirs"}]}},
    )
    assert I.uninstall("windsurf", str(tmp_path))
    assert _read(tmp_path, _LEGACY) == {"hooks": {"pre_run_command": [{"command": "theirs"}]}}
    assert not I.uninstall("windsurf", str(tmp_path))
