param(
    [string]$ProjectId = "rugby-ai-61fd0",
    [int]$MaxRetries = 6,
    [int]$InitialDelaySeconds = 20
)

$ErrorActionPreference = "Stop"
$FirebaseCli = "firebase.cmd"

# PowerShell 7 can convert native stderr output into terminating errors when
# $ErrorActionPreference='Stop'. Firebase/Node emits benign warnings on stderr
# (e.g. deprecation notices), so disable that behavior for native commands.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Invoke-FirebaseDeploy {
    param(
        [Parameter(Mandatory = $true)][string[]]$Args
    )

    $oldErrorAction = $ErrorActionPreference
    try {
        # PowerShell 5 emits native stderr as ErrorRecord objects; with Stop this aborts
        # even when process exit code is still usable. Relax only for native command call.
        $ErrorActionPreference = "Continue"
        $output = @()
        & $FirebaseCli @Args 2>&1 |
            Tee-Object -Variable output |
            ForEach-Object { Write-Host $_ }
        return ,$output
    }
    finally {
        $ErrorActionPreference = $oldErrorAction
    }
}

function Invoke-DeployWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$DeployTarget,
        [Parameter(Mandatory = $true)][int]$MaxAttempts,
        [Parameter(Mandatory = $true)][int]$BaseDelaySeconds
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-Host ""
        Write-Host "[$attempt/$MaxAttempts] Deploying: $DeployTarget" -ForegroundColor Cyan

        $output = Invoke-FirebaseDeploy -Args @("deploy", "--project", $ProjectId, "--only", $DeployTarget)
        $exitCode = $LASTEXITCODE
        $outputText = ($output | Out-String)

        if ($exitCode -eq 0) {
            Write-Host "SUCCESS: $DeployTarget" -ForegroundColor Green
            return
        }

        $isQueueConflict = $outputText -match "HTTP Error:\s*409" -or
                           $outputText -match "unable to queue the operation"

        if ($isQueueConflict -and $attempt -lt $MaxAttempts) {
            $delay = [Math]::Min(300, $BaseDelaySeconds * [Math]::Pow(2, $attempt - 1))
            $delay = [int][Math]::Round($delay)
            Write-Host "Queue conflict (409). Waiting $delay seconds before retry..." -ForegroundColor Yellow
            Start-Sleep -Seconds $delay
            continue
        }

        throw "FAILED: $DeployTarget (exit $exitCode)"
    }
}

function Get-FailedFunctionNames {
    param(
        [Parameter(Mandatory = $true)][string]$DeployOutput
    )

    $names = New-Object System.Collections.Generic.HashSet[string]
    $patterns = @(
        "failed to update function .*?/functions/([A-Za-z0-9_-]+)",
        "failed to create function .*?/functions/([A-Za-z0-9_-]+)"
    )

    foreach ($pattern in $patterns) {
        $matches = [regex]::Matches($DeployOutput, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        foreach ($m in $matches) {
            if ($m.Groups.Count -gt 1) {
                [void]$names.Add($m.Groups[1].Value)
            }
        }
    }

    return @($names)
}

Write-Host "Running full deploy: firebase.cmd deploy --project $ProjectId" -ForegroundColor Cyan
$fullOutput = Invoke-FirebaseDeploy -Args @("deploy", "--project", $ProjectId)
$fullExitCode = $LASTEXITCODE
$fullText = ($fullOutput | Out-String)

if ($fullExitCode -eq 0) {
    Write-Host "Full deploy completed successfully." -ForegroundColor Green
    return
}

$failedFunctions = Get-FailedFunctionNames -DeployOutput $fullText

if (-not $failedFunctions -or $failedFunctions.Count -eq 0) {
    throw "firebase deploy failed, and no failed function names could be parsed. Please inspect output above."
}

Write-Host ""
Write-Host "Retrying failed functions sequentially with backoff..." -ForegroundColor Yellow
Write-Host ("Failed functions: " + ($failedFunctions -join ", ")) -ForegroundColor Yellow

foreach ($fn in $failedFunctions) {
    Invoke-DeployWithRetry -DeployTarget "functions:$fn" -MaxAttempts $MaxRetries -BaseDelaySeconds $InitialDelaySeconds
}

Write-Host ""
Write-Host "Full deploy had partial failures, but failed functions were retried successfully." -ForegroundColor Green
