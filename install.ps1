# Threadline: get it onto this computer in one line.
#
# Paste this in PowerShell and press Enter:
#
#   Windows (PowerShell):
#     irm https://raw.githubusercontent.com/roccoterr97/threadline/main/install.ps1 | iex
#
#   macOS or Linux:
#     curl -LsSf https://raw.githubusercontent.com/roccoterr97/threadline/main/install.sh | sh
#
# What it does, in order. Every step is skipped when it is already done, so
# pasting the line again is safe and carries on where things stopped.
#
#   1. Installs Git if it is missing (with winget, Windows' own installer).
#   2. Installs uv, the tool that runs Threadline, if it is missing.
#   3. Installs the GitHub command-line tool (gh) if it is missing.
#   4. Signs you in to GitHub in the browser if you are not signed in yet.
#   5. Makes your own private copy of Threadline on GitHub (from the public
#      template, as a private repository called "threadline"), waits until
#      GitHub has filled it, and downloads it to the "threadline" folder in
#      your user folder. A copy that already exists, on GitHub or in that
#      folder, is reused and brought up to date.
#   6. Installs Threadline's parts and starts the guided set-up.
#
# How the keyboard is kept: "irm | iex" runs the downloaded text inside this
# very PowerShell window, so the sign-in and the set-up read from your
# keyboard as usual. Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Everything below runs inside one script block, so its names stay out of
# your session, and it stops with a message rather than "exit", which would
# close this window before you could read why.

& {

$ErrorActionPreference = 'Stop'
# A program that ends with an error code is handled below by hand, never thrown.
$PSNativeCommandUseErrorActionPreference = $false

# The public project this copy is made from. Change it here and nowhere else.
$TemplateRepository = 'roccoterr97/threadline'

# Where the copy goes, on GitHub and on this computer.
$CopyName = 'threadline'
$CopyFolder = Join-Path $HOME 'threadline'

# The official installer of uv, and where the GitHub tool is explained.
$UvInstaller = 'https://astral.sh/uv/install.ps1'
$GitHubCliPage = 'https://cli.github.com'

# The winget names of the tools that may be missing.
$GitPackage = 'Git.Git'
$GitHubCliPackage = 'GitHub.cli'

# A freshly made copy may take a moment to appear on GitHub.
$CopyWaitAttempts = 10
$CopyWaitSeconds = 3

function Say([string] $Text) {
    Write-Host ''
    Write-Host "==> $Text"
}

function Note([string] $Text) {
    Write-Host "    $Text"
}

function Stop-Install([string] $Reason, [string[]] $Advice) {
    Write-Host ''
    Write-Host "!!  $Reason" -ForegroundColor Red
    foreach ($Line in $Advice) {
        Write-Host "    $Line"
    }
    throw 'Threadline was not installed. See the lines above.'
}

function Test-Program([string] $Name) {
    return [bool] (Get-Command $Name -ErrorAction SilentlyContinue)
}

# Picks up programs installed a moment ago, which this window does not see yet.
function Update-SessionPath {
    $Machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $User = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$Machine;$User;$env:Path"
}

# Runs a program and answers with its exit code; what it prints stays hidden.
function Invoke-Quietly([string] $Program, [string[]] $Arguments) {
    $ErrorActionPreference = 'Continue'
    & $Program @Arguments *> $null
    return $LASTEXITCODE
}

function Install-WithWinget([string] $Package, [string] $Label) {
    if (-not (Test-Program 'winget')) {
        return $false
    }
    Note "Windows may ask you to allow the installation of $Label."
    # Out-Host shows winget's progress without making it this function's answer.
    & winget install --id $Package --exact --source winget --accept-package-agreements --accept-source-agreements | Out-Host
    Update-SessionPath
    return $true
}

function Install-Git {
    if (Test-Program 'git') {
        Say 'Git is installed.'
        return
    }
    Say 'Installing Git.'
    if (-not (Install-WithWinget $GitPackage 'Git')) {
        Stop-Install 'Git is not installed yet.' @(
            'Install it from https://git-scm.com/download/win, then paste the line again.'
        )
    }
    if (-not (Test-Program 'git')) {
        Stop-Install 'Git was installed but cannot be found yet.' @(
            'Close this window, open PowerShell again, and paste the line again.'
        )
    }
}

function Install-Uv {
    if (Test-Program 'uv') {
        Say 'uv is installed.'
        return
    }
    Say 'Installing uv, the tool that runs Threadline.'
    # uv's own documented line, in a separate PowerShell so that an "exit" in
    # its installer cannot close this window. The bypass is for that one
    # process only and changes no setting of this computer.
    & powershell -NoProfile -ExecutionPolicy ByPass -Command "irm $UvInstaller | iex" | Out-Host
    # The installer adds uv to future windows; this one needs it now.
    $UvFolder = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } else { Join-Path $HOME '.local\bin' }
    $env:Path = "$UvFolder;$env:Path"
    Update-SessionPath
    if (-not (Test-Program 'uv')) {
        Stop-Install 'uv was installed but cannot be found yet.' @(
            'Close this window, open PowerShell again, and paste the line again.'
        )
    }
}

function Install-GitHubCli {
    if (Test-Program 'gh') {
        Say 'The GitHub tool (gh) is installed.'
        return
    }
    Say 'Installing the GitHub tool (gh).'
    if (-not (Install-WithWinget $GitHubCliPackage 'the GitHub tool')) {
        Stop-Install 'The GitHub tool could not be installed automatically.' @(
            "Install it by hand from $GitHubCliPage, then paste the line again."
        )
    }
    if (-not (Test-Program 'gh')) {
        Stop-Install 'The GitHub tool was installed but cannot be found yet.' @(
            'Close this window, open PowerShell again, and paste the line again.'
        )
    }
}

function Connect-GitHub {
    if ((Invoke-Quietly 'gh' @('auth', 'status')) -eq 0) {
        Say 'You are signed in to GitHub.'
    } else {
        Say 'Signing you in to GitHub: a browser window opens, follow what it says.'
        & gh auth login --hostname github.com --web --git-protocol https
        if ($LASTEXITCODE -ne 0) {
            Stop-Install 'The GitHub sign-in did not finish.' @('Paste the line again to retry.')
        }
    }
    # Lets git download and upload your private copy with the same sign-in.
    & gh auth setup-git
}

# Answers with the copy's full name (you/threadline) when it exists on GitHub.
function Get-ExistingCopy {
    $ErrorActionPreference = 'Continue'
    $Name = & gh repo view $CopyName --json nameWithOwner --jq .nameWithOwner 2> $null
    if ($LASTEXITCODE -eq 0 -and $Name) {
        return "$Name".Trim()
    }
    return $null
}

# Tells whether GitHub shows the project's files in the copy.
function Test-CopyContent([string] $FullName) {
    $Path = "repos/$FullName/contents/backend/pyproject.toml"
    return (Invoke-Quietly 'gh' @('api', $Path, '--silent')) -eq 0
}

# GitHub fills a copy made from the template in the background, so a clone
# taken straight away can be empty. Waits for the files, then names the copy.
function Wait-ForCopy {
    $Attempt = 0
    while ($true) {
        $FullName = Get-ExistingCopy
        if ($FullName -and (Test-CopyContent $FullName)) {
            return $FullName
        }
        $Attempt += 1
        if ($Attempt -gt $CopyWaitAttempts) {
            Stop-Install 'Your copy on GitHub is not ready yet.' @('Wait a minute, then paste the line again.')
        }
        Note 'GitHub is still preparing your copy; waiting a moment.'
        Start-Sleep -Seconds $CopyWaitSeconds
    }
}

function Get-Copy {
    if (Test-Path (Join-Path $CopyFolder '.git')) {
        Say "Your copy is already at $CopyFolder; bringing it up to date."
        & git -C $CopyFolder pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            Note 'It could not be updated; carrying on with what is there.'
        }
        return
    }
    if (Test-Path $CopyFolder) {
        Stop-Install "$CopyFolder exists but is not a copy of Threadline." @(
            'Move or rename that folder, then paste the line again.'
        )
    }
    if (Get-ExistingCopy) {
        Say "You already have a copy called '$CopyName' on GitHub; downloading it to $CopyFolder."
    } else {
        Say 'Making your private copy of Threadline on GitHub.'
        & gh repo create $CopyName --template $TemplateRepository --private | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Stop-Install 'Your copy could not be made on GitHub.' @('Paste the line again to retry.')
        }
    }
    $FullName = Wait-ForCopy
    Say "Downloading $FullName to $CopyFolder."
    & gh repo clone $FullName $CopyFolder | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Stop-Install 'Your copy could not be downloaded.' @('Paste the line again to retry.')
    }
}

function Start-Setup {
    Say "Installing Threadline's parts."
    Set-Location (Join-Path $CopyFolder 'backend')
    & uv sync
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Threadline's parts could not be installed." @('Paste the line again to retry.')
    }
    Say 'Starting the guided set-up. From now on it asks you what it needs.'
    Note "To come back later: open PowerShell, type 'cd ~\threadline\backend', then"
    Note "'uv run tracker setup'."
    & uv run tracker setup
}

try {
    Install-Git
    Install-Uv
    Install-GitHubCli
    Connect-GitHub
    Get-Copy
    Start-Setup
} catch {
    Write-Host ''
    Write-Host "!!  $($_.Exception.Message)" -ForegroundColor Red
}

}
