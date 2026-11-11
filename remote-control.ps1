param([string]$Pasta = $PSScriptRoot)

# Liga o Remote Control escondido (sem janela de terminal), grava tudo em C:\logs,
# copia o link para a area de transferencia e abre o resultado no Bloco de Notas.

$cli = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe'
$logs = 'C:\logs'
$out = Join-Path $logs 'remote-control.txt'
$err = Join-Path $logs 'remote-control-erros.txt'
$pidFile = Join-Path $logs 'remote-control.pid'
$resumo = Join-Path $logs 'remote-control-resumo.txt'

New-Item -ItemType Directory -Force $logs | Out-Null

function Mostrar($texto) {
    Set-Content -Path $resumo -Value $texto -Encoding utf8
    Start-Process notepad.exe $resumo
}

if (-not (Test-Path $cli)) {
    Mostrar "Nao encontrei o claude.exe do SDK em: $cli`r`nAtualize com: python -m pip install -U claude-agent-sdk"
    exit 1
}
if (-not (Test-Path $Pasta -PathType Container)) {
    Mostrar "Pasta invalida: $Pasta"
    exit 1
}

# Ja esta rodando?
if (Test-Path $pidFile) {
    $antigo = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
    if ($antigo -and $antigo.ProcessName -eq 'claude') {
        Mostrar "O Remote Control ja esta ligado (processo $($antigo.Id)). Para desligar, use remote-control-parar.bat.`r`nLog: $out"
        exit 0
    }
}

Remove-Item $out, $err -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $cli `
    -ArgumentList @('remote-control', '--name', '"PC do Fabio"', '--permission-mode', 'default') `
    -WorkingDirectory $Pasta -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $out -RedirectStandardError $err
Set-Content -Path $pidFile -Value $p.Id

# Espera ate 20 s por um link na saida.
$link = $null
for ($i = 0; $i -lt 20 -and -not $link; $i++) {
    Start-Sleep -Seconds 1
    if ($p.HasExited) { break }
    $texto = (Get-Content $out, $err -Raw -ErrorAction SilentlyContinue) -join "`n"
    if ($texto -match 'https://\S+') { $link = $Matches[0] }
}

$status = if ($p.HasExited) { "ENCERROU com codigo $($p.ExitCode)." } else { "Ligado (processo $($p.Id))." }
$linhas = @("Remote Control: $status", "Pasta de trabalho: $Pasta")
if ($link) {
    Set-Clipboard -Value $link
    $linhas += "Link (ja copiado para a area de transferencia, cole com Ctrl+V): $link"
} else {
    $linhas += 'Nenhum link apareceu. No iPhone, abra o app Claude e procure "PC do Fabio" na area do Claude Code.'
}
$linhas += ''
$linhas += "Saida completa do servidor (cheia de codigos de tela): $out"
$linhas += ''
$linhas += 'Para desligar: remote-control-parar.bat'
Mostrar ($linhas -join "`r`n")
