import os

import links


def make(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('oi')\n", encoding="utf-8")
    (tmp_path / "LEIAME.md").write_text("# Olá\n", encoding="utf-8")
    (tmp_path / "pasta com espaço").mkdir()
    (tmp_path / "pasta com espaço" / "nota.txt").write_text("nota", encoding="utf-8")
    return str(tmp_path)


def test_finds_urls_markdown_and_files(tmp_path):
    cwd = make(tmp_path)
    nota = os.path.join(cwd, "pasta com espaço", "nota.txt")
    text = (
        "Veja [a documentação](https://docs.example.com/guia?a=1) e https://exemplo.com.br/x).\n"
        "Mudei [app.py](src/app.py:42) e `LEIAME.md`. Também www.site.org, e o arquivo "
        f'"{nota}" e @"{nota}". `inexistente.py` e [sumiu](nao/existe.py) ficam de fora.'
    )
    found = links.find_links(text, cwd)
    assert [(l.kind, l.label) for l in found] == [
        ("url", "a documentação"),
        ("url", "https://exemplo.com.br/x"),
        ("file", "app.py"),
        ("file", "LEIAME.md"),
        ("url", "http://www.site.org"),
        ("file", nota),
    ]
    assert found[0].target == "https://docs.example.com/guia?a=1"
    assert found[2].target == os.path.join(cwd, "src", "app.py")
    assert found[2].runnable and not found[3].runnable


def test_bare_windows_path_and_extra_files(tmp_path):
    cwd = make(tmp_path)
    app = os.path.join(cwd, "src", "app.py")
    found = links.find_links(f"Criei {app}.", None, extra_files=[app, os.path.join(cwd, "LEIAME.md")])
    assert [l.target for l in found] == [app, os.path.join(cwd, "LEIAME.md")]
    assert found[0].describe() == f"Arquivo app.py, pasta {os.path.join(cwd, 'src')}"


def test_summary_and_read_text(tmp_path):
    cwd = make(tmp_path)
    found = links.find_links("https://a.com https://b.com `src/app.py`", cwd)
    assert links.summary(found) == "2 links e 1 arquivo"
    assert links.summary([]) == ""
    assert links.read_text(os.path.join(cwd, "LEIAME.md")) == "# Olá\n"
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    assert links.read_text(str(tmp_path / "bin.dat")) is None
