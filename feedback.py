"""Fala pelo NVDA ou pelo JAWS e sons de aviso. Tudo é opcional: se nenhum
leitor de telas estiver rodando ou a biblioteca faltar, as funções simplesmente não fazem nada."""

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
    "limite": [(262, 45)],  # início ou fim de uma lista, como no TeleZapp
}


class Speaker:
    """Fala pelo leitor de telas que estiver ativo: NVDA ou JAWS. A escolha é
    refeita a cada fala, porque ele pode trocar de leitor com o app aberto, e o
    JAWS só aceita a conexão depois de estar rodando."""

    _READERS = (("nvda", "NVDA"), ("jaws", "Jaws"))

    def __init__(self):
        self._nvda = None  # mantido por compatibilidade com os testes
        self._outputs = {}

    def _output(self, module, cls):
        if module in self._outputs:
            return self._outputs[module]
        out = None
        try:
            mod = __import__("accessible_output2.outputs." + module, fromlist=["output_class"])
            out = mod.output_class()
        except Exception:
            out = None  # leitor não instalado ou ainda fechado: tenta de novo depois
        if out is not None or module == "nvda":
            self._outputs[module] = out
        return out

    def _active(self):
        if self._nvda is not None:  # injetado por teste
            try:
                return self._nvda if self._nvda.is_active() else None
            except Exception:
                return None
        for module, cls in self._READERS:
            out = self._output(module, cls)
            try:
                if out is not None and out.is_active():
                    return out
            except Exception:
                self._outputs.pop(module, None)
        return None

    def available(self):
        return self._active() is not None

    def speak(self, text, interrupt=False):
        if not text:
            return
        out = self._active()
        if out is None:
            return
        try:
            out.speak(text, interrupt=interrupt)
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
