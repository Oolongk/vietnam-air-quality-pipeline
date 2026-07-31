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

Write-Host ""
Write-Host "Running backend unit and integration tests with coverage"

python -m pytest `
    tests `
    -v `
    --cov=src `
    --cov=api `
    --cov-report=term-missing `
    --cov-report=xml `
    --cov-report=html

Assert-LastCommandSucceeded `
    -StepName "Backend tests and coverage"

Write-Host ""
Write-Host "Coverage XML: coverage.xml"
Write-Host "Coverage HTML: htmlcov\index.html"
Write-Host "Backend tests and coverage passed."
