"""Publica uma release do CCA no GitHub, sempre marcada como Latest.

Uso: py publicar.py [--simular]

Lê a versão de formatting.VERSION, confere se o CHANGELOG.md tem a seção dela,
se tudo está commitado e enviado, e se a tag ainda não existe. Monta dois zips
com os arquivos versionados (menos testes e estes scripts): CCA-<versão>.zip
para baixar e CCA-<versão>-atualizacao.zip para o atualizador do app. Com
--simular só monta e mostra, sem publicar."""

import os
import re
import subprocess
import sys
import zipfile

import formatting

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dist")
EXCLUDE_DIRS = ("tests/",)
EXCLUDE_FILES = {".gitignore", "publicar.py", "publicar.cmd", "downloads.py", "downloads.cmd",
                 "instalacao-release.md"}


def run(*args):
    done = subprocess.run(args, cwd=HERE, capture_output=True, text=True, encoding="utf-8")
    return done.returncode, (done.stdout or "").strip(), (done.stderr or "").strip()


def changelog_section(text, version):
    """O texto da seção '## <versão>' do CHANGELOG, ou '' se não existe."""
    match = re.search(r"^## " + re.escape(version) + r"\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1).strip() if match else ""


def release_notes(changelog_notes, version):
    """Notas da release: o texto do CHANGELOG e, depois do marcador, o passo a
    passo de instalação (instalacao-release.md). O atualizador do app corta as
    notas no marcador, então o passo a passo não aparece na janela de versão nova."""
    try:
        with open(os.path.join(HERE, "instalacao-release.md"), encoding="utf-8") as f:
            install = f.read().replace("{versao}", version).strip()
    except OSError:
        return changelog_notes
    return changelog_notes + "\n\n" + install


def release_files(tracked):
    return [f for f in tracked
            if f not in EXCLUDE_FILES and not f.startswith(EXCLUDE_DIRS)]


def build_zip(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            zf.write(os.path.join(HERE, name), name)


def main():
    simulate = "--simular" in sys.argv
    version = formatting.VERSION
    try:
        with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as f:
            notes = changelog_section(f.read(), version)
    except OSError:
        notes = ""
    if not notes:
        return fail(f"O CHANGELOG.md não tem a seção '## {version}'.")
    code, out, _ = run("git", "status", "--porcelain")
    if out and not simulate:
        return fail("Há alterações não commitadas. Faça o commit e envie antes de publicar.")
    if not simulate:
        run("git", "fetch", "--tags", "--quiet")
        _, head, _ = run("git", "rev-parse", "HEAD")
        _, remote, _ = run("git", "rev-parse", "origin/main")
        if head != remote:
            return fail("O commit atual não está enviado (push) para o GitHub.")
        code, out, _ = run("git", "tag", "--list", version)
        if out:
            return fail(f"A tag {version} já existe. Suba o número da versão (formatting.VERSION e CHANGELOG.md).")
    _, listing, _ = run("git", "ls-files")
    files = release_files([n for n in listing.splitlines() if n])
    os.makedirs(OUT, exist_ok=True)
    manual = os.path.join(OUT, f"CCA-{version}.zip")
    auto = os.path.join(OUT, f"CCA-{version}-atualizacao.zip")
    build_zip(manual, files)
    build_zip(auto, files)
    print(f"Montei {len(files)} arquivos em:\n  {manual}\n  {auto}")
    if simulate:
        print("Simulação: nada foi publicado.")
        return 0
    notes_path = os.path.join(OUT, f"notas-{version}.md")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(release_notes(notes, version) + "\n")
    code, out, err = run("gh", "release", "create", version, manual, auto, "--title", version,
                         "--notes-file", notes_path, "--latest", "--target", "main")
    if code:
        return fail(f"O gh não publicou: {err or out}")
    print(f"Publicado como Latest: {out}")
    return 0


def fail(text):
    print("ERRO: " + text)
    return 1


if __name__ == "__main__":
    sys.exit(main())
