"""CCA (Claude Code Acessível): janela leve, só com controles padrão do Windows, para
conversar com o Claude Code pelo Claude Agent SDK.

Atalhos: Alt+1 sessões por pasta, Alt+2 conversa, Alt+3 mensagem, Alt+P reabre
a pergunta do Claude, Alt+T pasta de trabalho, Alt+S liga e desliga a fala automática,
Alt+L limite de uso, Alt+F fila de mensagens agendadas, Ctrl+vírgula
configurações, Ctrl+N nova sessão, F2 renomear, Ctrl+M mover sessão para
outra pasta, Ctrl+Q sair, Escape interrompe a resposta."""

import datetime
import json
import os
import shutil
import subprocess
import threading
import uuid
import webbrowser
import zipfile

import wx

import feedback
import formatting
import limits
import links
import scheduled
import sessions
import subjects
import transfer
from worker import OTHER, AgentWorker, Answer, fetch_models

NL = chr(10)
NEW_SESSION_TITLE = "Nova sessão"

DEFAULTS = {
    "permission_mode": "default",
    "model": "",
    "effort": "",
    "sound_attention": True,
    "sound_done": True,
    "speak_steps": True,
    "speak_answer": False,
    "compact_reminder": 200_000,
}


def find_cli():
    try:
        import claude_agent_sdk
        bundled = os.path.join(os.path.dirname(claude_agent_sdk.__file__), "_bundled", "claude.exe")
        if os.path.exists(bundled):
            return bundled
    except ImportError:
        pass
    return shutil.which("claude")


def log_path():
    return os.path.join(os.path.dirname(sessions.config_path()), "registro.txt")


class MessageDialog(wx.Dialog):
    def __init__(self, parent, title, text, found=(), label="Texto da mensagem"):
        super().__init__(parent, title=title, size=(700, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, label=label)
        self.text = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        row = wx.BoxSizer(wx.HORIZONTAL)
        if found:
            button = wx.Button(self, label=f"&Links e arquivos: {links.summary(found)}…")
            button.Bind(wx.EVT_BUTTON, lambda e: LinksDialog.show(self, found))
            row.Add(button, 0, wx.RIGHT, 5)
        row.Add(wx.Button(self, wx.ID_CANCEL, "Fechar"), 0)
        sizer.Add(label, 0, wx.ALL, 5)
        sizer.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)


class LinksDialog(wx.Dialog):
    """Links e arquivos de uma mensagem. Enter abre; os botões leem o arquivo
    aqui mesmo, abrem a pasta dele ou copiam o endereço."""

    def __init__(self, parent, found):
        super().__init__(parent, title="Links e arquivos da mensagem", size=(700, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.found = list(found)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="&Links e arquivos"), 0, wx.LEFT | wx.TOP, 5)
        self.list = wx.ListBox(self, choices=[link.describe() for link in self.found], style=wx.LB_SINGLE)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (("&Abrir", self.on_open), ("Ler &aqui", self.on_read),
                               ("Abrir &pasta", self.on_folder), ("&Copiar endereço", self.on_copy)):
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, lambda e, h=handler: h())
            row.Add(button, 0, wx.RIGHT, 5)
        row.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        sizer.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.on_open())
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        if self.found:
            self.list.SetSelection(0)
        self.list.SetFocus()

    @classmethod
    def show(cls, parent, found):
        with cls(parent, found) as dialog:
            dialog.ShowModal()

    def _on_key(self, event):
        if (wx.Window.FindFocus() is self.list and not event.HasAnyModifiers()
                and event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)):
            self.on_open()
            return
        event.Skip()

    def _selected(self):
        index = self.list.GetSelection()
        return self.found[index] if index != wx.NOT_FOUND else None

    def _status(self, text):
        parent = self.GetParent()
        while parent is not None and not isinstance(parent, MainFrame):
            parent = parent.GetParent()
        if parent:
            parent.announce(text)

    def on_open(self):
        link = self._selected()
        if not link:
            return
        try:
            if link.kind == "url":
                webbrowser.open(link.target)
                self._status("Abrindo no navegador.")
            elif link.runnable:
                # Abrir direto executaria o programa ou script.
                subprocess.Popen(["notepad.exe", link.target])
                self._status("Este tipo de arquivo seria executado; abri no Bloco de Notas.")
            else:
                os.startfile(link.target)
                self._status("Abrindo " + os.path.basename(link.target))
        except OSError as exc:
            self._status(f"Não consegui abrir: {exc}")

    def on_read(self):
        link = self._selected()
        if not link:
            return
        if link.kind != "file":
            self._status("Ler aqui só vale para arquivos.")
            return
        text = links.read_text(link.target)
        if text is None:
            self._status("Não é um arquivo de texto, ou é grande demais para ler aqui. Use Abrir.")
            return
        with MessageDialog(self, os.path.basename(link.target), text,
                           links.find_links(text, os.path.dirname(link.target)),
                           label="Conteúdo do arquivo") as dialog:
            dialog.ShowModal()

    def on_folder(self):
        link = self._selected()
        if not link:
            return
        if link.kind != "file":
            self._status("Abrir pasta só vale para arquivos.")
            return
        if os.path.isdir(link.target):
            os.startfile(link.target)
        else:
            subprocess.Popen(["explorer.exe", "/select,", link.target])

    def on_copy(self):
        link = self._selected()
        if link and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(link.target))
            wx.TheClipboard.Close()
            self._status("Endereço copiado.")


class RequestDialog(wx.Dialog):
    """Pergunta ou pedido de permissão do Claude, como a janela de versão nova
    do TeleZapp: o texto, somente leitura, recebe o foco; o Tab leva aos
    botões. Escape fecha sem responder; Alt+P na janela principal reabre.
    Não é modal: se o Claude cancelar a pergunta, a janela principal a fecha."""

    def __init__(self, parent, request, on_choice, on_dismiss):
        title = "Pedido de permissão" if request.kind == "permission" else "Pergunta do Claude"
        super().__init__(parent, title=title, size=(640, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.on_dismiss = on_dismiss
        self.answered = False
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=title), 0, wx.ALL, 8)
        self.text = wx.TextCtrl(
            self, value=formatting.request_dialog_text(request.text, request.options, OTHER),
            name=title, style=wx.TE_MULTILINE | wx.TE_READONLY)
        sizer.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        row = wx.WrapSizer(wx.HORIZONTAL)
        for i, label in enumerate(request.options):
            # & no rótulo viraria atalho de tecla; && mostra o caractere.
            button = wx.Button(self, label=label.replace("&", "&&"))
            button.Bind(wx.EVT_BUTTON, lambda e, i=i, label=label: self._choose(on_choice, i, label))
            row.Add(button, 0, wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.text.SetInsertionPoint(0)
        self.text.SetFocus()
        self.CentreOnParent()

    def _choose(self, on_choice, index, label):
        self.answered = True
        on_choice(index, label)

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
            self.Close()
            return
        event.Skip()

    def _on_close(self, event):
        dismissed = not self.answered
        self.Destroy()
        if dismissed:
            self.on_dismiss(self)


class QueueDialog(wx.Dialog):
    """Mensagens que esperam o limite renovar. Enter na lista edita, Delete
    remove; os botões também mudam a ordem. As mudanças valem na hora."""

    def __init__(self, parent, queue, when):
        super().__init__(parent, title="Fila de mensagens agendadas", size=(700, 450),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.queue = queue
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="Envio previsto: " + when), 0, wx.ALL, 5)
        sizer.Add(wx.StaticText(self, label="&Mensagens na fila"), 0, wx.LEFT | wx.TOP, 5)
        self.list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (("&Editar", self.on_edit), ("&Remover", self.on_remove),
                               ("&Subir", lambda e: self.on_move(-1)),
                               ("&Descer", lambda e: self.on_move(1))):
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, 0, wx.RIGHT, 5)
        row.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        sizer.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CANCEL)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self._fill(0)
        self.list.SetFocus()

    def _fill(self, selection):
        self.list.Set([item.label(n + 1) for n, item in enumerate(self.queue.items)]
                      or ["Fila vazia."])
        if self.queue.items:
            self.list.SetSelection(max(0, min(selection, len(self.queue) - 1)))

    def _selected(self):
        index = self.list.GetSelection()
        return index if self.queue.items and index != wx.NOT_FOUND else None

    def _on_key(self, event):
        key = event.GetKeyCode()
        if wx.Window.FindFocus() is self.list and not event.HasAnyModifiers():
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.on_edit(None)
                return
            if key == wx.WXK_DELETE:
                self.on_remove(None)
                return
        event.Skip()

    def on_edit(self, _):
        index = self._selected()
        if index is None:
            return
        with wx.TextEntryDialog(self, "Texto da mensagem", "Editar mensagem agendada",
                                self.queue.items[index].text,
                                style=wx.TE_MULTILINE | wx.OK | wx.CANCEL) as dialog:
            if dialog.ShowModal() == wx.ID_OK and dialog.GetValue().strip():
                self.queue.edit(index, dialog.GetValue().strip())
        self._fill(index)
        self.list.SetFocus()

    def on_remove(self, _):
        index = self._selected()
        if index is None:
            return
        self.queue.remove(index)
        self._fill(index)
        self.list.SetFocus()

    def on_move(self, delta):
        index = self._selected()
        if index is None:
            return
        self._fill(self.queue.move(index, delta))
        self.list.SetFocus()


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, config, cwd, models):
        super().__init__(parent, title="Configurações")
        self.cwd = cwd
        self.models = list(models)
        sizer = wx.BoxSizer(wx.VERTICAL)

        def check(label, key):
            box = wx.CheckBox(self, label=label)
            box.SetValue(bool(config.get(key)))
            sizer.Add(box, 0, wx.ALL, 5)
            return box

        def choice(label, choices, value):
            sizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.TOP, 5)
            ctrl = wx.Choice(self, choices=[c[1] for c in choices])
            values = [c[0] for c in choices]
            ctrl.SetSelection(values.index(value) if value in values else 0)
            sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
            return ctrl

        self.sound_attention = check("&Som quando o Claude precisar de você", "sound_attention")
        self.sound_done = check("Som quando a resposta &terminar", "sound_done")
        self.speak_steps = check("&Falar as etapas pelo NVDA (ações, perguntas, pronto)", "speak_steps")
        self.speak_answer = check("&Ler a resposta inteira pelo NVDA ao terminar", "speak_answer")
        self.mode = choice("&Modo de permissão", formatting.PERMISSION_MODES, config.get("permission_mode"))
        self.model = choice("M&odelo", self.models, config.get("model"))
        self.refresh = wx.Button(self, label="Atualizar lista de mo&delos")
        self.refresh.Bind(wx.EVT_BUTTON, lambda e: parent.refresh_models(True, done=self.set_models))
        sizer.Add(self.refresh, 0, wx.ALL, 5)
        self.effort = choice("&Esforço", formatting.EFFORTS, config.get("effort"))
        self.reminder = choice("Lembrar de &compactar quando a conversa passar de",
                               formatting.COMPACT_REMINDERS, config.get("compact_reminder"))
        self.folder = wx.Button(self, label="")
        self._update_folder()
        self.folder.Bind(wx.EVT_BUTTON, self.on_folder)
        sizer.Add(self.folder, 0, wx.ALL, 5)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self.FindWindowById(wx.ID_OK).SetLabel("Salvar")
        self.FindWindowById(wx.ID_CANCEL).SetLabel("Cancelar")
        sizer.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.SetSizerAndFit(sizer)
        self.sound_attention.SetFocus()

    def set_models(self, models):
        """Lista nova depois de Atualizar; mantém o modelo escolhido."""
        if not self:
            return
        current = self.models[self.model.GetSelection()][0] if self.model.GetSelection() >= 0 else ""
        self.models = list(models)
        self.model.Set([label for _, label in self.models])
        values = [value for value, _ in self.models]
        self.model.SetSelection(values.index(current) if current in values else 0)

    def _update_folder(self):
        self.folder.SetLabel("&Pasta de trabalho das novas sessões: " + self.cwd)

    def on_folder(self, _):
        with wx.DirDialog(self, "Escolha a pasta de trabalho para novas sessões", self.cwd) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.cwd = dialog.GetPath()
                self._update_folder()

    def values(self):
        return {
            "sound_attention": self.sound_attention.GetValue(),
            "sound_done": self.sound_done.GetValue(),
            "speak_steps": self.speak_steps.GetValue(),
            "speak_answer": self.speak_answer.GetValue(),
            "permission_mode": formatting.PERMISSION_MODES[self.mode.GetSelection()][0],
            "model": self.models[self.model.GetSelection()][0],
            "effort": formatting.EFFORTS[self.effort.GetSelection()][0],
            "compact_reminder": formatting.COMPACT_REMINDERS[self.reminder.GetSelection()][0],
        }


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=formatting.APP_NAME, size=(900, 750))
        self.config = dict(DEFAULTS)
        self.config.update(sessions.load_config())
        self.cwd = self.config.get("cwd") or os.path.expanduser("~")
        self.cli = find_cli()
        self.speaker = feedback.Speaker()
        feedback.ensure_sounds()
        self.last_spoken_state = None
        self.worker = AgentWorker(self._post, cli_path=self.cli,
                                  permission_mode=self.config["permission_mode"],
                                  model=self.config["model"], effort=self.config["effort"])
        self.session_title = NEW_SESSION_TITLE
        self.state = "Pronto"
        self.items = []          # [papel, texto]
        self.turn_items = {}     # turno do worker -> índice do item
        self.item_files = {}     # índice do item -> arquivos que o Claude criou ou editou
        self.turn_files = {}     # turno do worker -> esses arquivos, antes do texto chegar
        self.dirty = set()
        self.flush_pending = False
        self.session_entries = []
        self.request = None
        self.request_dialog = None
        self.session_cwd = self.cwd
        self.new_group = uuid.uuid4().hex    # grupo da fila para a sessão nova ainda sem id
        self.queue = scheduled.Queue()
        self.running_item = None             # mensagem da fila em andamento
        self.limit_tracker = limits.LimitTracker()
        self.compacting = False              # /compact em andamento
        self.context = None                  # (tokens, porcentagem) da conversa, medido a cada resposta
        self.context_max = 0                 # limite de tokens da conversa
        self.reminded_at = 0                 # tamanho no último lembrete de compactar
        self.limited_until = self.config.get("limit_resets_at") or None
        self.pending_title = None            # nome dado à sessão nova antes de ela existir
        self.queued_rows = []                # mensagens agendadas mostradas no fim da conversa

        self._build()
        self._update_title()
        self.worker.start_session(None, self.cwd)
        self.refresh_sessions()
        self.check_login()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.queue_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self.check_queue(), self.queue_timer)
        self.queue_timer.Start(20000)
        self.update_awake()
        if self.queue.items:
            wx.CallLater(3000, self._announce_queue_at_start)
        # A Anthropic lança modelos novos: confere a lista uma vez por semana.
        checked = self.config.get("models_checked") or 0
        if datetime.datetime.now().timestamp() - checked > 7 * 86400:
            wx.CallLater(8000, lambda: self and self.refresh_models(False))

    # ---------- montagem ----------

    def _build(self):
        menubar = wx.MenuBar()
        arquivo = wx.Menu()
        self.id_new = arquivo.Append(wx.ID_ANY, "&Nova sessão\tCtrl+N").GetId()
        self.id_rename = arquivo.Append(wx.ID_ANY, "&Renomear sessão…\tF2").GetId()
        self.id_move = arquivo.Append(wx.ID_ANY, "&Mover sessão para outra pasta…\tCtrl+M").GetId()
        self.id_refresh = arquivo.Append(wx.ID_ANY, "&Atualizar lista de sessões\tF5").GetId()
        self.id_folder = arquivo.Append(wx.ID_ANY, "Escolher &pasta de trabalho…").GetId()
        self.id_stop = arquivo.Append(wx.ID_ANY, "&Interromper resposta").GetId()
        arquivo.AppendSeparator()
        self.id_export = arquivo.Append(wx.ID_ANY, "E&xportar preferências e memórias…").GetId()
        self.id_import = arquivo.Append(wx.ID_ANY, "Importar pre&ferências e memórias…").GetId()
        arquivo.AppendSeparator()
        arquivo.Append(wx.ID_EXIT, "&Sair\tCtrl+Q")
        conta = wx.Menu()
        self.id_login = conta.Append(wx.ID_ANY, "&Entrar na conta Claude…").GetId()
        self.id_status = conta.Append(wx.ID_ANY, "&Verificar conexão").GetId()
        claude = wx.Menu()
        self.mode_items = self._radio_submenu(claude, "Modo de &permissão", formatting.PERMISSION_MODES,
                                              "permission_mode", self.change_mode)
        self.model_menu = wx.Menu()
        claude.AppendSubMenu(self.model_menu, "&Modelo")
        self._fill_model_menu()
        self.effort_items = self._radio_submenu(claude, "&Esforço", formatting.EFFORTS, "effort", self.change_effort)
        claude.AppendSeparator()
        self.speech_item = claude.AppendCheckItem(wx.ID_ANY, "&Fala automática\tAlt+S")
        self.speech_item.Check(bool(self.config.get("speak_steps")))
        self.id_compact = claude.Append(wx.ID_ANY, "Com&pactar a conversa…\tCtrl+K").GetId()
        self.id_context = claude.Append(wx.ID_ANY, "&Tamanho da conversa").GetId()
        self.id_usage = claude.Append(wx.ID_ANY, "Consultar &limite de uso\tAlt+L").GetId()
        self.id_queue = claude.Append(wx.ID_ANY, "Fila de mensagens a&gendadas…\tAlt+F").GetId()
        self.id_enqueue = claude.Append(
            wx.ID_ANY, "&Agendar a mensagem escrita para quando o limite renovar (Ctrl+Shift+Enter)").GetId()
        self.id_settings = claude.Append(wx.ID_ANY, "&Configurações…\tCtrl+,").GetId()
        menubar.Append(arquivo, "&Arquivo")
        menubar.Append(claude, "&Claude")
        menubar.Append(conta, "C&onta")
        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, lambda e: self.compact(), id=self.id_compact)
        self.Bind(wx.EVT_MENU, lambda e: self.show_context(), id=self.id_context)
        self.Bind(wx.EVT_MENU, lambda e: self.show_usage(), id=self.id_usage)
        self.Bind(wx.EVT_MENU, lambda e: self.open_queue(), id=self.id_queue)
        self.Bind(wx.EVT_MENU, lambda e: self.enqueue(), id=self.id_enqueue)
        self.Bind(wx.EVT_MENU, lambda e: self.open_settings(), id=self.id_settings)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_speech(), id=self.speech_item.GetId())

        panel = wx.Panel(self)
        self.panel = panel
        sizer = wx.BoxSizer(wx.VERTICAL)

        def labeled(text, ctrl, proportion=0):
            # O NVDA dá ao controle o nome do texto que vem logo antes dele.
            label = wx.StaticText(panel, label=text)
            label.MoveBeforeInTabOrder(ctrl)
            sizer.Add(label, 0, wx.LEFT | wx.TOP, 5)
            sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        # A ordem de criação define a ordem do Tab.
        self.msg = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 70))
        labeled("Mensagem", self.msg)
        self.conv = wx.ListBox(panel, style=wx.LB_SINGLE)
        labeled("Conversa", self.conv, 3)
        self.sess = wx.TreeCtrl(panel, style=wx.TR_HIDE_ROOT | wx.TR_HAS_BUTTONS
                                | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE)
        labeled("Sessões por pasta", self.sess, 2)
        panel.SetSizer(sizer)
        # Fora da ordem do Tab; o NVDA lê com NVDA+End.
        self.CreateStatusBar()

        self.msg.Bind(wx.EVT_KEY_DOWN, self.on_msg_key)
        # Nas listas o Enter é consumido pela navegação do painel antes do
        # EVT_KEY_DOWN; o EVT_CHAR_HOOK da janela vê a tecla antes disso.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.conv.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.open_message())
        self.conv.Bind(wx.EVT_CONTEXT_MENU, lambda e: self.message_menu())
        self.sess.Bind(wx.EVT_TREE_ITEM_ACTIVATED, lambda e: self.open_session())
        self.sess.Bind(wx.EVT_TREE_ITEM_MENU, lambda e: self.tree_menu())
        self.sess.Bind(wx.EVT_TREE_ITEM_EXPANDED, lambda e: self._remember_expanded())
        self.sess.Bind(wx.EVT_TREE_ITEM_COLLAPSED, lambda e: self._remember_expanded())

        shortcuts = (("1", self.sess.SetFocus), ("2", self.conv.SetFocus), ("3", self.msg.SetFocus),
                     ("P", self.reopen_request), ("T", self.choose_folder))
        entries = []
        for key, action in shortcuts:
            ident = wx.NewIdRef()
            entries.append(wx.AcceleratorEntry(wx.ACCEL_ALT, ord(key), ident))
            self.Bind(wx.EVT_MENU, lambda e, a=action: a(), id=ident)
        self.id_escape = wx.NewIdRef()
        entries.append(wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, self.id_escape))
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))

        self.Bind(wx.EVT_MENU, lambda e: self.new_session(), id=self.id_new)
        self.Bind(wx.EVT_MENU, lambda e: self.rename_selected(), id=self.id_rename)
        self.Bind(wx.EVT_MENU, lambda e: self.move_session(), id=self.id_move)
        self.Bind(wx.EVT_MENU, lambda e: self.refresh_sessions(), id=self.id_refresh)
        self.Bind(wx.EVT_MENU, lambda e: self.choose_folder(), id=self.id_folder)
        self.Bind(wx.EVT_MENU, lambda e: self.stop(), id=self.id_stop)
        self.Bind(wx.EVT_MENU, lambda e: self.export_memories(), id=self.id_export)
        self.Bind(wx.EVT_MENU, lambda e: self.import_memories(), id=self.id_import)
        self.Bind(wx.EVT_MENU, lambda e: self.stop(), id=self.id_escape)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, lambda e: self.login(), id=self.id_login)
        self.Bind(wx.EVT_MENU, lambda e: self.check_login(), id=self.id_status)
        self.msg.SetFocus()

    def _radio_submenu(self, menu, label, choices, key, handler):
        sub = wx.Menu()
        items = {}
        for value, text in choices:
            item = sub.AppendRadioItem(wx.ID_ANY, text)
            items[value] = item
            self.Bind(wx.EVT_MENU, lambda e, v=value: handler(v), id=item.GetId())
        current = self.config.get(key, "")
        if current in items:
            items[current].Check()
        menu.AppendSubMenu(sub, label)
        return items

    # ---------- modelos ----------

    def model_choices(self):
        """Modelos da última atualização, ou a lista embutida se nunca atualizou.
        O modelo escolhido sempre aparece, mesmo que tenha saído da lista."""
        saved = self.config.get("models")
        choices = formatting.model_choices(saved) if saved else list(formatting.MODELS)
        current = self.config.get("model", "")
        if current not in [value for value, _ in choices]:
            choices.append((current, current))
        return choices

    def _fill_model_menu(self):
        menu = self.model_menu
        for item in list(menu.GetMenuItems()):
            menu.Delete(item)
        self.model_items = {}
        for value, text in self.model_choices():
            item = menu.AppendRadioItem(wx.ID_ANY, text.replace("&", "&&"))
            self.model_items[value] = item
            self.Bind(wx.EVT_MENU, lambda e, v=value: self.change_model(v), id=item.GetId())
        current = self.config.get("model", "")
        if current in self.model_items:
            self.model_items[current].Check()
        menu.AppendSeparator()
        refresh = menu.Append(wx.ID_ANY, "&Atualizar lista de modelos")
        self.Bind(wx.EVT_MENU, lambda e: self.refresh_models(True), id=refresh.GetId())

    def refresh_models(self, announce, done=None):
        """Pergunta ao Claude Code quais modelos a conta tem. Sem `announce`
        (a checagem semanal ao abrir), só fala se aparecer modelo novo."""
        if not self.cli:
            if announce:
                self.set_status("Não encontrei o Claude Code.")
            return
        if announce:
            self.announce("Atualizando lista de modelos…")

        def work():
            try:
                models, error = fetch_models(self.cli, os.path.dirname(os.path.abspath(__file__))), None
            except Exception as exc:
                models, error = [], str(exc)
            wx.CallAfter(self._models_ready, models, error, announce, done)

        threading.Thread(target=work, daemon=True).start()

    def _models_ready(self, models, error, announce, done):
        if not self:
            return
        if error or not models:
            self.write_log("ERRO lista de modelos: " + (error or "vazia"))
            if announce:
                self.set_status("Não consegui atualizar a lista de modelos: " + (error or "lista vazia"))
            return
        old = {m[0] for m in self.config.get("models") or []}
        self.config["models"] = [list(m) for m in models]
        self.config["models_checked"] = datetime.datetime.now().timestamp()
        self.save_config()
        self._fill_model_menu()
        labels = dict(formatting.model_choices(models))
        new = [labels[m[0]] for m in models if old and m[0] not in old]
        text = f"Lista de modelos atualizada: {len(models)} opções."
        if new:
            text += " Novos: " + ", ".join(new) + "."
        if announce or new:
            self.announce(text)
        if done:
            done(self.model_choices())

    # ---------- configurações ----------

    def save_config(self):
        self.config["cwd"] = self.cwd
        sessions.save_config(self.config)

    def announce(self, text):
        """Status, e fala pelo NVDA quando a opção estiver ligada."""
        self.set_status(text)
        if self.config.get("speak_steps"):
            self.speaker.speak(text)

    def change_mode(self, mode, announce=True):
        self.config["permission_mode"] = mode
        self.mode_items[mode].Check()
        self.save_config()
        self.worker.set_permission_mode(mode)
        if announce:
            self.announce("Modo de permissão: " + formatting.choice_label(formatting.PERMISSION_MODES, mode))

    def change_model(self, model, announce=True):
        self.config["model"] = model
        if model in self.model_items:
            self.model_items[model].Check()
        self.save_config()
        self.worker.set_model(model)
        if announce:
            text = "Modelo: " + formatting.choice_label(self.model_choices(), model)
            if self.items:
                # O cache do contexto é por modelo: a conversa toda é gravada de novo.
                text += (". Nesta conversa, a próxima mensagem gasta mais: o contexto inteiro é"
                         " enviado de novo para o modelo novo.")
            self.announce(text)

    def change_effort(self, effort, announce=True):
        self.config["effort"] = effort
        self.effort_items[effort].Check()
        self.save_config()
        self.worker.set_effort(effort)
        if announce:
            self.announce("Esforço: " + formatting.choice_label(formatting.EFFORTS, effort)
                          + ". Vale a partir da próxima mensagem.")

    def toggle_speech(self):
        on = not self.config.get("speak_steps")
        self.config["speak_steps"] = on
        self.speech_item.Check(on)
        self.save_config()
        text = "Fala automática ligada." if on else "Fala automática desligada."
        self.set_status(text)
        self.speaker.speak(text, interrupt=True)  # fala mesmo ao desligar

    def open_settings(self):
        with SettingsDialog(self, self.config, self.cwd, self.model_choices()) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            values = dialog.values()
            new_cwd = dialog.cwd
        old = dict(self.config)
        self.config.update(values)
        if new_cwd != self.cwd:
            self.cwd = new_cwd
        self.save_config()
        self.speech_item.Check(bool(self.config.get("speak_steps")))
        if values["permission_mode"] != old.get("permission_mode"):
            self.change_mode(values["permission_mode"], announce=False)
        if values["model"] != old.get("model"):
            self.change_model(values["model"], announce=False)
        if values["effort"] != old.get("effort"):
            self.change_effort(values["effort"], announce=False)
        self.announce("Configurações salvas.")

    def show_usage(self):
        if not self.cli:
            self.set_status("Não encontrei o Claude Code.")
            return
        self.announce("Consultando limite de uso…")

        def work():
            try:
                result = subprocess.run(
                    [self.cli, "-p", "/usage", "--no-session-persistence"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    creationflags=subprocess.CREATE_NO_WINDOW)
                text = result.stdout.strip() or result.stderr.strip()
            except Exception as exc:
                text = f"Não consegui consultar o limite: {exc}"
            wx.CallAfter(self._usage_ready, text)

        threading.Thread(target=work, daemon=True).start()

    def _usage_ready(self, text):
        if not self:
            return
        summary = formatting.usage_summary(text)
        if summary:
            self.set_status(" ".join(summary))  # a janela abaixo já é lida pelo NVDA
            full = "\n".join(summary) + "\n\nDetalhes do Claude Code (em inglês):\n\n" + text
        else:
            self.set_status("Limite de uso: veja os detalhes.")
            full = text
        with MessageDialog(self, "Limite de uso", full) as dialog:
            dialog.ShowModal()

    # ---------- título e status ----------

    def _update_title(self):
        self.SetTitle(formatting.window_title(self.state, self.session_title))

    def set_state(self, state):
        self.state = state
        self._update_title()
        self.set_status(state)

    def set_status(self, text):
        self.SetStatusText(text)

    # ---------- eventos do worker (chegam de outra thread) ----------

    def _post(self, name, **data):
        wx.CallAfter(self._dispatch, name, data)

    def _dispatch(self, name, data):
        if not self:
            return
        handler = getattr(self, "ev_" + name, None)
        if handler:
            handler(**data)

    def ev_status(self, text):
        self.set_status(text)

    def ev_busy(self, state):
        if self.compacting and state == "Respondendo":
            state = "Compactando a conversa"
        self.set_state(state)
        # A pergunta tem fala própria; as outras etapas são faladas quando mudam.
        if (self.config.get("speak_steps") and state != self.last_spoken_state
                and state != "Aguardando sua resposta"):
            self.last_spoken_state = state
            self.speaker.speak(state)

    def ev_error(self, text):
        self.set_status(text)
        self.write_log("ERRO " + text)
        if self.config.get("sound_done"):
            feedback.play("erro")
        if self.config.get("speak_steps"):
            self.speaker.speak(text)

    def ev_context(self, session_id, tokens, max_tokens, percentage):
        if session_id != self.worker.session_id:
            return
        self.context = (tokens, percentage)
        self.context_max = max_tokens
        threshold = self.config.get("compact_reminder") or 0
        if tokens < threshold:
            self.reminded_at = 0  # compactou ou é outra conversa: o próximo aviso volta a valer
        if formatting.should_remind_compact(tokens, threshold, self.reminded_at):
            self.reminded_at = tokens
            text = (formatting.context_text(tokens, percentage) + ". Cada mensagem relê tudo isso:"
                    " Ctrl+K compacta a conversa e deixa as próximas mais baratas.")
            self.set_status(text)
            self.write_log(text)
            # Fala mesmo com a fala automática desligada; quem não quer, escolhe Nunca em Configurações.
            self.speaker.speak(text)

    def show_context(self):
        """Janela somente leitura, como a do limite de uso: o NVDA lê o texto
        ao abrir, sem depender da fala automática."""
        if self.context:
            tokens, percentage = self.context
            text = formatting.context_details(tokens, self.context_max, percentage,
                                              self.config.get("compact_reminder") or 0)
            self.set_status(formatting.context_text(tokens, percentage) + ".")
        else:
            text = ("O tamanho ainda não foi medido. Ele é medido ao fim de cada resposta do Claude: "
                    "envie uma mensagem nesta sessão e abra esta janela de novo.")
            self.set_status("Tamanho da conversa: ainda não medido.")
        with MessageDialog(self, "Tamanho da conversa", text, label="Tamanho da conversa") as dialog:
            dialog.ShowModal()

    def ev_rate_limit(self, status, utilization=None, resets_at=None, kind=None):
        """O Claude Code informa cada janela (5 horas, semanal...) em eventos
        separados. Todas entram no rastreador, e só a mais próxima do fim gera
        aviso."""
        self.limit_tracker.update(kind, status, utilization, resets_at)
        if self.limit_tracker.is_rejected():
            self.set_limit(self.limit_tracker.rejected_until() or self.limited_until)
        elif status == "allowed" and self.limited_until:
            self.set_limit(None)
        text = self.limit_tracker.message()
        if text:
            self.write_log(text)
            self.announce(text)

    def ev_log(self, text):
        self.write_log(text)

    def ev_session(self, session_id):
        # O título é buscado quando o turno termina. Mensagens agendadas na
        # sessão nova, antes de ela ter id, passam a apontar para ela.
        self.queue.bind_session(self.new_group, session_id)
        self.refresh_queued_rows()

    def ev_tool_file(self, turn, path):
        files = self.turn_files.setdefault(turn, [])
        if path not in files:
            files.append(path)
        index = self.turn_items.get(turn)
        if index is not None:
            self.item_files[index] = files
            self.dirty.add(index)
            if not self.flush_pending:
                self.flush_pending = True
                wx.CallLater(800, self.flush)

    def _links(self, index):
        role, text = self.items[index]
        return links.find_links(text, self.session_cwd, self.item_files.get(index, ()))

    def _item_label(self, index):
        role, text = self.items[index]
        return formatting.item_label(role, index + 1, text, links.summary(self._links(index)))

    def ev_assistant_text(self, turn, text):
        index = self.turn_items.get(turn)
        if index is None:
            self.items.append(["assistant", text])
            index = len(self.items) - 1
            self.turn_items[turn] = index
            if turn in self.turn_files:
                self.item_files[index] = self.turn_files[turn]
            self.conv.Insert(self._item_label(index), index)
        else:
            self.items[index][1] = text
            self.dirty.add(index)
            if not self.flush_pending:
                self.flush_pending = True
                wx.CallLater(800, self.flush)

    def flush(self):
        self.flush_pending = False
        for index in sorted(self.dirty):
            role, text = self.items[index]
            self.conv.SetString(index, self._item_label(index))
        self.dirty.clear()

    def ev_done(self, state, session_id, error, cost=None):
        self.flush()
        self.last_spoken_state = None
        if error:
            self.state = "Erro"
            self._update_title()
            self.set_status("Erro: " + error)
            self.write_log("ERRO " + error)
            spoken = "Erro: " + error
            sound = "erro"
        else:
            self.set_state(state)
            spoken = state
            if self.config.get("speak_answer") and self.items and self.items[-1][0] == "assistant":
                spoken += ". " + self.items[-1][1]
            sound = "pronto"
        if self.config.get("sound_done"):
            feedback.play(sound)
        if self.config.get("speak_steps") or self.config.get("speak_answer"):
            self.speaker.speak(spoken)
        if session_id and self.pending_title:
            # Só agora o arquivo da sessão existe para receber o nome.
            title, self.pending_title = self.pending_title, None
            self._apply_rename(session_id, self.session_cwd, title, announce=False)
        elif session_id:
            threading.Thread(target=self._fetch_title, args=(session_id,), daemon=True).start()
        if session_id and not error:
            self._drop_rewind(session_id)  # a próxima mensagem já gravou o novo ramo
        if session_id and not any(e.session_id == session_id for e in self.session_entries):
            wx.CallLater(1500, self.refresh_sessions)  # sessão nova entra na árvore
        if error and "limit" in error.lower() and not self.limited():
            ts = formatting.reset_timestamp(error, datetime.datetime.now().timestamp())
            if ts:
                self.set_limit(ts)
        if self.compacting:
            self.compacting = False
            if not error:
                self.announce("Conversa compactada. O Claude segue com um resumo do que foi feito até aqui.")
        self._scheduled_done(error)

    def _fetch_title(self, session_id):
        title = sessions.fetch_title(session_id)
        if title:
            wx.CallAfter(self._set_title_if_current, session_id, title)

    def _set_title_if_current(self, session_id, title):
        if self and self.worker.session_id == session_id:
            self.session_title = title
            self._update_title()

    def ev_request(self, request):
        self.request = request
        self.set_state("Aguardando sua resposta")
        active = self.IsActive()
        if self.config.get("sound_attention"):
            feedback.play("atencao")
        self.open_request_dialog()
        # Com a janela aberta em primeiro plano, o NVDA já lê a pergunta; falar
        # junto atropelaria. Com o app em segundo plano o Windows pode não dar o
        # foco à janela, então a fala continua.
        if self.config.get("speak_steps") and not active:
            self.speaker.speak("Pergunta do Claude, Alt+P. " + request.text[:400]
                               + ". Opções: " + ", ".join(request.options), interrupt=True)
        if not active:
            self.RequestUserAttention()

    def ev_request_closed(self):
        had_focus = self.request_dialog is not None
        self.close_request_dialog()
        self.request = None
        if had_focus:
            wx.CallAfter(self.msg.SetFocus)

    def reopen_request(self):
        """Alt+P: volta à pergunta pendente, se a janela foi fechada com Escape."""
        if self.request is None:
            self.announce("Nenhuma pergunta do Claude no momento.")
            return
        self.open_request_dialog()

    def open_request_dialog(self):
        if self.request is None:
            return
        self.close_request_dialog()
        self.request_dialog = RequestDialog(self, self.request, self.on_option,
                                            self._request_dialog_dismissed)
        self.request_dialog.Show()

    def close_request_dialog(self):
        dialog, self.request_dialog = self.request_dialog, None
        if dialog:
            dialog.answered = True  # fechada por nós: não é um Escape
            dialog.Destroy()

    def _request_dialog_dismissed(self, dialog):
        if self.request_dialog is dialog:
            self.request_dialog = None
        if self.request is not None:
            self.set_status("Janela fechada sem responder. Alt+P reabre a pergunta; o que você "
                            "escrever na caixa de mensagem responde a ela.")
            wx.CallAfter(self.msg.SetFocus)

    def on_option(self, index, label):
        # O foco vai depois que a janela de pergunta some, senão o Windows o
        # devolve ao último controle ativo da janela principal.
        self.close_request_dialog()
        wx.CallAfter(self.msg.SetFocus)
        if label == OTHER:
            self.set_status("Digite sua resposta na caixa de mensagem e pressione Enter.")
            return
        self.worker.answer(Answer(index=index))

    # ---------- caixa de mensagem ----------

    def on_msg_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if event.ControlDown() and event.ShiftDown():
                self.enqueue()
            elif event.ControlDown():
                self.msg.WriteText("\n")
            elif not event.HasAnyModifiers():
                self.send()
            else:
                event.Skip()
            return
        if key == ord("V") and event.ControlDown() and not event.AltDown():
            if self.paste_files():
                return
        event.Skip()

    def paste_files(self):
        paths = []
        if wx.TheClipboard.Open():
            try:
                if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
                    data = wx.FileDataObject()
                    if wx.TheClipboard.GetData(data):
                        paths = data.GetFilenames()
            finally:
                wx.TheClipboard.Close()
        if not paths:
            return False
        self.msg.WriteText(formatting.file_refs(paths) + " ")
        self.set_status(f"{len(paths)} arquivo(s) inserido(s) como referência.")
        return True

    def send(self):
        text = self.msg.GetValue().strip()
        if not text:
            return
        if self.request is not None:
            self.msg.SetValue("")
            self.worker.answer(Answer(text=text))
            self.set_status("Resposta enviada.")
            return
        if self.limited():
            self.enqueue()
            return
        self.msg.SetValue("")
        self.send_text(text)

    def send_text(self, text):
        self.items.append(["user", text])
        self.conv.Insert(self._item_label(len(self.items) - 1), len(self.items) - 1)
        self.refresh_queued_rows()
        if self.session_title == NEW_SESSION_TITLE and len(self.items) == 1:
            self.session_title = formatting.one_line(text)[:60]
        self.set_state("Respondendo")
        self.worker.send(text)

    def compact(self):
        """Ctrl+K: o /compact do Claude Code. Troca a conversa por um resumo,
        e as próximas mensagens ficam bem mais baratas numa sessão longa."""
        if self.worker.session_id is None:
            self.set_status("Ainda não há conversa para compactar.")
            return
        if self.state not in ("Pronto", "Erro") or self.request is not None:
            self.set_status("Espere a resposta terminar. Escape interrompe.")
            return
        size = formatting.context_text(*self.context) + ". " if self.context else ""
        with wx.TextEntryDialog(
                self, size + "Instruções para o resumo, opcional. Por exemplo: guarde as decisões sobre a fila. "
                "Deixe em branco para o resumo padrão.", "Compactar a conversa") as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            instructions = formatting.one_line(dialog.GetValue())
        self.compacting = True
        self.set_state("Compactando a conversa")
        self.worker.send(("/compact " + instructions).strip())

    def stop(self):
        if self.state != "Pronto":
            self.worker.interrupt()
            self.set_status("Interrompendo…")

    # ---------- conversa ----------

    def on_char_hook(self, event):
        key = event.GetKeyCode()
        focused = wx.Window.FindFocus()
        enter = key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers()
        if focused is self.sess:
            if enter:
                self.open_session()
                return
        if focused is self.conv:
            if enter:
                self.open_message()
                return
            if key == ord("C") and event.GetModifiers() == wx.MOD_CONTROL:
                self.copy_message()
                return
            if key == wx.WXK_DELETE and not event.HasAnyModifiers():
                self.remove_message()
                return
            if key == ord("L") and event.GetModifiers() == wx.MOD_CONTROL:
                self.show_links()
                return
        event.Skip()

    def _row_links(self, row):
        kind, value = row
        return self._links(value) if kind == "item" else links.find_links(value.text, value.cwd)

    def show_links(self):
        row = self._selected_row()
        if not row:
            return
        found = self._row_links(row)
        if not found:
            self.set_status("Esta mensagem não tem links nem arquivos.")
            return
        LinksDialog.show(self, found)

    def _selected_row(self):
        """("item", índice) para mensagem da conversa, ("queued", item) para
        mensagem agendada, ou None."""
        index = self.conv.GetSelection()
        if index == wx.NOT_FOUND:
            return None
        if index < len(self.items):
            return "item", index
        queued = index - len(self.items)
        if queued < len(self.queued_rows):
            return "queued", self.queued_rows[queued]
        return None

    def _row_text(self, row):
        kind, value = row
        return self.items[value][1] if kind == "item" else value.text

    def copy_message(self):
        row = self._selected_row()
        if row and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self._row_text(row)))
            wx.TheClipboard.Close()
            self.set_status("Mensagem copiada.")

    def open_message(self):
        row = self._selected_row()
        if not row:
            return
        kind, value = row
        if kind == "queued":
            title = "Você, mensagem agendada"
        else:
            title = ("Você" if self.items[value][0] == "user" else "Claude") + f", mensagem {value + 1}"
        with MessageDialog(self, title, self._row_text(row), self._row_links(row)) as dialog:
            dialog.ShowModal()

    def load_items(self, items, files=None):
        self.items = [list(i) for i in items]
        self.item_files = {i: f for i, f in (files or {}).items() if i < len(self.items)}
        self.turn_items = {}
        self.turn_files = {}
        self.dirty.clear()
        self.conv.Set([self._item_label(n) for n in range(len(self.items))])
        self.queued_rows = []
        self.refresh_queued_rows()

    def refresh_queued_rows(self):
        """As mensagens agendadas desta sessão aparecem no fim da conversa."""
        selection = self.conv.GetSelection()
        while self.conv.GetCount() > len(self.items):
            self.conv.Delete(len(self.items))
        sid = self.worker.session_id
        self.queued_rows = [
            q for q in self.queue.items if q is not self.running_item and (
                (sid and q.session_id == sid) or (not sid and q.session_id is None and q.group == self.new_group))]
        when = self._queue_when()
        for q in self.queued_rows:
            self.conv.Append(formatting.queued_label(when, q.text))
        if selection != wx.NOT_FOUND and self.conv.GetCount():
            self.conv.SetSelection(min(selection, self.conv.GetCount() - 1))

    # ---------- menu de contexto das mensagens ----------

    def message_menu(self):
        """Tecla de aplicativos, Shift+F10 ou clique direito na conversa."""
        row = self._selected_row()
        if not row:
            return
        kind, value = row
        actions = [("&Ler mensagem\tEnter", self.open_message), ("&Copiar\tCtrl+C", self.copy_message)]
        found = self._row_links(row)
        if found:
            actions.append((f"Lin&ks e arquivos: {links.summary(found)}…\tCtrl+L", self.show_links))
        if kind == "queued":
            actions += [("&Editar mensagem agendada…", self.edit_message),
                        ("&Remover da fila\tDelete", self.remove_message)]
        elif self.items[value][0] == "user":
            actions += [("&Editar e reenviar", self.edit_message),
                        ("A&diar: tirar da conversa e pôr na fila", self.postpone_message),
                        ("&Remover da conversa\tDelete", self.remove_message)]
        menu = wx.Menu()
        for label, handler in actions:
            item = menu.Append(wx.ID_ANY, label)
            menu.Bind(wx.EVT_MENU, lambda e, h=handler: h(), id=item.GetId())
        self.conv.PopupMenu(menu)
        menu.Destroy()

    def edit_message(self):
        row = self._selected_row()
        if not row:
            return
        kind, value = row
        if kind == "queued":
            with wx.TextEntryDialog(self, "Texto da mensagem", "Editar mensagem agendada", value.text,
                                    style=wx.TE_MULTILINE | wx.OK | wx.CANCEL) as dialog:
                if dialog.ShowModal() != wx.ID_OK or not dialog.GetValue().strip():
                    return
                text = dialog.GetValue().strip()
            for index, queued in enumerate(self.queue.items):
                if queued is value:
                    self.queue.edit(index, text)
            self.refresh_queued_rows()
            self.announce("Mensagem agendada editada.")
            return
        self.rewind(value, "edit")

    def postpone_message(self):
        row = self._selected_row()
        if row and row[0] == "item":
            self.rewind(row[1], "postpone")

    def remove_message(self):
        row = self._selected_row()
        if not row:
            return
        kind, value = row
        if kind == "queued":
            for index, queued in enumerate(self.queue.items):
                if queued is value:
                    self.queue.remove(index)
                    break
            self.update_awake()
            self.refresh_queued_rows()
            self.announce("Mensagem removida da fila.")
            return
        if self.items[value][0] != "user":
            self.set_status("Só as suas mensagens podem ser removidas.")
            return
        self.rewind(value, "remove")

    _REWIND_VERB = {"edit": "Editar", "postpone": "Adiar", "remove": "Remover"}

    def rewind(self, index, action):
        """Volta a conversa para antes da mensagem `index` da pessoa, como o
        rewind do Claude Code. O arquivo da sessão só muda quando a próxima
        mensagem for enviada; até lá o app guarda o ponto de volta."""
        if self.items[index][0] != "user":
            self.set_status("Só as suas mensagens podem ser editadas, adiadas ou removidas.")
            return
        if self.state not in ("Pronto", "Erro") or self.request is not None:
            self.set_status("Espere a resposta terminar. Escape interrompe.")
            return
        sid = self.worker.session_id
        if not sid:
            self.set_status("A sessão ainda não foi gravada. Espere a primeira resposta.")
            return
        after = len(self.items) - index - 1
        text = (f"{self._REWIND_VERB[action]} volta a conversa para antes da mensagem {index + 1}. "
                "Ela sai da conversa")
        text += f", junto com as {after} mensagens depois dela." if after > 1 else (
            ", junto com a resposta do Claude." if after == 1 else ".")
        if action == "edit":
            text += " O texto vai para a caixa de mensagem para você mudar e enviar."
        elif action == "postpone":
            text += " O texto vai para a fila e sai quando o limite renovar ou o Claude ficar livre."
        if wx.MessageBox(text + " Continuar?", self._REWIND_VERB[action] + " mensagem",
                         wx.YES_NO | wx.NO_DEFAULT, self) != wx.YES:
            return
        expected = self.items[index][1]
        cwd = self.session_cwd
        self.set_status("Voltando a conversa…")

        def work():
            try:
                result, error = sessions.load_history_points(sid, cwd or None), None
            except Exception as exc:
                result, error = None, str(exc)
            wx.CallAfter(self._rewind_loaded, sid, index, expected, action, result, error)

        threading.Thread(target=work, daemon=True).start()

    def _rewind_loaded(self, sid, index, expected, action, result, error):
        if not self or self.worker.session_id != sid:
            return
        if error:
            self.set_status("Não consegui ler o histórico da sessão: " + error)
            return
        items, points, last, files = result
        same = (index < len(items) and items[index][0] == "user"
                and formatting.one_line(items[index][1]) == formatting.one_line(expected))
        if not same:
            self.set_status("Não encontrei esta mensagem no histórico gravado. Atualize a sessão e tente de novo.")
            return
        at = points.get(index)
        if not at:
            self.set_status("É a primeira mensagem da sessão: não há para onde voltar. "
                            "Para recomeçar, use Ctrl+N e envie de novo.")
            return
        rewinds = dict(self.config.get("rewinds") or {})
        rewinds[sid] = {"at": at, "keep": index, "last": last}
        self.config["rewinds"] = rewinds
        self.save_config()
        self.worker.start_session(sid, self.session_cwd, resume_at=at)
        self.load_items(items[:index], files)
        if action == "edit":
            self.msg.SetValue(expected)
            self.msg.SetInsertionPointEnd()
            self.msg.SetFocus()
            self.announce(f"Conversa voltou para antes da mensagem {index + 1}. Edite e envie com Enter.")
        elif action == "postpone":
            self.add_to_queue(expected)
        else:
            if self.conv.GetCount():
                self.conv.SetSelection(self.conv.GetCount() - 1)
            self.announce("Mensagem removida; a conversa voltou para antes dela.")

    # ---------- sessões ----------

    def refresh_sessions(self):
        self.set_status("Carregando sessões…")

        def work():
            try:
                entries = sessions.list_user_sessions()
                error = None
            except Exception as exc:
                entries, error = [], str(exc)
            wx.CallAfter(self._fill_sessions, entries, error)

        threading.Thread(target=work, daemon=True).start()

    def _fill_sessions(self, entries, error):
        if not self:
            return
        self.session_entries = entries
        self.fill_tree()
        self.set_status(f"Erro ao listar sessões: {error}" if error else f"{len(entries)} sessões encontradas.")

    def fill_tree(self):
        """Monta a árvore: Nova sessão e depois as pastas. Cada
        grupo começa com um item para criar sessão nele. Guarda o que estava
        selecionado e os grupos abertos."""
        tree = self.sess
        keep = self._tree_ident(self._tree_data())
        expanded = set(self.config.get("expanded_groups") or [])
        self.filling_tree = True
        tree.DeleteAllItems()
        root = tree.AddRoot("Sessões")
        select = tree.AppendItem(root, NEW_SESSION_TITLE, data=("new", None))
        groups = subjects.group_sessions(self.session_entries)
        for group in groups:
            node = tree.AppendItem(root, group.label(), data=("group", group))
            tree.AppendItem(node, f"{NEW_SESSION_TITLE} nesta pasta", data=("new", group))
            for entry in group.entries:
                item = tree.AppendItem(node, entry.label(show_folder=False),
                                       data=("session", entry))
                if keep == "session:" + entry.session_id:
                    select = item
            if keep == group.ident:
                select = node
            if group.ident in expanded or (select != node and tree.GetItemParent(select) == node):
                tree.Expand(node)
        tree.SelectItem(select)
        self.filling_tree = False

    def _tree_data(self, item=None):
        item = item if item is not None else self.sess.GetSelection()
        if not item or not item.IsOk() or item == self.sess.GetRootItem():
            return None
        return self.sess.GetItemData(item)

    @staticmethod
    def _tree_ident(data):
        if not data:
            return None
        kind, value = data
        if kind == "session":
            return "session:" + value.session_id
        if kind == "group":
            return value.ident
        return None

    def _remember_expanded(self):
        if getattr(self, "filling_tree", False):
            return
        tree, opened = self.sess, []
        child, cookie = tree.GetFirstChild(tree.GetRootItem())
        while child.IsOk():
            data = tree.GetItemData(child)
            if data and data[0] == "group" and tree.IsExpanded(child):
                opened.append(data[1].ident)
            child, cookie = tree.GetNextChild(tree.GetRootItem(), cookie)
        self.config["expanded_groups"] = opened
        self.save_config()

    def open_session(self):
        item = self.sess.GetSelection()
        data = self._tree_data(item)
        if not data:
            return
        kind, value = data
        if kind == "group":
            self.sess.Toggle(item)
        elif kind == "new":
            self.new_session(value.cwd if value else None)
        else:
            self.resume_session(value.session_id, value.cwd, value.title)

    # ---------- mover sessão de pasta ----------

    def move_session(self):
        """Ctrl+M: move a sessão escolhida na árvore para o grupo de outra
        pasta. O arquivo da sessão vai para a pasta de projeto do destino."""
        data = self._tree_data() if wx.Window.FindFocus() is self.sess else None
        if not data or data[0] != "session":
            self.set_status("Para mover, escolha uma sessão na árvore (Alt+1) e aperte Ctrl+M.")
            return
        entry = data[1]
        if entry.session_id == self.worker.session_id:
            self.set_status("Esta sessão está aberta. Abra outra sessão ou crie uma nova e mova esta de lá.")
            return
        here = subjects.folder_key(entry.cwd)
        groups = [g for g in subjects.group_sessions(self.session_entries) if g.key != here and g.cwd]
        choices = [f"{g.name} ({g.cwd})" if g.name != g.cwd else g.cwd for g in groups]
        choices.append("Outra pasta do computador…")
        with wx.SingleChoiceDialog(self, f"Mover a sessão {entry.title} para a pasta",
                                   "Mover sessão para outra pasta", choices) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            index = dialog.GetSelection()
        if index < len(groups):
            target, like = groups[index].cwd, groups[index].entries[0].session_id
        else:
            with wx.DirDialog(self, "Pasta de destino da sessão", self.cwd or "") as picker:
                if picker.ShowModal() != wx.ID_OK:
                    return
                target = picker.GetPath()
            like = next((e.session_id for e in self.session_entries
                         if subjects.folder_key(e.cwd) == subjects.folder_key(target)), None)
        folder = os.path.basename(target.rstrip("\\/")) or target
        if wx.MessageBox(f"Mover a sessão {entry.title} para a pasta {folder}? O arquivo dela muda de lugar "
                         "no Claude Code; vale também no aplicativo Claude e no terminal. Arquivos do projeto "
                         "não são mexidos.", "Mover sessão", wx.YES_NO | wx.NO_DEFAULT, self) != wx.YES:
            return
        try:
            sessions.move_session_file(entry.session_id, entry.cwd, target, like)
        except OSError as exc:
            self.set_status(f"Não consegui mover a sessão: {exc}")
            self.write_log(f"ERRO ao mover sessão {entry.session_id}: {exc}")
            return
        entry.cwd = target
        self.fill_tree()
        self.announce(f"Sessão movida para a pasta {folder}.")
        self.refresh_sessions()

    def export_memories(self):
        """Arquivo, Exportar: grava num .zip o CLAUDE.md global, os comandos e a
        memória de cada pasta. Não leva sessões nem credenciais."""
        default = f"claude-memorias-{datetime.date.today():%Y-%m-%d}.zip"
        with wx.FileDialog(self, "Exportar preferências e memórias", defaultFile=default,
                           wildcard="Pacote zip (*.zip)|*.zip",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            dest = dialog.GetPath()
        try:
            count, secrets = transfer.export_zip(dest)
        except OSError as exc:
            self.set_status(f"Não consegui exportar: {exc}")
            self.write_log(f"ERRO ao exportar memórias: {exc}")
            return
        text = f"Exportei {count} arquivos para {os.path.basename(dest)}. O pacote não leva sessões nem login."
        if secrets:
            text += (" Atenção: estes arquivos parecem conter chave ou senha, confira antes de compartilhar: "
                     + ", ".join(secrets) + ".")
            wx.MessageBox(text, "Exportar preferências e memórias", wx.OK | wx.ICON_WARNING, self)
        self.announce(text)

    def _ask_folder_mapping(self, src):
        """Pastas de memória do pacote que não existem aqui com o mesmo caminho
        precisam de um destino (o nome da pasta de memória vem do caminho).
        Devolve {pasta no pacote: novo caminho, ou None para não importar},
        None se não há o que mapear, ou False se a pessoa desistiu."""
        folders = transfer.unmatched_folders(transfer.package_folders(src))
        if not folders:
            return None
        names = [f.path or f"{f.key} (caminho original desconhecido)" for f in folders]
        shown = NL.join(names[:12]) + (f"{NL}… e mais {len(names) - 12}." if len(names) > 12 else "")
        message = (f"{len(folders)} pastas do pacote não existem aqui com o mesmo caminho:{NL}{shown}{NL}{NL}"
                   "O que fazer com a memória delas?")
        choices = ["Trocar o começo do caminho de todas (por exemplo, de C: para D:, ou de uma pasta para outra)",
                   "Escolher a pasta de destino de cada uma",
                   "Importar sem mudar o nome (para quando eu criar as pastas com o mesmo caminho)",
                   "Não importar a memória dessas pastas"]
        with wx.SingleChoiceDialog(self, message, "Pastas que não existem aqui", choices) as picker:
            if picker.ShowModal() != wx.ID_OK:
                return False
            option = picker.GetSelection()
        if option == 2:
            return None
        if option == 3:
            return {f.key: None for f in folders}
        mapping = {}
        if option == 0:
            with wx.DirDialog(self, "Pasta que passa a ser o começo dos caminhos", self.cwd or "") as picker:
                if picker.ShowModal() != wx.ID_OK:
                    return False
                mapping = transfer.suggest_mapping(folders, picker.GetPath())
            # As sem caminho conhecido não dá para trocar pelo começo: ficam como estão.
        else:
            for f in folders:
                title = f"Pasta de destino para {f.path or f.key}"
                with wx.DirDialog(self, title, self.cwd or "") as picker:
                    if picker.ShowModal() == wx.ID_OK:
                        mapping[f.key] = picker.GetPath()
                    else:
                        mapping[f.key] = None  # cancelar = não importar esta pasta
        lines = [f"{f.path or f.key}  →  {mapping[f.key] or 'não importar'}" for f in folders if f.key in mapping]
        more = f"{NL}… e mais {len(lines) - 15}." if len(lines) > 15 else ""
        if wx.MessageBox(f"Vai ficar assim:{NL}{NL.join(lines[:15])}{more}{NL}{NL}Continuar?",
                         "Pastas de destino", wx.YES_NO | wx.YES_DEFAULT, self) != wx.YES:
            return False
        return mapping

    def import_memories(self):
        """Arquivo, Importar: lê um pacote exportado e põe no lugar certo, sem
        apagar nada: ou só acrescenta o que falta, ou também troca os arquivos
        diferentes depois de guardar uma cópia dos atuais."""
        with wx.FileDialog(self, "Importar preferências e memórias",
                           wildcard="Pacote zip (*.zip)|*.zip",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            src = dialog.GetPath()
        try:
            mapping = self._ask_folder_mapping(src)
            if mapping is False:
                return
            items, ignored = transfer.plan_import(src, mapping=mapping)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.set_status(f"Não consegui ler o pacote: {exc}")
            return
        new, different, same = transfer.summarize(items)
        if not new and not different:
            self.announce(f"Nada a importar: os {same} arquivos do pacote já são iguais aos daqui.")
            return
        choices = [f"Só acrescentar o que falta aqui ({new} novos)"]
        if different:
            choices.append(f"Acrescentar e também trocar os {different} que são diferentes "
                           "(guarda uma cópia dos atuais)")
        message = (f"O pacote tem {new} arquivos novos, {different} diferentes dos daqui e {same} iguais."
                   + (f" {len(ignored)} itens fora do padrão foram ignorados." if ignored else ""))
        with wx.SingleChoiceDialog(self, message, "Importar preferências e memórias", choices) as picker:
            if picker.ShowModal() != wx.ID_OK:
                return
            replace = picker.GetSelection() == 1
        try:
            created, replaced, backup = transfer.import_zip(src, replace, mapping=mapping)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.set_status(f"Não consegui importar: {exc}")
            self.write_log(f"ERRO ao importar memórias: {exc}")
            return
        text = f"Importei {created} arquivos novos"
        if replaced:
            text += f" e troquei {replaced}; a cópia dos atuais está em {backup}"
        text += ". Vale a partir da próxima sessão."
        self.write_log(text)
        self.announce(text)

    def rename_selected(self):
        """F2: renomeia a sessão escolhida na árvore; em outro lugar, a sessão aberta."""
        data = self._tree_data() if wx.Window.FindFocus() is self.sess else None
        if data and data[0] in ("group", "new"):
            return
        self.rename_session()

    def _select_group(self, ident):
        tree = self.sess
        child, cookie = tree.GetFirstChild(tree.GetRootItem())
        while child.IsOk():
            if self._tree_ident(tree.GetItemData(child)) == ident:
                tree.SelectItem(child)
                return
            child, cookie = tree.GetNextChild(tree.GetRootItem(), cookie)

    def tree_menu(self):
        """Tecla de aplicativos ou clique direito na árvore."""
        data = self._tree_data()
        menu = wx.Menu()
        actions = []
        if data and data[0] == "session":
            actions += [("&Abrir sessão", self.open_session), ("&Mover para outra pasta…\tCtrl+M", self.move_session),
                        ("&Renomear sessão…\tF2", self.rename_selected)]
        for label, handler in actions:
            item = menu.Append(wx.ID_ANY, label)
            menu.Bind(wx.EVT_MENU, lambda e, h=handler: h(), id=item.GetId())
        self.sess.PopupMenu(menu)
        menu.Destroy()

    def resume_session(self, session_id, cwd, title, then=None):
        """Retoma a sessão e carrega o histórico; `then` roda depois, com a
        conversa já na lista (a fila usa para enviar a mensagem agendada)."""
        self.worker.start_session(session_id, cwd or self.cwd)
        self.session_title = title
        self.session_cwd = cwd or self.cwd
        self.pending_title = None
        self.context, self.reminded_at = None, 0
        self.request = None
        self.load_items([])
        self.set_state("Carregando histórico")

        def work():
            try:
                items, points, last, files = sessions.load_history_points(session_id, cwd or None)
                error = None
            except Exception as exc:
                items, last, files, error = [], None, {}, str(exc)
            wx.CallAfter(self._history_loaded, session_id, items, error, then, last, files)

        threading.Thread(target=work, daemon=True).start()

    def _history_loaded(self, session_id, items, error, then=None, last=None, files=None):
        if not self or self.worker.session_id != session_id:
            return
        point = (self.config.get("rewinds") or {}).get(session_id)
        if point and not error:
            if point.get("last") == last:
                items = items[:point["keep"]]
                self.worker.start_session(session_id, self.session_cwd, resume_at=point["at"])
            else:
                self._drop_rewind(session_id)  # a sessão continuou em outro lugar
        self.load_items(items, files)
        self.set_state("Pronto")
        if error:
            self.set_status("Erro ao carregar histórico: " + error)
        else:
            self.set_status(f"Sessão retomada, {len(items)} mensagens.")
        if then:
            then()
            return
        if self.items:
            self.conv.SetSelection(len(self.items) - 1)
            self.conv.SetFocus()
        else:
            self.msg.SetFocus()

    def rename_session(self):
        """F2: renomeia a sessão escolhida na lista de sessões, ou a sessão
        atual quando o foco está em outro lugar."""
        data = self._tree_data() if wx.Window.FindFocus() is self.sess else None
        if data and data[0] == "session":
            entry = data[1]
            session_id, cwd, current = entry.session_id, entry.cwd, entry.title
        else:
            session_id, cwd = self.worker.session_id, self.session_cwd
            current = self.pending_title or ("" if self.session_title == NEW_SESSION_TITLE
                                             else self.session_title)
        with wx.TextEntryDialog(self, "Novo nome da sessão", "Renomear sessão", current) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            title = formatting.one_line(dialog.GetValue())[:150]
        if not title:
            self.set_status("O nome não pode ficar vazio. A sessão não foi renomeada.")
            return
        if session_id is None:
            self.pending_title = title
            self.session_title = title
            self._update_title()
            self.announce(f"A sessão vai se chamar {title} quando você enviar a primeira mensagem.")
            return
        self._apply_rename(session_id, cwd, title)

    def _apply_rename(self, session_id, cwd, title, announce=True):
        def work():
            try:
                sessions.rename(session_id, title, cwd or None)
                error = None
            except Exception as exc:
                error = str(exc)
            wx.CallAfter(self._renamed, session_id, title, error, announce)

        threading.Thread(target=work, daemon=True).start()

    def _renamed(self, session_id, title, error, announce):
        if not self:
            return
        if error:
            self.set_status("Não consegui renomear a sessão: " + error)
            self.write_log("ERRO renomear " + error)
            return
        if self.worker.session_id == session_id:
            self.session_title = title
            self._update_title()
        for item in self.queue.items:
            if item.session_id == session_id:
                item.session_title = title
        self.queue.save()
        for entry in self.session_entries:
            if entry.session_id == session_id:
                entry.title = title
        self.fill_tree()
        if announce:
            self.announce("Sessão renomeada: " + title)

    def ask_new_session_folder(self):
        """Pergunta em que pasta abrir a sessão nova. Devolve o caminho, ou
        None se a pessoa cancelou. 'Sem pasta' usa a pasta do usuário."""
        home = os.path.expanduser("~")
        choices = [f"Usar a pasta padrão: {self.cwd}",
                   "Escolher outra pasta…",
                   f"Iniciar sem abrir pasta (usa a pasta do usuário: {home})"]
        with wx.SingleChoiceDialog(self, "Em que pasta quer iniciar a nova sessão?",
                                   "Nova sessão", choices) as dialog:
            dialog.SetSelection(0)
            if dialog.ShowModal() != wx.ID_OK:
                return None
            picked = dialog.GetSelection()
        if picked == 0:
            return self.cwd
        if picked == 2:
            return home
        with wx.DirDialog(self, "Escolha a pasta da nova sessão", self.cwd) as picker:
            if picker.ShowModal() != wx.ID_OK:
                return None
            return picker.GetPath()

    def new_session(self, cwd=None, group=None):
        if cwd is None and group is None:
            cwd = self.ask_new_session_folder()
            if cwd is None:
                return
        cwd = cwd or self.cwd
        self.worker.start_session(None, cwd)
        self.session_title = NEW_SESSION_TITLE
        self.session_cwd = cwd
        self.new_group = group or uuid.uuid4().hex
        self.pending_title = None
        self.context, self.reminded_at = None, 0
        self.request = None
        self.load_items([])
        self.set_state("Pronto")
        self.set_status("Nova sessão na pasta " + cwd)
        self.msg.SetFocus()

    def choose_folder(self):
        with wx.DirDialog(self, "Escolha a pasta de trabalho para novas sessões", self.cwd) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.cwd = dialog.GetPath()
        self.config["cwd"] = self.cwd
        sessions.save_config(self.config)
        if self.worker.session_id is None and not self.items:
            self.worker.start_session(None, self.cwd)
            self.session_cwd = self.cwd
        self.set_status("Pasta de trabalho para novas sessões: " + self.cwd)

    # ---------- fila para quando o limite renovar ----------

    def limited(self):
        return bool(self.limited_until) and not scheduled.is_due(self.limited_until)

    def set_limit(self, resets_at):
        self.limited_until = resets_at or None
        self.config["limit_resets_at"] = self.limited_until
        self.save_config()

    def update_awake(self):
        scheduled.keep_awake(bool(self.queue.items))

    def _queue_when(self):
        return scheduled.when_text(self.limited_until if self.limited() else None)

    def enqueue(self):
        text = self.msg.GetValue().strip()
        if not text:
            self.set_status("Escreva a mensagem antes de agendar.")
            return
        self.msg.SetValue("")
        self.add_to_queue(text)

    def add_to_queue(self, text):
        item = scheduled.Item(text, self.worker.session_id, self.session_cwd, self.session_title,
                              group=self.worker.session_id or self.new_group)
        position = self.queue.add(item)
        self.update_awake()
        self.refresh_queued_rows()
        self.announce(f"Mensagem na fila, posição {position}. Sai {self._queue_when()}.")
        wx.CallAfter(self.check_queue)

    def _drop_rewind(self, session_id):
        rewinds = dict(self.config.get("rewinds") or {})
        if rewinds.pop(session_id, None) is not None:
            self.config["rewinds"] = rewinds
            self.save_config()

    def open_queue(self):
        with QueueDialog(self, self.queue, self._queue_when()) as dialog:
            dialog.ShowModal()
        self.update_awake()
        self.refresh_queued_rows()
        self.set_status(f"Mensagens na fila: {len(self.queue)}.")

    def _announce_queue_at_start(self):
        if self and self.queue.items:
            self.announce(f"Mensagens na fila: {len(self.queue)}. Saem {self._queue_when()}.")

    def check_queue(self):
        """Chamada pelo relógio: com o limite renovado e o Claude livre, envia a
        próxima mensagem da fila, na sessão em que ela foi escrita."""
        if not self or self.running_item or not self.queue.items or self.limited():
            return
        if self.state not in ("Pronto", "Erro") or self.request is not None:
            return
        if self.limited_until:
            self.set_limit(None)  # já renovou
        item = self.queue.first()
        self.running_item = item
        self.announce(f"Enviando mensagem agendada, {len(self.queue)} na fila.")
        send = lambda: self.send_text(item.text)
        if item.session_id and item.session_id == self.worker.session_id:
            send()
        elif item.session_id:
            self.resume_session(item.session_id, item.cwd, item.session_title, then=send)
        elif self.worker.session_id is None and item.group == self.new_group:
            send()
        else:
            self.new_session(item.cwd, item.group)
            send()

    def _scheduled_done(self, error):
        item, self.running_item = self.running_item, None
        if item is None:
            return
        if error and self.limited():
            self.announce("Ainda no limite. A mensagem continua na fila e sai "
                          + self._queue_when() + ".")
            return
        for index, queued in enumerate(self.queue.items):
            if queued is item:
                self.queue.remove(index)
                break
        if item.session_id is None and self.worker.session_id:
            self.queue.bind_session(item.group, self.worker.session_id)
        self.update_awake()
        self.refresh_queued_rows()
        if self.queue.items:
            wx.CallLater(3000, self.check_queue)
        else:
            self.announce("Fila de mensagens agendadas concluída.")

    # ---------- conta ----------

    def login(self):
        if not self.cli:
            self.set_status("Não encontrei o Claude Code. Reinstale o pacote claude-agent-sdk.")
            return
        subprocess.Popen([self.cli, "auth", "login"], creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.set_status("Abri a janela de login da Anthropic. Depois de entrar, use Conta, Verificar conexão.")

    def check_login(self):
        if not self.cli:
            self.set_status("Não encontrei o Claude Code.")
            return

        def work():
            try:
                out = subprocess.run([self.cli, "auth", "status"], capture_output=True, text=True,
                                     timeout=30, creationflags=subprocess.CREATE_NO_WINDOW).stdout
                info = json.loads(out)
                if info.get("loggedIn"):
                    text = "Conectado à conta Claude."
                else:
                    text = "Não conectado. Use o menu Conta, Entrar na conta Claude."
            except Exception as exc:
                text = f"Não consegui verificar a conexão: {exc}"
            wx.CallAfter(lambda: self and self.set_status(text))

        threading.Thread(target=work, daemon=True).start()

    # ---------- registro e saída ----------

    def write_log(self, text):
        try:
            path = log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
        except OSError:
            pass

    def on_close(self, event):
        self.queue_timer.Stop()
        scheduled.keep_awake(False)
        self.worker.close()
        event.Skip()


def main():
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
