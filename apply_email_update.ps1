$ErrorActionPreference = "Stop"

$UpdateRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $UpdateRoot

New-Item -ItemType Directory -Force -Path "$ProjectRoot\services" | Out-Null

Copy-Item "$UpdateRoot\services\email_service.py" "$ProjectRoot\services\email_service.py" -Force
Copy-Item "$UpdateRoot\setup_email.py" "$ProjectRoot\setup_email.py" -Force
Copy-Item "$UpdateRoot\send_test_email.py" "$ProjectRoot\send_test_email.py" -Force
Copy-Item "$UpdateRoot\EMAIL_SETUP.md" "$ProjectRoot\EMAIL_SETUP.md" -Force

Write-Host "CampusPass email update applied successfully."
Write-Host "Next: python setup_email.py"
