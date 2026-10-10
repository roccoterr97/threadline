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
#   2. Installs uv, the tool that runs Threadline, if it is missing. uv's own
#      installer also adds uv to your user PATH, so that new PowerShell windows
#      find it.
#   3. Installs the GitHub command-line tool (gh) if it is missing, or updates
#      it when it is too old (with winget).
#   4. Installs Claude Code if it is missing, with Anthropic's own installer,
#      which puts the "claude" command in the ".local\bin" folder in your user
#      folder. Claude Code may need Git, which step 1 adds first. You use it
#      to make the key that lets the daily run use your Claude subscription.
#      If it cannot be installed, the installer carries on: the set-up asks
#      you to paste that key either way.
#   5. Signs you in to GitHub in the browser if you are not signed in yet, with
#      the extra permission that saving the daily-run file needs. Then it runs
#      "gh auth setup-git", which adds a line to your git settings so that git
#      uses this GitHub sign-in for github.com. If git has no name or e-mail
#      yet, it sets them from your GitHub account (GitHub's private no-reply
#      address) and tells you; values you already set are never changed.
#   6. Makes your own private copy of Threadline on GitHub (from the public
#      template, as a private repository called "threadline"), waits until
#      GitHub has filled it, and downloads it to the "threadline" folder in
#      your user folder. A copy that already exists, on GitHub or in that
#      folder, is reused and brought up to date, after checking that it is
#      private and yours. An earlier set-up in the "tracker" folder is offered
#      instead of a second copy.
#   7. Installs Threadline's parts and starts the guided set-up.
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
# Windows PowerShell 5.1 downloads far faster without its progress bar.
$ProgressPreference = 'SilentlyContinue'
# A program that ends with an error code is handled below by hand, never thrown.
$PSNativeCommandUseErrorActionPreference = $false

# The public project this copy is made from. Change it here and nowhere else.
$TemplateRepository = 'roccoterr97/threadline'

# Where the copy goes, on GitHub and on this computer.
$CopyName = 'threadline'
$CopyFolder = Join-Path $HOME 'threadline'

# Where an earlier version of the set-up put the copy.
$OlderCopyFolder = Join-Path $HOME 'tracker'

# The folder that finally holds the copy; Get-Copy may point it at the older one.
$State = @{ Folder = $CopyFolder }

# The official installer of uv, and where the GitHub tool is explained.
$UvInstaller = 'https://astral.sh/uv/install.ps1'
$GitHubCliPage = 'https://cli.github.com'

# Anthropic's official installer of Claude Code, where it puts "claude", and
# where its installation is explained.
$ClaudeInstaller = 'https://claude.ai/install.ps1'
$ClaudeFolder = Join-Path $HOME '.local\bin'
$ClaudeSetupPage = 'https://code.claude.com/docs/en/setup'

# The winget names of the tools that may be missing, and where to get them by hand.
$GitPackage = 'Git.Git'
$GitHubCliPackage = 'GitHub.cli'
$GitPage = 'https://git-scm.com/download/win'
$WingetPage = 'https://aka.ms/getwinget'

# The oldest GitHub tool the set-up works with. It uses "gh variable",
# "gh secret list --json", "gh workflow run" and "gh attestation verify
# --source-ref", the last of which arrived in 2.68. Keep equal to
# GITHUB_CLI_MINIMUM_VERSION in the backend.
$GitHubCliMinimum = [version] '2.68'

# The permission a GitHub sign-in needs to save the daily-run file (a workflow).
$GitHubWorkflowScope = 'workflow'

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

# Downloads a web address into a file; any failure is an error, never a half-written file.
function Save-Download([string] $Address, [string] $Path) {
    # Older Windows PowerShell does not ask for TLS 1.2 by itself.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Address -OutFile $Path
}

# Runs winget (Windows' own installer) for one package and answers with its exit code.
function Invoke-Winget([string] $Verb, [string] $Package, [string] $Label, [string] $ManualPage) {
    if (-not (Test-Program 'winget')) {
        Stop-Install "Windows' installer (winget) is not on this computer, so $Label cannot be installed for you." @(
            "Get 'App Installer' from the Microsoft Store ($WingetPage), then paste the line again.",
            "Or install $Label by hand from $ManualPage, then paste the line again."
        )
    }
    Note "Windows may ask you to allow the installation of $Label."
    # Out-Host shows winget's progress without making it this function's answer.
    & winget $Verb --id $Package --exact --source winget --accept-package-agreements --accept-source-agreements | Out-Host
    $Code = $LASTEXITCODE
    Update-SessionPath
    return $Code
}

function Stop-WingetFailed([string] $Label, [int] $Code, [string] $ManualPage) {
    Stop-Install "The installation of $Label did not finish (code $Code)." @(
        'The usual causes are that the Windows question "Do you want to allow this app',
        'to make changes?" was closed or answered No (it needs administrator approval),',
        'or that the internet connection dropped.',
        'Paste the line again and click Yes when Windows asks.',
        "If it keeps failing, install $Label by hand from $ManualPage, then paste the line again."
    )
}

function Install-Git {
    if (Test-Program 'git') {
        Say 'Git is installed.'
        return
    }
    Say 'Installing Git.'
    $Code = Invoke-Winget 'install' $GitPackage 'Git' $GitPage
    # Winget also answers with an error code when Git is already there but this
    # window cannot see it yet; Git being found after all is what counts.
    if ($Code -ne 0 -and -not (Test-Program 'git')) {
        Stop-WingetFailed 'Git' $Code $GitPage
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
    # Saved first and run second, in a separate PowerShell so that an "exit" in
    # uv's installer cannot close this window. The bypass is for that one
    # process only and changes no setting of this computer.
    $UvScript = Join-Path ([IO.Path]::GetTempPath()) "threadline-uv-install-$PID.ps1"
    try {
        Save-Download $UvInstaller $UvScript
    } catch {
        Stop-Install 'Could not download uv.' @('Check your internet connection, then paste the line again.')
    }
    try {
        & powershell -NoProfile -ExecutionPolicy ByPass -File $UvScript | Out-Host
        $UvCode = $LASTEXITCODE
    } finally {
        Remove-Item $UvScript -ErrorAction SilentlyContinue
    }
    if ($UvCode -ne 0) {
        Stop-Install "The uv installer did not finish (code $UvCode)." @(
            'Read the lines above for the reason, then paste the line again.'
        )
    }
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

# Claude Code makes the key that lets the daily run use your Claude
# subscription. Without it the set-up still works, so a failure here is said
# and the installer carries on.
function Install-ClaudeCode {
    if ((Test-Program 'claude') -or (Test-Path (Join-Path $ClaudeFolder 'claude.exe'))) {
        Use-ClaudeFolder
        Say 'Claude Code is installed.'
        return
    }
    Say 'Installing Claude Code, which makes the key for your Claude subscription.'
    # Saved first and run second, in a separate PowerShell, as for uv.
    $ClaudeScript = Join-Path ([IO.Path]::GetTempPath()) "threadline-claude-install-$PID.ps1"
    try {
        Save-Download $ClaudeInstaller $ClaudeScript
        & powershell -NoProfile -ExecutionPolicy ByPass -File $ClaudeScript | Out-Host
        $ClaudeCode = $LASTEXITCODE
    } catch {
        $ClaudeCode = 1
    } finally {
        Remove-Item $ClaudeScript -ErrorAction SilentlyContinue
    }
    Use-ClaudeFolder
    if ($ClaudeCode -ne 0 -or -not (Test-Program 'claude')) {
        Note 'Claude Code did not install. You can carry on: install it later from'
        Note "$ClaudeSetupPage before the set-up asks for the Claude key."
    }
}

# The installer adds Claude Code to future windows, or says how; this one needs it now.
function Use-ClaudeFolder {
    if (-not (($env:Path -split ';') -contains $ClaudeFolder)) {
        $env:Path = "$ClaudeFolder;$env:Path"
    }
    Update-SessionPath
}

# Answers with the installed GitHub tool's version, or $null when it cannot be read.
function Get-GitHubCliVersion {
    $ErrorActionPreference = 'Continue'
    $Line = & gh --version 2> $null | Select-Object -First 1
    if ("$Line" -match 'gh version (\d+\.\d+(\.\d+)?)') {
        return [version] $Matches[1]
    }
    return $null
}

function Test-GitHubCliRecent {
    $Version = Get-GitHubCliVersion
    return ($null -ne $Version) -and ($Version -ge $GitHubCliMinimum)
}

function Install-GitHubCli {
    $Installed = Test-Program 'gh'
    if ($Installed -and (Test-GitHubCliRecent)) {
        Say 'The GitHub tool (gh) is installed.'
        return
    }
    if ($Installed) {
        Say 'Updating the GitHub tool (gh).'
        Note "Version $(Get-GitHubCliVersion) is older than the $GitHubCliMinimum that Threadline needs."
        $Verb = 'upgrade'
    } else {
        Say 'Installing the GitHub tool (gh).'
        $Verb = 'install'
    }
    $Code = Invoke-Winget $Verb $GitHubCliPackage 'the GitHub tool' $GitHubCliPage
    if ($Code -ne 0 -and ($Installed -or -not (Test-Program 'gh'))) {
        Stop-WingetFailed 'the GitHub tool' $Code $GitHubCliPage
    }
    if (-not (Test-Program 'gh')) {
        Stop-Install 'The GitHub tool was installed but cannot be found yet.' @(
            'Close this window, open PowerShell again, and paste the line again.'
        )
    }
    if (-not (Test-GitHubCliRecent)) {
        Stop-Install "The GitHub tool this computer uses is still version $(Get-GitHubCliVersion)." @(
            "Threadline needs $GitHubCliMinimum or newer. Install the newest from $GitHubCliPage,",
            'close this window, open PowerShell again, and paste the line again.'
        )
    }
}

# Answers with the permissions of the GitHub sign-in as one text, or $null for a
# kind of sign-in that does not list them.
function Get-GitHubScopes {
    $ErrorActionPreference = 'Continue'
    $Lines = & gh api --include user 2> $null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    foreach ($Line in $Lines) {
        if ("$Line" -imatch '^x-oauth-scopes:\s*(.*)$') {
            return $Matches[1].Trim()
        }
    }
    return $null
}

# A sign-in made before this installer asked for the workflow permission cannot
# save the daily-run file later, so it is topped up now.
function Confirm-WorkflowPermission {
    $Scopes = Get-GitHubScopes
    if ($null -eq $Scopes) {
        return
    }
    if (($Scopes -split '\s*,\s*') -contains $GitHubWorkflowScope) {
        return
    }
    Say 'Your GitHub sign-in needs one more permission, to save the daily-run file.'
    Note 'A browser window opens: follow what it says.'
    & gh auth refresh --hostname github.com --scopes $GitHubWorkflowScope
    if ($LASTEXITCODE -ne 0) {
        Stop-Install 'The extra GitHub permission was not added.' @(
            "Run 'gh auth login --scopes $GitHubWorkflowScope' (if you set GH_TOKEN, give that token",
            "the '$GitHubWorkflowScope' permission), then paste the line again."
        )
    }
}

# Git records a name and an e-mail address with every change, and the set-up
# saves one change. A new computer has neither, so they are taken from the
# GitHub account, using GitHub's private no-reply address. Values that are
# already set are never touched.
function Confirm-GitIdentity {
    $ErrorActionPreference = 'Continue'
    $GitName = "$(& git config user.name 2> $null)".Trim()
    $GitEmail = "$(& git config user.email 2> $null)".Trim()
    if ($GitName -and $GitEmail) {
        return
    }
    $AccountJson = (& gh api user 2> $null) -join "`n"
    $Account = if ($LASTEXITCODE -eq 0 -and $AccountJson) { $AccountJson | ConvertFrom-Json } else { $null }
    if (-not $Account -or -not $Account.login -or -not $Account.id) {
        Stop-Install 'Could not read your GitHub account.' @(
            'Tell git who you are with these two lines (use your own name and e-mail), then paste the line again:',
            '  git config --global user.name "Your Name"',
            '  git config --global user.email you@example.com'
        )
    }
    Say 'Git did not know your name or e-mail address, which it needs to save changes.'
    if (-not $GitName) {
        $NewName = if ($Account.name) { $Account.name } else { $Account.login }
        & git config --global user.name $NewName
        Note "Set your name to ""$NewName"" (from your GitHub account)."
    }
    if (-not $GitEmail) {
        $NewEmail = "$($Account.id)+$($Account.login)@users.noreply.github.com"
        & git config --global user.email $NewEmail
        Note "Set your e-mail to $NewEmail, GitHub's private"
        Note 'address for you; your real address stays hidden.'
    }
    Note 'Change either later with: git config --global user.name "New Name"'
}

function Connect-GitHub {
    if ((Invoke-Quietly 'gh' @('auth', 'status')) -eq 0) {
        Say 'You are signed in to GitHub.'
        Confirm-WorkflowPermission
    } else {
        Say 'Signing you in to GitHub: a browser window opens, follow what it says.'
        Note 'Before you click Authorize, check the account name at the top of the GitHub page:'
        Note "if it is not the account you want Threadline on, click 'Use a different account'."
        & gh auth login --hostname github.com --web --git-protocol https --scopes $GitHubWorkflowScope
        if ($LASTEXITCODE -ne 0) {
            Stop-Install 'The GitHub sign-in did not finish.' @('Paste the line again to retry.')
        }
    }
    # Lets git download and upload your private copy with the same sign-in.
    & gh auth setup-git
    Confirm-GitIdentity
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

# Answers with what matters about the repository called "threadline" on this
# GitHub account, or $null when there is none.
function Get-CopyFacts {
    $ErrorActionPreference = 'Continue'
    $Json = (& gh repo view $CopyName --json nameWithOwner,isPrivate,viewerPermission,templateRepository 2> $null) -join "`n"
    if ($LASTEXITCODE -ne 0 -or -not $Json) {
        return $null
    }
    return $Json | ConvertFrom-Json
}

# Tells whether GitHub shows the project's files in the copy.
function Test-CopyContent([string] $FullName) {
    $Path = "repos/$FullName/contents/backend/pyproject.toml"
    return (Invoke-Quietly 'gh' @('api', $Path, '--silent')) -eq 0
}

# A repository that already has the name must be this tool's own private copy,
# or the set-up would put your mail summaries somewhere else. Answers $true when
# a usable copy exists, $false when there is none, and stops on one that is unfit.
function Test-ExistingCopy {
    $Facts = Get-CopyFacts
    if (-not $Facts) {
        return $false
    }
    $Name = $Facts.nameWithOwner
    # The account that publishes the template finds the template itself under
    # this name, and can never have a copy of its own called that.
    if ($Name -eq $TemplateRepository) {
        Stop-Install "You are signed in to GitHub with the account that publishes Threadline ($Name)." @(
            "Your own copy needs the name '$CopyName', which this account already uses for Threadline itself.",
            "Sign in to GitHub with another account: run 'gh auth logout', then paste the line again",
            'and sign in with the other account when the browser opens.'
        )
    }
    if (-not $Facts.isPrivate) {
        Stop-Install "$Name on GitHub is public." @(
            'Your copy of Threadline must be private, because it will hold your job-search data.',
            'Make it private (on GitHub: Settings, then Danger Zone, then Change visibility),',
            'or rename it so a new copy can be made, then paste the line again.'
        )
    }
    if ($Facts.viewerPermission -ne 'ADMIN') {
        Stop-Install "You are not the owner of $Name (your access: $($Facts.viewerPermission))." @(
            'The set-up needs to change its settings and secrets.',
            'Rename or remove that repository, or sign in to GitHub as its owner, then paste the line again.'
        )
    }
    $Template = $Facts.templateRepository
    $TemplateName = if ($Template) { "$($Template.owner.login)/$($Template.name)" } else { '' }
    if ($TemplateName -ne $TemplateRepository -and -not (Test-CopyContent $Name)) {
        Stop-Install "$Name is not a copy of Threadline." @(
            'A repository with the same name already exists on your GitHub account.',
            'Rename it on GitHub (Settings, then Repository name), or delete it if you do not need it,',
            'then paste the line again.'
        )
    }
    return $true
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

# Brings the copy in a folder up to date, when it is a git folder.
function Update-Copy([string] $Folder) {
    Say "Your copy is already at $Folder; bringing it up to date."
    if (-not (Test-Path (Join-Path $Folder '.git'))) {
        return
    }
    & git -C $Folder pull --ff-only | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Note 'It could not be updated; carrying on with what is there.'
    }
}

# An earlier version of the set-up kept the copy in ~\tracker. Offers to carry
# on with it rather than make a second copy that would start from nothing.
function Test-OlderCopyWanted {
    if (-not (Test-Path (Join-Path $OlderCopyFolder 'backend\pyproject.toml'))) {
        return $false
    }
    Say "An earlier Threadline set-up is already on this computer, at $OlderCopyFolder."
    Note 'Using it keeps the settings you saved there; a new copy starts from the beginning.'
    $Answer = Read-Host '    Use the earlier set-up? [Y/n]'
    return -not ("$Answer" -match '^\s*[nN]')
}

function Get-NewCopy {
    if (Test-ExistingCopy) {
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

# Settles which folder holds the copy (in $State.Folder) and brings it up to date.
function Get-Copy {
    if (Test-Path (Join-Path $CopyFolder '.git')) {
        Update-Copy $CopyFolder
        return
    }
    if (Test-Path $CopyFolder) {
        Stop-Install "$CopyFolder exists but is not a copy of Threadline." @(
            'Move or rename that folder, then paste the line again.'
        )
    }
    if (Test-OlderCopyWanted) {
        $State.Folder = $OlderCopyFolder
        Update-Copy $OlderCopyFolder
        return
    }
    Get-NewCopy
}

function Start-Setup {
    $Folder = $State.Folder
    if (-not (Test-Path (Join-Path $Folder 'backend\pyproject.toml'))) {
        Stop-Install "$Folder does not hold Threadline's files." @(
            'Move or rename that folder, then paste the line again.'
        )
    }
    Say "Installing Threadline's parts. The first time, this can download Python and take a few minutes."
    Set-Location (Join-Path $Folder 'backend')
    & uv sync
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Threadline's parts could not be installed." @('Paste the line again to retry.')
    }
    Say 'Starting the guided set-up. From now on it asks you what it needs.'
    $Shown = $Folder.Replace($HOME, '~')
    Note "To come back later: open PowerShell, type 'cd $Shown\backend', then"
    Note "'uv run tracker setup'."
    & uv run tracker setup
}

try {
    Install-Git
    Install-Uv
    Install-GitHubCli
    Install-ClaudeCode
    Connect-GitHub
    Get-Copy
    Start-Setup
} catch {
    Write-Host ''
    Write-Host "!!  $($_.Exception.Message)" -ForegroundColor Red
}

}
