"""Links e arquivos citados nas mensagens: endereços da web, links em
Markdown (o Claude Code escreve [app.py](app.py:42)), caminhos do Windows,
referências @"caminho" e nomes de arquivo entre crases. Arquivos só entram
se existirem. Nada aqui depende de wx."""

import os
import re
from dataclasses import dataclass

# Abrir estes direto executaria o arquivo; o app abre no Bloco de Notas.
RUNNABLE = {".bat", ".cmd", ".com", ".exe", ".js", ".jse", ".lnk", ".msi", ".ps1", ".py", ".pyw",
            ".reg", ".scr", ".vbe", ".vbs", ".wsf", ".hta", ".cpl", ".jar"}
TEXT_MAX_BYTES = 2_000_000

_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(<?([^)\s>]+)>?\)")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\[\]\"'`]+", re.IGNORECASE)
_QUOTED_PATH = re.compile(r"\"([A-Za-z]:\\[^\"\n]+)\"")
_WIN_PATH = re.compile(r"(?<![\w/])[A-Za-z]:\\[^\s\"'<>|*?`]+")
_BACKTICK = re.compile(r"`([^`\n]{1,260})`")
_LINE_SUFFIX = re.compile(r"(?::\d+){1,2}$|#L\d+(?:-L?\d+)?$")
_TRAILING = ".,;:!?"


@dataclass
class Link:
    kind: str      # "url" ou "file"
    target: str    # endereço completo ou caminho absoluto
    label: str     # nome mostrado

    def describe(self):
        if self.kind == "url":
            return self.target if self.label == self.target else f"{self.label}, {self.target}"
        folder = os.path.dirname(self.target)
        name = os.path.basename(self.target) or self.target
        text = f"{name}, pasta {folder}" if self.label in (name, self.target) else f"{self.label}, {name}, pasta {folder}"
        return ("Pasta " if os.path.isdir(self.target) else "Arquivo ") + text

    @property
    def runnable(self):
        return os.path.splitext(self.target)[1].lower() in RUNNABLE


def _clean_url(url):
    url = url.rstrip(_TRAILING)
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(_TRAILING)
    if url.lower().startswith("www."):
        url = "http://" + url
    return url


def _resolve_file(raw, cwd):
    """Caminho absoluto de um arquivo ou pasta existente, ou None."""
    path = raw.strip().strip("<>").rstrip(_TRAILING)
    if path.lower().startswith("file:///"):
        from urllib.parse import unquote
        path = unquote(path[8:])
    path = _LINE_SUFFIX.sub("", path)
    if not path or "://" in path or path.startswith(("#", "mailto:")):
        return None
    path = path.replace("/", os.sep) if os.sep == "\\" else path
    if not os.path.isabs(path):
        if not cwd:
            return None
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    try:
        return path if os.path.exists(path) else None
    except (OSError, ValueError):
        return None


def find_links(text, cwd=None, extra_files=()):
    """Links e arquivos na ordem em que aparecem, sem repetição. `extra_files`
    são arquivos que o Claude criou ou editou naquela resposta."""
    found = []   # (posição, Link)
    seen = set()
    taken = []   # trechos já usados, para um caminho não ser lido duas vezes

    def add(pos, link, span=None):
        key = (link.kind, link.target.lower() if link.kind == "file" else link.target)
        if span:
            taken.append(span)
        if key not in seen:
            seen.add(key)
            found.append((pos, link))

    def free(span):
        return not any(a < span[1] and span[0] < b for a, b in taken)

    text = text or ""
    for m in _MD_LINK.finditer(text):
        label, target = m.group(1).strip(), m.group(2)
        if re.match(r"https?://", target, re.IGNORECASE):
            add(m.start(), Link("url", _clean_url(target), label), m.span())
            continue
        path = _resolve_file(target, cwd)
        if path:
            add(m.start(), Link("file", path, label), m.span())
        else:
            taken.append(m.span())
    for m in _URL.finditer(text):
        if free(m.span()):
            url = _clean_url(m.group(0))
            add(m.start(), Link("url", url, url), m.span())
    for regex in (_QUOTED_PATH, _WIN_PATH):
        for m in regex.finditer(text):
            if free(m.span()):
                raw = m.group(1) if regex is _QUOTED_PATH else m.group(0)
                path = _resolve_file(raw, cwd)
                if path:
                    add(m.start(), Link("file", path, raw.rstrip(_TRAILING)), m.span())
    for m in _BACKTICK.finditer(text):
        inner = m.group(1).strip()
        if free(m.span()) and ("/" in inner or "\\" in inner or re.search(r"\.\w{1,8}(?::\d+)?$", inner)):
            path = _resolve_file(inner, cwd)
            if path:
                add(m.start(), Link("file", path, inner), m.span())
    found.sort(key=lambda pair: pair[0])
    links = [link for _, link in found]
    for raw in extra_files:
        path = _resolve_file(raw, cwd)
        key = ("file", path.lower()) if path else None
        if path and key not in seen:
            seen.add(key)
            links.append(Link("file", path, os.path.basename(path)))
    return links


def summary(links):
    """'2 links e 1 arquivo', para o rótulo da mensagem; '' se não houver."""
    urls = sum(1 for link in links if link.kind == "url")
    files = len(links) - urls
    parts = []
    if urls:
        parts.append("1 link" if urls == 1 else f"{urls} links")
    if files:
        parts.append("1 arquivo" if files == 1 else f"{files} arquivos")
    return " e ".join(parts)


def read_text(path):
    """Conteúdo de um arquivo de texto para ler no app, ou None se não for texto."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > TEXT_MAX_BYTES:
            return None
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding).replace("\r\n", "\n")
        except UnicodeDecodeError:
            continue
    return None
