"""Transient Windows file locks must not corrupt or lose saved knowledge."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from acumen.storage import JSONLStore, atomic_write_json


def sharing_error(code=32):
    error = PermissionError("The file is temporarily locked")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
@pytest.mark.parametrize("json_lines", [False, True])
def test_atomic_save_recovers_from_temporary_windows_lock(tmp_path, code, json_lines):
    target = tmp_path / "saved.json"
    target.write_text('{"old": true}', encoding="utf-8")
    original_replace = Path.replace
    attempts = []

    def replace(source, destination):
        attempts.append(source)
        if len(attempts) <= 2:
            assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
            raise sharing_error(code)
        return original_replace(source, destination)

    with patch.object(Path, "replace", replace), patch("acumen.storage.time.sleep") as sleep:
        if json_lines:
            JSONLStore(target).write_all([{"new": True}])
        else:
            atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert len(attempts) == 3 and sleep.call_count == 2


def test_persistent_lock_fails_with_original_file_intact(tmp_path):
    target = tmp_path / "saved.json"
    target.write_text('{"old": true}', encoding="utf-8")
    with patch.object(Path, "replace", side_effect=sharing_error()) as replace:
        with patch("acumen.storage.time.sleep") as sleep:
            with pytest.raises(PermissionError):
                atomic_write_json(target, {"new": True})
    assert replace.call_count == 5 and sleep.call_count == 4
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert json.loads(target.with_suffix(".json.tmp").read_text(encoding="utf-8")) == {"new": True}


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("disk failure"), sharing_error(87)])
def test_other_write_errors_are_not_retried(tmp_path, error):
    with patch.object(Path, "replace", side_effect=error) as replace:
        with patch("acumen.storage.time.sleep") as sleep:
            with pytest.raises(type(error)):
                atomic_write_json(tmp_path / "saved.json", {"value": 1})
    assert replace.call_count == 1
    sleep.assert_not_called()
