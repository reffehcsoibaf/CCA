import wx

import feedback
import list_edge


class FakeList:
    def __init__(self, count, index):
        self._c, self._i = count, index

    def GetCount(self):
        return self._c

    def GetSelection(self):
        return self._i


def test_bate_no_inicio_e_no_fim():
    assert list_edge.at_edge(FakeList(5, 0), wx.WXK_UP)
    assert list_edge.at_edge(FakeList(5, 4), wx.WXK_DOWN)
    assert list_edge.at_edge(FakeList(1, 0), wx.WXK_UP)


def test_no_meio_ou_com_modificadores_nao_bate():
    assert not list_edge.at_edge(FakeList(5, 2), wx.WXK_UP)
    assert not list_edge.at_edge(FakeList(5, 0), wx.WXK_DOWN)
    assert not list_edge.at_edge(FakeList(5, 0), wx.WXK_UP, shift=True)
    assert not list_edge.at_edge(FakeList(5, 0), wx.WXK_UP, ctrl_or_alt=True)
    assert not list_edge.at_edge(FakeList(0, -1), wx.WXK_UP)
    assert not list_edge.at_edge(object(), wx.WXK_UP)
    assert not list_edge.at_edge(FakeList(5, 0), wx.WXK_LEFT)


def test_som_existe(tmp_path):
    feedback.ensure_sounds(str(tmp_path))
    assert (tmp_path / "limite.wav").exists()
