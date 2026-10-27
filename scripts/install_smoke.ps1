<#
  Teste de fumaça do instalador (roda no GitHub Actions, em Windows limpo):
  instala em silêncio -> confere arquivos/registro -> roda o autoteste do programa instalado ->
  abre o app com um PDF e confere que a 2ª instância entrega o arquivo à 1ª -> desinstala e confere a limpeza.
#>
param([Parameter(Mandatory = $true)][string]$Installer)
$ErrorActionPreference = "Stop"
$dir = Join-Path $env:RUNNER_TEMP "VerticeSmoke"
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
function Fail($m) { Write-Host "FALHA: $m"; exit 1 }
function Ok($m) { Write-Host "OK    $m" }

Write-Host "== Instalando $Installer em $dir"
$p = Start-Process -FilePath $Installer -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=`"$dir`"", "/TASKS=`"assoc`"",
    "/LOG=`"$env:RUNNER_TEMP\setup.log`"")
if ($p.ExitCode -ne 0) { Get-Content "$env:RUNNER_TEMP\setup.log" -Tail 40; Fail "instalador saiu com código $($p.ExitCode)" }
Ok "instalação silenciosa"

$exe = Join-Path $dir "VerticePDF.exe"
if (-not (Test-Path $exe)) { Fail "VerticePDF.exe não foi instalado" }
Ok "executável presente"
if (-not (Test-Path (Join-Path $dir "unins000.exe"))) { Fail "desinstalador ausente" }
if (-not (Test-Path (Join-Path $dir "tesseract\tessdata\por.traineddata"))) { Fail "OCR (tesseract + português) não foi instalado" }
Ok "componente de OCR presente"
$assoc = Get-ItemProperty "HKCU:\Software\Classes\VerticePDF.pdf\shell\open\command" -ErrorAction SilentlyContinue
if (-not $assoc) { Fail "associação de arquivo .pdf não registrada" }
Ok "associação .pdf registrada"

Write-Host "== Autoteste do programa instalado (fora da pasta do projeto)"
$env:QT_QPA_PLATFORM = "offscreen"
$report = Join-Path $env:RUNNER_TEMP "selftest.txt"
$st = Start-Process -FilePath $exe -ArgumentList @("--selftest", "`"$report`"") -Wait -PassThru -WorkingDirectory $env:TEMP
$text = if (Test-Path $report) { Get-Content $report -Raw } else { "(sem relatório)" }
Write-Host $text
if ($st.ExitCode -ne 0 -or $text -notmatch "TUDO OK") { Fail "autoteste do programa instalado falhou" }
Ok "autoteste (PDF, edição, assinatura, OCR)"
Remove-Item Env:QT_QPA_PLATFORM

Write-Host "== Abrindo o aplicativo e testando instância única"
$pdf = Join-Path $env:RUNNER_TEMP "smoke.pdf"
python -c "import fitz; d=fitz.open(); d.new_page().insert_text((72,100),'smoke'); d.save(r'$pdf')"
$app = Start-Process -FilePath $exe -ArgumentList "`"$pdf`"" -PassThru
Start-Sleep -Seconds 8
if ($app.HasExited) { Fail "o aplicativo fechou sozinho (código $($app.ExitCode))" }
Ok "aplicativo abriu e continua rodando"
$second = Start-Process -FilePath $exe -ArgumentList "`"$pdf`"" -PassThru
if (-not $second.WaitForExit(15000)) { $second.Kill(); Fail "a 2ª instância não encerrou (instância única não funcionou)" }
Ok "2ª instância entregou o arquivo e saiu"
if ($app.HasExited) { Fail "o aplicativo principal caiu ao receber o 2º arquivo" }
Stop-Process -Id $app.Id -Force

Write-Host "== Desinstalando"
$u = Start-Process -FilePath (Join-Path $dir "unins000.exe") -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
Start-Sleep -Seconds 3
if (Test-Path $exe) { Fail "VerticePDF.exe continuou no disco após desinstalar" }
if (Get-ItemProperty "HKCU:\Software\Classes\VerticePDF.pdf" -ErrorAction SilentlyContinue) { Fail "chaves de registro sobraram" }
Ok "desinstalação limpa"
Write-Host "TUDO OK"
