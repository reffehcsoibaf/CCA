import json
import zipfile

import pytest

import transfer


def make_claude(base):
    (base / "commands").mkdir(parents=True)
    (base / "CLAUDE.md").write_text("# Geral\n", encoding="utf-8")
    (base / "commands" / "revisar.md").write_text("revise", encoding="utf-8")
    memory = base / "projects" / "C--github-app" / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("- [x](x.md)\n", encoding="utf-8")
    (memory / "x.md").write_text("fato", encoding="utf-8")
    # Não devem entrar:
    (base / "settings.json").write_text('{"env": {"K": "v"}}', encoding="utf-8")
    (base / "projects" / "C--github-app" / "abc.jsonl").write_text("{}", encoding="utf-8")
    (base / ".credentials.json").write_text("{}", encoding="utf-8")


def test_collect_only_preferences_and_memories(tmp_path):
    make_claude(tmp_path)
    names = sorted(n for n, _ in transfer.collect(str(tmp_path)))
    assert names == ["CLAUDE.md", "commands/revisar.md",
                     "projects/C--github-app/memory/MEMORY.md",
                     "projects/C--github-app/memory/x.md"]


def test_export_and_import_into_empty_folder(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    make_claude(src)
    pack = str(tmp_path / "p.zip")
    count, secrets = transfer.export_zip(pack, str(src))
    assert count == 4 and secrets == []
    created, replaced, backup = transfer.import_zip(pack, replace=False, base=str(dst))
    assert (created, replaced, backup) == (4, 0, None)
    assert (dst / "CLAUDE.md").read_text(encoding="utf-8") == "# Geral\n"
    assert (dst / "projects" / "C--github-app" / "memory" / "x.md").read_text(encoding="utf-8") == "fato"


def test_import_without_replace_keeps_different_files(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    make_claude(src)
    make_claude(dst)
    (dst / "CLAUDE.md").write_text("# Meu\n", encoding="utf-8")
    pack = str(tmp_path / "p.zip")
    transfer.export_zip(pack, str(src))
    items, _ = transfer.plan_import(pack, str(dst))
    assert transfer.summarize(items) == (0, 1, 3)
    assert transfer.import_zip(pack, replace=False, base=str(dst)) == (0, 0, None)
    assert (dst / "CLAUDE.md").read_text(encoding="utf-8") == "# Meu\n"


def test_import_with_replace_makes_backup(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    make_claude(src)
    make_claude(dst)
    (dst / "CLAUDE.md").write_text("# Meu\n", encoding="utf-8")
    pack = str(tmp_path / "p.zip")
    transfer.export_zip(pack, str(src))
    created, replaced, backup = transfer.import_zip(pack, replace=True, base=str(dst),
                                                    backup_to=str(tmp_path / "bk"))
    assert (created, replaced) == (0, 1)
    assert (dst / "CLAUDE.md").read_text(encoding="utf-8") == "# Geral\n"
    with zipfile.ZipFile(backup) as z:
        assert z.read("claude/CLAUDE.md").decode("utf-8").strip() == "# Meu"


def test_export_warns_about_possible_secrets(tmp_path):
    make_claude(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("chave sk-ant-api03-abcdefghijklmnop", encoding="utf-8")
    _count, secrets = transfer.export_zip(str(tmp_path / "p.zip"), str(tmp_path))
    assert secrets == ["CLAUDE.md"]


def test_import_ignores_paths_outside_the_allowed_ones(tmp_path):
    pack = tmp_path / "p.zip"
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr(transfer.MANIFEST, json.dumps({"format": transfer.FORMAT}))
        z.writestr("claude/CLAUDE.md", "ok")
        z.writestr("claude/../fora.txt", "mau")
        z.writestr("claude/settings.json", "{}")
        z.writestr("claude/projects/p/abc.jsonl", "{}")
        z.writestr("claude/projects/../../x/memory/a.md", "mau")
    dst = tmp_path / "dst"
    items, ignored = transfer.plan_import(str(pack), str(dst))
    assert [i.name for i in items] == ["CLAUDE.md"]
    assert len(ignored) == 4
    transfer.import_zip(str(pack), replace=True, base=str(dst))
    assert not (tmp_path / "fora.txt").exists()
    assert sorted(p.name for p in dst.iterdir()) == ["CLAUDE.md"]


def test_import_rejects_foreign_zip(tmp_path):
    pack = tmp_path / "p.zip"
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("qualquer.txt", "x")
    with pytest.raises(ValueError):
        transfer.plan_import(str(pack), str(tmp_path / "d"))


# ---------- mapeamento de pastas ----------

def test_search_path_rebuilds_path_with_hyphens_and_underscores(tmp_path):
    target = tmp_path / "meus-apps" / "app_novo"
    target.mkdir(parents=True)
    key = transfer.sanitize_folder(str(target))[len(transfer.sanitize_folder(str(tmp_path))) + 1:]
    assert transfer._search_path(str(tmp_path), key) == str(target)
    assert transfer._search_path(str(tmp_path), "nao-existe") == ""


def test_cwd_is_read_from_sessions_only_when_it_matches(tmp_path):
    cwd = r"C:\github\app"
    key = transfer.sanitize_folder(cwd)
    folder = tmp_path / key
    folder.mkdir()
    (folder / "s1.jsonl").write_text(json.dumps({"type": "x"}) + "\n" + json.dumps({"cwd": cwd}) + "\n",
                                     encoding="utf-8")
    assert transfer._cwd_from_sessions(str(folder), key) == cwd
    assert transfer._cwd_from_sessions(str(folder), "C--outra") == ""


def test_export_records_original_folder_paths(tmp_path):
    make_claude(tmp_path / "a")
    base = tmp_path / "a"
    key = "C--github-app"
    (base / "projects" / key / "s1.jsonl").write_text(json.dumps({"cwd": r"C:\github\app"}) + "\n",
                                                      encoding="utf-8")
    pack = str(tmp_path / "p.zip")
    transfer.export_zip(pack, str(base))
    assert [(f.key, f.path) for f in transfer.package_folders(pack)] == [(key, r"C:\github\app")]


def test_suggest_mapping_replaces_common_prefix():
    folders = [transfer.Folder("C--github-a", r"C:\github\a"), transfer.Folder("C--github-b", r"C:\github\b"),
               transfer.Folder("C--x", "")]
    mapping = transfer.suggest_mapping(folders, r"D:\codigo")
    assert mapping == {"C--github-a": r"D:\codigo\a", "C--github-b": r"D:\codigo\b"}


def test_suggest_mapping_single_folder_goes_to_new_base():
    folders = [transfer.Folder("C--github-a", r"C:\github\a")]
    assert transfer.suggest_mapping(folders, r"D:\codigo\app") == {"C--github-a": r"D:\codigo\app"}


def test_import_with_mapping_renames_memory_folder_and_skips_none(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    make_claude(src)
    other = src / "projects" / "C--github-outra" / "memory"
    other.mkdir(parents=True)
    (other / "z.md").write_text("z", encoding="utf-8")
    pack = str(tmp_path / "p.zip")
    transfer.export_zip(pack, str(src))
    mapping = {"C--github-app": r"D:\codigo\app", "C--github-outra": None}
    created, _, _ = transfer.import_zip(pack, replace=False, base=str(dst), mapping=mapping)
    new_key = transfer.sanitize_folder(r"D:\codigo\app")
    assert (dst / "projects" / new_key / "memory" / "x.md").read_text(encoding="utf-8") == "fato"
    assert not (dst / "projects" / "C--github-outra").exists()
    assert not (dst / "projects" / "C--github-app").exists()
    assert created == 4  # CLAUDE.md, commands/revisar.md, MEMORY.md e x.md


def test_unmatched_folders_ignores_folders_that_exist_here(tmp_path):
    here = tmp_path / "meu-app"
    here.mkdir()
    ok = transfer.Folder(transfer.sanitize_folder(str(here)), str(here))
    gone = transfer.Folder("C--nao-existe", r"C:\nao\existe")
    unknown = transfer.Folder("C--sem-caminho", "")
    assert transfer.unmatched_folders([ok, gone, unknown]) == [gone, unknown]
