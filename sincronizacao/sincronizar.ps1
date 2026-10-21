<#
.SYNOPSIS
    Sincroniza E:\Projetos com a pasta "Projetos-sync" do Google Drive (rclone bisync).

.DESCRIPTION
    Sincronização bidirecional, sob demanda (ou agendada). Roda igual nos dois PCs
    (casa e CNPq), sem precisar de administrador. Documentação: README.md nesta pasta.

.PARAMETER Resync
    Primeira execução em um PC, ou depois de mudar filtros.txt. Une os dois lados
    (nunca apaga nada); em arquivos que existem nos dois lados, fica o mais novo.

.PARAMETER DryRun
    Mostra o que seria feito, sem alterar nada.

.PARAMETER Force
    Ignora a trava de segurança que aborta quando mais de 50% dos arquivos seriam apagados.
    Use só se você realmente apagou muita coisa de propósito.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\sincronizar.ps1"
#>
[CmdletBinding()]
param(
    [switch]$Resync,
    [switch]$DryRun,
    [switch]$Force
)

# 'Continue': com 'Stop', o Windows PowerShell 5.1 trata qualquer saída de erro de programa externo
# (rclone, attrib) como falha fatal. Os erros são tratados pelos códigos de saída.
$ErrorActionPreference = 'Continue'

# --- Configuração --------------------------------------------------------------
$Local      = 'E:\Projetos'
$Remoto     = 'gdrive:Projetos-sync'
$Versoes    = 'gdrive:Projetos-sync-versoes'   # versões antigas de arquivos sobrescritos/apagados no Drive
$Rclone     = Join-Path $env:LOCALAPPDATA 'rclone\rclone.exe'
$Filtros    = Join-Path $PSScriptRoot 'filtros.txt'
$PastaLogs  = Join-Path $env:LOCALAPPDATA 'rclone\logs'
$Marcador   = 'RCLONE_TEST'                     # precisa existir na raiz dos dois lados
# -------------------------------------------------------------------------------

function Sair([string]$Mensagem, [int]$Codigo = 1) {
    Write-Host $Mensagem -ForegroundColor Red
    exit $Codigo
}

if (-not (Test-Path -LiteralPath $Rclone)) {
    Sair "rclone nao encontrado em $Rclone. Rode instalar_rclone.ps1 (veja README.md)."
}

# Proteção contra o pendrive (E:) que caiu ou não montou: sem a pasta ou sem o
# marcador, o bisync acharia que tudo foi apagado e propagaria isso para o Drive.
if (-not (Test-Path -LiteralPath $Local)) {
    Sair "$Local nao existe (pendrive desconectado?). Nada foi sincronizado."
}
if (-not (Test-Path -LiteralPath (Join-Path $Local $Marcador))) {
    Sair "Marcador $Local\$Marcador ausente. Se o disco esta montado e e a primeira vez, crie-o (veja README.md)."
}

# O git (Windows) marca como somente leitura arquivos de .git (commit-graph, packs). O rclone não
# consegue sobrescrever nem apagar arquivo somente leitura ("Acesso negado"). Tirar o atributo não
# afeta o git. Os projetos ficam a no máximo 4 níveis de E:\Projetos.
Get-ChildItem -LiteralPath $Local -Directory -Force -Recurse -Depth 4 -Filter '.git' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(\.venv|venv|node_modules|\.next)\\' } |
    ForEach-Object { & attrib.exe -R "$($_.FullName)\*" /S /D 2>$null | Out-Null }

New-Item -ItemType Directory -Force -Path $PastaLogs | Out-Null
$Agora = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$Log   = Join-Path $PastaLogs "sincronizar_$Agora.log"

$Argumentos = @(
    'bisync', $Local, $Remoto,
    '--filters-file', $Filtros,
    '--backup-dir2', "$Versoes/$Agora",
    '--conflict-resolve', 'newer',
    '--conflict-loser', 'num',
    '--create-empty-src-dirs',
    '--resilient', '--recover', '--max-lock', '2h',
    '--drive-skip-gdocs',
    '--fast-list',
    '--transfers', '8', '--checkers', '16',
    '--stats', '1m', '--stats-one-line',
    '--log-file', $Log, '--log-level', 'INFO'
)
# No -Resync o marcador ainda pode não existir no Drive (primeira vez); vale só a trava local acima.
if ($Resync) { $Argumentos += @('--resync', '--resync-mode', 'newer') }
else         { $Argumentos += @('--check-access', '--check-filename', $Marcador) }
# Pendrive em FAT32/exFAT guarda a hora com precisão de até 2 s: sem tolerância, o bisync veria
# diferença de data em todo arquivo.
try { $Formato = ([IO.DriveInfo]::new($Local.Substring(0, 1))).DriveFormat } catch { $Formato = '' }
if ($Formato -match 'FAT') { $Argumentos += @('--modify-window', '2s') }
if ($DryRun) { $Argumentos += '--dry-run' }
if ($Force)  { $Argumentos += '--force' }

Write-Host "Sincronizando $Local <-> $Remoto ..." -ForegroundColor Cyan
Write-Host "Log: $Log"
$Inicio = Get-Date
& $Rclone @Argumentos
$Codigo = $LASTEXITCODE
$Duracao = (Get-Date) - $Inicio

if ($Codigo -eq 0) {
    Write-Host ("Concluido em {0:hh\:mm\:ss}." -f $Duracao) -ForegroundColor Green
} else {
    Write-Host ("rclone terminou com codigo $Codigo apos {0:hh\:mm\:ss}. Ultimas linhas do log:" -f $Duracao) -ForegroundColor Red
    Get-Content -LiteralPath $Log -Tail 25
}

# Mantém só os últimos 60 logs
Get-ChildItem -LiteralPath $PastaLogs -Filter 'sincronizar_*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $Codigo
