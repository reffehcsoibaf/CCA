import wave

import feedback


def test_sounds_are_generated(tmp_path):
    feedback.ensure_sounds(str(tmp_path))
    for name in ("atencao", "pronto", "erro"):
        with wave.open(str(tmp_path / f"{name}.wav")) as w:
            assert w.getnframes() > 1000


def test_speaker_without_nvda_is_silent(monkeypatch):
    s = feedback.Speaker()
    s._nvda = None
    assert not s.available()
    s.speak("nada")  # não pode falhar
