# Gera um token aleatorio para EXTERNAL_DISPATCH_TOKEN (GitHub) + TWILIO_REPO_DISPATCH_SECRET (scheduler).
# O valor NAO e escrito no repositorio; fica num ficheiro temporario na pasta do utilizador.
$ErrorActionPreference = "Stop"

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes)

$out = Join-Path $env:USERPROFILE ".twilio-dispatch-secret-temp.txt"
Set-Content -Path $out -Value $token -Encoding utf8

Write-Host ""
Write-Host "=== Token gerado ==="
Write-Host "1) Abre o ficheiro (copia o conteudo numa linha so):"
Write-Host "   $out"
Write-Host ""
Write-Host "2) GitHub: repo jmarcilio-tech/twilio-dashboard > Settings > Secrets and variables > Actions > New repository secret"
Write-Host "   Nome:  EXTERNAL_DISPATCH_TOKEN"
Write-Host "   Valor: (cola o conteudo do ficheiro)"
Write-Host ""
Write-Host "3) Windows (variavel persistente para o utilizador atual):"
Write-Host '   setx TWILIO_REPO_DISPATCH_SECRET "<cola o mesmo valor aqui>"'
Write-Host ""
Write-Host "4) Reinicia a sessao PowerShell (ou faz logoff/login) para o setx fazer efeito nas tarefas agendadas."
Write-Host "5) Apaga o ficheiro temporario depois de colar: $out"
Write-Host ""
Write-Host "Nota: enquanto EXTERNAL_DISPATCH_TOKEN nao existir no GitHub, o workflow ainda aceita dispatches sem client_payload."
