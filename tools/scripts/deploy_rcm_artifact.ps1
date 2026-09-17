[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactZip,

    [Parameter(Mandatory = $true)]
    [string]$McdkTarget,

    [Parameter(Mandatory = $true)]
    [string]$BridgeTarget,

    [string]$BackupRoot,

    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$VersionLabel,

    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-ExistingFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedName
    )

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $item = Get-Item -LiteralPath $resolved
    if ($item.PSIsContainer) {
        throw "Expected a file but found a directory: $resolved"
    }
    if ($item.Name -cne $ExpectedName) {
        throw "Expected file name '$ExpectedName' but found '$($item.Name)': $resolved"
    }
    return $resolved
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Get-RuntimeProcesses {
    $names = @('mcdk', 'Minecraft.Windows', 'mcdk_stdio_bridge')
    return @(Get-Process | Where-Object { $names -contains $_.ProcessName })
}

function Find-Payload {
    param([Parameter(Mandatory = $true)][string]$ExtractedRoot)

    $mcdk = @(Get-ChildItem -LiteralPath $ExtractedRoot -Recurse -File -Filter 'mcdk.exe')
    $bridge = @(Get-ChildItem -LiteralPath $ExtractedRoot -Recurse -File -Filter 'mcdk_stdio_bridge.exe')
    if ($mcdk.Count -ne 1 -or $bridge.Count -ne 1) {
        throw "Artifact payload must contain exactly one mcdk.exe and one mcdk_stdio_bridge.exe."
    }

    return [pscustomobject]@{
        Mcdk = $mcdk[0].FullName
        Bridge = $bridge[0].FullName
    }
}

$artifactPath = (Resolve-Path -LiteralPath $ArtifactZip).Path
$artifactItem = Get-Item -LiteralPath $artifactPath
if ($artifactItem.PSIsContainer -or $artifactItem.Extension -ine '.zip') {
    throw "Artifact must be a ZIP file: $artifactPath"
}

$mcdkTargetPath = Resolve-ExistingFile -Path $McdkTarget -ExpectedName 'mcdk.exe'
$bridgeTargetPath = Resolve-ExistingFile -Path $BridgeTarget -ExpectedName 'mcdk_stdio_bridge.exe'

if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $backupRootPath = Join-Path (Split-Path -Parent $bridgeTargetPath) 'backups'
} else {
    $backupRootPath = [IO.Path]::GetFullPath($BackupRoot)
}

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$stagingRoot = Join-Path $tempRoot ("mcdk-rcm-deploy-" + [guid]::NewGuid().ToString('N'))
$outerRoot = Join-Path $stagingRoot 'outer'
$innerRoot = Join-Path $stagingRoot 'inner'

New-Item -ItemType Directory -Path $outerRoot | Out-Null

try {
    Expand-Archive -LiteralPath $artifactPath -DestinationPath $outerRoot

    $outerMcdk = @(Get-ChildItem -LiteralPath $outerRoot -Recurse -File -Filter 'mcdk.exe')
    $outerBridge = @(Get-ChildItem -LiteralPath $outerRoot -Recurse -File -Filter 'mcdk_stdio_bridge.exe')
    if ($outerMcdk.Count -eq 1 -and $outerBridge.Count -eq 1) {
        $payload = Find-Payload -ExtractedRoot $outerRoot
    } else {
        $nestedZips = @(Get-ChildItem -LiteralPath $outerRoot -Recurse -File -Filter '*.zip')
        if ($nestedZips.Count -ne 1) {
            throw "Artifact must contain the executable pair directly or exactly one nested ZIP."
        }
        New-Item -ItemType Directory -Path $innerRoot | Out-Null
        Expand-Archive -LiteralPath $nestedZips[0].FullName -DestinationPath $innerRoot
        $payload = Find-Payload -ExtractedRoot $innerRoot
    }

    $artifactHash = Get-Sha256 -Path $artifactPath
    $newMcdkHash = Get-Sha256 -Path $payload.Mcdk
    $newBridgeHash = Get-Sha256 -Path $payload.Bridge
    $currentMcdkHash = Get-Sha256 -Path $mcdkTargetPath
    $currentBridgeHash = Get-Sha256 -Path $bridgeTargetPath

    if ([string]::IsNullOrWhiteSpace($VersionLabel)) {
        $VersionLabel = $artifactHash.Substring(0, 8).ToLowerInvariant()
    }
    $backupName = (Get-Date -Format 'yyyy-MM-dd-HHmmss') + '-' + $VersionLabel
    $backupPath = Join-Path $backupRootPath $backupName
    $runtimeProcesses = @(Get-RuntimeProcesses)

    [pscustomobject]@{
        Mode = $(if ($Apply) { 'APPLY' } else { 'DRY-RUN' })
        Artifact = $artifactPath
        ArtifactSha256 = $artifactHash
        McdkTarget = $mcdkTargetPath
        CurrentMcdkSha256 = $currentMcdkHash
        NewMcdkSha256 = $newMcdkHash
        BridgeTarget = $bridgeTargetPath
        CurrentBridgeSha256 = $currentBridgeHash
        NewBridgeSha256 = $newBridgeHash
        Backup = $backupPath
        BlockingProcesses = $(if ($runtimeProcesses.Count) {
            ($runtimeProcesses | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ', '
        } else {
            '(none)'
        })
    } | Format-List | Out-Host

    if (-not $Apply) {
        Write-Host 'Dry run only. Re-run with -Apply after reviewing the paths and stopping all listed processes.'
        return
    }

    if ($runtimeProcesses.Count) {
        throw "Deployment blocked while MCDK runtime processes are active."
    }
    if (Test-Path -LiteralPath $backupPath) {
        throw "Backup path already exists: $backupPath"
    }

    New-Item -ItemType Directory -Path $backupPath | Out-Null
    $backupMcdk = Join-Path $backupPath 'mcdk.exe'
    $backupBridge = Join-Path $backupPath 'mcdk_stdio_bridge.exe'
    Copy-Item -LiteralPath $mcdkTargetPath -Destination $backupMcdk
    Copy-Item -LiteralPath $bridgeTargetPath -Destination $backupBridge

    $deployToken = [guid]::NewGuid().ToString('N')
    $stagedMcdk = "$mcdkTargetPath.deploy-$deployToken"
    $stagedBridge = "$bridgeTargetPath.deploy-$deployToken"

    try {
        Copy-Item -LiteralPath $payload.Mcdk -Destination $stagedMcdk
        Copy-Item -LiteralPath $payload.Bridge -Destination $stagedBridge

        if ((Get-Sha256 -Path $stagedMcdk) -cne $newMcdkHash -or
            (Get-Sha256 -Path $stagedBridge) -cne $newBridgeHash) {
            throw 'Staged executable hash verification failed.'
        }

        Move-Item -LiteralPath $stagedMcdk -Destination $mcdkTargetPath -Force
        Move-Item -LiteralPath $stagedBridge -Destination $bridgeTargetPath -Force

        if ((Get-Sha256 -Path $mcdkTargetPath) -cne $newMcdkHash -or
            (Get-Sha256 -Path $bridgeTargetPath) -cne $newBridgeHash) {
            throw 'Deployed executable hash verification failed.'
        }
    } catch {
        Copy-Item -LiteralPath $backupMcdk -Destination $mcdkTargetPath -Force
        Copy-Item -LiteralPath $backupBridge -Destination $bridgeTargetPath -Force
        throw
    } finally {
        if (Test-Path -LiteralPath $stagedMcdk) {
            Remove-Item -LiteralPath $stagedMcdk -Force
        }
        if (Test-Path -LiteralPath $stagedBridge) {
            Remove-Item -LiteralPath $stagedBridge -Force
        }
    }

    Write-Host "Deployment complete. Backup: $backupPath"
} finally {
    $resolvedStagingRoot = [IO.Path]::GetFullPath($stagingRoot)
    $expectedPrefix = $tempRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedStagingRoot.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $resolvedStagingRoot) -notlike 'mcdk-rcm-deploy-*') {
        throw "Refusing to clean unexpected staging path: $resolvedStagingRoot"
    }
    if (Test-Path -LiteralPath $resolvedStagingRoot) {
        Remove-Item -LiteralPath $resolvedStagingRoot -Recurse -Force
    }
}
