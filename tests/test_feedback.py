import wave

import feedback


def test_sounds_are_generated(tmp_path):
    feedback.ensure_sounds(str(tmp_path))
    for name in ("atencao", "pronto", "erro"):
        with wave.open(str(tmp_path / f"{name}.wav")) as w:
            assert w.getnframes() > 1000


def test_speaker_without_nvda_is_silent(monkeypatch):
    s = feedback.Speaker()
    monkeypatch.setattr(s, "_output", lambda module, cls: None)
    assert not s.available()
    s.speak("nada")  # não pode falhar


def test_speaker_uses_jaws_when_nvda_is_off(monkeypatch):
    class Fake:
        def __init__(self, active):
            self.active, self.said = active, []

        def is_active(self):
            return self.active

        def speak(self, text, interrupt=False):
            self.said.append(text)

    nvda, jaws = Fake(False), Fake(True)
    s = feedback.Speaker()
    monkeypatch.setattr(s, "_output", lambda module, cls: {"nvda": nvda, "jaws": jaws}[module])
    s.speak("Atenção: limite")
    assert jaws.said == ["Atenção: limite"] and not nvda.said
