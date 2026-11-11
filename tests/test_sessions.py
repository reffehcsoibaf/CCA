from types import SimpleNamespace

import sessions


def info(sid, modified, custom=None, summary=None, first=None, cwd=r"C:\proj\app"):
    return SimpleNamespace(session_id=sid, last_modified=modified, custom_title=custom,
                           summary=summary, first_prompt=first, cwd=cwd)


def test_session_title_preference():
    assert sessions.session_title(info("a", 1, custom="Título", summary="Resumo")) == "Título"
    assert sessions.session_title(info("a", 1, summary="Resumo", first="oi\nlá")) == "oi lá"
    assert sessions.session_title(info("a", 1, summary="Resumo")) == "Resumo"
    assert sessions.session_title(info("a", 1)) == "Sessão sem título"


def test_list_user_sessions_most_recent_first():
    calls = {}

    def lister(limit):
        calls["limit"] = limit
        return [info("old", 1000, custom="Velha"), info("new", 2000, custom="Nova")]

    entries = sessions.list_user_sessions(limit=50, lister=lister)
    assert calls["limit"] == 50
    assert [e.session_id for e in entries] == ["new", "old"]
    label = entries[0].label()
    assert label.startswith("Nova, pasta app, ")


def test_load_history_uses_sdk_messages():
    msgs = [SimpleNamespace(type="user", message={"role": "user", "content": "Olá"}),
            SimpleNamespace(type="assistant", message={"role": "assistant",
                                                       "content": [{"type": "text", "text": "Oi!"}]})]
    seen = {}

    def getter(sid, directory=None):
        seen["args"] = (sid, directory)
        return msgs

    assert sessions.load_history("s1", r"C:\p", getter=getter) == [("user", "Olá"), ("assistant", "Oi!")]
    assert seen["args"] == ("s1", r"C:\p")


def test_fetch_title_ignores_summary():
    assert sessions.fetch_title("a", getter=lambda sid, directory=None: info("a", 1, summary="último prompt")) is None
    assert sessions.fetch_title("a", getter=lambda sid, directory=None: info("a", 1, custom="Título")) == "Título"


def test_config_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.json"
    assert sessions.load_config(str(path)) == {}
    sessions.save_config({"cwd": r"C:\ação"}, str(path))
    assert sessions.load_config(str(path)) == {"cwd": r"C:\ação"}


def test_rename_strips_and_passes_directory():
    calls = []
    sessions.rename("sess-1", "  Novo nome  ", r"C:\proj", renamer=lambda *a, **k: calls.append((a, k)))
    assert calls == [(("sess-1", "Novo nome"), {"directory": r"C:\proj"})]


def _make_session(root, folder, sid, cwd, extra_dir=False):
    import json, os
    path = os.path.join(root, folder)
    os.makedirs(path, exist_ok=True)
    lines = [json.dumps({"type": "user", "cwd": cwd, "message": "oi"}, separators=(",", ":"), ensure_ascii=False),
             json.dumps({"type": "assistant", "cwd": cwd, "message": "olá é"}, separators=(",", ":"), ensure_ascii=False)]
    file = os.path.join(path, sid + ".jsonl")
    with open(file, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    if extra_dir:
        os.makedirs(os.path.join(path, sid, "subagents"))
    return file


def test_move_session_file_to_existing_folder(tmp_path):
    import os
    root = str(tmp_path)
    old = r"C:\proj\velha"
    new = r"C:\proj\nova"
    source = _make_session(root, "C--proj-velha", "s1", old, extra_dir=True)
    _make_session(root, "C--proj-nova", "s2", new)
    target = sessions.move_session_file("s1", old, new, like_session_id="s2", root=root)
    assert target == os.path.join(root, "C--proj-nova", "s1.jsonl")
    assert not os.path.exists(source) and not os.path.exists(os.path.join(root, "C--proj-velha", "s1"))
    assert os.path.isdir(os.path.join(root, "C--proj-nova", "s1", "subagents"))
    text = open(target, encoding="utf-8").read()
    assert text.count(json_cwd(new)) == 2 and json_cwd(old) not in text and "olá é" in text


def json_cwd(cwd):
    import json
    return '"cwd":' + json.dumps(cwd)


def test_move_session_file_creates_new_folder_and_refuses_same(tmp_path):
    import os
    import pytest
    root = str(tmp_path)
    _make_session(root, "C--proj-velha", "s1", r"C:\proj\velha")
    target = sessions.move_session_file("s1", r"C:\proj\velha", r"C:\proj\outra", root=root)
    assert os.path.dirname(target).endswith("C--proj-outra")
    with pytest.raises(OSError):
        sessions.move_session_file("s1", r"C:\proj\outra", r"C:\proj\outra", root=root)
    with pytest.raises(OSError):
        sessions.move_session_file("nao-existe", "", r"C:\x", root=root)
