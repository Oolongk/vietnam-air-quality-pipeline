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

$requestedTargets = @(
    "api",
    "dags",
    "infra",
    "scripts",
    "src",
    "tests"
)

$targets = @(
    $requestedTargets | Where-Object {
        Test-Path $_
    }
)

if ($targets.Count -eq 0) {
    throw "No Python target directories were found."
}

Write-Host ""
Write-Host "1. Ruff lint check"

python -m ruff check @targets

Assert-LastCommandSucceeded `
    -StepName "Ruff lint check"

Write-Host ""
Write-Host "2. Ruff format check"

python -m ruff format `
    --check `
    @targets

Assert-LastCommandSucceeded `
    -StepName "Ruff format check"

Write-Host ""
Write-Host "3. Python dependency consistency"

python -m pip check

Assert-LastCommandSucceeded `
    -StepName "Dependency consistency check"

Write-Host ""
Write-Host "4. Data contract catalog check"

python -m scripts.export_data_contracts `
    --check

Assert-LastCommandSucceeded `
    -StepName "Data contract catalog check"

Write-Host ""
Write-Host "5. Runtime inventory check"

python -m scripts.check_runtime_inventory

Assert-LastCommandSucceeded `
    -StepName "Runtime inventory check"

Write-Host ""
Write-Host ""
Write-Host "6. Operations documentation check"

python -m scripts.check_operations_documentation

Assert-LastCommandSucceeded `
    -StepName "Operations documentation check"

Write-Host "Backend code-quality checks passed."