<#
.SYNOPSIS
    Deixa cada repositório git em E:\Projetos igual ao GitHub antes de sincronizar:
    commit do que estiver pendente, pull (rebase) do que estiver atrás e push do que estiver à frente.

.DESCRIPTION
    Rode ANTES de "sincronizar.ps1 -Resync" quando os dois PCs estiverem defasados. Com isso, os
    arquivos versionados ficam idênticos nos dois PCs, e o rclone só precisa decidir (pelo mais novo)
    os arquivos fora do git: dados, .env etc.

    Travas por repositório (o repositório é pulado e marcado como REVISAR):
      - arquivos que parecem segredo (.env, *.pem, *.key, credentials*.json...) prestes a entrar no commit;
      - arquivos com mais de 50 MB prestes a entrar no commit (o GitHub recusa acima de 100 MB);
      - conflito no rebase (o rebase é desfeito e nada se perde);
      - HEAD destacado, rebase/merge em andamento.

.PARAMETER SoListar
    Só mostra a situação de cada repositório, sem alterar nada.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\preparar_git.ps1" -SoListar
#>
[CmdletBinding()]
param(
    [switch]$SoListar,
    [string]$Raiz = 'E:\Projetos'
)

$ErrorActionPreference = 'Continue'
$MaxMB = 50
$PadraoSegredo = '(^|/)\.env($|\.)|\.(pem|key|p12|pfx|ppk)$|(^|/)id_(rsa|ed25519|ecdsa)$|credentials?[^/]*\.json$|client_secret[^/]*\.json$|service[-_]?account[^/]*\.json$|(^|/)token[^/]*\.(json|pickle)$|\.ini$'
$Mensagem = "Sincronizacao automatica antes do rclone ($env:COMPUTERNAME, $(Get-Date -Format 'yyyy-MM-dd HH:mm'))"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host 'git nao encontrado no PATH.' -ForegroundColor Red; exit 1
}
if (-not (Test-Path -LiteralPath $Raiz)) {
    Write-Host "$Raiz nao existe (pendrive desconectado?)." -ForegroundColor Red; exit 1
}

# Executa git no repositório. safe.directory=* evita o erro "dubious ownership" em pendrive (exFAT/FAT).
function G([string]$Repo) {
    $saida = & git -c safe.directory=* -c core.quotepath=false -C $Repo @args 2>&1 | ForEach-Object { "$_" }
    [pscustomobject]@{ Codigo = $LASTEXITCODE; Saida = ($saida -join "`n").Trim() }
}

Write-Host "Procurando repositorios em $Raiz ..." -ForegroundColor Cyan
$repos = Get-ChildItem -LiteralPath $Raiz -Recurse -Force -Directory -Filter '.git' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(\.venv|venv|node_modules|\.next)\\' } |
    ForEach-Object { $_.Parent.FullName } | Sort-Object -Unique
Write-Host "$($repos.Count) repositorios encontrados.`n"

$resultado = foreach ($repo in $repos) {
    $nome = $repo.Substring($Raiz.Length).TrimStart('\')
    $acoes = New-Object System.Collections.Generic.List[string]
    $situacao = 'OK'

    $gitDir = Join-Path $repo '.git'
    if ((Test-Path "$gitDir\rebase-merge") -or (Test-Path "$gitDir\rebase-apply") -or (Test-Path "$gitDir\MERGE_HEAD")) {
        [pscustomobject]@{ Repositorio = $nome; Situacao = 'REVISAR'; Detalhe = 'rebase/merge em andamento' }; continue
    }
    $ramo = (G $repo rev-parse --abbrev-ref HEAD).Saida
    if ($ramo -eq 'HEAD' -or -not $ramo) {
        [pscustomobject]@{ Repositorio = $nome; Situacao = 'REVISAR'; Detalhe = 'HEAD destacado ou repositorio sem commits' }; continue
    }

    # Sem remoto o git não tem ponto em comum entre os PCs: não faz commit; o rclone mantém
    # o arquivo mais novo (inclusive dentro de .git).
    if (-not (G $repo remote).Saida) {
        $n = @(((G $repo status --porcelain '-uall').Saida -split "`n") | Where-Object { $_ }).Count
        [pscustomobject]@{ Repositorio = $nome; Situacao = 'OK'; Detalhe = "sem remoto: fica com o rclone (mais novo vence); $n pendente(s), sem commit" }
        continue
    }

    # 1. Alterações pendentes -> commit (com travas)
    $pendentes = (G $repo status --porcelain '-uall').Saida
    if ($pendentes) {
        $arquivos = $pendentes -split "`n" | ForEach-Object {
            $p = $_.Substring(3); if ($p -match ' -> ') { $p = ($p -split ' -> ')[-1] }; $p.Trim('"')
        }
        $n = @($arquivos).Count
        if ($SoListar) {
            $acoes.Add("$n arquivo(s) pendente(s)")
        } else {
            $novosOuAlterados = $pendentes -split "`n" | Where-Object { $_ -notmatch '^ ?D' } | ForEach-Object {
                $p = $_.Substring(3); if ($p -match ' -> ') { $p = ($p -split ' -> ')[-1] }; $p.Trim('"')
            }
            $segredos = @($novosOuAlterados | Where-Object { $_ -replace '\\', '/' -match $PadraoSegredo })
            $grandes = @($novosOuAlterados | Where-Object {
                $f = Join-Path $repo $_; (Test-Path -LiteralPath $f -PathType Leaf) -and ((Get-Item -LiteralPath $f).Length -gt $MaxMB * 1MB)
            })
            if ($segredos.Count -or $grandes.Count) {
                $det = @()
                if ($segredos.Count) { $det += "possivel segredo: $($segredos -join ', ')" }
                if ($grandes.Count)  { $det += "maior que $MaxMB MB: $($grandes -join ', ')" }
                [pscustomobject]@{ Repositorio = $nome; Situacao = 'REVISAR'; Detalhe = ($det -join ' | ') + ' (adicione ao .gitignore ou faca o commit a mao)' }
                continue
            }
            $r = G $repo add -A
            if ($r.Codigo -ne 0) { [pscustomobject]@{ Repositorio = $nome; Situacao = 'ERRO'; Detalhe = "git add: $($r.Saida)" }; continue }
            $r = G $repo commit '-m' $Mensagem
            if ($r.Codigo -ne 0) { [pscustomobject]@{ Repositorio = $nome; Situacao = 'ERRO'; Detalhe = "git commit: $($r.Saida)" }; continue }
            $acoes.Add("commit de $n arquivo(s)")
        }
    }

    # 2. Sincronizar com o remoto
    $upstream = (G $repo rev-parse --abbrev-ref --symbolic-full-name '@{u}')
    if ($upstream.Codigo -ne 0) {
        $acoes.Add("ramo '$ramo' sem upstream (nao enviado)")
        if (-not $SoListar) { $situacao = 'AVISO' }
        [pscustomobject]@{ Repositorio = $nome; Situacao = $situacao; Detalhe = ($acoes -join '; ') }; continue
    }
    $r = G $repo fetch --prune
    if ($r.Codigo -ne 0) {
        $acoes.Add("fetch falhou: $($r.Saida -split "`n" | Select-Object -Last 1)")
        [pscustomobject]@{ Repositorio = $nome; Situacao = 'ERRO'; Detalhe = ($acoes -join '; ') }; continue
    }
    $contagem = ((G $repo rev-list --left-right --count 'HEAD...@{u}').Saida -split '\s+')
    $frente = [int]$contagem[0]; $atras = [int]$contagem[1]

    if ($SoListar) {
        if ($frente) { $acoes.Add("$frente commit(s) a enviar") }
        if ($atras)  { $acoes.Add("$atras commit(s) a receber") }
        if (-not $acoes.Count) { $acoes.Add('em dia') }
        [pscustomobject]@{ Repositorio = $nome; Situacao = 'OK'; Detalhe = ($acoes -join '; ') }; continue
    }

    if ($atras) {
        $r = G $repo pull --rebase
        if ($r.Codigo -ne 0) {
            G $repo rebase --abort | Out-Null
            $acoes.Add("CONFLITO no pull --rebase ($atras a receber, $frente a enviar); rebase desfeito, resolva a mao")
            [pscustomobject]@{ Repositorio = $nome; Situacao = 'REVISAR'; Detalhe = ($acoes -join '; ') }; continue
        }
        $acoes.Add("recebidos $atras commit(s)")
        $frente = [int](((G $repo rev-list --left-right --count 'HEAD...@{u}').Saida -split '\s+')[0])
    }
    if ($frente) {
        $r = G $repo push
        if ($r.Codigo -ne 0) {
            $acoes.Add("push falhou: $($r.Saida -split "`n" | Select-Object -Last 1)")
            [pscustomobject]@{ Repositorio = $nome; Situacao = 'ERRO'; Detalhe = ($acoes -join '; ') }; continue
        }
        $acoes.Add("enviados $frente commit(s)")
    }
    if (-not $acoes.Count) { $acoes.Add('em dia') }
    [pscustomobject]@{ Repositorio = $nome; Situacao = $situacao; Detalhe = ($acoes -join '; ') }
}

$resultado | Format-Table -AutoSize -Wrap | Out-String -Width 300 | Write-Host
$problemas = @($resultado | Where-Object { $_.Situacao -in 'REVISAR', 'ERRO' })
if ($problemas.Count) {
    Write-Host "$($problemas.Count) repositorio(s) precisam de atencao (REVISAR/ERRO). Resolva antes do -Resync." -ForegroundColor Yellow
    exit 2
}
Write-Host 'Todos os repositorios estao em dia com o remoto.' -ForegroundColor Green
exit 0
