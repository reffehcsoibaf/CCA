"""Som ao bater no início ou no fim de uma lista: seta para cima no primeiro
item ou seta para baixo no último, em qualquer lista do programa (janela
principal e todas as janelas). Um filtro de eventos do wx vê as teclas antes
de chegarem ao controle, então nenhuma janela precisa cuidar disso, e a tecla
segue o caminho normal. Portado do TeleZapp."""

import wx

import feedback

_filter = None


def position(ctrl):
    """(quantos itens, índice do item atual) se `ctrl` é uma lista; senão None."""
    if hasattr(ctrl, "GetCount") and hasattr(ctrl, "GetSelection"):
        count, index = ctrl.GetCount(), ctrl.GetSelection()
    elif hasattr(ctrl, "GetItemCount") and hasattr(ctrl, "GetFocusedItem"):
        count, index = ctrl.GetItemCount(), ctrl.GetFocusedItem()
    else:
        return None
    if not isinstance(count, int) or not isinstance(index, int):
        return None
    return count, index


def at_edge(ctrl, key, shift=False, ctrl_or_alt=False):
    """A tecla (cima ou baixo) bate no começo ou no fim da lista?"""
    if key not in (wx.WXK_UP, wx.WXK_DOWN) or shift or ctrl_or_alt:
        return False
    found = position(ctrl)
    if found is None or found[0] == 0:
        return False
    count, index = found
    return (key == wx.WXK_UP and index == 0) or (key == wx.WXK_DOWN and index == count - 1)


def install(enabled=lambda: True):
    """Liga o som em todas as janelas (uma vez, depois de criar o wx.App).
    `enabled` diz se o som está ligado nas configurações."""
    global _filter
    if _filter is not None:
        return _filter

    class Filter(wx.EventFilter):
        def __init__(self):
            super().__init__()
            wx.EvtHandler.AddFilter(self)

        def FilterEvent(self, evt):
            try:
                if (evt.GetEventType() == wx.wxEVT_KEY_DOWN and enabled()
                        and at_edge(evt.GetEventObject(), evt.GetKeyCode(), evt.ShiftDown(),
                                    evt.ControlDown() or evt.AltDown())):
                    feedback.play("limite")
            except Exception:
                pass
            return wx.EventFilter.Event_Skip

    _filter = Filter()
    return _filter
