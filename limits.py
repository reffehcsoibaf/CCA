"""Limites de uso do Claude (5 horas, semanal...). O Claude Code informa cada
janela por separado; aqui elas são comparadas para avisar só da que está mais
perto de acabar. Nada aqui depende de wx."""

import datetime

WINDOW_NAMES = {
    "five_hour": "limite de 5 horas",
    "seven_day": "limite semanal",
    "seven_day_opus": "limite semanal do Opus",
    "seven_day_sonnet": "limite semanal do Sonnet",
    "overage": "uso extra",
}


WARN_FROM = 0.75    # primeiro aviso
WARN_AGAIN = 0.90   # segundo aviso


def window_name(kind):
    return WINDOW_NAMES.get(kind, "limite de uso")


def when_text(timestamp, now=None):
    """'hoje às 17:10', 'amanhã às 9:00' ou '12/11 às 23:00'."""
    now = datetime.datetime.fromtimestamp(now if now is not None else datetime.datetime.now().timestamp())
    dt = datetime.datetime.fromtimestamp(timestamp)
    hour = f"{dt.hour}:{dt.minute:02d}"
    if dt.date() == now.date():
        return "hoje às " + hour
    if dt.date() == now.date() + datetime.timedelta(days=1):
        return "amanhã às " + hour
    return f"{dt.day}/{dt.month} às {hour}"


class LimitTracker:
    def __init__(self):
        self.windows = {}      # tipo -> dict(status, utilization, resets_at)
        self._announced = None

    def update(self, kind, status, utilization=None, resets_at=None):
        kind = kind or "unknown"
        self.windows[kind] = {"status": status, "utilization": utilization, "resets_at": resets_at}

    @staticmethod
    def _rank(window):
        if window["status"] == "rejected":
            return 2.0
        if window["utilization"] is not None:
            return window["utilization"]
        return 0.9 if window["status"] == "allowed_warning" else 0.0

    def closest(self):
        """(tipo, janela) da que está mais perto de acabar, ou None."""
        if not self.windows:
            return None
        return max(self.windows.items(), key=lambda pair: self._rank(pair[1]))

    def rejected_until(self):
        """Quando o limite volta, se alguma janela estiver esgotada: a última
        renovação entre as esgotadas. None se nenhuma."""
        times = [w["resets_at"] for w in self.windows.values() if w["status"] == "rejected"]
        if not times:
            return None
        return max((t for t in times if t), default=0) or None

    def is_rejected(self):
        return any(w["status"] == "rejected" for w in self.windows.values())

    def message(self, now=None):
        """Texto do aviso sobre a janela mais próxima do fim, ou None se ela
        não merece aviso ou se este mesmo aviso já foi dado. Só há aviso a
        partir de WARN_FROM de uso, e de novo ao passar de WARN_AGAIN; antes
        disso o app fica em silêncio."""
        top = self.closest()
        if top is None:
            return None
        kind, window = top
        pct = window["utilization"]
        if window["status"] == "rejected":
            level = "rejected"
        elif window["status"] == "allowed_warning" and pct is None:
            level = "flagged"      # o servidor avisou mas não disse quanto
        elif pct is not None and pct >= WARN_AGAIN:
            level = "high"
        elif pct is not None and pct >= WARN_FROM:
            level = "warn"
        else:
            self._announced = None  # abaixo do limite (ou renovou): o próximo cruzamento volta a avisar
            return None
        key = (kind, level)
        if key == self._announced:
            return None
        self._announced = key
        name = window_name(kind)
        when = f", renova {when_text(window['resets_at'], now)}" if window["resets_at"] else ""
        if window["status"] == "rejected":
            return (f"Limite atingido: {name}{when}. O que você enviar agora vai para a fila"
                    " e sai quando o limite renovar. Alt+F mostra a fila.")
        used = f", {round(pct * 100)}% usado" if pct is not None else ""
        return f"Atenção: perto do {name}{used}{when}."
