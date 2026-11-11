"""Conversa com o Claude Code pelo Claude Agent SDK num loop asyncio em thread
própria. A interface nunca espera por aqui: tudo que acontece vira um evento
entregue pela função `emit(nome, **dados)`, que a janela embrulha com
wx.CallAfter."""

import asyncio
import subprocess
import sys
import threading
from dataclasses import dataclass, field

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    RateLimitEvent,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, StreamEvent

import formatting

OTHER = "Outro"


def hide_child_consoles():
    """O SDK abre o claude.exe com anyio.open_process sem opção para esconder
    a janela. Como o app roda com pythonw (sem console), o Windows criava um
    terminal visível que o NVDA lia. Aqui todo processo aberto pelo anyio
    ganha CREATE_NO_WINDOW."""
    if sys.platform != "win32" or getattr(anyio.open_process, "_sem_janela", False):
        return
    original = anyio.open_process

    async def open_process(command, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return await original(command, **kwargs)

    open_process._sem_janela = True
    anyio.open_process = open_process


hide_child_consoles()


def fetch_models(cli_path=None, cwd=None, client_factory=ClaudeSDKClient):
    """Modelos que o Claude Code oferece para esta conta, como (valor, nome,
    descrição). Abre um Claude Code à parte só para ler a resposta de início;
    não envia mensagem nem gasta uso. O item "default" (padrão da conta) vem
    com valor vazio."""

    async def run():
        client = client_factory(options=ClaudeAgentOptions(cli_path=cli_path, cwd=cwd or None))
        await client.connect()
        try:
            info = await client.get_server_info() or {}
        finally:
            await client.disconnect()
        return info.get("models") or []

    models = []
    for m in asyncio.run(run()):
        value = m.get("value")
        if not value:
            continue
        models.append(("" if value == "default" else value, m.get("displayName") or value,
                       m.get("description") or ""))
    return models


@dataclass
class Request:
    """Pergunta pendente mostrada como botões."""
    kind: str            # "permission" ou "question"
    text: str
    options: list = field(default_factory=list)


@dataclass
class Answer:
    index: int | None = None   # opção escolhida
    text: str | None = None    # resposta digitada (Outro)


_ERROR_TEXT = {
    "authentication_failed": "Não conectado à conta Claude. Use o menu Conta, Entrar na conta Claude.",
    "billing_error": "Problema de cobrança ou limite da conta.",
    "rate_limit": "Limite de uso atingido. Tente mais tarde.",
    "invalid_request": "Pedido inválido.",
    "server_error": "Erro no servidor do Claude.",
}


class AgentWorker:
    def __init__(self, emit, client_factory=ClaudeSDKClient, cli_path=None,
                 permission_mode="default", model="", effort=""):
        self._emit = emit
        self._factory = client_factory
        self._cli_path = cli_path
        self._permission_mode = permission_mode or "default"
        self._model = model or ""
        self._effort = effort or ""
        self._restart_after_turn = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True,
                                        name="claude-sdk")
        self._thread.start()
        self._client = None
        self._reader = None
        self._session_id = None
        self._cwd = None
        self._resume_at = None     # volta a conversa até esta entrada na próxima conexão
        self._pending = None       # (Request, Future)
        self._in_flight = 0
        self._activity = 0         # conta mensagens recebidas do Claude Code
        self._settle_seconds = 4.0
        self._turn = 0
        self._committed = ""
        self._partial = ""

    # ---- chamadas da interface (thread da UI) ----

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def start_session(self, session_id, cwd, resume_at=None):
        """Troca de sessão. session_id None começa uma nova. Com resume_at, a
        conversa continua a partir dessa entrada do histórico, deixando de fora
        o que veio depois (como o rewind do Claude Code)."""
        # Já vale para quem perguntar session_id logo depois, na thread da UI.
        self._session_id = session_id
        return self.submit(self._start_session(session_id, cwd, resume_at))

    def send(self, text):
        return self.submit(self._send(text))

    def answer(self, answer):
        self._loop.call_soon_threadsafe(self._resolve, answer)

    def interrupt(self):
        return self.submit(self._interrupt())

    def set_permission_mode(self, mode):
        return self.submit(self._set_permission_mode(mode))

    def set_model(self, model):
        return self.submit(self._set_model(model))

    def set_effort(self, effort):
        return self.submit(self._set_effort(effort))

    def close(self):
        fut = self.submit(self._disconnect())
        try:
            fut.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def session_id(self):
        return self._session_id

    # ---- dentro do loop ----

    async def _start_session(self, session_id, cwd, resume_at=None):
        # Grava a escolha antes de esperar o desligamento: se outra troca de
        # sessão rodar enquanto este await espera, a última escolha vence.
        self._session_id = session_id
        self._cwd = cwd
        self._resume_at = resume_at if session_id else None
        await self._disconnect()

    async def _ensure_client(self):
        if self._client is not None:
            return
        options = ClaudeAgentOptions(
            # Sem isto o SDK abre o Claude Code com instrução de sistema vazia,
            # diferente do aplicativo Claude e do terminal.
            system_prompt={"type": "preset", "preset": "claude_code"},
            cwd=self._cwd or None,
            resume=self._session_id,
            resume_session_at=self._resume_at,
            can_use_tool=self._can_use_tool,
            include_partial_messages=True,
            cli_path=self._cli_path,
            stderr=self._on_stderr,
            permission_mode=self._permission_mode,
            model=self._model or None,
            effort=self._effort or None,
        )
        client = self._factory(options=options)
        self._emit("status", text="Conectando ao Claude…")
        await client.connect()
        self._client = client
        self._resume_at = None  # a volta vale uma vez; depois segue o novo ramo
        self._reader = asyncio.create_task(self._read_loop(client))

    async def _send(self, text):
        try:
            await self._ensure_client()
        except Exception as exc:
            self._emit("error", text=f"Não consegui iniciar o Claude: {exc}")
            return
        self._turn += 1
        self._committed = ""
        self._partial = ""
        self._in_flight += 1
        self._emit("busy", state="Respondendo")
        try:
            await self._client.query(text)
        except Exception as exc:
            self._in_flight -= 1
            self._emit("error", text=f"Falha ao enviar: {exc}")

    async def _interrupt(self):
        self._cancel_pending()
        if self._client is not None:
            try:
                await self._client.interrupt()
                self._settle_later()
            except Exception as exc:
                self._emit("error", text=f"Falha ao interromper: {exc}")

    async def _set_permission_mode(self, mode):
        self._permission_mode = mode
        if self._client is not None:
            try:
                await self._client.set_permission_mode(mode)
            except Exception as exc:
                self._emit("error", text=f"Não consegui mudar o modo de permissão: {exc}")
                return
        # Quem pediu "permitir tudo" não quer ficar preso numa pergunta já aberta.
        if mode == "bypassPermissions" and self._pending and self._pending[0].kind == "permission":
            self._resolve(Answer(index=0))

    async def _set_model(self, model):
        self._model = model
        if self._client is not None:
            try:
                await self._client.set_model(model or None)
            except Exception as exc:
                self._emit("error", text=f"Não consegui trocar o modelo: {exc}")

    async def _set_effort(self, effort):
        # O esforço só é lido quando o Claude Code inicia: reinicia mantendo a
        # sessão, agora se estiver parado ou ao fim do turno em andamento.
        self._effort = effort
        if self._client is None:
            return
        if self._in_flight:
            self._restart_after_turn = True
        else:
            await self._disconnect()

    async def _disconnect(self):
        self._cancel_pending()
        client, reader = self._client, self._reader
        self._client = self._reader = None
        self._in_flight = 0
        if reader is not None:
            reader.cancel()
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def _read_loop(self, client):
        try:
            async for message in client.receive_messages():
                self._handle(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._emit("error", text=f"Conexão com o Claude encerrada: {exc}")
        if self._client is client:
            self._client = None
            self._in_flight = 0
            self._emit("done", state="Pronto", session_id=self._session_id, error=None)

    def _handle(self, message):
        self._activity += 1
        if isinstance(message, StreamEvent):
            self._on_stream_event(message.event)
        elif isinstance(message, AssistantMessage):
            if message.error:
                self._emit("error", text=_ERROR_TEXT.get(message.error, "Erro: " + str(message.error)))
            if message.parent_tool_use_id:
                return  # subagente: não entra na conversa
            texts = []
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    texts.append(block.text.strip())
                elif isinstance(block, ToolUseBlock):
                    self._emit("busy", state=formatting.tool_action(block.name, block.input))
                    path = formatting.tool_file(block.name, block.input)
                    if path:
                        self._emit("tool_file", turn=self._turn, path=path)
            if texts:
                joined = "\n\n".join(texts)
                self._committed = (self._committed + "\n\n" + joined) if self._committed else joined
                self._partial = ""
                self._emit_text()
        elif isinstance(message, SystemMessage):
            sid = message.data.get("session_id") if isinstance(message.data, dict) else None
            if sid:
                self._set_session(sid)
        elif isinstance(message, ResultMessage):
            self._set_session(message.session_id)
            self._in_flight = max(0, self._in_flight - 1)
            error = None
            if message.is_error:
                error = message.result or ", ".join(message.errors or []) or message.subtype
                if "login" in error.lower() or "api key" in error.lower():
                    error = _ERROR_TEXT["authentication_failed"]
            elif message.subtype not in ("success", None):
                error = message.subtype
            if self._in_flight == 0:
                self._finish(error, message.total_cost_usd)
            else:
                # Ainda há mensagens contadas como pendentes. Se o Claude Code
                # juntou várias num só turno, este era o único resultado que viria.
                self._settle_later(error, message.total_cost_usd)
        elif isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            self._emit("rate_limit", status=info.status, utilization=info.utilization,
                       resets_at=info.resets_at, kind=info.rate_limit_type)

    def _finish(self, error, cost):
        self._emit("done", state="Pronto", session_id=self._session_id, error=error, cost=cost)
        restart, self._restart_after_turn = self._restart_after_turn, False
        asyncio.ensure_future(self._after_turn(self._client, restart))

    def _settle_later(self, error=None, cost=None):
        self._loop.call_later(self._settle_seconds, self._settle, self._activity, error, cost)

    def _settle(self, stamp, error, cost):
        """Nada chegou do Claude Code desde o último resultado: o que sobrou na
        contagem de pendentes não vai mais responder. Sem isto o título ficaria
        em "Respondendo" e o som de pronto nunca mais tocaria."""
        if self._in_flight > 0 and self._activity == stamp and self._client is not None:
            self._in_flight = 0
            self._finish(error, cost)

    async def _after_turn(self, client, restart):
        """Mede a conversa (o mesmo que o /context; não gasta uso) e, se o
        esforço mudou durante o turno, reinicia o Claude Code."""
        if client is not None:
            try:
                usage = await client.get_context_usage()
                self._emit("context", session_id=self._session_id, tokens=usage.get("totalTokens") or 0,
                           max_tokens=usage.get("maxTokens") or 0, percentage=usage.get("percentage") or 0)
            except Exception as exc:
                self._emit("log", text=f"Não consegui medir a conversa: {exc}")
        if restart:
            await self._disconnect()

    def _on_stream_event(self, event):
        kind = event.get("type")
        if kind == "content_block_start":
            self._partial = ""
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                self._partial += delta.get("text", "")
                self._emit_text()

    def _emit_text(self):
        text = self._committed
        if self._partial.strip():
            text = (text + "\n\n" + self._partial.strip()) if text else self._partial.strip()
        if text:
            self._emit("assistant_text", turn=self._turn, text=text)

    def _set_session(self, sid):
        if sid and sid != self._session_id:
            self._session_id = sid
            self._emit("session", session_id=sid)

    def _on_stderr(self, line):
        self._emit("log", text=line)

    # ---- permissões e perguntas ----

    async def _wait(self, request):
        self._cancel_pending()
        fut = self._loop.create_future()
        self._pending = (request, fut)
        self._emit("request", request=request)
        try:
            return await fut
        finally:
            if self._pending and self._pending[1] is fut:
                self._pending = None
            self._emit("request_closed")

    def _resolve(self, answer):
        if self._pending and not self._pending[1].done():
            self._pending[1].set_result(answer)

    def _cancel_pending(self):
        if self._pending and not self._pending[1].done():
            self._pending[1].set_result(None)
        self._pending = None

    async def _can_use_tool(self, tool_name, input_data, context):
        if tool_name == "AskUserQuestion":
            return await self._ask_questions(input_data)
        suggestions = list(getattr(context, "suggestions", None) or [])
        options = ["Permitir"]
        if suggestions:
            options.append("Permitir sempre")
        options += ["Negar", OTHER]
        self._emit("busy", state="Aguardando sua resposta")
        answer = await self._wait(Request("permission", formatting.permission_text(tool_name, input_data), options))
        self._emit("busy", state="Respondendo")
        if answer is None:
            return PermissionResultDeny(message="Cancelado pelo usuário.", interrupt=True)
        if answer.text is not None:
            return PermissionResultDeny(message="O usuário recusou e respondeu: " + answer.text)
        choice = options[answer.index]
        if choice == "Permitir":
            return PermissionResultAllow(updated_input=input_data)
        if choice == "Permitir sempre":
            return PermissionResultAllow(updated_input=input_data, updated_permissions=suggestions)
        return PermissionResultDeny(message="O usuário negou esta ação.")

    async def _ask_questions(self, input_data):
        questions = input_data.get("questions", []) or []
        answers = {}
        self._emit("busy", state="Aguardando sua resposta")
        for i, q in enumerate(questions, 1):
            labels = [o.get("label", "") for o in q.get("options", [])]
            request = Request("question", formatting.question_text(q, i, len(questions)), labels + [OTHER])
            answer = await self._wait(request)
            if answer is None:
                return PermissionResultDeny(message="O usuário cancelou a pergunta.", interrupt=True)
            answers[q.get("question", "")] = answer.text if answer.text is not None else labels[answer.index]
        self._emit("busy", state="Respondendo")
        return PermissionResultAllow(updated_input={"questions": questions, "answers": answers})
