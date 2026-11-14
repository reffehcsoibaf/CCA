import formatting
import markup


def test_negrito_italico_tachado():
    assert markup.announce("isto é **muito** bom") == "isto é negrito: muito bom"
    assert markup.announce("isto é *muito* bom") == "isto é itálico: muito bom"
    assert markup.announce("isto é _muito_ bom") == "isto é itálico: muito bom"
    assert markup.announce("isto é ~~errado~~") == "isto é tachado: errado"


def test_trecho_longo_diz_onde_acaba():
    assert markup.announce("**um dois três quatro cinco seis sete oito nove** fim") == \
        "negrito: um dois três quatro cinco seis sete oito nove, fim do negrito fim"


def test_titulo_e_item():
    assert markup.announce("## Resumo\n- um\n* dois") == "título: Resumo\nitem: um\nitem: dois"


def test_codigo_fica_como_esta():
    assert markup.announce("rode `a **b** c`") == "rode código: a **b** c"
    assert markup.announce("```py\nx = 2*3*4\n```") == "código: x = 2*3*4"


def test_nao_mexe_no_que_nao_e_formatacao():
    assert markup.announce("nome_do_arquivo.py") == "nome_do_arquivo.py"
    assert markup.announce("veja https://a.com/x_y_z") == "veja https://a.com/x_y_z"
    assert markup.announce("2*3") == "2 vezes 3"


def test_item_label_anuncia():
    assert formatting.item_label("assistant", 1, "Feito **ok**") == "Claude, mensagem 1: Feito negrito: ok"
