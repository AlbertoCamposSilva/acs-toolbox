<#
.SYNOPSIS
    Baixa a versão atual do rclone (site oficial), confere o SHA-256 e instala em
    %LOCALAPPDATA%\rclone\rclone.exe. Não precisa de administrador.
    Rodar de novo atualiza o rclone.
#>
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Destino = Join-Path $env:LOCALAPPDATA 'rclone'
$Temp    = Join-Path $env:TEMP ("rclone_instalacao_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Destino, $Temp | Out-Null

try {
    $Versao = ((Invoke-WebRequest 'https://downloads.rclone.org/version.txt' -UseBasicParsing).Content |
        ForEach-Object { if ($_ -is [byte[]]) { [Text.Encoding]::UTF8.GetString($_) } else { $_ } }).Trim() -replace '^rclone ', ''
    $Nome = "rclone-$Versao-windows-amd64"
    $Zip  = Join-Path $Temp "$Nome.zip"
    Write-Host "Baixando rclone $Versao ..."
    Invoke-WebRequest "https://downloads.rclone.org/$Versao/$Nome.zip" -OutFile $Zip -UseBasicParsing

    $Somas = (Invoke-WebRequest "https://downloads.rclone.org/$Versao/SHA256SUMS" -UseBasicParsing).Content
    if ($Somas -is [byte[]]) { $Somas = [Text.Encoding]::UTF8.GetString($Somas) }
    $Esperado = (($Somas -split "`n") | Where-Object { $_ -match [regex]::Escape("$Nome.zip") } |
        Select-Object -First 1) -replace '\s.*$', ''
    $Obtido = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLower()
    if (-not $Esperado -or $Esperado -ne $Obtido) {
        throw "SHA-256 nao confere (esperado '$Esperado', obtido '$Obtido'). Instalacao abortada."
    }

    Expand-Archive -LiteralPath $Zip -DestinationPath $Temp -Force
    Copy-Item -LiteralPath (Join-Path $Temp "$Nome\rclone.exe") -Destination (Join-Path $Destino 'rclone.exe') -Force
    & (Join-Path $Destino 'rclone.exe') version
    Write-Host "Instalado em $Destino\rclone.exe" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
