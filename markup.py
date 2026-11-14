"""Formatação escrita no texto das mensagens (Markdown): **negrito**, *itálico*,
`código`, # títulos, - itens. O leitor de tela lê esses símbolos sem dizer o
que significam; aqui eles viram palavras ("negrito: texto"). Sem wx.

Só pares bem formados são tratados: o símbolo de abrir cola no texto e vem
depois de espaço, pontuação ou do começo; o de fechar também cola e vem antes
de espaço, pontuação ou do fim. Assim `2*3*4`, `nome_do_arquivo`, um `*` solto
e os endereços ficam como estão. O texto guardado e o que se copia não mudam:
isto só vale para o que se lê e se ouve. Portado do TeleZapp."""

import re

# trechos com mais palavras que isto dizem onde acabam ("fim do negrito")
WORDS_WITHOUT_END = 8

_BLOCK = re.compile(r"```(?:[A-Za-z0-9_+-]*\n)?(.*?)```", re.S)
_CODE = re.compile(r"`([^`\n]+)`")
# endereço: fica como está; o símbolo de fechar logo depois dele não entra
_URL = re.compile(r"(?:https?://|www\.)\S*[^\s*_~.,;:!?)\]]")
_FORMATS = (
    (re.compile(r"(?<![\w*])\*\*(?=[^\s*])([^\n]+?)(?<=[^\s*])\*\*(?![\w*])"), "negrito"),
    (re.compile(r"(?<![\w_])__(?=[^\s_])([^\n]+?)(?<=[^\s_])__(?![\w_])"), "negrito"),
    (re.compile(r"(?<![\w*])\*(?=[^\s*])([^\n*]+?)(?<=[^\s*])\*(?![\w*])"), "itálico"),
    (re.compile(r"(?<![\w_])_(?=[^\s_])([^\n_]+?)(?<=[^\s_])_(?![\w_])"), "itálico"),
    (re.compile(r"(?<![\w~])~~(?=[^\s~])([^\n]+?)(?<=[^\s~])~~(?![\w~])"), "tachado"),
    (re.compile(r"(?<![\w~])~(?=[^\s~])([^\n~]+?)(?<=[^\s~])~(?![\w~])"), "tachado"),
)
_TITLE = re.compile(r"^[ \t]*#{1,6}[ \t]+(?=\S)", re.M)
_ITEM = re.compile(r"^([ \t]*)[-*•][ \t]+(?=\S)", re.M)
# conta: 2*3 e 5 * 3 (só entre números); o leitor de tela diz "vezes"
_TIMES = re.compile(r"(?<=\d)[ \t]*\*[ \t]*(?=\d)")
_MARK = "\x00%d\x00"


def announce(text):
    """O texto com a formatação dita em palavras e os símbolos removidos."""
    if not text or not any(c in text for c in "*_~`#-•"):
        return text
    kept = []

    def keep(value):
        kept.append(value)
        return _MARK % (len(kept) - 1)

    # o código fica como está: o que parece formatação dentro dele não é
    text = _BLOCK.sub(lambda m: keep("código: " + m.group(1).strip("\n")), text)
    text = _CODE.sub(lambda m: keep("código: " + m.group(1)), text)
    text = _URL.sub(lambda m: keep(m.group(0)), text)
    text = _TITLE.sub("título: ", text)
    text = _ITEM.sub(lambda m: m.group(1) + "item: ", text)
    for pattern, name in _FORMATS:
        def swap(m, name=name):
            inside = m.group(1)
            end = f", fim do {name}" if len(inside.split()) > WORDS_WITHOUT_END else ""
            return f"{name}: {inside}{end}"
        text = pattern.sub(swap, text)
    text = _TIMES.sub(" vezes ", text)
    for i, part in enumerate(kept):
        text = text.replace(_MARK % i, part)
    return text
