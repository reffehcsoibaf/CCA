import datetime

import formatting
import scheduled
from scheduled import Item, Queue


def ts(*args):
    return datetime.datetime(*args).timestamp()


def item(text, sid="s1", group=None):
    return Item(text, sid, r"C:\proj", "Título", group=group or (sid or "g"))


def test_queue_persists_and_reorders(tmp_path):
    path = tmp_path / "fila.json"
    q = Queue(str(path))
    q.add(item("um"))
    q.add(item("dois"))
    q.add(item("três"))
    assert q.move(2, -1) == 1
    assert q.move(0, -1) == 0  # já é o primeiro
    q.edit(0, "um editado")
    q.remove(2)
    again = Queue(str(path))
    assert [i.text for i in again.items] == ["um editado", "três"]
    assert again.first().text == "um editado"


def test_queue_ignores_broken_file(tmp_path):
    path = tmp_path / "fila.json"
    path.write_text("não é json", encoding="utf-8")
    assert len(Queue(str(path))) == 0


def test_bind_session_only_touches_its_group(tmp_path):
    q = Queue(str(tmp_path / "fila.json"))
    q.add(item("a", sid=None, group="nova"))
    q.add(item("b", sid=None, group="outra"))
    q.bind_session("nova", "sess-9")
    assert [i.session_id for i in Queue(q.path).items] == ["sess-9", None]


def test_due_waits_margin_after_reset():
    reset = ts(2026, 11, 6, 17, 10)
    assert scheduled.is_due(None)
    assert not scheduled.is_due(reset, now=reset + 30)
    assert scheduled.is_due(reset, now=reset + scheduled.MARGIN_SECONDS)


def test_when_text():
    now = ts(2026, 11, 6, 13, 0)
    assert scheduled.when_text(None, now) == "quando o Claude ficar livre"
    assert scheduled.when_text(ts(2026, 11, 6, 17, 10), now) == "hoje às 17:11"
    assert scheduled.when_text(ts(2026, 11, 7, 9, 0), now) == "amanhã às 9:01"
    assert scheduled.when_text(ts(2026, 11, 10, 9, 0), now) == "10/11 às 9:01"


def test_item_label():
    assert item("faça\nisso").label(2) == "2: faça isso. Sessão Título"


def test_reset_timestamp_from_error():
    now = ts(2026, 11, 6, 12, 58)
    text = "You've hit your 5-hour limit · resets 5:10pm (America/Sao_Paulo)"
    assert formatting.reset_timestamp(text, now) == ts(2026, 11, 6, 17, 10)
    # horário que já passou hoje é de amanhã
    assert formatting.reset_timestamp("resets 9am", now) == ts(2026, 11, 7, 9, 0)
    assert formatting.reset_timestamp("resets Nov 10, 5:10pm", now) == ts(2026, 11, 10, 17, 10)
    assert formatting.reset_timestamp("resets Jan 2, 1am", now) == ts(2027, 1, 2, 1, 0)
    assert formatting.reset_timestamp("Erro qualquer", now) is None
