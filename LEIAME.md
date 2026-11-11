# CCA, Claude Code Acessível (protótipo)

CCA é o nome curto do app (antes chamado "Claude Acessível"). Janela leve, feita só com controles padrão do Windows, para conversar com o Claude Code pelo Claude Agent SDK, sem ler a árvore de acessibilidade do aplicativo Claude.

## Instalação e uso

Requer Python 3.10 ou mais novo, com wxPython e claude-agent-sdk:

    python -m pip install wxPython claude-agent-sdk

Para abrir: Enter no atalho "Abrir CCA" nesta pasta. Ele chama o pythonw do Python 3.13 direto, sem janela de terminal. O `abrir.cmd` também funciona, mas sempre mostra um terminal antes de abrir o app.

O app inicia o Claude Code com a opção do Windows que não cria janela de console. Sem isso, com o Windows Terminal como terminal padrão, aparecia uma aba "claude" que o NVDA lia. Para conferir: `pythonw tests\console_check.pyw` grava em `tests\console_check.txt` se algum console visível apareceu.

Na primeira vez, use o menu Conta, Entrar na conta Claude. Abre uma janela do próprio Claude Code com o login oficial da Anthropic; o app nunca vê nem guarda senha ou token. Se a variável ANTHROPIC_API_KEY estiver definida, a chave de API é usada no lugar da assinatura.

## Atalhos

- Alt+1: árvore de sessões, agrupadas pela pasta de trabalho, como os projetos do aplicativo Claude. Primeiro vem Nova sessão e depois as pastas. Seta para a direita abre o grupo e para a esquerda fecha; Enter num grupo também abre e fecha. Dentro de cada grupo, o primeiro item cria uma sessão nova naquela pasta, e as sessões vêm das mais recentes para as mais antigas. Enter numa sessão retoma a sessão. A tecla de aplicativos abre um menu com os comandos do item.
- Ctrl+M na árvore: mover a sessão escolhida para outra pasta, para corrigir uma sessão que ficou na pasta errada. Na lista estão as outras pastas da árvore e Outra pasta do computador…. O app move o arquivo da sessão para a pasta de projeto do destino e troca a pasta registrada dentro dele; vale também no aplicativo Claude e no terminal. Antes de mover pede confirmação. Uma sessão aberta não pode ser movida: abra outra ou crie uma nova antes. Arquivos do projeto não são mexidos.
- Alt+2: lista das mensagens da sessão, um item por mensagem. Enter abre o texto completo, somente leitura; Ctrl+C copia a mensagem. As mensagens agendadas desta sessão aparecem no fim, como "Você, agendada, sai hoje às 17:11".
- Ctrl+L na conversa: links e arquivos da mensagem. Quando uma mensagem tem links ou arquivos, o item diz logo no começo, por exemplo "Claude, mensagem 4, 1 link e 2 arquivos". Entram os endereços da web, os links que o Claude escreve (como app.py, que aponta para o arquivo do projeto), caminhos do Windows, referências @"caminho", nomes de arquivo entre crases e os arquivos que o Claude criou ou editou naquela resposta. Arquivos só aparecem se existirem. Na janela: Enter ou Abrir abre o link no navegador ou o arquivo no programa padrão (scripts e programas, como .py, .bat e .exe, abrem no Bloco de Notas em vez de rodar); Ler aqui mostra o conteúdo de um arquivo de texto numa caixa somente leitura; Abrir pasta abre o Explorer com o arquivo selecionado; Copiar endereço copia o link ou o caminho. Na janela de ler a mensagem (Enter) também há o botão Links e arquivos, e o item aparece no menu de contexto.
- Menu de contexto da conversa (tecla de aplicativos ou Shift+F10): Ler e Copiar em qualquer mensagem. Nas suas mensagens também Editar e reenviar, Adiar e Remover (Delete). As três voltam a conversa para antes da mensagem, como o rewind do Claude Code, e pedem confirmação: ela e o que veio depois saem da conversa. Editar põe o texto na caixa de mensagem; Adiar põe na fila. A volta fica gravada no arquivo da sessão quando a próxima mensagem é enviada; até lá o app guarda o ponto e mantém a conversa voltada ao retomar a sessão. A primeira mensagem de uma sessão não pode ser removida. Arquivos alterados pelo Claude não voltam. Nas mensagens agendadas: Editar e Remover da fila.
- Alt+3: caixa para escrever. Enter envia, Ctrl+Enter quebra linha, Ctrl+V com arquivos copiados no Explorer insere `@"caminho"`.
- Quando o Claude pergunta ou pede permissão, abre uma janela como a de versão nova do TeleZapp: o foco fica no texto somente leitura com a pergunta, e o Tab leva aos botões de resposta. Outro fecha a janela e leva à caixa de mensagem; o que for digitado ali responde a pergunta pendente. Escape fecha a janela sem responder.
- Alt+P: reabre a janela da pergunta pendente, se ela foi fechada com Escape.
- Alt+T: escolher a pasta de trabalho das novas sessões. Também fica no menu Arquivo e em Configurações.
- Alt+S: liga e desliga a fala automática pelo NVDA (etapas, perguntas, pronto).
- Alt+L: consultar o limite de uso.
- Ctrl+K: compactar a conversa, como o /compact do Claude Code. O Claude troca a conversa por um resumo e as próximas mensagens ficam bem mais baratas numa sessão longa. Uma janela pede instruções opcionais para o resumo; deixe em branco para o resumo padrão. As mensagens antigas continuam na lista da conversa.
- Lembrete de compactar: ao fim de cada resposta o app mede a conversa (o mesmo que o /context; não gasta uso). Quando ela passa de 200 mil tokens, o NVDA avisa o tamanho e lembra do Ctrl+K, mesmo com a fala automática desligada; o aviso se repete a cada 100 mil tokens a mais. O limite muda em Configurações, "Lembrar de compactar quando a conversa passar de", onde Nunca desliga. O item Tamanho da conversa, no menu Claude, abre uma janela somente leitura, como a do limite de uso, com o tamanho medido na última resposta.
- Atualizar lista de modelos: no fim do submenu Claude, Modelo, e como botão em Configurações. Pergunta ao Claude Code quais modelos a sua conta tem, sem enviar mensagem e sem gastar uso. Os nomes curtos (Opus, Sonnet, Haiku, Fable) sempre levam ao modelo mais novo da família; os marcados "versão fixa" ficam presos àquela versão. O app também confere sozinho uma vez por semana, ao abrir, e avisa se aparecer modelo novo.
- Alt+F: fila de mensagens agendadas. Enter edita a mensagem escolhida, Delete remove; os botões Subir e Descer mudam a ordem.
- Ctrl+Shift+Enter na caixa de mensagem: põe a mensagem na fila em vez de enviar.
- Ctrl+vírgula: Configurações.
- Escape: interrompe a resposta em andamento.
- F2: renomear a sessão escolhida na árvore ou, em qualquer outro lugar, a sessão aberta. O nome fica gravado na própria sessão, como o /rename do Claude Code, e aparece também no aplicativo Claude e no terminal. Numa sessão nova, o nome é aplicado quando a primeira mensagem termina.
- Ctrl+N: nova sessão. O app pergunta em que pasta abrir: a pasta padrão, outra pasta que você escolhe, ou sem abrir pasta (usa a pasta do usuário). Escape cancela. O item "Nova sessão" da lista de sessões faz a mesma pergunta; o item "Nova sessão nesta pasta" de cada grupo abre direto naquela pasta. F5: atualizar a lista de sessões. Ctrl+Q: sair.
- Arquivo, Exportar preferências e memórias: grava num .zip o CLAUDE.md global, os comandos próprios e a memória de cada pasta de trabalho (os mesmos arquivos que o Claude Code lê no início de cada sessão). Não leva as sessões, o settings.json nem o login. Se algum arquivo parecer ter chave ou senha, o app avisa.
- Arquivo, Importar preferências e memórias: lê um .zip exportado e mostra quantos arquivos são novos, diferentes ou iguais. Duas opções: só acrescentar o que falta, ou também trocar os diferentes, guardando antes uma cópia dos atuais em `%APPDATA%\CCA`. Nada é apagado, e só entram caminhos conhecidos. Vale a partir da próxima sessão. O nome da pasta de memória vem do caminho da pasta de trabalho, então o pacote guarda o caminho original de cada uma. Na importação, as pastas que não existem aqui com o mesmo caminho (num computador novo) ganham destino: trocar o começo do caminho de todas de uma vez (por exemplo, de C:\github para D:\codigo), escolher o destino de cada uma, importar sem mudar o nome ou não importar. O app mostra como vai ficar e pede confirmação antes de gravar. Pastas de que não se descobriu o caminho original aparecem só pelo nome codificado.
- Menus: Arquivo (Alt+A), Claude (Alt+C) e Conta (Alt+O). No menu Claude ficam Modo de permissão, Modelo e Esforço, cada um com as opções marcáveis, além de Fala automática, Compactar a conversa, Consultar limite de uso e Configurações.

## Avisos

- Som de atenção quando o Claude faz uma pergunta ou pede permissão; som de pronto ao fim da resposta; som de erro. Os sons ficam na pasta `sons` e são gerados na primeira vez.
- O NVDA fala as etapas (por exemplo "Lendo arquivo app.py"), a pergunta com as opções e "Pronto". Opcionalmente lê a resposta inteira ao terminar. A fala usa a biblioteca accessible_output2 (`python -m pip install accessible_output2`).
- O modo de permissão e o modelo mudam na hora. O esforço vale a partir da próxima mensagem: o app reinicia o Claude Code mantendo a sessão.
- Trocar de modelo no meio de uma conversa longa gasta mais na mensagem seguinte: o cache do contexto é separado por modelo, e a conversa inteira é enviada de novo. Para usar outro modelo, o mais barato é escolher antes de começar a sessão.
- O Claude Code roda com a mesma instrução de sistema do aplicativo Claude e do terminal.
- Aviso de limite: o Claude Code informa cada limite em separado (5 horas, semanal, semanal do Opus ou do Sonnet). O app compara todos e avisa só do que está mais perto de acabar, dizendo qual é: "Atenção: perto do limite de 5 horas, 93% usado, renova hoje às 23:10". O app fica em silêncio abaixo de 75%. Depois disso fala só duas vezes: ao chegar a 75% e ao chegar a 90%. Se o limite se esgota, avisa uma vez e a fila assume. O aviso só volta a falar se outro limite passar a ser o mais próximo ou depois de o limite renovar. Para saber o uso a qualquer momento, Alt+L mostra todos os limites.
- Quando o limite de uso é atingido, o Enter passa a pôr a mensagem na fila. Um minuto depois da renovação, o app envia as mensagens da fila uma a uma, cada uma na sessão em que foi escrita, esperando cada resposta terminar. Se ainda estiver no limite, a mensagem continua na fila. A fila fica guardada em `%APPDATA%\CCA\fila.json`: se o app estiver fechado na hora, ela sai quando ele abrir de novo. Enquanto houver fila, o app impede o Windows de entrar em suspensão (não impede desligar a tela).
- O limite de uso vem do comando /usage do Claude Code, rodado sem criar sessão e sem gastar uso.

O título da janela mostra o andamento: Respondendo, o nome da ação em curso (por exemplo Lendo arquivo app.py), Aguardando sua resposta, Pronto ou Erro, seguido do título da sessão. A barra de status, no fim da janela, repete o estado e mostra erros; o NVDA a lê com NVDA+End. A tela principal tem só a caixa de mensagem, a conversa e a árvore de sessões.

## Arquivos

- `app.py`: a janela.
- `worker.py`: conversa com o SDK numa thread com loop asyncio; nunca bloqueia a janela.
- `links.py`: acha links e arquivos nas mensagens.
- `limits.py`: compara os limites de uso (5 horas, semanal...) e escolhe de qual avisar.
- `scheduled.py`: a fila de mensagens agendadas.
- `sessions.py`: lista e lê sessões de `~/.claude/projects` e guarda a configuração em `%APPDATA%\CCA\config.json` (na primeira abertura copia o conteúdo da pasta antiga `%APPDATA%\claudeAcessivel`, sem apagá-la).
- `subjects.py`: agrupa as sessões pela pasta de trabalho.
- `transfer.py`: exporta e importa as preferências e memórias.
- `formatting.py`: textos e rótulos.
- Erros e a saída de diagnóstico do Claude Code vão para `%APPDATA%\CCA\registro.txt`.

Testes: `python -m pytest` nesta pasta (não usam rede).
