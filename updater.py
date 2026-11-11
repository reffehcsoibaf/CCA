"""Atualização do CCA pelas releases do GitHub.

Tudo aqui é lógica sem janela, para poder ser testada: ler as releases,
comparar versões, baixar o zip de atualização, conferir o SHA-256 e trocar os
arquivos do programa. A janela fica no app.py.

Cada release publica dois zips com o mesmo conteúdo: `CCA-<versão>.zip`, que a
pessoa baixa pela página, e `CCA-<versão>-atualizacao.zip`, que só o
atualizador baixa. Assim a contagem de downloads do GitHub separa quem baixou
de quem atualizou (ver downloads.py)."""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field

import formatting

REPO = "reffehcsoibaf/CCA"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
PAGE = f"https://github.com/{REPO}/releases/latest"
UPDATE_SUFFIX = "-atualizacao.zip"
CHECK_EVERY_HOURS = 24
# Nunca sobrescritos nem criados pela atualização.
KEEP = ("__pycache__", ".git")


@dataclass
class Release:
    version: str
    notes: str = ""
    url: str = ""          # página da release
    asset_url: str = ""    # zip de atualização
    asset_name: str = ""
    size: int = 0
    sha256: str = ""
    history: list = field(default_factory=list)  # [(versão, notas)] mais novas primeiro


def parse_version(text):
    """'2026.11.10.0' -> (2026, 11, 10, 0). Aceita um 'v' na frente. Vazio se
    não for um número de versão."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,4})", (text or "").strip())
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def is_newer(candidate, current):
    a, b = parse_version(candidate), parse_version(current)
    return bool(a) and bool(b) and a > b


def releases_from_json(data, current):
    """Escolhe a release mais nova (fora rascunhos e pré-lançamentos) e junta as
    notas de tudo que saiu depois da versão em uso. None se não há nada novo."""
    newer = []
    for item in data if isinstance(data, list) else []:
        if item.get("draft") or item.get("prerelease"):
            continue
        version = item.get("tag_name", "")
        if is_newer(version, current):
            newer.append(item)
    if not newer:
        return None
    newer.sort(key=lambda i: parse_version(i["tag_name"]), reverse=True)
    top = newer[0]
    release = Release(version=top["tag_name"].lstrip("v"), notes=(top.get("body") or "").strip(),
                      url=top.get("html_url") or PAGE)
    for asset in top.get("assets") or []:
        if asset.get("name", "").endswith(UPDATE_SUFFIX):
            release.asset_url = asset.get("browser_download_url", "")
            release.asset_name = asset["name"]
            release.size = int(asset.get("size") or 0)
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:"):
                release.sha256 = digest[7:].lower()
    release.history = [(i["tag_name"].lstrip("v"), (i.get("body") or "").strip()) for i in newer]
    return release


def http_get(url, opener=None, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": f"CCA/{formatting.VERSION}",
                                                   "Accept": "application/vnd.github+json"})
    with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
        return response.read()


def check(current=None, opener=None):
    """(Release ou None, erro). Erro é texto para a pessoa; rede fora do ar não
    é exceção."""
    current = current or formatting.VERSION
    try:
        data = json.loads(http_get(API, opener).decode("utf-8"))
    except Exception as exc:  # rede, limite da API, JSON ruim
        return None, f"Não consegui consultar o GitHub: {exc}"
    return releases_from_json(data, current), ""


def due(last_check, now, hours=CHECK_EVERY_HOURS):
    """Se já passou tempo para a checagem automática. Tempos em segundos."""
    return not last_check or now - last_check >= hours * 3600


def can_install(app_dir):
    """Cópia de desenvolvimento (com .git) não se atualiza sozinha: o git é o
    caminho dela, e a troca de arquivos apagaria alterações não commitadas."""
    return not os.path.exists(os.path.join(app_dir, ".git"))


def download(release, dest_dir, progress=None, opener=None):
    """Baixa o zip de atualização para dest_dir e confere o SHA-256 quando o
    GitHub informa. Devolve o caminho; levanta OSError/ValueError."""
    if not release.asset_url:
        raise ValueError("Esta versão não tem o arquivo de atualização.")
    request = urllib.request.Request(release.asset_url, headers={"User-Agent": f"CCA/{formatting.VERSION}"})
    path = os.path.join(dest_dir, release.asset_name)
    digest = hashlib.sha256()
    done = 0
    with (opener or urllib.request.urlopen)(request, timeout=30) as response, open(path, "wb") as out:
        total = int(response.headers.get("Content-Length") or release.size or 0)
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)
    if release.sha256 and digest.hexdigest() != release.sha256:
        os.remove(path)
        raise ValueError("O arquivo baixado não confere com o SHA-256 da release. Nada foi instalado.")
    return path


def _root_prefix(names):
    """Se o zip tem tudo dentro de uma pasta única, devolve 'pasta/'."""
    if "app.py" in names:
        return ""
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    if len(tops) == 1 and all("/" in n for n in names if n.strip("/")):
        return next(iter(tops)) + "/"
    return ""


def install(zip_path, app_dir):
    """Troca os arquivos do programa pelos do zip. Confere o zip inteiro antes
    de tocar em qualquer arquivo. Devolve a lista de arquivos gravados."""
    app_dir = os.path.abspath(app_dir)
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"O zip está corrompido ({bad}).")
        names = [n for n in zf.namelist() if not n.endswith("/")]
        prefix = _root_prefix(zf.namelist())
        plan = []
        for name in names:
            rel = name[len(prefix):] if prefix and name.startswith(prefix) else name
            parts = rel.replace("\\", "/").split("/")
            if not rel or rel.startswith("/") or ".." in parts or ":" in parts[0]:
                raise ValueError(f"Caminho suspeito no zip: {name}")
            if any(p in KEEP for p in parts):
                continue
            target = os.path.abspath(os.path.join(app_dir, *parts))
            if os.path.commonpath([app_dir, target]) != app_dir:
                raise ValueError(f"Caminho suspeito no zip: {name}")
            plan.append((name, target))
        if not any(t == os.path.join(app_dir, "app.py") for _, t in plan):
            raise ValueError("O zip não parece ser do CCA (falta o app.py).")
        # Etapa 1: extrai tudo numa pasta temporária. Falhou aqui, nada mudou.
        staging = tempfile.mkdtemp(prefix="cca-update-")
        try:
            staged = []
            for name, target in plan:
                temp = os.path.join(staging, str(len(staged)))
                with zf.open(name) as src, open(temp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                staged.append((temp, target))
            # Etapa 2: copia por cima. Cada arquivo vai para um .novo e é
            # trocado de uma vez, para não deixar arquivo pela metade.
            written = []
            for temp, target in staged:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                partial = target + ".novo"
                shutil.copyfile(temp, partial)
                os.replace(partial, target)
                written.append(target)
            return written
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def restart_command(app_dir):
    """Comando que abre o app de novo, sem janela de console."""
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    return [exe, os.path.join(app_dir, "app.py")]
