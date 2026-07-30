$ErrorActionPreference = "Stop"

function Assert-LastCommandSucceeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE."
    }
}

$targets = @(
    "api",
    "dags",
    "infra",
    "scripts",
    "src",
    "tests"
)

Write-Host ""
Write-Host "1. Apply safe Ruff fixes"

python -m ruff check `
    --fix `
    @targets

Assert-LastCommandSucceeded `
    -StepName "Ruff automatic fixes"

Write-Host ""
Write-Host "2. Format backend Python files"

python -m ruff format @targets

Assert-LastCommandSucceeded `
    -StepName "Ruff formatting"

Write-Host ""
Write-Host "Backend lint fixes and formatting completed."