"""Agrupa as sessões pela pasta de trabalho, como os projetos do aplicativo
Claude. Nada aqui depende de wx."""

import os
from dataclasses import dataclass, field

NO_FOLDER = "Sem pasta"


@dataclass
class Group:
    key: str           # a pasta normalizada
    name: str          # nome mostrado
    cwd: str           # pasta para sessões novas criadas no grupo
    entries: list = field(default_factory=list)

    def label(self):
        count = len(self.entries)
        sessions = "1 sessão" if count == 1 else f"{count} sessões"
        return f"Pasta {self.name}, {sessions}"

    @property
    def ident(self):
        return f"folder:{self.key}"


def folder_key(cwd):
    return os.path.normcase(os.path.normpath(cwd)) if cwd else ""


def _recency(group):
    return max((e.last_modified for e in group.entries), default=0)


def group_sessions(entries):
    """Uma pasta por grupo, a usada mais recentemente primeiro. Dentro de cada
    grupo as sessões ficam na ordem recebida (mais recentes primeiro)."""
    folders = {}
    for entry in entries:
        key = folder_key(entry.cwd)
        if key not in folders:
            folders[key] = Group(key, "", entry.cwd or "")
        folders[key].entries.append(entry)
    names = {}
    for group in folders.values():
        base = os.path.basename(group.cwd.rstrip("\\/")) if group.cwd else NO_FOLDER
        names.setdefault(base.lower(), []).append(group)
        group.name = base or group.cwd
    for same in names.values():
        if len(same) > 1:  # duas pastas com o mesmo nome: mostra o caminho
            for group in same:
                group.name = group.cwd or NO_FOLDER
    return sorted(folders.values(), key=_recency, reverse=True)
