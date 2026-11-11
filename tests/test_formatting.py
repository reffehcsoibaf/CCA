import formatting
from claude_agent_sdk import TextBlock, ToolUseBlock


def test_window_title():
    assert formatting.window_title("Respondendo", "Meu projeto") == "Respondendo - Meu projeto"
    assert formatting.window_title("Pronto", "") == f"Pronto - CCA {formatting.VERSION}"
    assert formatting.window_title("", "X") == "X"


def test_item_label_joins_lines_and_truncates():
    assert formatting.item_label("user", 1, "oi\n\ntudo bem?") == "Você, mensagem 1: oi tudo bem?"
    long = "a" * 5000
    label = formatting.item_label("assistant", 2, long)
    assert label.startswith("Claude, mensagem 2: ")
    assert len(label) == len("Claude, mensagem 2: ") + formatting.ITEM_MAX_CHARS + 1


def test_file_refs():
    refs = formatting.file_refs([r"C:\a b\x.txt", r"C:\y.py"])
    assert refs == '@"C:\\a b\\x.txt" @"C:\\y.py"'


def test_text_of_content_skips_tools_and_system_text():
    content = [
        {"type": "text", "text": "Vou ler."},
        {"type": "tool_use", "id": "1", "name": "Read", "input": {}},
        {"type": "text", "text": "Pronto."},
    ]
    assert formatting.text_of_content(content, "assistant") == "Vou ler.\n\nPronto."
    user = [{"type": "tool_result", "tool_use_id": "1", "content": "x"}]
    assert formatting.text_of_content(user, "user") == ""
    assert formatting.text_of_content("<system-reminder>x</system-reminder>", "user") == ""
    assert formatting.text_of_content([TextBlock("a"), ToolUseBlock("1", "Bash", {})], "assistant") == "a"


def test_group_transcript_merges_assistant_turn():
    entries = [
        {"type": "user", "message": {"content": "Corrija o bug"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Vou olhar."},
                                                      {"type": "tool_use", "id": "1", "name": "Read", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "1", "content": "..."}]}},
        {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "hmm"},
                                                      {"type": "text", "text": "Corrigido."}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "Obrigado"}]}},
    ]
    assert formatting.group_transcript(entries) == [
        ("user", "Corrija o bug"),
        ("assistant", "Vou olhar.\n\nCorrigido."),
        ("user", "Obrigado"),
    ]


def test_tool_action():
    assert formatting.tool_action("Read", {"file_path": r"C:\x\app.py"}) == "Lendo arquivo app.py"
    assert formatting.tool_action("Bash", {"command": "ls"}) == "Executando comando"
    assert formatting.tool_action("mcp__github__create_issue", {}) == "Usando conector create_issue"
    assert formatting.tool_action("Novo", {}) == "Usando Novo"


def test_permission_text():
    text = formatting.permission_text("Bash", {"command": "rm x", "description": "Apaga x"})
    assert text == "Claude quer executar o comando: rm x\nDescrição: Apaga x"
    assert formatting.permission_text("Write", {"file_path": "a.txt"}).endswith("a.txt")
    assert "ferramenta Foo" in formatting.permission_text("Foo", {"a": 1})


def test_question_text():
    q = {"question": "Qual formato?", "options": [{"label": "Curto", "description": "Resumo"},
                                                  {"label": "Longo"}], "multiSelect": True}
    text = formatting.question_text(q, 1, 2)
    assert text.splitlines()[0] == "Pergunta 1 de 2. Qual formato?"
    assert "Curto: Resumo" in text and "Longo" in text and "vírgula" in text


USAGE = """You are currently using your subscription to power your Claude Code usage

Current session: 82% used · resets Nov 3, 5:10pm (America/Sao_Paulo)
Current week (all models): 92% used · resets Nov 5, 11pm (America/Sao_Paulo)
Current week (Sonnet only): 40% used · resets 9am (America/Sao_Paulo)

What's contributing to your usage?
"""


def test_usage_summary():
    assert formatting.usage_summary(USAGE) == [
        "Sessão atual de 5 horas: 82% usado, renova 3 de nov às 17:10.",
        "Semana atual (todos os modelos): 92% usado, renova 5 de nov às 23:00.",
        "Semana atual (Sonnet): 40% usado, renova hoje às 9:00.",
    ]
    assert formatting.usage_summary("nada aqui") == []


def test_choice_label():
    assert formatting.choice_label(formatting.EFFORTS, "xhigh") == "Muito alto"
    assert formatting.choice_label(formatting.MODELS, "") == "Padrão da conta"
    assert formatting.choice_label(formatting.MODELS, "claude-x") == "claude-x"


def test_request_dialog_text():
    text = formatting.request_dialog_text("Claude quer ler o arquivo a.txt\n", ["Permitir", "Negar", "Outro"], "Outro")
    lines = text.split("\n")
    assert lines[0] == "Claude quer ler o arquivo a.txt"
    assert lines[1] == ""
    assert lines[2] == "Use Tab para chegar aos botões: Permitir, Negar, Outro."
    assert lines[3].startswith("Outro: fecha esta janela")
    assert "Alt+P" in lines[4]
    sem_outro = formatting.request_dialog_text("Pergunta?", ["Sim", "Não"], "Outro")
    assert "Outro:" not in sem_outro


def test_group_transcript_records_rewind_points():
    entries = [
        {"type": "user", "uuid": "u1", "message": {"content": "primeira"}},
        {"type": "assistant", "uuid": "a1", "message": {"content": [{"type": "text", "text": "resposta"}]}},
        {"type": "user", "uuid": "t1", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "mais"}]}},
        {"type": "user", "uuid": "u2", "message": {"content": "segunda"}},
    ]
    points = {}
    items = formatting.group_transcript(entries, points)
    assert [r for r, _ in items] == ["user", "assistant", "user"]
    # volta para antes da segunda = fica até a última entrada do turno anterior
    assert points == {0: None, 2: "a2"}


def test_queued_label():
    assert formatting.queued_label("hoje às 17:11", "faça\nisso") == "Você, agendada, sai hoje às 17:11: faça isso"


def test_group_transcript_attaches_written_files_to_answer():
    entries = [
        {"type": "user", "message": {"content": "crie"}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": r"C:\p\a.txt"}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": r"C:\p\b.txt"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": r"C:\p\a.txt"}}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Pronto."}]}},
        {"type": "user", "message": {"content": "obrigado"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "De nada."}]}},
    ]
    files = {}
    formatting.group_transcript(entries, files=files)
    assert files == {1: [r"C:\p\a.txt"]}


def test_item_label_note():
    assert formatting.item_label("assistant", 4, "veja", "2 links") == "Claude, mensagem 4, 2 links: veja"


def test_item_label_hides_markdown_link_targets():
    assert formatting.item_label("assistant", 2, "Mudei [app.py](src/app.py:3).") == "Claude, mensagem 2: Mudei app.py."


def test_model_choices_from_claude_code():
    models = [("", "Default (recommended)", "Opus 5.5 · Best for everyday, complex tasks"),
              ("sonnet", "Sonnet 5.5", "Most efficient"),
              ("claude-opus-4-8", "Opus 4.8", "Best for everyday")]
    assert formatting.model_choices(models) == [
        ("", "Padrão da conta (Opus 5.5)"), ("sonnet", "Sonnet 5.5"), ("claude-opus-4-8", "Opus 4.8, versão fixa")]
    assert formatting.model_choices([("haiku", "Haiku 5.5", "")])[0] == formatting.MODELS[0]


def test_tokens_and_compact_reminder():
    assert formatting.tokens_text(669_192) == "669 mil tokens"
    assert formatting.tokens_text(1_200_000) == "1,2 milhão de tokens"
    assert formatting.tokens_text(2_000_000) == "2 milhões de tokens"
    assert formatting.context_text(669_192, 67) == "A conversa está com 669 mil tokens, 67% do limite"
    remind = formatting.should_remind_compact
    assert not remind(150_000, 200_000, 0)
    assert remind(210_000, 200_000, 0)
    assert not remind(290_000, 200_000, 210_000)   # ainda não cresceu 100 mil
    assert remind(310_000, 200_000, 210_000)
    assert not remind(900_000, 0, 0)               # desligado


def test_context_details():
    text = formatting.context_details(669_192, 1_000_000, 67, 200_000)
    lines = text.split("\n")
    assert lines[0] == "A conversa está com 669 mil tokens, 67% do limite."
    assert lines[1] == "O limite desta conversa é de 1 milhão de tokens."
    assert "Ctrl+K" in text and "200 mil tokens" in text
    assert "desligado" in formatting.context_details(1000, 0, 1, 0)
