import hashlib
import io
import os
import zipfile

import pytest

import downloads
import publicar
import updater


def rel(tag, body="", assets=(), **extra):
    item = {"tag_name": tag, "body": body, "html_url": "https://x/" + tag, "assets": list(assets)}
    item.update(extra)
    return item


def asset(name, count=0, digest="", size=10):
    return {"name": name, "download_count": count, "digest": digest, "size": size,
            "browser_download_url": "https://x/" + name}


def test_parse_and_compare_versions():
    assert updater.parse_version("2026.11.10.0") == (2026, 11, 10, 0)
    assert updater.parse_version("v2026.11.10.1") == (2026, 11, 10, 1)
    assert updater.parse_version("abc") == ()
    assert updater.is_newer("2026.11.10.1", "2026.11.10.0")
    assert updater.is_newer("2026.12.1.0", "2026.11.30.9")
    assert not updater.is_newer("2026.11.10.0", "2026.11.10.0")
    assert not updater.is_newer("lixo", "2026.11.10.0")


def test_releases_from_json_picks_newest_and_joins_notes():
    data = [
        rel("2026.11.12.0", "C", [asset("CCA-2026.11.12.0.zip"),
                                   asset("CCA-2026.11.12.0-atualizacao.zip", digest="sha256:ABC", size=99)]),
        rel("2026.11.11.0", "B"),
        rel("2026.11.10.0", "A"),
        rel("2026.11.13.0", "rascunho", draft=True),
        rel("2026.11.14.0", "beta", prerelease=True),
    ]
    release = updater.releases_from_json(data, "2026.11.10.0")
    assert release.version == "2026.11.12.0"
    assert release.asset_name == "CCA-2026.11.12.0-atualizacao.zip"
    assert release.sha256 == "abc" and release.size == 99
    assert [v for v, _ in release.history] == ["2026.11.12.0", "2026.11.11.0"]


def test_releases_from_json_nothing_new():
    assert updater.releases_from_json([rel("2026.11.10.0")], "2026.11.10.0") is None
    assert updater.releases_from_json({"message": "limite"}, "2026.11.10.0") is None


def test_check_reports_network_error():
    def boom(request, timeout=0):
        raise OSError("sem rede")
    release, error = updater.check("2026.11.10.0", opener=boom)
    assert release is None and "sem rede" in error


def test_due():
    assert updater.due(None, 1000)
    assert not updater.due(1000, 1000 + 3600)
    assert updater.due(1000, 1000 + 25 * 3600)


def test_can_install_refuses_git_copy(tmp_path):
    assert updater.can_install(str(tmp_path))
    (tmp_path / ".git").mkdir()
    assert not updater.can_install(str(tmp_path))


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_download_checks_sha256(tmp_path):
    data = b"conteudo"
    good = updater.Release("1.0.0.0", asset_url="https://x/a.zip", asset_name="a.zip",
                           sha256=hashlib.sha256(data).hexdigest())
    path = updater.download(good, str(tmp_path), opener=lambda r, timeout=0: FakeResponse(data))
    assert open(path, "rb").read() == data
    bad = updater.Release("1.0.0.0", asset_url="https://x/a.zip", asset_name="b.zip", sha256="0" * 64)
    with pytest.raises(ValueError):
        updater.download(bad, str(tmp_path), opener=lambda r, timeout=0: FakeResponse(data))
    assert not (tmp_path / "b.zip").exists()


def test_install_replaces_files_and_keeps_others(tmp_path):
    app = tmp_path / "app"
    (app / "__pycache__").mkdir(parents=True)
    (app / "app.py").write_text("velho")
    (app / "dados.txt").write_text("meu")
    zip_path = tmp_path / "u.zip"
    make_zip(zip_path, {"app.py": "novo", "sons/x.wav": "w", "__pycache__/z.pyc": "no"})
    updater.install(str(zip_path), str(app))
    assert (app / "app.py").read_text() == "novo"
    assert (app / "sons" / "x.wav").read_text() == "w"
    assert (app / "dados.txt").read_text() == "meu"
    assert not (app / "__pycache__" / "z.pyc").exists()
    assert not list(app.glob("*.novo"))


def test_install_accepts_single_top_folder(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    zip_path = tmp_path / "u.zip"
    make_zip(zip_path, {"CCA/app.py": "novo", "CCA/a/b.py": "b"})
    updater.install(str(zip_path), str(app))
    assert (app / "app.py").read_text() == "novo" and (app / "a" / "b.py").read_text() == "b"


def test_install_rejects_bad_zips_without_touching_files(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "app.py").write_text("velho")
    for files in ({"../fora.py": "x", "app.py": "n"}, {"outro.py": "x"}, {"C:/x.py": "x", "app.py": "n"}):
        zip_path = tmp_path / "u.zip"
        make_zip(zip_path, files)
        with pytest.raises(ValueError):
            updater.install(str(zip_path), str(app))
        assert (app / "app.py").read_text() == "velho"
    assert not (tmp_path / "fora.py").exists()


def test_downloads_summary_separates_manual_and_updates():
    data = [
        rel("2026.11.10.0", assets=[asset("CCA-2026.11.10.0.zip", 5), asset("CCA-2026.11.10.0-atualizacao.zip", 2)],
            published_at="2026-11-10T10:00:00Z"),
        rel("2026.11.11.0", assets=[asset("CCA-2026.11.11.0.zip", 1), asset("CCA-2026.11.11.0-atualizacao.zip", 7)]),
        rel("2026.11.12.0", draft=True),
    ]
    rows, totals = downloads.summarize(data)
    assert rows[0][0] == "2026.11.11.0" and rows[1][:4] == ("2026.11.10.0", "2026-11-10", 5, 2)
    assert totals == (6, 9)
    assert "Downloads no total: 15." in downloads.report(data)
    assert "Nenhuma" in downloads.report([])


def test_publicar_changelog_section_and_files():
    text = "# R\n\n## 2026.11.11.0\n\nB\n\n## 2026.11.10.0\n\nA\n"
    assert publicar.changelog_section(text, "2026.11.10.0") == "A"
    assert publicar.changelog_section(text, "2026.11.11.0") == "B"
    assert publicar.changelog_section(text, "2026.11.12.0") == ""
    kept = publicar.release_files(["app.py", "tests/test_x.py", "publicar.py", ".gitignore", "sons/a.wav"])
    assert kept == ["app.py", "sons/a.wav"]
