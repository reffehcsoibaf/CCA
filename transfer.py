"""Exportar e importar as preferências e memórias do Claude Code.

O que entra no pacote (um .zip):
- CLAUDE.md global (memória geral e preferências de trabalho);
- comandos próprios (pasta commands);
- a memória de cada pasta de trabalho (projects/<pasta>/memory).

Ficam de fora, de propósito: as sessões (conversas), o settings.json (pode ter
variáveis de ambiente com chaves) e qualquer credencial de login.

O nome da pasta de memória vem do caminho da pasta de trabalho (C:\\github\\app
vira C--github-app). Por isso o pacote guarda também o caminho original de cada
pasta, e na importação dá para mapear para outro caminho, num computador novo.
"""

import datetime
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass

import sessions
from sessions import sanitize_folder

FORMAT = 1
MANIFEST = "manifest.json"
PREFIX = "claude/"

# Padrões comuns de chave ou token; só para avisar, nunca para apagar nada.
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".py", ".js", ".cmd", ".bat"}


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def backup_dir():
    return sessions.data_dir()


@dataclass
class Item:
    name: str           # onde vai ficar aqui, com "/", relativo à pasta do Claude Code
    status: str = "new"  # new, same, different
    source: str = ""    # nome dentro do pacote (sem o prefixo claude/); igual a name se não mapeado


@dataclass
class Folder:
    key: str            # nome da pasta de memória no pacote (ex.: C--github-app)
    path: str = ""      # caminho original da pasta de trabalho, se se conseguiu descobrir


def _walk_files(folder):
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            yield os.path.join(root, name)


# ---------- descobrir o caminho original de cada pasta de memória ----------

def _cwd_from_sessions(project_dir, key):
    """Caminho de trabalho gravado nas sessões da pasta de projeto, se bater com o nome."""
    try:
        sessions = [os.path.join(project_dir, n) for n in os.listdir(project_dir) if n.endswith(".jsonl")]
    except OSError:
        return ""
    sessions.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for path in sessions[:3]:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for _ in range(60):
                    line = f.readline()
                    if not line:
                        break
                    if '"cwd"' not in line:
                        continue
                    try:
                        cwd = json.loads(line).get("cwd")
                    except ValueError:
                        continue
                    if isinstance(cwd, str) and sanitize_folder(cwd) == key:
                        return cwd
        except OSError:
            continue
    return ""


def _search_path(current, rest):
    """Acha, descendo pelas pastas existentes, o caminho cujo nome codificado é `rest`."""
    try:
        entries = os.listdir(current)
    except OSError:
        return ""
    for entry in entries:
        code = sanitize_folder(entry)
        full = os.path.join(current, entry)
        if code == rest and os.path.isdir(full):
            return full
        if rest.startswith(code + "-") and os.path.isdir(full):
            found = _search_path(full, rest[len(code) + 1:])
            if found:
                return found
    return ""


def guess_path(key):
    """Reconstrói o caminho a partir do nome codificado, olhando as pastas do disco (Windows)."""
    if len(key) > 3 and key[0].isalpha() and key[1:3] == "--":
        return _search_path(key[0].upper() + ":\\", key[3:])
    return ""


def folder_paths(base=None):
    """Caminho original de cada pasta de memória: {nome codificado: caminho ou ''}."""
    base = base or claude_dir()
    projects = os.path.join(base, "projects")
    result = {}
    if not os.path.isdir(projects):
        return result
    for key in sorted(os.listdir(projects)):
        folder = os.path.join(projects, key)
        if not os.path.isdir(os.path.join(folder, "memory")):
            continue
        result[key] = _cwd_from_sessions(folder, key) or guess_path(key)
    return result


# ---------- exportar ----------

def collect(base=None):
    """Arquivos a exportar: lista de (nome no pacote, caminho no disco)."""
    base = base or claude_dir()
    found = []
    claude_md = os.path.join(base, "CLAUDE.md")
    if os.path.isfile(claude_md):
        found.append(("CLAUDE.md", claude_md))
    commands = os.path.join(base, "commands")
    if os.path.isdir(commands):
        for path in _walk_files(commands):
            found.append((os.path.relpath(path, base).replace(os.sep, "/"), path))
    projects = os.path.join(base, "projects")
    if os.path.isdir(projects):
        for folder in sorted(os.listdir(projects)):
            memory = os.path.join(projects, folder, "memory")
            if os.path.isdir(memory):
                for path in _walk_files(memory):
                    found.append((os.path.relpath(path, base).replace(os.sep, "/"), path))
    return found


def find_secrets(files):
    """Nomes dos arquivos de texto que parecem conter chave ou token."""
    suspects = []
    for name, path in files:
        if os.path.splitext(path)[1].lower() not in _TEXT_SUFFIXES:
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read(200_000)
        except OSError:
            continue
        if any(p.search(text) for p in _SECRET_PATTERNS):
            suspects.append(name)
    return suspects


def export_zip(dest, base=None):
    """Grava o pacote em `dest`. Devolve (quantidade de arquivos, lista de
    arquivos com possível segredo)."""
    files = collect(base)
    keys = {n.split("/")[1] for n, _ in files if n.startswith("projects/")}
    paths = {k: p for k, p in folder_paths(base).items() if k in keys}
    manifest = {
        "format": FORMAT,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": [name for name, _ in files],
        "folders": paths,
    }
    temp = dest + ".tmp"
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, path in files:
            z.write(path, PREFIX + name)
    os.replace(temp, dest)
    return len(files), find_secrets(files)


# ---------- importar ----------

def _allowed(name):
    """Só entram os caminhos que o export gera, sem sair da pasta de destino."""
    if not name or name.startswith(("/", "\\")) or ":" in name or "\\" in name:
        return False
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    if name == "CLAUDE.md":
        return True
    if parts[0] == "commands" and len(parts) >= 2:
        return True
    return len(parts) >= 4 and parts[0] == "projects" and parts[2] == "memory"


def _read_package(src):
    with zipfile.ZipFile(src) as z:
        try:
            manifest = json.loads(z.read(MANIFEST).decode("utf-8"))
        except (KeyError, ValueError):
            raise ValueError("Este arquivo não é um pacote de preferências e memórias do CCA.")
        if manifest.get("format") != FORMAT:
            raise ValueError("Este pacote vem de uma versão que não conheço.")
        names = [n for n in z.namelist() if n.startswith(PREFIX) and not n.endswith("/")]
    return manifest, [n[len(PREFIX):] for n in names]


def package_folders(src):
    """Pastas de memória do pacote, com o caminho original quando se sabe."""
    manifest, names = _read_package(src)
    known = manifest.get("folders") if isinstance(manifest.get("folders"), dict) else {}
    keys = sorted({n.split("/")[1] for n in names if _allowed(n) and n.startswith("projects/")})
    return [Folder(k, known.get(k) if isinstance(known.get(k), str) else "") for k in keys]


def unmatched_folders(folders):
    """Pastas do pacote que não existem aqui com o mesmo caminho."""
    result = []
    for f in folders:
        if f.path and os.path.isdir(f.path) and sanitize_folder(f.path) == f.key:
            continue
        result.append(f)
    return result


def suggest_mapping(folders, new_base):
    """Troca o começo comum dos caminhos originais por `new_base`. Devolve
    {nome codificado: novo caminho}; pastas sem caminho conhecido ficam de fora."""
    with_path = [f for f in folders if f.path]
    if not with_path:
        return {}
    try:
        common = os.path.commonpath([f.path for f in with_path])
    except ValueError:  # unidades diferentes
        common = ""
    mapping = {}
    for f in with_path:
        if common:
            rest = os.path.relpath(f.path, common)
            mapping[f.key] = new_base if rest == "." else os.path.join(new_base, rest)
        else:
            mapping[f.key] = os.path.join(new_base, os.path.basename(f.path.rstrip("\\/")))
    return mapping


def _target_name(name, mapping):
    """Nome de destino de um arquivo, aplicando o mapa {chave: novo caminho ou None}."""
    parts = name.split("/")
    if parts[0] != "projects" or not mapping or parts[1] not in mapping:
        return name
    new_path = mapping[parts[1]]
    if new_path is None:
        return None  # não importar esta pasta
    parts[1] = sanitize_folder(new_path)
    return "/".join(parts)


def plan_import(src, base=None, mapping=None):
    """Compara o pacote com o que existe aqui. `mapping` é {nome da pasta no
    pacote: novo caminho de trabalho, ou None para não importar}. Devolve a
    lista de Item e a de nomes ignorados por não serem caminhos aceitos."""
    base = base or claude_dir()
    items, ignored = [], []
    _manifest, names = _read_package(src)
    with zipfile.ZipFile(src) as z:
        for name in names:
            if not _allowed(name):
                ignored.append(name)
                continue
            target_name = _target_name(name, mapping)
            if target_name is None:
                continue
            target = os.path.join(base, *target_name.split("/"))
            if not os.path.isfile(target):
                items.append(Item(target_name, "new", name))
                continue
            with open(target, "rb") as f:
                same = f.read() == z.read(PREFIX + name)
            items.append(Item(target_name, "same" if same else "different", name))
    return items, ignored


def import_zip(src, replace, base=None, backup_to=None, mapping=None):
    """Aplica o pacote. Sem `replace`, só cria o que não existe. Com `replace`,
    também troca os arquivos diferentes, guardando antes uma cópia dos atuais
    num .zip em `backup_to` (ou na pasta de dados do app). Devolve
    (criados, substituídos, caminho da cópia ou None)."""
    base = base or claude_dir()
    items, _ignored = plan_import(src, base, mapping)
    created = [i for i in items if i.status == "new"]
    changed = [i for i in items if i.status == "different"] if replace else []
    backup_path = None
    if changed:
        folder = backup_to or backup_dir()
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(folder, f"copia-antes-de-importar-{stamp}.zip")
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as b:
            for item in changed:
                b.write(os.path.join(base, *item.name.split("/")), PREFIX + item.name)
    with zipfile.ZipFile(src) as z:
        for item in created + changed:
            target = os.path.join(base, *item.name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(z.read(PREFIX + item.source))
                os.replace(temp, target)
            except BaseException:
                if os.path.exists(temp):
                    os.remove(temp)
                raise
    return len(created), len(changed), backup_path


def summarize(items):
    """Totais (novos, diferentes, iguais), para a janela de escolha."""
    new = sum(1 for i in items if i.status == "new")
    diff = sum(1 for i in items if i.status == "different")
    same = sum(1 for i in items if i.status == "same")
    return new, diff, same
