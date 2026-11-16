$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath) { Write-Host 'Existing .env preserved'; exit 0 }
function New-Secret { return [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLowerInvariant() }
$lines = @(
  ('POSTGRES_PASSWORD=' + (New-Secret))
  ('S3_ACCESS_KEY=' + (New-Secret))
  ('S3_SECRET_KEY=' + (New-Secret))
  'WEB_ORIGIN=http://localhost:3009'
  'LITELLM_URL='
  'LITELLM_KEY='
  ('SECRETS_KEY=' + [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('+','-').Replace('/','_'))
  'MEDIA_DOWNLOAD_HOSTS='
)
[IO.File]::WriteAllLines($envPath, $lines)
Write-Host 'Local configuration created. Secrets were not printed.'
