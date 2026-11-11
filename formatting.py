"""Funções puras de texto: rótulos da lista, título da janela, descrições de
ferramentas e pedidos de permissão. Nada aqui depende de wx ou do SDK, para
poder ser testado sem rede."""

import datetime
import json
import os
import re

APP_NAME = "CCA"  # Claude Code Acessível
ITEM_MAX_CHARS = 4000

# (valor para o SDK, rótulo no menu). Valor vazio = padrão do Claude Code.
PERMISSION_MODES = [
    ("default", "Perguntar antes de agir (padrão)"),
    ("acceptEdits", "Aceitar edições de arquivo sem perguntar"),
    ("auto", "Automático: o Claude só pergunta o que for arriscado"),
    ("bypassPermissions", "Permitir tudo sem perguntar (cuidado)"),
    ("plan", "Modo plano: só planeja, não executa"),
]
MODELS = [
    ("", "Padrão da conta"),
    ("opus", "Opus"),
    ("sonnet", "Sonnet"),
    ("haiku", "Haiku"),
]
EFFORTS = [
    ("", "Padrão"),
    ("low", "Baixo"),
    ("medium", "Médio"),
    ("high", "Alto"),
    ("xhigh", "Muito alto"),
    ("max", "Máximo"),
]


# Lembrete de compactar: (tokens, rótulo). 0 desliga.
COMPACT_REMINDERS = [
    (0, "Nunca"),
    (100_000, "100 mil tokens"),
    (200_000, "200 mil tokens"),
    (300_000, "300 mil tokens"),
    (500_000, "500 mil tokens"),
]
COMPACT_REMINDER_STEP = 100_000   # depois do primeiro, lembra de novo a cada tanto a mais


def tokens_text(tokens):
    """'669 mil tokens', '1,2 milhão de tokens', '850 tokens'."""
    if tokens >= 1_000_000:
        value = f"{tokens / 1_000_000:.1f}".replace(".", ",").replace(",0", "")
        return f"{value} {'milhão' if tokens < 2_000_000 else 'milhões'} de tokens"
    if tokens >= 1000:
        return f"{round(tokens / 1000)} mil tokens"
    return f"{tokens} tokens"


def context_text(tokens, percentage):
    return f"A conversa está com {tokens_text(tokens)}, {round(percentage)}% do limite"


def context_details(tokens, max_tokens, percentage, threshold=0):
    """Texto da janela Tamanho da conversa."""
    lines = [context_text(tokens, percentage) + "."]
    if max_tokens:
        lines.append(f"O limite desta conversa é de {tokens_text(max_tokens)}.")
    lines.append("Cada mensagem que você envia faz o Claude reler tudo isso; por isso uma conversa grande"
                 " gasta mais do seu limite de uso. Ctrl+K compacta a conversa e deixa as próximas mais baratas.")
    if threshold:
        lines.append(f"Você é lembrado de compactar quando passar de {tokens_text(threshold)}.")
    else:
        lines.append("O lembrete de compactar está desligado em Configurações.")
    lines.append("O tamanho é medido ao fim de cada resposta.")
    return "\n".join(lines)


def should_remind_compact(tokens, threshold, last_reminded):
    """Lembra ao passar do limite e de novo a cada COMPACT_REMINDER_STEP a mais."""
    if not threshold or tokens < threshold:
        return False
    return not last_reminded or tokens >= last_reminded + COMPACT_REMINDER_STEP


def model_choices(models):
    """(valor, rótulo) para o menu, a partir do que o Claude Code informa.
    Apelidos como "sonnet" sempre levam ao modelo mais novo da família; os
    nomes completos ficam presos a uma versão."""
    choices = []
    for value, name, description in models:
        if value == "":
            current = description.split("·")[0].strip()
            choices.append(("", f"Padrão da conta ({current})" if current else MODELS[0][1]))
        elif value.startswith("claude-"):
            choices.append((value, f"{name}, versão fixa"))
        else:
            choices.append((value, name))
    if not any(v == "" for v, _ in choices):
        choices.insert(0, MODELS[0])
    return choices


def choice_label(choices, value):
    for v, label in choices:
        if v == value:
            return label
    return value or choices[0][1]


_MONTHS = {"Jan": "jan", "Feb": "fev", "Mar": "mar", "Apr": "abr", "May": "mai", "Jun": "jun",
           "Jul": "jul", "Aug": "ago", "Sep": "set", "Oct": "out", "Nov": "nov", "Dec": "dez"}


def _reset_pt(text):
    """'Nov 3, 5:10pm (America/Sao_Paulo)' -> '3 de nov às 17:10'."""
    text = re.sub(r"\s*\(.*?\)\s*$", "", text.strip())
    m = re.match(r"(?:([A-Z][a-z]{2}) (\d{1,2}), )?(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
    if not m:
        return text
    month, day, hour, minute, ampm = m.groups()
    hour = int(hour) % 12 + (12 if ampm == "pm" else 0)
    when = f"{hour}:{minute or '00'}"
    if month:
        return f"{day} de {_MONTHS.get(month, month)} às {when}"
    return "hoje às " + when


_MONTH_NUMBERS = {m: i for i, m in enumerate(_MONTHS, 1)}


def reset_timestamp(text, now):
    """Horário de renovação numa mensagem de erro do Claude Code, como
    "You've hit your 5-hour limit · resets 5:10pm (America/Sao_Paulo)" ou
    "resets Nov 7, 5:10pm". Devolve timestamp ou None. Um horário que já
    passou hoje é de amanhã."""
    m = re.search(r"resets\s+(?:([A-Z][a-z]{2}) (\d{1,2}), )?(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
                  text or "", re.IGNORECASE)
    if not m:
        return None
    month, day, hour, minute, ampm = m.groups()
    hour = int(hour) % 12 + (12 if ampm.lower() == "pm" else 0)
    base = datetime.datetime.fromtimestamp(now)
    try:
        if month:
            when = base.replace(month=_MONTH_NUMBERS[month.capitalize()], day=int(day), hour=hour,
                                minute=int(minute or 0), second=0, microsecond=0)
            if when < base - datetime.timedelta(days=1):
                when = when.replace(year=when.year + 1)
        else:
            when = base.replace(hour=hour, minute=int(minute or 0), second=0, microsecond=0)
            if when < base:
                when += datetime.timedelta(days=1)
    except (KeyError, ValueError):
        return None
    return when.timestamp()


def _limit_label(label):
    label = label.replace("Current session", "Sessão atual de 5 horas")
    label = label.replace("Current week", "Semana atual")
    label = label.replace("(all models)", "(todos os modelos)")
    label = label.replace(" only)", ")")
    return label


def usage_summary(text):
    """Resume a saída do comando /usage em frases em português.
    Devolve [] se não reconhecer nada."""
    lines = []
    for raw in text.splitlines():
        m = re.match(r"\s*(Current [^:]+):\s*(\d+)% used(?:\s*\W\s*resets (.+))?", raw)
        if m:
            label, pct, reset = m.groups()
            sentence = f"{_limit_label(label)}: {pct}% usado"
            if reset:
                sentence += ", renova " + _reset_pt(reset)
            lines.append(sentence + ".")
    return lines

# Prefixos de texto que o Claude Code grava como mensagem de usuário mas que
# não foram digitados pela pessoa.
_HIDDEN_USER_PREFIXES = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<task-notification>",
    "Caveat: The messages below were generated",
    "[Request interrupted by user",
)


def window_title(state, session_title):
    title = session_title or APP_NAME
    return f"{state} - {title}" if state else title


def one_line(text):
    return " ".join(text.split())


def item_label(role, number, text, note=""):
    """'Claude, mensagem 4, 2 links: texto'. A nota vem antes do texto para o
    NVDA falar logo, sem ler a mensagem inteira."""
    who = "Você" if role == "user" else "Claude"
    # [app.py](src/app.py:3) vira só app.py: o endereço fica na janela de links.
    body = one_line(re.sub(r"\[([^\]\n]+)\]\([^)\s]+\)", r"\1", text))
    if len(body) > ITEM_MAX_CHARS:
        body = body[:ITEM_MAX_CHARS] + "…"
    note = f", {note}" if note else ""
    return f"{who}, mensagem {number}{note}: {body}"


def queued_label(when, text):
    body = one_line(text)
    if len(body) > ITEM_MAX_CHARS:
        body = body[:ITEM_MAX_CHARS] + "…"
    return f"Você, agendada, sai {when}: {body}"


def file_refs(paths):
    return " ".join(f'@"{p}"' for p in paths)


def _block_get(block, key):
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def _block_type(block):
    if isinstance(block, dict):
        return block.get("type")
    name = type(block).__name__
    return {"TextBlock": "text", "ToolUseBlock": "tool_use",
            "ToolResultBlock": "tool_result", "ThinkingBlock": "thinking"}.get(name, name)


def text_of_content(content, role):
    """Junta só os blocos de texto. Uso de ferramenta, resultados e raciocínio
    ficam de fora. Para mensagens do usuário, descarta textos gerados pelo
    sistema."""
    if content is None:
        return ""
    if isinstance(content, str):
        blocks = [{"type": "text", "text": content}]
    else:
        blocks = content
    parts = []
    for block in blocks:
        if _block_type(block) != "text":
            continue
        text = (_block_get(block, "text") or "").strip()
        if not text:
            continue
        if role == "user" and text.startswith(_HIDDEN_USER_PREFIXES):
            continue
        parts.append(text)
    return "\n\n".join(parts)


# Ferramentas que criam ou mudam arquivos: o arquivo acompanha a resposta.
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def tool_file(name, tool_input):
    if name not in FILE_TOOLS:
        return None
    tool_input = tool_input or {}
    return tool_input.get("file_path") or tool_input.get("notebook_path") or None


def _tool_files(content):
    found = []
    if isinstance(content, list):
        for block in content:
            if _block_type(block) == "tool_use":
                path = tool_file(_block_get(block, "name"), _block_get(block, "input"))
                if path and path not in found:
                    found.append(path)
    return found


def group_transcript(entries, points=None, files=None):
    """Transforma a transcrição (lista de dicts com 'type' e 'message') em
    itens da conversa [(papel, texto)]. Textos do Claude entre duas mensagens
    da pessoa viram um único item, como na janela do aplicativo.

    Com `points` (um dict), guarda para cada mensagem da pessoa o 'uuid' da
    entrada anterior a ela: é o ponto para onde a conversa volta quando a
    mensagem é editada ou removida (None se for a primeira).

    Com `files` (um dict), guarda para cada resposta do Claude os arquivos
    que ele criou ou editou nela."""
    items = []
    previous = None
    turn_files = []
    for entry in entries:
        role = entry.get("type")
        message = entry.get("message") or {}
        if role == "assistant":
            turn_files += [p for p in _tool_files(message.get("content")) if p not in turn_files]
        text = text_of_content(message.get("content"), role)
        before, previous = previous, entry.get("uuid") or previous
        if not text:
            continue
        if role == "user":
            turn_files = []
            if points is not None:
                points[len(items)] = before
        if role == "assistant" and items and items[-1][0] == "assistant":
            items[-1] = ("assistant", items[-1][1] + "\n\n" + text)
        else:
            items.append((role, text))
        if role == "assistant" and files is not None and turn_files:
            files[len(items) - 1] = turn_files
    return items


def _short_path(path):
    if not path:
        return ""
    return os.path.basename(str(path).rstrip("\\/")) or str(path)


def tool_action(name, tool_input):
    """Nome curto da ação, para o título da janela enquanto a ferramenta roda."""
    tool_input = tool_input or {}
    path = _short_path(tool_input.get("file_path") or tool_input.get("notebook_path")
                       or tool_input.get("path"))
    actions = {
        "Read": "Lendo arquivo",
        "Write": "Criando arquivo",
        "Edit": "Editando arquivo",
        "MultiEdit": "Editando arquivo",
        "NotebookEdit": "Editando notebook",
        "Bash": "Executando comando",
        "PowerShell": "Executando comando",
        "Glob": "Procurando arquivos",
        "Grep": "Procurando no código",
        "WebFetch": "Lendo página da web",
        "WebSearch": "Pesquisando na web",
        "Task": "Delegando a um subagente",
        "Agent": "Delegando a um subagente",
        "TodoWrite": "Atualizando lista de tarefas",
        "Skill": "Usando habilidade",
    }
    label = actions.get(name)
    if label is None:
        if name.startswith("mcp__"):
            return "Usando conector " + name.split("__")[-1]
        return "Usando " + name
    if name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit") and path:
        return f"{label} {path}"
    if name == "Skill" and tool_input.get("skill"):
        return f"{label} {tool_input['skill']}"
    return label


def permission_text(name, tool_input):
    """Frase para o campo Pergunta do Claude."""
    tool_input = tool_input or {}
    if name in ("Bash", "PowerShell"):
        text = "Claude quer executar o comando: " + str(tool_input.get("command", ""))
        if tool_input.get("description"):
            text += "\nDescrição: " + str(tool_input["description"])
        return text
    if name == "Write":
        return "Claude quer criar ou substituir o arquivo " + str(tool_input.get("file_path", ""))
    if name in ("Edit", "MultiEdit"):
        text = "Claude quer editar o arquivo " + str(tool_input.get("file_path", ""))
        if tool_input.get("old_string") is not None:
            text += "\nTrecho atual: " + str(tool_input["old_string"])
            text += "\nNovo trecho: " + str(tool_input.get("new_string", ""))
        return text
    if name == "Read":
        return "Claude quer ler o arquivo " + str(tool_input.get("file_path", ""))
    if name == "WebFetch":
        return "Claude quer abrir a página " + str(tool_input.get("url", ""))
    if name == "WebSearch":
        return "Claude quer pesquisar na web: " + str(tool_input.get("query", ""))
    if name == "ExitPlanMode":
        return "Claude terminou o plano e quer começar a executar.\n" + str(tool_input.get("plan", ""))
    detail = json.dumps(tool_input, ensure_ascii=False)
    if len(detail) > 1500:
        detail = detail[:1500] + "…"
    return f"Claude quer usar a ferramenta {name}: {detail}"


def question_text(question, index, total):
    """Texto de uma pergunta do AskUserQuestion, com a descrição de cada opção."""
    lines = []
    prefix = f"Pergunta {index} de {total}. " if total > 1 else ""
    lines.append(prefix + str(question.get("question", "")))
    if question.get("multiSelect"):
        lines.append("Pode escolher mais de uma: use Outro e digite as opções separadas por vírgula.")
    for opt in question.get("options", []):
        desc = opt.get("description")
        lines.append(f"{opt.get('label', '')}: {desc}" if desc else str(opt.get("label", "")))
    return "\n".join(lines)


def request_dialog_text(text, options, other=None):
    """Texto da janela de pergunta ou permissão: a pergunta e, no fim, como
    chegar aos botões, no estilo da janela de versão nova do TeleZapp."""
    lines = [text.rstrip(), ""]
    lines.append("Use Tab para chegar aos botões: " + ", ".join(options) + ".")
    if other and other in options:
        lines.append(f"{other}: fecha esta janela e leva à caixa de mensagem para você escrever a resposta.")
    lines.append("Escape fecha a janela sem responder; Alt+P na janela principal reabre a pergunta.")
    return "\n".join(lines)
