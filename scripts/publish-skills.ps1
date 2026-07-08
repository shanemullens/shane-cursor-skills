#Requires -Version 5.1
<#
.SYNOPSIS
  Publish local Cursor skills and agents to this repository.

.DESCRIPTION
  One-way sync from ~/.cursor/skills/ and ~/.cursor/agents/ into the repo's
  skills/ and agents/ directories, then stages and commits the changes.
  Run git push manually after a successful publish.

.PARAMETER DryRun
  Preview copy operations without modifying files or running git commands.

.PARAMETER Force
  Proceed even when the working tree has unstaged changes outside skills/ and agents/.

.PARAMETER CommitMessage
  Override the default commit message.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force,
    [string]$CommitMessage
)

$ErrorActionPreference = 'Stop'

$SkillAllowlist = @(
    'peak-threat-hunting',
    'splunk-ta-development',
    'splunk-dashboard-studio',
    'splunk-log-generator',
    'comprehensive-plan-mode'
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalSkillsRoot = Join-Path $env:USERPROFILE '.cursor\skills'
$LocalAgentsRoot = Join-Path $env:USERPROFILE '.cursor\agents'
$RepoSkillsRoot = Join-Path $RepoRoot 'skills'
$RepoAgentsRoot = Join-Path $RepoRoot 'agents'

function Write-Info([string]$Message) {
    Write-Host $Message
}

function Write-Warn([string]$Message) {
    Write-Warning $Message
}

function Test-GitRepository([string]$Path) {
    Push-Location $Path
    try {
        git rev-parse --is-inside-work-tree 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    finally {
        Pop-Location
    }
}

function Get-UnrelatedDirtyPaths([string]$Path) {
    Push-Location $Path
    try {
        $status = git status --porcelain
        if (-not $status) {
            return @()
        }

        return $status | ForEach-Object {
            $line = $_.Substring(3)
            if ($line -match '^skills/' -or $line -match '^agents/') {
                return
            }
            $line
        } | Where-Object { $_ }
    }
    finally {
        Pop-Location
    }
}

function Sync-DirectoryMirror {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Label
    )

    if (-not (Test-Path $Source)) {
        throw "Missing source for ${Label}: $Source"
    }

    if ($DryRun) {
        Write-Info "[DryRun] Would mirror: $Source -> $Destination"
        return
    }

    if (-not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }

    $robocopyArgs = @(
        $Source,
        $Destination,
        '/MIR',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NC',
        '/NS'
    )

    $result = & robocopy @robocopyArgs
    $exitCode = $LASTEXITCODE

  # robocopy exit codes 0-7 indicate success or benign differences
    if ($exitCode -gt 7) {
        throw "robocopy failed for ${Label} with exit code $exitCode"
    }

    Write-Info "Synced ${Label}"
}

if (-not (Test-GitRepository $RepoRoot)) {
    throw "Not a git repository: $RepoRoot"
}

foreach ($skill in $SkillAllowlist) {
    $source = Join-Path $LocalSkillsRoot $skill
    if (-not (Test-Path $source)) {
        throw "Allowlisted skill not found locally: $source"
    }
}

$unrelatedDirty = Get-UnrelatedDirtyPaths $RepoRoot
if ($unrelatedDirty -and -not $Force -and -not $DryRun) {
    Write-Warn 'Working tree has changes outside skills/ and agents/.'
    $unrelatedDirty | ForEach-Object { Write-Warn "  $_" }
    throw 'Aborting. Re-run with -Force to proceed anyway.'
}

Write-Info "Publishing from $LocalSkillsRoot and $LocalAgentsRoot"
Write-Info "Repository root: $RepoRoot"

if (-not $DryRun) {
    New-Item -ItemType Directory -Path $RepoSkillsRoot, $RepoAgentsRoot -Force | Out-Null
}

foreach ($skill in $SkillAllowlist) {
    $source = Join-Path $LocalSkillsRoot $skill
    $destination = Join-Path $RepoSkillsRoot $skill
    Sync-DirectoryMirror -Source $source -Destination $destination -Label "skill:$skill"
}

if (-not (Test-Path $LocalAgentsRoot)) {
    throw "Local agents directory not found: $LocalAgentsRoot"
}

$agentFiles = Get-ChildItem -Path $LocalAgentsRoot -Filter '*.md' -File
if (-not $agentFiles) {
    throw "No agent markdown files found in: $LocalAgentsRoot"
}

if ($DryRun) {
    foreach ($agent in $agentFiles) {
        $destination = Join-Path $RepoAgentsRoot $agent.Name
        Write-Info "[DryRun] Would copy agent: $($agent.FullName) -> $destination"
    }
}
else {
    New-Item -ItemType Directory -Path $RepoAgentsRoot -Force | Out-Null
    foreach ($agent in $agentFiles) {
        $destination = Join-Path $RepoAgentsRoot $agent.Name
        Copy-Item -Path $agent.FullName -Destination $destination -Force
        Write-Info "Copied agent: $($agent.Name)"
    }
}

if ($DryRun) {
    Write-Info '[DryRun] Would run: git add skills/ agents/'
    Write-Info '[DryRun] Would run: git commit'
    Write-Info 'Dry run complete. No files or git state were changed.'
    exit 0
}

Push-Location $RepoRoot
try {
    git add skills/ agents/
    if ($LASTEXITCODE -ne 0) {
        throw 'git add failed'
    }

    $status = git status --porcelain -- skills/ agents/
    if (-not $status) {
        Write-Info 'No changes to commit in skills/ or agents/.'
        exit 0
    }

    if (-not $CommitMessage) {
        $date = Get-Date -Format 'yyyy-MM-dd'
        $CommitMessage = "chore: sync skills and agents from local ($date)"
    }

    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) {
        throw 'git commit failed'
    }

    Write-Info "Committed: $CommitMessage"
    Write-Info 'Next step: git push origin main'
}
finally {
    Pop-Location
}
