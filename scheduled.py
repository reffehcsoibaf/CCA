"""Fila de mensagens que esperam o limite de uso renovar. Fica num arquivo
ao lado da configuração, para sobreviver ao fechamento do app: se a janela
estiver fechada na hora da renovação, a fila sai quando ela abrir de novo.
Nada aqui depende de wx."""

import datetime
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field

import formatting

# Espera depois do horário de renovação, para não bater no limite antigo.
MARGIN_SECONDS = 60


@dataclass
class Item:
    text: str
    session_id: str | None   # None: a sessão ainda não existia quando a mensagem entrou
    cwd: str
    session_title: str
    group: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: float = field(default_factory=lambda: datetime.datetime.now().timestamp())

    def label(self, number):
        return f"{number}: {formatting.one_line(self.text)[:300]}. Sessão {self.session_title}"


def queue_path():
    import sessions
    return os.path.join(os.path.dirname(sessions.config_path()), "fila.json")


class Queue:
    def __init__(self, path=None):
        self.path = path or queue_path()
        self.items = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = [Item(**d) for d in data if isinstance(d, dict) and d.get("text")]
        except (OSError, ValueError, TypeError):
            self.items = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([asdict(i) for i in self.items], f, ensure_ascii=False, indent=2)

    def add(self, item):
        self.items.append(item)
        self.save()
        return len(self.items)

    def remove(self, index):
        item = self.items.pop(index)
        self.save()
        return item

    def move(self, index, delta):
        target = index + delta
        if not (0 <= index < len(self.items) and 0 <= target < len(self.items)):
            return index
        self.items[index], self.items[target] = self.items[target], self.items[index]
        self.save()
        return target

    def edit(self, index, text):
        self.items[index].text = text
        self.save()

    def bind_session(self, group, session_id):
        """A primeira mensagem de uma sessão nova criou a sessão: as seguintes
        do mesmo grupo vão para ela."""
        changed = False
        for item in self.items:
            if item.group == group and item.session_id is None:
                item.session_id = session_id
                changed = True
        if changed:
            self.save()

    def __len__(self):
        return len(self.items)

    def first(self):
        return self.items[0] if self.items else None


def due_at(limited_until):
    """Momento (timestamp) a partir do qual a fila pode sair; None se não há limite."""
    if not limited_until:
        return None
    return limited_until + MARGIN_SECONDS


def is_due(limited_until, now=None):
    now = now if now is not None else datetime.datetime.now().timestamp()
    when = due_at(limited_until)
    return when is None or now >= when


def when_text(limited_until, now=None):
    """'hoje às 17:11', 'amanhã às 9:01' ou '7/11 às 17:11'."""
    when = due_at(limited_until)
    if when is None:
        return "quando o Claude ficar livre"
    now = datetime.datetime.fromtimestamp(now if now is not None else datetime.datetime.now().timestamp())
    dt = datetime.datetime.fromtimestamp(when)
    hour = f"{dt.hour}:{dt.minute:02d}"
    if dt.date() == now.date():
        return "hoje às " + hour
    if dt.date() == now.date() + datetime.timedelta(days=1):
        return "amanhã às " + hour
    return f"{dt.day}/{dt.month} às {hour}"


def keep_awake(on):
    """Impede o Windows de dormir enquanto há fila esperando. Vale para a
    thread que chamar; o app chama sempre da thread da janela."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass
