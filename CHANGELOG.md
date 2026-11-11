# Registro de mudanças

Versões no formato `ano.mês.dia.dígito` (o dígito começa em 0 e sobe se houver mais de uma versão no mesmo dia), o mesmo padrão do TeleZapp. Mais novas primeiro.

Cada versão é publicada como release no GitHub, sempre marcada como Latest. A tag e o título da release são o próprio número. O número também fica em `VERSION` no `formatting.py` e aparece no título da janela.

## 2026.11.10.0

Primeira versão no GitHub. Registro da evolução do app a partir daqui.

Atualização pelo app: ao abrir (no máximo uma vez por dia) e em Ajuda, Verificar atualizações, o app consulta as releases do GitHub. Se há versão nova, abre uma janela com as novidades desde a sua versão e pergunta se quer instalar. Instalar baixa o zip de atualização, confere o SHA-256, troca os arquivos do programa e abre de novo. Sessões, preferências e fila ficam em outra pasta e não são afetadas. Cópia de desenvolvimento (com pasta .git) só oferece a página de download. Em Ajuda, Sobre, versão, o app fala a versão em uso.

Medição de alcance: cada release tem dois zips iguais, CCA-versão.zip (baixado pela página) e CCA-versão-atualizacao.zip (baixado só pelo atualizador). downloads.cmd mostra a contagem de downloads do GitHub por versão, separando os dois. publicar.cmd monta os zips e publica a release sempre como Latest.
