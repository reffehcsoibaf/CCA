"""Fala pelo NVDA e sons de aviso. Tudo é opcional: se o NVDA não estiver
rodando ou a biblioteca faltar, as funções simplesmente não fazem nada."""

import math
import os
import struct
import sys
import wave

SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sons")

# nome: lista de (frequência em Hz, duração em ms)
_TONES = {
    "atencao": [(660, 110), (0, 40), (880, 110), (0, 40), (1100, 160)],
    "pronto": [(784, 90), (0, 30), (523, 150)],
    "erro": [(330, 220), (0, 40), (262, 260)],
}


class Speaker:
    def __init__(self):
        self._nvda = None
        try:
            from accessible_output2.outputs.nvda import NVDA
            self._nvda = NVDA()
        except Exception:
            self._nvda = None

    def available(self):
        try:
            return bool(self._nvda and self._nvda.is_active())
        except Exception:
            return False

    def speak(self, text, interrupt=False):
        if not text or not self.available():
            return
        try:
            self._nvda.speak(text, interrupt=interrupt)
        except Exception:
            pass


def _write_tone(path, notes, rate=22050, volume=0.35):
    frames = bytearray()
    for freq, ms in notes:
        count = int(rate * ms / 1000)
        for i in range(count):
            if freq:
                # envelope curto nas pontas para não estalar
                env = min(1.0, i / (rate * 0.008), (count - i) / (rate * 0.012))
                value = volume * env * math.sin(2 * math.pi * freq * i / rate)
            else:
                value = 0.0
            frames += struct.pack("<h", int(value * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def ensure_sounds(directory=SOUNDS_DIR):
    os.makedirs(directory, exist_ok=True)
    for name, notes in _TONES.items():
        path = os.path.join(directory, name + ".wav")
        if not os.path.exists(path):
            _write_tone(path, notes)


def play(name, directory=SOUNDS_DIR):
    if sys.platform != "win32":
        return
    import winsound
    path = os.path.join(directory, name + ".wav")
    try:
        if not os.path.exists(path):
            ensure_sounds(directory)
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass
