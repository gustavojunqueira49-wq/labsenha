<# Cria usuário e banco no PostgreSQL usando os dados do .env. Pede a senha do superusuário 'postgres'. #>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$envFile = Get-Content "$Root\.env" | Where-Object { $_ -match "^DATABASE_URL=" } | Select-Object -First 1
if ($envFile -notmatch "^DATABASE_URL=postgresql\+psycopg://([^:]+):([^@]+)@([^:/]+):?(\d*)/(\w+)") {
  Write-Host "DATABASE_URL não é PostgreSQL — nada a criar (SQLite/demonstração)."; exit 0 }
$u, $p, $dbhost, $port, $db = $Matches[1], $Matches[2], $Matches[3], $Matches[4], $Matches[5]
if (-not $port) { $port = "5432" }
$psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psql) {
  $cand = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
  if ($cand) { $psql = $cand.FullName } else { throw "psql não encontrado. Instale o PostgreSQL ou adicione a pasta bin ao PATH." }
}
$sec = Read-Host "Senha do superusuário 'postgres' do PostgreSQL" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$exists = & $psql -h $dbhost -p $port -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$u'"
if (-not $exists) { & $psql -h $dbhost -p $port -U postgres -c "CREATE ROLE $u WITH LOGIN PASSWORD '$p'" }
else { & $psql -h $dbhost -p $port -U postgres -c "ALTER ROLE $u WITH PASSWORD '$p'" }
$dbex = & $psql -h $dbhost -p $port -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'"
if (-not $dbex) { & $psql -h $dbhost -p $port -U postgres -c "CREATE DATABASE $db OWNER $u ENCODING 'UTF8'" }
Remove-Item Env:PGPASSWORD
Write-Host "Banco '$db' pronto." -ForegroundColor Green
