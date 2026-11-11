"""Verificação manual (não roda no pytest): com pythonw, envia uma mensagem
real e conta janelas de console visíveis antes e durante a conversa.
Grava o resultado em console_check.txt ao lado deste arquivo."""

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
if "--sem-correcao" in sys.argv:  # para provar que a verificação pega o problema
    import anyio
    anyio.open_process._sem_janela = True
import worker  # noqa: E402

user32 = ctypes.windll.user32


def child_pids():
    import subprocess
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={os.getpid()}').ProcessId"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    return {int(x) for x in out.split()}


def visible_consoles():
    """Janelas de console de processos filhos deste. Com o Windows Terminal
    como terminal padrão, o filho ganha uma PseudoConsoleWindow visível (vira
    uma aba, não uma janela nova), então contar janelas não basta."""
    kids = child_pids()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (cls.value in ("ConsoleWindowClass", "PseudoConsoleWindow") and pid.value in kids
                and user32.IsWindowVisible(hwnd)):
            found.append(f"{cls.value} do processo {pid.value}")
        return True

    user32.EnumWindows(cb, 0)
    return found


lines = []
done = threading.Event()
before = visible_consoles()
peak = []


def emit(name, **data):
    if name == "assistant_text":
        lines.append("texto: " + data["text"][:80])
    if name in ("done", "error"):
        lines.append(f"{name}: {data}")
        done.set()


w = worker.AgentWorker(emit)
w.start_session(None, HERE).result(10)
w.send("Responda só: ok").result(30)
end = time.time() + 90
while not done.is_set() and time.time() < end:
    now = visible_consoles()
    if len(now) > len(peak):
        peak = now
    time.sleep(0.2)
w.close()
new = [t for t in peak if t not in before]
with open(os.path.join(HERE, "console_check.txt"), "w", encoding="utf-8") as f:
    f.write(f"consoles antes: {len(before)}\nnovos consoles durante a conversa: {new}\n")
    f.write("\n".join(lines) + "\n")
