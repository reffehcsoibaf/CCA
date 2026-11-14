# Registro de mudanças

Versões no formato `ano.mês.dia.dígito` (o dígito começa em 0 e sobe se houver mais de uma versão no mesmo dia), o mesmo padrão do TeleZapp. Mais novas primeiro.

Cada versão é publicada como release no GitHub, sempre marcada como Latest. A tag e o título da release são o próprio número. O número também fica em `VERSION` no `formatting.py` e aparece no título da janela.

## 2026.11.14.0

Nova ordem da tela principal: de cima para baixo, Sessões por pasta, Conversa (a lista de mensagens) e Mensagem (a caixa para escrever). O Tab acompanha essa ordem, e Alt+1, Alt+2 e Alt+3 continuam levando a cada uma. O foco inicial continua na caixa de mensagem.

Som de limite de lista, como no TeleZapp: um toque curto quando você aperta seta para cima no primeiro item ou seta para baixo no último de qualquer lista (conversa, fila, sessões, links e as demais janelas). Pode ser desligado em Configurações, Som no início ou fim de uma lista.

Formatação dita em vez de símbolos, como no TeleZapp: na lista da conversa, na janela da mensagem (Enter) e na resposta falada, "**texto**" vira "negrito: texto", "*texto*" e "_texto_" viram "itálico: texto", "~~texto~~" vira "tachado: texto", "# Título" vira "título: Título", "- item" vira "item: item" e o código vira "código: ...". Trechos longos dizem onde acabam ("fim do negrito"). Endereços, nomes_com_sublinhado, contas como 2*3 e o conteúdo do código não são mexidos. O texto guardado e o que se copia continuam originais.

Fila presa depois de um reset do limite: quando o limite acabava, tudo ia para a fila até o horário de renovação previsto, mesmo que o limite voltasse antes, porque nada era enviado e o Claude Code nunca avisava que tinha liberado. Agora, no limite, o app consulta o /usage a cada 10 minutos (não gasta uso) e, se nenhum limite estiver em 100%, libera o Enter e envia a fila. Alt+L também libera ao ver o limite livre. Novo comando Claude, Enviar a fila agora (Ctrl+Shift+F), e botão Enviar agora na janela da fila. Um erro de limite sem horário não tira mais a mensagem da fila: ela fica e o app tenta de novo em 10 minutos.

Ordem da fila: Alt+Seta para cima e para baixo mudam a ordem na janela da fila (Alt+F) e nas mensagens agendadas da conversa, com a nova posição falada. O menu de contexto das agendadas ganhou Subir na fila e Descer na fila.

Mais etapas faladas pelo NVDA: cada comando é falado pela descrição que o Claude dá (por exemplo "Abrir a PR", "Mesclar no main"), e não só "Executando comando". Ações iguais seguidas, que antes eram caladas, agora são faladas. Pesquisas, buscas no código e páginas abertas dizem o que estão procurando. As ações dos subagentes são faladas com "Subagente:" na frente, e "Pensando" avisa quando o Claude começa a pensar.

Navegar pelo Chrome: nova opção em Claude, Navegar pelo Chrome (e em Configurações), que liga a extensão Claude in Chrome, a mesma do aplicativo Claude. O Claude passa a abrir páginas, ler, clicar e preencher no Chrome que você já tem aberto, e o resultado volta para a conversa. Cada ação pede a sua confirmação, com a frase em português (por exemplo "Abrindo no Chrome https://…"), e as etapas são faladas pelo NVDA. Vale a partir da próxima mensagem, mantendo a conversa. Exige o Chrome aberto, com a extensão entrada na sua conta.

## 2026.11.10.0

Primeira versão no GitHub. Registro da evolução do app a partir daqui.

Atualização pelo app: ao abrir (no máximo uma vez por dia) e em Ajuda, Verificar atualizações, o app consulta as releases do GitHub. Se há versão nova, abre uma janela com as novidades desde a sua versão e pergunta se quer instalar. Instalar baixa o zip de atualização, confere o SHA-256, troca os arquivos do programa e abre de novo. Sessões, preferências e fila ficam em outra pasta e não são afetadas. Cópia de desenvolvimento (com pasta .git) só oferece a página de download. Em Ajuda, Sobre, versão, o app fala a versão em uso.

Medição de alcance: cada release tem dois zips iguais, CCA-versão.zip (baixado pela página) e CCA-versão-atualizacao.zip (baixado só pelo atualizador). downloads.cmd mostra a contagem de downloads do GitHub por versão, separando os dois. publicar.cmd monta os zips e publica a release sempre como Latest.
