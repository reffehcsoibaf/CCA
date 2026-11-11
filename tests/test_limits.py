import datetime

from limits import LimitTracker, window_name, when_text


def ts(*args):
    return datetime.datetime(*args).timestamp()


NOW = ts(2026, 11, 6, 20, 0)
FIVE = ts(2026, 11, 6, 23, 10)
WEEK = ts(2026, 11, 12, 23, 0)


def test_silent_below_75_percent():
    t = LimitTracker()
    t.update("seven_day", "allowed_warning", 0.25, WEEK)    # o servidor avisa, mas é só 25%
    assert t.message(NOW) is None
    t.update("five_hour", "allowed", 0.74, FIVE)
    assert t.message(NOW) is None


def test_two_warnings_only_not_one_per_percent():
    t = LimitTracker()
    said = []
    for pct in (0.74, 0.75, 0.76, 0.80, 0.89, 0.90, 0.93, 0.99):
        t.update("five_hour", "allowed_warning", pct, FIVE)
        said.append(t.message(NOW))
    assert [m is not None for m in said] == [False, True, False, False, False, True, False, False]
    assert said[1] == "Atenção: perto do limite de 5 horas, 75% usado, renova hoje às 23:10."
    assert "90% usado" in said[5]


def test_after_renewal_the_next_crossing_warns_again():
    t = LimitTracker()
    t.update("five_hour", "allowed_warning", 0.80, FIVE)
    assert t.message(NOW)
    t.update("five_hour", "allowed", 0.0, None)
    assert t.message(NOW) is None
    t.update("five_hour", "allowed_warning", 0.80, FIVE)
    assert t.message(NOW)


def test_only_the_closest_window_is_announced():
    t = LimitTracker()
    t.update("seven_day", "allowed_warning", 0.80, WEEK)
    assert "limite semanal" in t.message(NOW)
    t.update("five_hour", "allowed_warning", 0.93, FIVE)
    assert "limite de 5 horas" in t.message(NOW)
    t.update("seven_day", "allowed_warning", 0.82, WEEK)    # a semanal sobe, mas não é a mais próxima
    assert t.message(NOW) is None


def test_flagged_without_percentage_is_announced_once():
    t = LimitTracker()
    t.update("five_hour", "allowed_warning", None, FIVE)
    assert t.message(NOW) == "Atenção: perto do limite de 5 horas, renova hoje às 23:10."
    t.update("five_hour", "allowed_warning", None, FIVE)
    assert t.message(NOW) is None


def test_rejected_wins_and_reports_the_latest_reset():
    t = LimitTracker()
    t.update("five_hour", "rejected", 1.0, FIVE)
    t.update("seven_day", "allowed_warning", 0.95, WEEK)
    assert t.is_rejected() and t.rejected_until() == FIVE
    assert t.message(NOW).startswith("Limite atingido: limite de 5 horas, renova hoje às 23:10.")
    assert t.message(NOW) is None
    t.update("seven_day", "rejected", 1.0, WEEK)
    assert t.rejected_until() == WEEK
    t.update("five_hour", "allowed", 0.0, None)
    assert t.rejected_until() == WEEK                      # a semanal ainda segura
    t.update("seven_day", "allowed", 0.0, None)
    assert not t.is_rejected() and t.rejected_until() is None


def test_names_and_dates():
    assert window_name("seven_day_opus") == "limite semanal do Opus"
    assert window_name("nova_janela") == "limite de uso"
    assert when_text(ts(2026, 11, 7, 9, 5), NOW) == "amanhã às 9:05"
