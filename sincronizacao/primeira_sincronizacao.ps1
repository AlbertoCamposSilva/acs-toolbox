<#
.SYNOPSIS
    Configura um PC e faz a primeira sincronização de E:\Projetos com o Google Drive.
    Feito para o PC do CNPq, onde E:\Projetos já existe com versões defasadas dos projetos.

.DESCRIPTION
    Etapas (cada uma é pulada se já estiver feita):
      1. Confere E:\Projetos.
      2. Instala o rclone em %LOCALAPPDATA%\rclone (sem admin).
      3. Conecta o rclone ao Google Drive (abre o navegador para autorizar).
      4. Cria o marcador E:\Projetos\RCLONE_TEST.
      5. Git: commit + pull + push de cada repositório com GitHub (preparar_git.ps1).
      6. rclone bisync --resync: une E:\Projetos e o Drive; em cada arquivo vence o MAIS NOVO; nada é apagado.
      7. Uma sincronização normal, para validar.

.PARAMETER ClientId
    Client ID OAuth próprio (projeto GCP flowresolve). Opcional, mas recomendado (veja README.md).

.PARAMETER ClientSecret
    Client secret correspondente ao ClientId.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\primeira_sincronizacao.ps1" -ClientId "123-abc.apps.googleusercontent.com" -ClientSecret "GOCSPX-..."
#>
[CmdletBinding()]
param(
    [string]$ClientId,
    [string]$ClientSecret
)

# 'Continue': no Windows PowerShell 5.1, qualquer aviso que o rclone escreva no stderr viraria erro
# fatal com 'Stop'. Os erros são tratados pelos códigos de saída ($LASTEXITCODE).
$ErrorActionPreference = 'Continue'
$Local    = 'E:\Projetos'
$Pasta    = $PSScriptRoot
$Rclone   = Join-Path $env:LOCALAPPDATA 'rclone\rclone.exe'
$Marcador = Join-Path $Local 'RCLONE_TEST'

function Etapa([string]$Texto) { Write-Host "`n=== $Texto ===" -ForegroundColor Cyan }
function Parar([string]$Texto) { Write-Host "`n$Texto" -ForegroundColor Red; Read-Host 'Enter para sair' | Out-Null; exit 1 }
function Rodar([string]$Script, [string[]]$Argumentos = @()) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Pasta $Script) @Argumentos | Out-Host
    return $LASTEXITCODE
}

Etapa '1/7 Pasta E:\Projetos'
if (-not (Test-Path -LiteralPath $Local)) { Parar "$Local nao existe. Conecte o pendrive e rode de novo." }
try { Write-Host "Unidade E: em $(([IO.DriveInfo]::new('E')).DriveFormat)." } catch { }
Write-Host 'OK'

Etapa '2/7 rclone'
if (Test-Path -LiteralPath $Rclone) { & $Rclone version | Select-Object -First 1 }
else {
    if ((Rodar 'instalar_rclone.ps1') -ne 0 -or -not (Test-Path -LiteralPath $Rclone)) { Parar 'Falha ao instalar o rclone.' }
}

Etapa '3/7 Conexao com o Google Drive (conta albertodecamposesilva)'
$remotos = & $Rclone listremotes 2>$null
if ($remotos -contains 'gdrive:') {
    Write-Host 'Remoto gdrive ja configurado.'
    $config  = & $Rclone config show gdrive 2>$null
    $idAtual = (($config | Select-String '^client_id = (.+)$') | ForEach-Object { $_.Matches[0].Groups[1].Value }) -join ''
    $temToken = [bool]($config | Select-String '^token = \S')
    if ($ClientId -and $ClientSecret -and ($idAtual -ne $ClientId -or -not $temToken)) {
        & $Rclone config update gdrive client_id=$ClientId client_secret=$ClientSecret | Out-Null
        Write-Host 'Client ID atualizado. Autorize de novo no navegador que vai abrir.'
        & $Rclone config reconnect gdrive: --auto-confirm
    }
} else {
    Write-Host 'O navegador vai abrir: entre com albertodecamposesilva e clique em Permitir.' -ForegroundColor Yellow
    Write-Host '(Se aparecer "app nao verificado": Avancado -> Continuar.)'
    $parametros = @('config', 'create', 'gdrive', 'drive', 'scope=drive')
    if ($ClientId -and $ClientSecret) { $parametros += @("client_id=$ClientId", "client_secret=$ClientSecret") }
    & $Rclone @parametros | Out-Null
}
$teste = & $Rclone lsf gdrive:Projetos-sync --max-depth 1 2>&1
if ($LASTEXITCODE -ne 0) { Parar "Nao consegui ler gdrive:Projetos-sync:`n$teste" }
Write-Host "Drive acessivel ($(@($teste).Count) itens na raiz de Projetos-sync)."
# O notebook de casa grava este aviso quando o envio inicial termina.
& $Rclone lsf gdrive:Projetos-sync-status/envio_inicial_concluido.txt 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Parar 'O envio inicial do notebook de casa ainda nao terminou (falta gdrive:Projetos-sync-status/envio_inicial_concluido.txt). Espere e rode de novo.'
}

Etapa '4/7 Marcador RCLONE_TEST'
if (-not (Test-Path -LiteralPath $Marcador)) {
    Set-Content -LiteralPath $Marcador -Value 'Marcador do rclone bisync. Nao apagar.' -Encoding ASCII
    Write-Host 'Criado.'
} else { Write-Host 'Ja existe.' }

Etapa '5/7 Git: commit + pull + push de cada repositorio'
# Só antes da PRIMEIRA tentativa de sincronizar. Depois de um -Resync interrompido, E:\Projetos fica
# com uma mistura de versões (e arquivos ainda não baixados): um commit automático ali registraria
# versões intermediárias e apagaria arquivos.
$jaTentou = @(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'rclone\logs') -Filter 'sincronizar_*.log' -ErrorAction SilentlyContinue).Count -gt 0
if ($jaTentou) {
    Write-Host 'Pulada: ja houve uma tentativa de sincronizacao neste PC (o git ficou para antes da primeira).' -ForegroundColor Yellow
    $codigo = 0
} else {
    $codigo = Rodar 'preparar_git.ps1'
}
if ($codigo -ne 0) {
    Write-Host 'Ha repositorios marcados REVISAR/ERRO (veja a tabela acima).' -ForegroundColor Yellow
    Write-Host 'Voce pode resolver agora e rodar este script de novo, ou continuar: nesses repositorios'
    Write-Host 'o rclone vai manter, arquivo a arquivo, a versao mais nova.'
    if ((Read-Host 'Continuar mesmo assim? (s/N)') -notmatch '^[sS]') { exit 2 }
}

Etapa '6/7 Primeira sincronizacao (une os dois lados; vence o mais novo; nada e apagado)'
Write-Host 'Pode levar horas (download de ~46 GB). Pode interromper: rodar de novo continua.' -ForegroundColor Yellow
$env:SINCRONIZAR_SEM_PAUSA = '1'
if ((Rodar 'sincronizar.ps1' @('-Resync')) -ne 0) { Parar 'O -Resync terminou com erro (veja o log acima). Rode este script de novo.' }

Etapa '7/7 Sincronizacao normal (validacao)'
if ((Rodar 'sincronizar.ps1') -ne 0) { Parar 'A sincronizacao normal falhou (veja o log acima).' }

Write-Host "`nPronto. Daqui em diante, use sincronizar.cmd ao chegar e antes de sair." -ForegroundColor Green
Write-Host 'Projetos com ambiente virtual: rode "uv sync" neles quando for usar (o .venv nao e sincronizado).'
Read-Host 'Enter para sair' | Out-Null
