"""Testa o worker com um cliente falso no lugar do ClaudeSDKClient, sem rede."""

import asyncio
import threading
import time

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    StreamEvent,
    ToolPermissionContext,
)

from worker import AgentWorker, Answer


class Recorder:
    def __init__(self):
        self.events = []
        self.cond = threading.Condition()

    def __call__(self, name, **data):
        with self.cond:
            self.events.append((name, data))
            self.cond.notify_all()

    def wait(self, name, count=1, timeout=5):
        deadline = time.time() + timeout
        with self.cond:
            while True:
                found = [d for n, d in self.events if n == name]
                if len(found) >= count:
                    return found[count - 1]
                left = deadline - time.time()
                if left <= 0:
                    raise AssertionError(f"evento {name} não chegou: {self.events}")
                self.cond.wait(left)

    def names(self):
        return [n for n, _ in self.events]


def result(sid="sess-1", **kw):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                         num_turns=1, session_id=sid, **kw)


def delta(text):
    return StreamEvent(uuid="u", session_id="sess-1",
                       event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


class FakeClient:
    """Imita o ClaudeSDKClient. `script(client, prompt)` roda como tarefa e
    empurra mensagens com `client.push`."""
    instances = []

    def __init__(self, options):
        self.options = options
        self.queries = []
        self.queue = asyncio.Queue()
        self.interrupted = False
        self.disconnected = False
        FakeClient.instances.append(self)

    async def connect(self):
        pass

    async def query(self, prompt):
        self.queries.append(prompt)
        asyncio.create_task(FakeClient.script(self, prompt))

    def push(self, message):
        self.queue.put_nowait(message)

    async def receive_messages(self):
        while True:
            message = await self.queue.get()
            if message is None:
                return
            yield message

    async def get_context_usage(self):
        return {"totalTokens": 250_000, "maxTokens": 1_000_000, "percentage": 25}

    async def interrupt(self):
        self.interrupted = True

    async def disconnect(self):
        self.disconnected = True
        self.queue.put_nowait(None)
        await asyncio.sleep(0.05)  # o processo real demora para fechar


@pytest.fixture
def setup():
    FakeClient.instances = []
    rec = Recorder()
    worker = AgentWorker(rec, client_factory=FakeClient)
    yield worker, rec
    worker.close()


def test_streams_text_and_finishes(setup):
    worker, rec = setup

    async def script(client, prompt):
        client.push(SystemMessage("init", {"session_id": "sess-1"}))
        client.push(delta("Olá"))
        client.push(delta(", mundo"))
        client.push(AssistantMessage([TextBlock("Olá, mundo")], model="m"))
        client.push(AssistantMessage([ToolUseBlock("t1", "Read", {"file_path": r"C:\a\x.py"})], model="m"))
        client.push(AssistantMessage([TextBlock("Li o arquivo.")], model="m"))
        client.push(result(total_cost_usd=0.01))

    FakeClient.script = script
    worker.start_session(None, r"C:\proj").result(5)
    worker.send("oi").result(5)
    done = rec.wait("done")
    assert done["error"] is None and done["session_id"] == "sess-1"
    texts = [d["text"] for n, d in rec.events if n == "assistant_text"]
    assert texts[0] == "Olá"
    assert texts[-1] == "Olá, mundo\n\nLi o arquivo."
    assert {"state": "Lendo arquivo x.py"} in [d for n, d in rec.events if n == "busy"]
    client = FakeClient.instances[0]
    assert client.queries == ["oi"]
    assert client.options.cwd == r"C:\proj" and client.options.resume is None
    assert client.options.include_partial_messages is True
    assert client.options.system_prompt == {"type": "preset", "preset": "claude_code"}
    assert worker.session_id == "sess-1"


def test_permission_allow_reaches_sdk(setup):
    worker, rec = setup
    decisions = []

    async def script(client, prompt):
        ctx = ToolPermissionContext(suggestions=[])
        decisions.append(await client.options.can_use_tool("Bash", {"command": "dir"}, ctx))
        client.push(result())

    FakeClient.script = script
    worker.send("liste").result(5)
    request = rec.wait("request")["request"]
    assert request.kind == "permission"
    assert request.options == ["Permitir", "Negar", "Outro"]
    assert "dir" in request.text
    worker.answer(Answer(index=0))
    rec.wait("done")
    assert isinstance(decisions[0], PermissionResultAllow)
    assert decisions[0].updated_input == {"command": "dir"}
    assert "request_closed" in rec.names()


def test_permission_free_text_denies_with_message(setup):
    worker, rec = setup
    decisions = []

    async def script(client, prompt):
        ctx = ToolPermissionContext(suggestions=["regra"])
        decisions.append(await client.options.can_use_tool("Write", {"file_path": "a"}, ctx))
        client.push(result())

    FakeClient.script = script
    worker.send("crie").result(5)
    request = rec.wait("request")["request"]
    assert request.options == ["Permitir", "Permitir sempre", "Negar", "Outro"]
    worker.answer(Answer(text="use outro nome"))
    rec.wait("done")
    assert isinstance(decisions[0], PermissionResultDeny)
    assert "use outro nome" in decisions[0].message


def test_permission_always_passes_suggestions(setup):
    worker, rec = setup
    decisions = []

    async def script(client, prompt):
        ctx = ToolPermissionContext(suggestions=["regra"])
        decisions.append(await client.options.can_use_tool("Write", {"file_path": "a"}, ctx))
        client.push(result())

    FakeClient.script = script
    worker.send("crie").result(5)
    rec.wait("request")
    worker.answer(Answer(index=1))
    rec.wait("done")
    assert decisions[0].updated_permissions == ["regra"]


def test_ask_user_question_collects_answers(setup):
    worker, rec = setup
    decisions = []
    questions = [
        {"question": "Formato?", "header": "F", "multiSelect": False,
         "options": [{"label": "Curto", "description": ""}, {"label": "Longo", "description": ""}]},
        {"question": "Idioma?", "header": "I", "multiSelect": False,
         "options": [{"label": "PT", "description": ""}, {"label": "EN", "description": ""}]},
    ]

    async def script(client, prompt):
        decisions.append(await client.options.can_use_tool(
            "AskUserQuestion", {"questions": questions}, ToolPermissionContext()))
        client.push(result())

    FakeClient.script = script
    worker.send("pergunte").result(5)
    first = rec.wait("request", 1)["request"]
    assert first.kind == "question" and first.options == ["Curto", "Longo", "Outro"]
    worker.answer(Answer(index=1))
    rec.wait("request", 2)
    worker.answer(Answer(text="espanhol"))
    rec.wait("done")
    assert decisions[0].updated_input == {"questions": questions,
                                          "answers": {"Formato?": "Longo", "Idioma?": "espanhol"}}


def test_resume_and_interrupt(setup):
    worker, rec = setup
    decisions = []

    async def script(client, prompt):
        decisions.append(await client.options.can_use_tool("Bash", {"command": "x"}, ToolPermissionContext()))
        client.push(result(sid="old-session"))

    FakeClient.script = script
    worker.start_session("old-session", r"C:\outro").result(5)
    worker.send("continue").result(5)
    rec.wait("request")
    worker.interrupt().result(5)
    rec.wait("done")
    client = FakeClient.instances[0]
    assert client.options.resume == "old-session" and client.options.cwd == r"C:\outro"
    assert client.interrupted
    assert isinstance(decisions[0], PermissionResultDeny) and decisions[0].interrupt


def test_auth_error_is_reported(setup):
    worker, rec = setup

    async def script(client, prompt):
        client.push(AssistantMessage([TextBlock("Not logged in")], model="m", error="authentication_failed"))
        client.push(ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=True,
                                  num_turns=1, session_id="s", result="Not logged in · Please run /login"))

    FakeClient.script = script
    worker.send("oi").result(5)
    done = rec.wait("done")
    assert "Entrar na conta Claude" in done["error"]
    assert "Entrar na conta Claude" in rec.wait("error")["text"]


def test_last_session_choice_wins(setup):
    """Nova sessão seguida logo de retomar outra: a retomada não pode se perder."""
    worker, rec = setup

    async def script(client, prompt):
        client.push(result(sid=client.options.resume or "nova"))

    FakeClient.script = script
    worker.send("um").result(5)
    rec.wait("done")
    worker.start_session(None, r"C:\a")
    worker.start_session("antiga", r"C:\b")
    worker.send("dois").result(5)
    rec.wait("done", 2)
    assert FakeClient.instances[-1].options.resume == "antiga"
    assert FakeClient.instances[-1].options.cwd == r"C:\b"


def test_new_session_disconnects_previous_client(setup):
    worker, rec = setup

    async def script(client, prompt):
        client.push(result())

    FakeClient.script = script
    worker.send("um").result(5)
    rec.wait("done")
    worker.start_session(None, r"C:\novo").result(5)
    assert FakeClient.instances[0].disconnected
    worker.send("dois").result(5)
    rec.wait("done", 2)
    assert len(FakeClient.instances) == 2
    assert FakeClient.instances[1].options.resume is None


def _add_setters():
    async def set_permission_mode(self, mode):
        self.modes = getattr(self, "modes", []) + [mode]

    async def set_model(self, model):
        self.models = getattr(self, "models", []) + [model]

    FakeClient.set_permission_mode = set_permission_mode
    FakeClient.set_model = set_model


def test_options_carry_mode_model_effort():
    FakeClient.instances = []
    rec = Recorder()
    w = AgentWorker(rec, client_factory=FakeClient, permission_mode="acceptEdits", model="sonnet", effort="high")
    try:
        async def script(client, prompt):
            client.push(result())
        FakeClient.script = script
        w.send("oi").result(5)
        rec.wait("done")
        opts = FakeClient.instances[0].options
        assert (opts.permission_mode, opts.model, opts.effort) == ("acceptEdits", "sonnet", "high")
    finally:
        w.close()


def test_mode_and_model_change_live(setup):
    worker, rec = setup
    _add_setters()

    async def script(client, prompt):
        client.push(result())

    FakeClient.script = script
    worker.send("oi").result(5)
    rec.wait("done")
    worker.set_permission_mode("auto").result(5)
    worker.set_model("opus").result(5)
    client = FakeClient.instances[0]
    assert client.modes == ["auto"] and client.models == ["opus"]
    assert not client.disconnected


def test_bypass_answers_open_permission(setup):
    worker, rec = setup
    _add_setters()
    decisions = []

    async def script(client, prompt):
        decisions.append(await client.options.can_use_tool("Bash", {"command": "x"}, ToolPermissionContext()))
        client.push(result())

    FakeClient.script = script
    worker.send("oi").result(5)
    rec.wait("request")
    worker.set_permission_mode("bypassPermissions").result(5)
    rec.wait("done")
    assert isinstance(decisions[0], PermissionResultAllow)


def test_effort_restarts_after_turn_keeping_session(setup):
    worker, rec = setup

    async def script(client, prompt):
        if prompt == "longo":
            await asyncio.sleep(0.3)
        client.push(result(sid="s-1"))

    FakeClient.script = script
    worker.send("longo").result(5)
    worker.set_effort("max").result(5)          # turno em andamento: espera
    assert not FakeClient.instances[0].disconnected
    rec.wait("done")
    time.sleep(0.3)
    assert FakeClient.instances[0].disconnected
    worker.send("depois").result(5)
    rec.wait("done", 2)
    new = FakeClient.instances[1].options
    assert new.effort == "max" and new.resume == "s-1"


def test_rate_limit_event_is_forwarded(setup):
    from claude_agent_sdk import RateLimitEvent
    from claude_agent_sdk.types import RateLimitInfo
    worker, rec = setup

    async def script(client, prompt):
        client.push(RateLimitEvent(RateLimitInfo(status="allowed_warning", utilization=0.9,
                                                 resets_at=1700000000, rate_limit_type="seven_day"), uuid="u", session_id="s"))
        client.push(result())

    FakeClient.script = script
    worker.send("oi").result(5)
    event = rec.wait("rate_limit")
    assert event["status"] == "allowed_warning" and event["utilization"] == 0.9


def test_resume_at_applies_once(setup):
    worker, rec = setup

    async def script(client, prompt):
        client.push(result(sid="sess-1"))

    FakeClient.script = script
    worker.start_session("sess-1", r"C:\proj", resume_at="a2").result(5)
    assert worker.session_id == "sess-1"
    worker.send("de novo").result(5)
    rec.wait("done")
    assert FakeClient.instances[0].options.resume == "sess-1"
    assert FakeClient.instances[0].options.resume_session_at == "a2"
    worker.set_effort("high").result(5)  # reinicia o Claude Code mantendo a sessão
    worker.send("outra").result(5)
    rec.wait("done", count=2)
    assert FakeClient.instances[1].options.resume_session_at is None


def test_fetch_models_reads_server_info_without_query():
    from worker import fetch_models

    class InfoClient:
        def __init__(self, options):
            self.queries = []
            InfoClient.last = self
        async def connect(self):
            pass
        async def get_server_info(self):
            return {"models": [{"value": "default", "displayName": "Default", "description": "Opus 5.5 · x"},
                               {"value": "sonnet", "displayName": "Sonnet 5.5", "description": "y"},
                               {"displayName": "sem valor"}]}
        async def disconnect(self):
            self.closed = True

    assert fetch_models("cli", client_factory=InfoClient) == [
        ("", "Default", "Opus 5.5 · x"), ("sonnet", "Sonnet 5.5", "y")]
    assert InfoClient.last.closed and InfoClient.last.queries == []


def test_context_measured_after_turn(setup):
    worker, rec = setup

    async def script(client, prompt):
        client.push(result(sid="sess-1"))

    FakeClient.script = script
    worker.send("oi").result(5)
    context = rec.wait("context")
    assert context == {"session_id": "sess-1", "tokens": 250_000, "max_tokens": 1_000_000, "percentage": 25}


def test_done_even_when_cli_merges_two_queued_messages(setup):
    """Duas mensagens enviadas seguidas, mas o Claude Code responde com um
    único resultado: o app não pode ficar preso em "Respondendo" para sempre."""
    worker, rec = setup
    worker._settle_seconds = 0.3

    async def script(client, prompt):
        if prompt == "segunda":
            client.push(result(sid="sess-1"))   # um só resultado para as duas

    FakeClient.script = script
    worker.send("primeira").result(5)
    worker.send("segunda").result(5)
    done = rec.wait("done", timeout=3)
    assert done["error"] is None

    # e a próxima mensagem volta a funcionar normalmente
    async def script2(client, prompt):
        client.push(result(sid="sess-1"))

    FakeClient.script = script2
    worker.send("terceira").result(5)
    rec.wait("done", count=2, timeout=3)


def test_done_after_interrupt_without_result(setup):
    worker, rec = setup
    worker._settle_seconds = 0.3

    async def script(client, prompt):
        pass  # o Claude Code não devolve resultado nenhum

    FakeClient.script = script
    worker.send("longa").result(5)
    worker.interrupt().result(5)
    rec.wait("done", timeout=3)


def test_sequential_turns_do_not_finish_early(setup):
    """Duas mensagens pendentes ao mesmo tempo e uma resposta para cada uma, uma
    depois da outra: o 'pronto' só vem depois da segunda."""
    worker, rec = setup
    worker._settle_seconds = 0.4

    async def script(client, prompt):
        await asyncio.sleep(0.3 if prompt == "primeira" else 0.5)
        client.push(result(sid="sess-1"))

    FakeClient.script = script
    worker.send("primeira").result(5)
    worker.send("segunda").result(5)
    rec.wait("done", timeout=3)
    time.sleep(0.8)
    assert [n for n in rec.names() if n == "done"] == ["done"]
