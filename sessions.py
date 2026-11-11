"""Lista e carrega sessões do Claude Code a partir de ~/.claude/projects,
usando as funções de leitura do próprio SDK (não abrem processo nem rede)."""

import datetime
import json
import os
import re
import shutil
from dataclasses import dataclass

import formatting


@dataclass
class SessionEntry:
    session_id: str
    title: str
    cwd: str
    last_modified: int  # milissegundos desde a época

    def label(self, show_folder=True):
        when = ""
        if self.last_modified:
            dt = datetime.datetime.fromtimestamp(self.last_modified / 1000)
            when = dt.strftime("%d/%m/%Y %H:%M")
        folder = os.path.basename(self.cwd.rstrip("\\/")) if self.cwd else ""
        parts = [self.title]
        if folder and show_folder:
            parts.append("pasta " + folder)
        if when:
            parts.append(when)
        return ", ".join(parts)


def session_title(info):
    # O resumo do SDK costuma ser o último prompt; o primeiro identifica melhor.
    for value in (getattr(info, "custom_title", None), getattr(info, "first_prompt", None),
                  getattr(info, "summary", None)):
        if value and value.strip():
            return formatting.one_line(value)[:150]
    return "Sessão sem título"


def list_user_sessions(limit=200, lister=None):
    if lister is None:
        from claude_agent_sdk import list_sessions as lister
    infos = lister(limit=limit)
    entries = [SessionEntry(i.session_id, session_title(i), i.cwd or "", i.last_modified or 0)
               for i in infos]
    entries.sort(key=lambda e: e.last_modified, reverse=True)
    return entries


def load_history(session_id, directory=None, getter=None):
    """Devolve [(papel, texto)] da sessão, já agrupado por mensagem."""
    return load_history_points(session_id, directory, getter)[0]


def load_history_points(session_id, directory=None, getter=None):
    """Como load_history, mais os pontos de volta de cada mensagem da pessoa
    ({índice: uuid da entrada anterior}), o uuid da última entrada e os
    arquivos que o Claude criou ou editou em cada resposta ({índice: [caminhos]})."""
    if getter is None:
        from claude_agent_sdk import get_session_messages as getter
    messages = getter(session_id, directory=directory)
    entries = [{"type": m.type, "message": m.message, "uuid": getattr(m, "uuid", None)}
               for m in messages]
    points, files = {}, {}
    items = formatting.group_transcript(entries, points, files)
    last = entries[-1]["uuid"] if entries else None
    return items, points, last, files


def fetch_title(session_id, directory=None, getter=None):
    if getter is None:
        from claude_agent_sdk import get_session_info as getter
    """Só o título de verdade (custom-title). O resumo do SDK costuma ser o
    último prompt, que trocaria o título da janela a cada turno."""
    try:
        info = getter(session_id, directory=directory)
    except Exception:
        return None
    title = getattr(info, "custom_title", None) if info else None
    return formatting.one_line(title)[:150] if title and title.strip() else None


def rename(session_id, title, directory=None, renamer=None):
    """Grava o título no arquivo da sessão, como o /rename do Claude Code;
    vale também no aplicativo Claude e no terminal."""
    if renamer is None:
        from claude_agent_sdk import rename_session as renamer
    renamer(session_id, title.strip(), directory=directory)


def projects_root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def sanitize_folder(path):
    """Nome da pasta de projeto do Claude Code para um caminho de trabalho."""
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def find_session_file(session_id, root=None):
    root = root or projects_root()
    try:
        for name in os.listdir(root):
            candidate = os.path.join(root, name, session_id + ".jsonl")
            if os.path.isfile(candidate):
                return candidate
    except OSError:
        pass
    return None


def move_session_file(session_id, old_cwd, new_cwd, like_session_id=None, root=None):
    """Move a sessão para o grupo de outra pasta de trabalho: o arquivo vai
    para a pasta de projeto do destino e o campo cwd dentro dele passa a ser o
    novo. `like_session_id` é uma sessão que já está no destino; a pasta de
    projeto dela é usada, para não depender de adivinhar o nome. Devolve o
    novo caminho do arquivo."""
    root = root or projects_root()
    source = find_session_file(session_id, root)
    if not source:
        raise OSError("Não achei o arquivo desta sessão.")
    target_dir = None
    if like_session_id:
        like = find_session_file(like_session_id, root)
        target_dir = os.path.dirname(like) if like else None
    if not target_dir:
        name = sanitize_folder(new_cwd)
        if len(name) > 200:
            raise OSError("O caminho da pasta é longo demais para mover a sessão.")
        target_dir = os.path.join(root, name)
    if os.path.normcase(target_dir) == os.path.normcase(os.path.dirname(source)):
        raise OSError("A sessão já está nessa pasta.")
    target = os.path.join(target_dir, session_id + ".jsonl")
    if os.path.exists(target):
        raise OSError("Já existe uma sessão com esse código na pasta de destino.")
    with open(source, encoding="utf-8", newline="") as f:
        text = f.read()
    if old_cwd:
        for ascii_only in (False, True):
            old = '"cwd":' + json.dumps(old_cwd, ensure_ascii=ascii_only)
            new = '"cwd":' + json.dumps(new_cwd, ensure_ascii=ascii_only)
            text = text.replace(old, new)
    os.makedirs(target_dir, exist_ok=True)
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(temp, target)
    os.remove(source)
    # Pasta ao lado do arquivo (subagentes, resultados de ferramentas).
    extra = os.path.join(os.path.dirname(source), session_id)
    if os.path.isdir(extra) and not os.path.exists(os.path.join(target_dir, session_id)):
        shutil.move(extra, os.path.join(target_dir, session_id))
    return target


DATA_FOLDER = "CCA"
OLD_DATA_FOLDER = "claudeAcessivel"  # nome antigo do app; copiado na primeira abertura


def data_dir():
    """Pasta de dados do app (configuração, fila, registro, cópias de segurança).
    Se só existe a pasta com o nome antigo, copia o conteúdo para a nova sem
    apagar a antiga."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    new = os.path.join(base, DATA_FOLDER)
    old = os.path.join(base, OLD_DATA_FOLDER)
    if not os.path.isdir(new) and os.path.isdir(old):
        try:
            shutil.copytree(old, new)
        except OSError:
            pass
    return new


def config_path():
    return os.path.join(data_dir(), "config.json")


def load_config(path=None):
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data, path=None):
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
