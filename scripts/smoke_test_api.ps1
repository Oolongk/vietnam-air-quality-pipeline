param(
    [string]$BaseUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"

$results = [System.Collections.Generic.List[object]]::new()


function Add-SmokeResult {
    param(
        [string]$Name,
        [string]$Path,
        [string]$Result,
        [string]$Details
    )

    $script:results.Add(
        [PSCustomObject]@{
            Endpoint = $Name
            Path     = $Path
            Result   = $Result
            Details  = $Details
        }
    )
}


function Invoke-SmokeEndpoint {
    param(
        [string]$Name,
        [string]$Path,
        [string[]]$RequiredProperties = @()
    )

    try {
        $response = Invoke-RestMethod `
            -Uri "$BaseUrl$Path" `
            -Method Get `
            -TimeoutSec 30

        if ($null -eq $response) {
            throw "Endpoint không trả response."
        }

        $propertyNames = @(
            $response.PSObject.Properties.Name
        )

        foreach (
            $propertyName in $RequiredProperties
        ) {
            if (
                -not (
                    $propertyNames -contains
                    $propertyName
                )
            ) {
                throw (
                    "Response thiếu property: " +
                    $propertyName
                )
            }
        }

        if (
            $propertyNames -contains "status"
        ) {
            $applicationStatus = (
                [string]$response.status
            )
        }
        else {
            $applicationStatus = "HTTP_OK"
        }

        if (
            $propertyNames -contains
            "record_count"
        ) {
            $recordCount = (
                [string]$response.record_count
            )
        }
        elseif (
            $propertyNames -contains
            "stage_count"
        ) {
            $recordCount = (
                [string]$response.stage_count
            )
        }
        elseif (
            $propertyNames -contains
            "check_count"
        ) {
            $recordCount = (
                [string]$response.check_count
            )
        }
        else {
            $recordCount = "-"
        }

        Add-SmokeResult `
            -Name $Name `
            -Path $Path `
            -Result "PASS" `
            -Details (
                "status=$applicationStatus; " +
                "count=$recordCount"
            )

        return $response
    }
    catch {
        Add-SmokeResult `
            -Name $Name `
            -Path $Path `
            -Result "FAIL" `
            -Details $_.Exception.Message

        return $null
    }
}


Write-Host
Write-Host "Vietnam Air Quality API smoke test"
Write-Host "Base URL: $BaseUrl"
Write-Host


$healthResponse = Invoke-SmokeEndpoint `
    -Name "Health" `
    -Path "/health" `
    -RequiredProperties @(
        "status",
        "service",
        "database"
    )


$locationsResponse = Invoke-SmokeEndpoint `
    -Name "Locations" `
    -Path "/api/v1/locations" `
    -RequiredProperties @(
        "status",
        "record_count",
        "data"
    )


$pointsResponse = Invoke-SmokeEndpoint `
    -Name "Monitoring Points" `
    -Path "/api/v1/monitoring-points" `
    -RequiredProperties @(
        "status",
        "record_count",
        "data"
    )


$locationId = $null

if (
    $null -ne $locationsResponse -and
    $locationsResponse.data.Count -gt 0
) {
    $locationId = (
        $locationsResponse.data |
        Select-Object -First 1
    ).location_id
}


$pointId = $null

if (
    $null -ne $pointsResponse -and
    $pointsResponse.data.Count -gt 0
) {
    $pointId = (
        $pointsResponse.data |
        Select-Object -First 1
    ).point_id
}


Invoke-SmokeEndpoint `
    -Name "Latest Air Quality" `
    -Path (
        "/api/v1/air-quality/latest" +
        "?limit=500"
    ) `
    -RequiredProperties @(
        "status",
        "batch_id",
        "record_count",
        "data"
    ) |
Out-Null


if ($pointId) {
    Invoke-SmokeEndpoint `
        -Name "Air Quality by Point" `
        -Path (
            "/api/v1/air-quality/points/" +
            "${pointId}?limit=24"
        ) `
        -RequiredProperties @(
            "status",
            "point_id",
            "batch_id",
            "record_count",
            "data"
        ) |
    Out-Null
}
else {
    Add-SmokeResult `
        -Name "Air Quality by Point" `
        -Path "-" `
        -Result "FAIL" `
        -Details (
            "Không lấy được point_id từ " +
            "Monitoring Points API."
        )
}


if ($locationId) {
    Invoke-SmokeEndpoint `
        -Name "Air Quality by Location" `
        -Path (
            "/api/v1/air-quality/locations/" +
            "${locationId}?limit=72"
        ) `
        -RequiredProperties @(
            "status",
            "location_id",
            "batch_id",
            "record_count",
            "data"
        ) |
    Out-Null
}
else {
    Add-SmokeResult `
        -Name "Air Quality by Location" `
        -Path "-" `
        -Result "FAIL" `
        -Details (
            "Không lấy được location_id từ " +
            "Locations API."
        )
}


Invoke-SmokeEndpoint `
    -Name "Top Polluted" `
    -Path (
        "/api/v1/air-quality/top-polluted" +
        "?limit=10"
    ) `
    -RequiredProperties @(
        "status",
        "batch_id",
        "reference_time",
        "record_count",
        "data"
    ) |
Out-Null


if ($pointId) {
    Invoke-SmokeEndpoint `
        -Name "Air Quality History" `
        -Path (
            "/api/v1/air-quality/history" +
            "?point_id=$pointId" +
            "&hours=24"
        ) `
        -RequiredProperties @(
            "status",
            "point_id",
            "requested_hours",
            "record_count",
            "data"
        ) |
    Out-Null
}
else {
    Add-SmokeResult `
        -Name "Air Quality History" `
        -Path "-" `
        -Result "FAIL" `
        -Details (
            "Không lấy được point_id để " +
            "kiểm tra History API."
        )
}


Invoke-SmokeEndpoint `
    -Name "Latest Alerts" `
    -Path (
        "/api/v1/alerts/latest" +
        "?limit=100"
    ) `
    -RequiredProperties @(
        "status",
        "record_count",
        "data"
    ) |
Out-Null


Invoke-SmokeEndpoint `
    -Name "Pipeline Health" `
    -Path "/api/v1/pipeline/health/latest" `
    -RequiredProperties @(
        "status",
        "batch_id",
        "stage_count",
        "data"
    ) |
Out-Null


Invoke-SmokeEndpoint `
    -Name "Data Quality" `
    -Path "/api/v1/data-quality/latest" `
    -RequiredProperties @(
        "status",
        "check_count",
        "failed_check_count",
        "data"
    ) |
Out-Null


Write-Host
Write-Host "Smoke test results"
Write-Host

$results |
Format-Table `
    Endpoint, `
    Result, `
    Details `
    -AutoSize


$failedResults = @(
    $results |
    Where-Object {
        $_.Result -eq "FAIL"
    }
)


Write-Host

if ($failedResults.Count -gt 0) {
    Write-Host (
        "Smoke test FAILED: " +
        "$($failedResults.Count) endpoint lỗi."
    )

    exit 1
}


Write-Host (
    "Smoke test PASSED: " +
    "$($results.Count) endpoint hoạt động."
)

exit 0