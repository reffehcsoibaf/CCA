import subprocess
import sys

import anyio
import pytest

import worker


@pytest.mark.skipif(sys.platform != "win32", reason="só no Windows")
def test_child_processes_get_no_window_flag(monkeypatch):
    seen = {}

    async def fake_open_process(command, **kwargs):
        seen.update(kwargs)
        return "processo"

    monkeypatch.setattr(anyio, "open_process", fake_open_process)
    worker.hide_child_consoles()
    assert anyio.run(lambda: anyio.open_process(["x"], creationflags=0x10)) == "processo"
    assert seen["creationflags"] == 0x10 | subprocess.CREATE_NO_WINDOW
    wrapped = anyio.open_process
    worker.hide_child_consoles()
    assert anyio.open_process is wrapped  # não embrulha duas vezes
