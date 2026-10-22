# padronizar_uv_E.ps1
# Deixa o ambiente uv IGUAL nos dois PCs (casa e CNPq), com tudo sob E:\Programas\uv, e recria os .venv de E:\Projetos.
# Rode em cada PC, num PowerShell normal (sem admin). Pode rodar de novo: so corrige o que estiver diferente.
#
# Padrao (identico nos dois PCs):
#   E:\Programas\uv\bin\uv.exe          o uv
#   E:\Programas\uv\python\...          Pythons gerenciados (cpython-3.14.8-windows-x86_64-none e o apelido ...3.14-...)
#   E:\Programas\uv\cache               cache de pacotes
#   variaveis de USUARIO: UV_CACHE_DIR, UV_PYTHON_INSTALL_DIR  e  E:\Programas\uv\bin no PATH
#   cada .venv de projeto aponta para E:\Programas\uv\python (por isso nao ha mais caminho de usuario do Windows nele)
#
# Parametros:
#   -PythonVersao  versao do Python gerenciado (padrao 3.14.8; use a mesma nos dois PCs)
#   -SoVerificar   mostra o que faria, sem alterar nada
#   -SemVenvs      nao recria os .venv (so padroniza o uv)
param(
    [string]$PythonVersao = '3.14.8',
    [string]$Raiz = 'E:\Programas\uv',
    [string]$Projetos = 'E:\Projetos',
    [switch]$SoVerificar,
    [switch]$SemVenvs
)
$ErrorActionPreference = 'Stop'
$uvExe = Join-Path $Raiz 'bin\uv.exe'
function Log($m) { Write-Host $m }
if (-not (Test-Path 'E:\')) { throw 'E: nao existe neste PC.' }

# 1) uv no lugar padrao ---------------------------------------------------------------------------------
if (-not (Test-Path $uvExe)) {
    $achado = @("$env:USERPROFILE\.local\bin\uv.exe", (Get-Command uv -ErrorAction SilentlyContinue).Source) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $achado) { throw "uv nao encontrado. Instale o uv (https://docs.astral.sh/uv/) e rode de novo." }
    Log "uv: copiando $achado -> $uvExe"
    if (-not $SoVerificar) { New-Item -ItemType Directory -Force (Split-Path $uvExe) | Out-Null; foreach ($f in 'uv.exe','uvx.exe','uvw.exe') { $s = Join-Path (Split-Path $achado) $f; if (Test-Path $s) { Copy-Item $s (Join-Path (Split-Path $uvExe) $f) -Force } } }
} else { Log "uv: ja esta em $uvExe" }

# 2) variaveis de usuario e PATH ------------------------------------------------------------------------
$vars = @{ UV_CACHE_DIR = (Join-Path $Raiz 'cache'); UV_PYTHON_INSTALL_DIR = (Join-Path $Raiz 'python') }
foreach ($k in $vars.Keys) {
    $atual = [Environment]::GetEnvironmentVariable($k, 'User')
    if ($atual -ne $vars[$k]) { Log "variavel $k : '$atual' -> '$($vars[$k])'"; if (-not $SoVerificar) { [Environment]::SetEnvironmentVariable($k, $vars[$k], 'User') } } else { Log "variavel $k : ok" }
}
$binUv = Split-Path $uvExe
$pathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | Where-Object { $_ }
$semAntigos = @($pathUsuario | Where-Object { $_ -ine "$env:USERPROFILE\.local\bin" })
if ($semAntigos -notcontains $binUv) { $semAntigos = @($binUv) + $semAntigos }
if (($semAntigos -join ';') -ne ($pathUsuario -join ';')) { Log "PATH do usuario: uv em $binUv (e sem $env:USERPROFILE\.local\bin)"; if (-not $SoVerificar) { [Environment]::SetEnvironmentVariable('Path', ($semAntigos -join ';'), 'User') } } else { Log 'PATH: ok' }
$env:UV_CACHE_DIR = $vars.UV_CACHE_DIR; $env:UV_PYTHON_INSTALL_DIR = $vars.UV_PYTHON_INSTALL_DIR

# 3) Python gerenciado ----------------------------------------------------------------------------------
$pyDir = Join-Path $Raiz "python\cpython-$PythonVersao-windows-x86_64-none"
if (-not (Test-Path (Join-Path $pyDir 'python.exe'))) {
    Log "Python $PythonVersao : instalando em $($vars.UV_PYTHON_INSTALL_DIR)"
    if (-not $SoVerificar) {
        New-Item -ItemType Directory -Force $vars.UV_PYTHON_INSTALL_DIR | Out-Null
        & $uvExe python install $PythonVersao
        if ($LASTEXITCODE -ne 0) { throw "uv python install $PythonVersao falhou. Sem internet? Copie a pasta do outro PC para $($vars.UV_PYTHON_INSTALL_DIR)." }
    }
} else { Log "Python $PythonVersao : ja instalado" }
$minor = ($PythonVersao -split '\.')[0..1] -join '.'
$apelido = Join-Path $Raiz "python\cpython-$minor-windows-x86_64-none"
if (-not (Test-Path $apelido) -and (Test-Path $pyDir) -and -not $SoVerificar) { New-Item -ItemType Junction -Path $apelido -Target $pyDir | Out-Null; Log "apelido criado: $apelido" }

# 4) .venv de todos os projetos uv de E:\Projetos -------------------------------------------------------
if ($SemVenvs) { Log 'Venvs: ignorados (-SemVenvs).'; return }
$dirsProj = @(Get-ChildItem $Projetos -Recurse -Depth 5 -Filter pyproject.toml -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules|\.git|site-packages|worktrees|_venvs_antigos)\\' -and (Test-Path (Join-Path $_.DirectoryName 'uv.lock')) } | ForEach-Object { $_.DirectoryName } | Sort-Object -Unique)
$baseCorreta = (Join-Path $Raiz 'python')
foreach ($p in $dirsProj) {
    $cfg = Join-Path $p '.venv\pyvenv.cfg'
    $home_ = if (Test-Path $cfg) { ((Get-Content $cfg | Where-Object { $_ -match '^home' }) -replace '^home\s*=\s*','').Trim() } else { $null }
    if ($home_ -and $home_.StartsWith($baseCorreta, [StringComparison]::OrdinalIgnoreCase)) { Log "venv ok     : $p"; continue }
    Log "venv ajustar: $p  (home atual: $home_)"
    if ($SoVerificar) { continue }
    $emUso = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { try { $_.Path -and $_.Path.StartsWith((Join-Path $p '.venv') + '\', [StringComparison]::OrdinalIgnoreCase) } catch { $false } })
    if ($emUso.Count -gt 0) { Write-Warning "em uso, pulado: $p ($($emUso[0].ProcessName))"; continue }
    $velho = "E:\_venvs_antigos\$(Split-Path $p -Leaf)-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    New-Item -ItemType Directory -Force (Split-Path $velho) | Out-Null
    $tinha = Test-Path (Join-Path $p '.venv'); if ($tinha) { Move-Item -LiteralPath (Join-Path $p '.venv') -Destination $velho }
    Push-Location $p
    try {
        $pyProj = if (Test-Path (Join-Path $p '.python-version')) { (Get-Content (Join-Path $p '.python-version') -Raw).Trim() } else { $minor }
        & $uvExe sync --frozen --python $pyProj 2>&1 | Select-Object -Last 2
        if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE)" }
    } catch {
        Write-Warning "FALHOU em $p : $($_.Exception.Message) - devolvendo o venv antigo."
        Pop-Location; if (Test-Path (Join-Path $p '.venv')) { [IO.Directory]::Delete((Join-Path $p '.venv'), $true) }
        if ($tinha) { Move-Item -LiteralPath $velho -Destination (Join-Path $p '.venv') }
        continue
    }
    Pop-Location
}
Log "`n=== Conferencia final dos .venv ==="
$pendentes = 0
foreach ($p in $dirsProj) {
    $cfg = Join-Path $p '.venv\pyvenv.cfg'
    $h = if (Test-Path $cfg) { ((Get-Content $cfg | Where-Object { $_ -match '^home' }) -replace '^home\s*=\s*','').Trim() } else { '(sem .venv)' }
    $ok = $h.StartsWith($baseCorreta, [StringComparison]::OrdinalIgnoreCase)
    if (-not $ok) { $pendentes++ }
    Log ("{0,-6} {1}  ->  {2}" -f $(if ($ok) { 'OK' } else { 'FALTA' }), $p.Replace("$Projetos\",''), $h)
}
Log "`nPronto. Pendentes: $pendentes. Venvs antigos (se houver) ficam em E:\_venvs_antigos; apague quando quiser."
