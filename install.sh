#!/bin/sh
# Threadline: get it onto this computer in one line.
#
# Paste this in a terminal and press Return:
#
#   macOS or Linux:
#     curl -LsSf https://raw.githubusercontent.com/roccoterr97/threadline/main/install.sh | sh
#
#   Windows (PowerShell):
#     irm https://raw.githubusercontent.com/roccoterr97/threadline/main/install.ps1 | iex
#
# What it does, in order. Every step is skipped when it is already done, so
# pasting the line again is safe and carries on where things stopped.
#
#   1. Checks that git is installed (on a Mac, the system offers to install it).
#   2. Installs uv, the tool that runs Threadline, if it is missing. uv's own
#      installer also adds uv to your terminal's PATH: it adds a line to your
#      shell's start-up file (such as .zshrc or .profile).
#   3. Installs the GitHub command-line tool (gh) if it is missing or too old:
#      with Homebrew on a Mac, or from GitHub's own package source on Linux.
#      Where those cannot be used, it downloads GitHub's release into
#      ~/.local/bin and checks it against the release's checksums.
#   4. Signs you in to GitHub in the browser if you are not signed in yet, with
#      the extra permission that saving the daily-run file needs. Then it runs
#      "gh auth setup-git", which adds a line to your git settings so that git
#      uses this GitHub sign-in for github.com. If git has no name or e-mail
#      yet, it sets them from your GitHub account (GitHub's private no-reply
#      address) and tells you; values you already set are never changed.
#   5. Makes your own private copy of Threadline on GitHub (from the public
#      template, as a private repository called "threadline"), waits until
#      GitHub has filled it, and downloads it to ~/threadline. A copy that
#      already exists, on GitHub or in that folder, is reused and brought up
#      to date, after checking that it is private and yours. An earlier
#      set-up in ~/tracker is offered instead of a second copy.
#   6. Installs Threadline's parts and starts the guided set-up.
#
# How the terminal is kept: with "curl | sh", the shell reads this script from
# the pipe, so the keyboard is not where "stdin" points. The whole script is
# one function, called on the very last line with its input re-attached to
# the terminal (/dev/tty). That gives the shell the complete script before any
# of it runs (a connection that drops half-way cannot run half a script) and
# gives the sign-in and the set-up the keyboard they need. Without a terminal
# (a job that runs unattended) the function runs with the input it was given.

set -eu

# The public project this copy is made from. Change it here and nowhere else.
TEMPLATE_REPOSITORY="roccoterr97/threadline"

# Where the copy goes, on GitHub and on this computer.
COPY_NAME="threadline"
COPY_FOLDER="$HOME/threadline"

# Where an earlier version of the set-up put the copy.
OLDER_COPY_FOLDER="$HOME/tracker"

# The official installer of uv, and where the GitHub tool is explained.
UV_INSTALLER="https://astral.sh/uv/install.sh"
GITHUB_CLI_PAGE="https://cli.github.com"

# The oldest GitHub tool the set-up works with. It uses "gh variable",
# "gh secret list --json", "gh workflow run" and "gh attestation verify
# --source-ref", the last of which arrived in 2.68. Apt on Debian 12 and
# Ubuntu 22.04 offers versions far older than that, so Linux uses GitHub's own
# package sources. Keep equal to GITHUB_CLI_MINIMUM_VERSION in the backend.
GITHUB_CLI_MINIMUM="2.68"

# GitHub's official package sources and release downloads for the GitHub tool.
GITHUB_CLI_PACKAGES="https://cli.github.com/packages"
GITHUB_CLI_LATEST_RELEASE="https://github.com/cli/cli/releases/latest"
GITHUB_CLI_DOWNLOADS="https://github.com/cli/cli/releases/download"
APT_KEYRING="/etc/apt/keyrings/githubcli-archive-keyring.gpg"
APT_SOURCE="/etc/apt/sources.list.d/github-cli.list"
DNF_REPOSITORY_FILE="/etc/yum.repos.d/gh-cli.repo"

# Where a downloaded GitHub tool goes when no package manager can install it.
LOCAL_BIN="$HOME/.local/bin"

# Where uv puts itself, so it works in this very session.
UV_FOLDER="${UV_INSTALL_DIR:-$HOME/.local/bin}"

# Where downloads are kept while the installer runs; made in main, removed at the end.
WORK_DIR=""

# The permission a GitHub sign-in needs to save the daily-run file (a workflow).
GITHUB_WORKFLOW_SCOPE="workflow"

# A freshly made copy may take a moment to appear on GitHub.
COPY_WAIT_ATTEMPTS=10
COPY_WAIT_SECONDS=3

say() {
  printf '\n==> %s\n' "$1"
}

note() {
  printf '    %s\n' "$1"
}

stop() {
  printf '\n!!  %s\n' "$1" >&2
  shift
  for line in "$@"; do
    printf '    %s\n' "$line" >&2
  done
  exit 1
}

has() {
  command -v "$1" >/dev/null 2>&1
}

# Asks a yes/no question, with yes as the answer to a bare Return (and when
# there is no keyboard to ask).
ask_yes_no() {
  printf '    %s [Y/n] ' "$1"
  answer=""
  read -r answer || answer=""
  case "$answer" in
    [nN]*) return 1 ;;
    *) return 0 ;;
  esac
}

cleanup() {
  [ -z "$WORK_DIR" ] || rm -rf "$WORK_DIR"
}

# Downloads $1 into the file $2: secure connection only, and any failure
# (no network, a missing page) is an error rather than a half-written file.
download() {
  curl --proto '=https' --tlsv1.2 -fsSL -o "$2" "$1"
}

operating_system() {
  case "$(uname -s)" in
    Darwin) echo "mac" ;;
    Linux) echo "linux" ;;
    *) echo "other" ;;
  esac
}

# Runs a package manager's install, with sudo only when it is there and needed.
install_with() {
  if [ "$(id -u)" = "0" ]; then
    "$@"
  elif has sudo; then
    note "Your computer's password may be asked for, to install the GitHub tool."
    sudo "$@"
  else
    return 1
  fi
}

check_git() {
  if git --version >/dev/null 2>&1; then
    return
  fi
  if [ "$(operating_system)" = "mac" ]; then
    stop "Git is not installed yet." \
      "A window may just have opened offering to install the 'command line developer" \
      "tools': click Install and wait for it to finish. Then paste the line again."
  fi
  stop "Git is not installed yet." \
    "Install it with your system's package manager (for example 'sudo apt install git')," \
    "then paste the line again."
}

check_curl() {
  has curl || stop "curl is not installed yet." \
    "Install it with your system's package manager (for example 'sudo apt install curl')," \
    "then paste the line again."
}

install_uv() {
  if has uv; then
    say "uv is installed."
    return
  fi
  say "Installing uv, the tool that runs Threadline."
  # Saved first and run second: piped straight into the shell, a failed download
  # would look like a successful empty install.
  uv_installer="$WORK_DIR/uv-install.sh"
  download "$UV_INSTALLER" "$uv_installer" || stop "Could not download uv." \
    "Check your internet connection, then paste the line again."
  sh "$uv_installer" || stop "The uv installer did not finish." \
    "Read the lines above for the reason, then paste the line again."
  # The installer adds uv to future terminals; this session needs it now.
  if [ -f "$UV_FOLDER/env" ]; then
    # shellcheck source=/dev/null
    . "$UV_FOLDER/env"
  fi
  PATH="$UV_FOLDER:$PATH"
  export PATH
  has uv || stop "uv was installed but cannot be found yet." \
    "Close this terminal, open a new one, and paste the line again."
}

# Prints the installed GitHub tool's version, such as 2.68.0 (nothing if unreadable).
github_cli_version() {
  gh --version 2>/dev/null | sed -n '1s/^gh version \([0-9][0-9.]*\).*/\1/p'
}

# Succeeds when version $1 is at least version $2 (both like 2.68 or 2.68.0).
version_at_least() {
  awk -v have="$1" -v need="$2" 'BEGIN {
    count = split(have, h, "."); wanted = split(need, w, ".")
    for (i = 1; i <= (count > wanted ? count : wanted); i++) {
      if (h[i] + 0 > w[i] + 0) exit 0
      if (h[i] + 0 < w[i] + 0) exit 1
    }
    exit 0
  }'
}

install_github_cli() {
  if has gh; then
    version="$(github_cli_version)"
    if version_at_least "$version" "$GITHUB_CLI_MINIMUM"; then
      say "The GitHub tool (gh) is installed."
      return
    fi
    say "Updating the GitHub tool (gh)."
    note "Version ${version:-unknown} is older than the $GITHUB_CLI_MINIMUM that Threadline needs."
  else
    say "Installing the GitHub tool (gh)."
  fi
  case "$(operating_system)" in
    mac) install_github_cli_mac ;;
    linux) install_github_cli_linux ;;
    *)
      stop "This installer knows macOS and Linux only." \
        "On Windows, open PowerShell and paste the Windows line at the top of this script."
      ;;
  esac
  confirm_github_cli
}

confirm_github_cli() {
  hash -r
  has gh || stop "The GitHub tool was installed but cannot be found yet." \
    "Close this terminal, open a new one, and paste the line again."
  version="$(github_cli_version)"
  version_at_least "$version" "$GITHUB_CLI_MINIMUM" || stop \
    "The GitHub tool this computer uses is still version ${version:-unknown} ($(command -v gh))." \
    "Threadline needs $GITHUB_CLI_MINIMUM or newer. Install the newest from $GITHUB_CLI_PAGE," \
    "close this terminal, open a new one, and paste the line again."
}

install_github_cli_mac() {
  if ! has brew; then
    note "Homebrew is not installed; downloading the GitHub tool directly."
    install_github_cli_from_release
    return
  fi
  if brew list gh >/dev/null 2>&1; then
    brew upgrade gh
  else
    brew install gh
  fi
}

install_github_cli_linux() {
  if has apt-get && install_github_cli_with_apt; then
    return
  fi
  if has dnf && install_github_cli_with_dnf; then
    return
  fi
  note "This computer's package manager could not be used; downloading the GitHub tool directly."
  install_github_cli_from_release
}

# GitHub's own package source, set up as cli.github.com describes it. The
# distribution's own "gh" package is too old on several common systems.
install_github_cli_with_apt() {
  apt_key="$WORK_DIR/githubcli-archive-keyring.gpg"
  apt_list="$WORK_DIR/github-cli.list"
  download "$GITHUB_CLI_PACKAGES/githubcli-archive-keyring.gpg" "$apt_key" || return 1
  printf 'deb [arch=%s signed-by=%s] %s stable main\n' \
    "$(dpkg --print-architecture)" "$APT_KEYRING" "$GITHUB_CLI_PACKAGES" >"$apt_list"
  install_with install -D -m 644 "$apt_key" "$APT_KEYRING" || return 1
  install_with install -D -m 644 "$apt_list" "$APT_SOURCE" || return 1
  install_with apt-get update || return 1
  install_with apt-get install -y gh
}

install_github_cli_with_dnf() {
  dnf_file="$WORK_DIR/gh-cli.repo"
  download "$GITHUB_CLI_PACKAGES/rpm/gh-cli.repo" "$dnf_file" || return 1
  install_with install -D -m 644 "$dnf_file" "$DNF_REPOSITORY_FILE" || return 1
  install_with dnf install -y gh --repo gh-cli
}

# Prints the name GitHub gives the download for this computer, such as macOS_arm64.
release_platform() {
  case "$(operating_system):$(uname -m)" in
    mac:arm64) echo "macOS_arm64" ;;
    mac:x86_64) echo "macOS_amd64" ;;
    linux:x86_64) echo "linux_amd64" ;;
    linux:aarch64 | linux:arm64) echo "linux_arm64" ;;
    linux:armv6l | linux:armv7l) echo "linux_armv6" ;;
    linux:i386 | linux:i686) echo "linux_386" ;;
    *) return 1 ;;
  esac
}

# Prints the newest release's version, such as 2.62.0, read from where
# GitHub's "latest" address leads.
latest_github_cli_version() {
  latest_address="$(curl --proto '=https' --tlsv1.2 -fsSL -o /dev/null -w '%{url_effective}' \
    "$GITHUB_CLI_LATEST_RELEASE")" || return 1
  latest_version="${latest_address##*/v}"
  case "$latest_version" in
    "" | *[!0-9.]*) return 1 ;;
  esac
  echo "$latest_version"
}

sha256_of() {
  if has sha256sum; then
    sha256sum "$1" | awk '{ print $1 }'
  elif has shasum; then
    shasum -a 256 "$1" | awk '{ print $1 }'
  else
    return 1
  fi
}

# Succeeds when file $1, listed as $3 in the checksums file $2, matches its checksum.
checksum_matches() {
  expected_sum="$(awk -v name="$3" '$2 == name { print $1 }' "$2")"
  actual_sum="$(sha256_of "$1")" || return 1
  [ -n "$expected_sum" ] && [ "$expected_sum" = "$actual_sum" ]
}

# Downloads GitHub's own release of the GitHub tool into ~/.local/bin, checks it
# against the release's list of checksums, and puts that folder on this
# session's PATH. Needs no administrator rights and no package manager.
install_github_cli_from_release() {
  platform="$(release_platform)" || stop "No download of the GitHub tool fits this computer." \
    "Install it by hand from $GITHUB_CLI_PAGE, then paste the line again."
  release="$(latest_github_cli_version)" || stop "Could not look up the newest GitHub tool." \
    "Check your internet connection, then paste the line again."
  case "$platform" in
    macOS_*) extension="zip" ;;
    *) extension="tar.gz" ;;
  esac
  archive="gh_${release}_${platform}.${extension}"
  sums="gh_${release}_checksums.txt"
  note "Downloading the GitHub tool $release."
  { download "$GITHUB_CLI_DOWNLOADS/v$release/$archive" "$WORK_DIR/$archive" \
    && download "$GITHUB_CLI_DOWNLOADS/v$release/$sums" "$WORK_DIR/$sums"; } \
    || stop "Could not download the GitHub tool." \
      "Check your internet connection, then paste the line again."
  checksum_matches "$WORK_DIR/$archive" "$WORK_DIR/$sums" "$archive" \
    || stop "The downloaded GitHub tool did not match its checksum, so it was not used." \
      "Paste the line again; if it keeps happening, install from $GITHUB_CLI_PAGE."
  unpack_archive "$WORK_DIR/$archive" "$extension"
  built="$WORK_DIR/gh_${release}_${platform}/bin/gh"
  [ -f "$built" ] || stop "The downloaded GitHub tool was not what was expected." \
    "Install it by hand from $GITHUB_CLI_PAGE, then paste the line again."
  mkdir -p "$LOCAL_BIN"
  install -m 755 "$built" "$LOCAL_BIN/gh"
  PATH="$LOCAL_BIN:$PATH"
  export PATH
  note "The GitHub tool is now in $LOCAL_BIN."
}

# Unpacks archive $1 (of kind $2) into the work folder.
unpack_archive() {
  case "$2" in
    zip) unzip -q "$1" -d "$WORK_DIR" ;;
    *) tar -xzf "$1" -C "$WORK_DIR" ;;
  esac
}

# Prints "scopes:" and the permissions of the GitHub sign-in, or nothing for a
# kind of sign-in that does not list them.
github_scopes() {
  gh api --include user 2>/dev/null | tr -d '\r' \
    | awk 'tolower($1) == "x-oauth-scopes:" { sub(/^[^:]*:[ ]*/, ""); print "scopes:" $0 }'
}

# A sign-in made before this installer asked for the workflow permission cannot
# save the daily-run file later, so it is topped up now.
ensure_workflow_permission() {
  scopes="$(github_scopes)"
  [ -n "$scopes" ] || return 0
  case ",$(printf '%s' "${scopes#scopes:}" | tr -d ' ')," in
    *,"$GITHUB_WORKFLOW_SCOPE",*) return 0 ;;
  esac
  say "Your GitHub sign-in needs one more permission, to save the daily-run file."
  note "A browser window opens: follow what it says."
  gh auth refresh --hostname github.com --scopes "$GITHUB_WORKFLOW_SCOPE" \
    || stop "The extra GitHub permission was not added." \
      "Run 'gh auth login --scopes $GITHUB_WORKFLOW_SCOPE' (if you set GH_TOKEN, give that token" \
      "the '$GITHUB_WORKFLOW_SCOPE' permission), then paste the line again."
}

# Sets account_login, account_id and account_name from the signed-in GitHub account.
read_github_account() {
  account_login="$(gh api user --jq .login 2>/dev/null)" || return 1
  account_id="$(gh api user --jq .id 2>/dev/null)" || return 1
  account_name="$(gh api user --jq '.name // .login' 2>/dev/null)" || return 1
  [ -n "$account_login" ] && [ -n "$account_id" ] && [ -n "$account_name" ]
}

# Git records a name and an e-mail address with every change, and the set-up
# saves one change. A new computer has neither, so they are taken from the
# GitHub account, using GitHub's private no-reply address. Values that are
# already set are never touched.
ensure_git_identity() {
  git_name="$(git config user.name 2>/dev/null || true)"
  git_email="$(git config user.email 2>/dev/null || true)"
  if [ -n "$git_name" ] && [ -n "$git_email" ]; then
    return
  fi
  read_github_account || stop "Could not read your GitHub account." \
      "Tell git who you are with these two lines (use your own name and e-mail), then paste the line again:" \
      "  git config --global user.name \"Your Name\"" \
      "  git config --global user.email you@example.com"
  say "Git did not know your name or e-mail address, which it needs to save changes."
  if [ -z "$git_name" ]; then
    git config --global user.name "$account_name"
    note "Set your name to \"$account_name\" (from your GitHub account)."
  fi
  if [ -z "$git_email" ]; then
    git config --global user.email "$account_id+$account_login@users.noreply.github.com"
    note "Set your e-mail to $account_id+$account_login@users.noreply.github.com, GitHub's private"
    note "address for you; your real address stays hidden."
  fi
  note "Change either later with: git config --global user.name \"New Name\""
}

sign_in_to_github() {
  if gh auth status >/dev/null 2>&1; then
    say "You are signed in to GitHub."
    ensure_workflow_permission
  else
    say "Signing you in to GitHub: a browser window opens, follow what it says."
    note "Before you click Authorize, check the account name at the top of the GitHub page:"
    note "if it is not the account you want Threadline on, click 'Use a different account'."
    gh auth login --hostname github.com --web --git-protocol https \
      --scopes "$GITHUB_WORKFLOW_SCOPE" \
      || stop "The GitHub sign-in did not finish." "Paste the line again to retry."
  fi
  # Lets git download and upload your private copy with the same sign-in.
  gh auth setup-git
  ensure_git_identity
}

# Prints the copy's full name (you/threadline) when it exists on GitHub.
existing_copy() {
  gh repo view "$COPY_NAME" --json nameWithOwner --jq .nameWithOwner 2>/dev/null
}

# Prints what matters about the repository called "threadline" on this
# GitHub account, as: full-name is-private your-permission template-it-came-from.
# Prints nothing when there is no such repository.
copy_facts() {
  gh repo view "$COPY_NAME" --json nameWithOwner,isPrivate,viewerPermission,templateRepository \
    --jq '[.nameWithOwner, (.isPrivate | tostring), .viewerPermission,
      ((.templateRepository // {}) | ((.owner.login // "") + "/" + (.name // "")))] | join(" ")' \
    2>/dev/null
}

lowercase() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

# A repository that already has the name must be this tool's own private copy,
# or the set-up would put your mail summaries somewhere else. Succeeds when a
# usable copy exists, fails when there is none, and stops on one that is unfit.
check_existing_copy() {
  facts="$(copy_facts)" || return 1
  [ -n "$facts" ] || return 1
  read -r found_name found_private found_permission found_template <<FACTS
$facts
FACTS
  # The account that publishes the template finds the template itself under
  # this name, and can never have a copy of its own called that.
  [ "$(lowercase "$found_name")" != "$(lowercase "$TEMPLATE_REPOSITORY")" ] \
    || stop "You are signed in to GitHub with the account that publishes Threadline ($found_name)." \
      "Your own copy needs the name '$COPY_NAME', which this account already uses for Threadline itself." \
      "Sign in to GitHub with another account: run 'gh auth logout', then paste the line again" \
      "and sign in with the other account when the browser opens."
  [ "$found_private" = "true" ] || stop "$found_name on GitHub is public." \
    "Your copy of Threadline must be private, because it will hold your job-search data." \
    "Make it private (on GitHub: Settings, then Danger Zone, then Change visibility)," \
    "or rename it so a new copy can be made, then paste the line again."
  [ "$found_permission" = "ADMIN" ] || stop "You are not the owner of $found_name (your access: $found_permission)." \
    "The set-up needs to change its settings and secrets." \
    "Rename or remove that repository, or sign in to GitHub as its owner, then paste the line again."
  [ "$(lowercase "$found_template")" = "$(lowercase "$TEMPLATE_REPOSITORY")" ] \
    || copy_has_content "$found_name" \
    || stop "$found_name is not a copy of Threadline." \
      "A repository with the same name already exists on your GitHub account." \
      "Rename it on GitHub (Settings, then Repository name), or delete it if you do not need it," \
      "then paste the line again."
}

# Succeeds once GitHub shows the project's files in the copy named by $1.
copy_has_content() {
  gh api "repos/$1/contents/backend/pyproject.toml" --silent >/dev/null 2>&1
}

# GitHub fills a copy made from the template in the background, so a clone
# taken straight away can be empty. Waits for the files, then sets COPY_FULL_NAME.
wait_for_copy() {
  attempt=0
  until COPY_FULL_NAME="$(existing_copy)" && copy_has_content "$COPY_FULL_NAME"; do
    attempt=$((attempt + 1))
    [ "$attempt" -le "$COPY_WAIT_ATTEMPTS" ] || stop "Your copy on GitHub is not ready yet." \
      "Wait a minute, then paste the line again."
    note "GitHub is still preparing your copy; waiting a moment."
    sleep "$COPY_WAIT_SECONDS"
  done
}

# Brings the copy in folder $1 up to date, when it is a git folder.
bring_up_to_date() {
  say "Your copy is already at $1; bringing it up to date."
  [ -d "$1/.git" ] || return 0
  git -C "$1" pull --ff-only || note "It could not be updated; carrying on with what is there."
}

# An earlier version of the set-up kept the copy in ~/tracker. Offers to carry
# on with it rather than make a second copy that would start from nothing.
older_copy_wanted() {
  [ -f "$OLDER_COPY_FOLDER/backend/pyproject.toml" ] || return 1
  say "An earlier Threadline set-up is already on this computer, at $OLDER_COPY_FOLDER."
  note "Using it keeps the settings you saved there; a new copy starts from the beginning."
  ask_yes_no "Use the earlier set-up?"
}

download_copy() {
  if check_existing_copy; then
    say "You already have a copy called '$COPY_NAME' on GitHub; downloading it to $COPY_FOLDER."
  else
    say "Making your private copy of Threadline on GitHub."
    gh repo create "$COPY_NAME" --template "$TEMPLATE_REPOSITORY" --private
  fi
  wait_for_copy
  say "Downloading $COPY_FULL_NAME to $COPY_FOLDER."
  gh repo clone "$COPY_FULL_NAME" "$COPY_FOLDER"
}

# Settles which folder holds the copy (setting COPY_FOLDER) and brings it up to date.
get_copy() {
  if [ -d "$COPY_FOLDER/.git" ]; then
    bring_up_to_date "$COPY_FOLDER"
    return
  fi
  if [ -e "$COPY_FOLDER" ]; then
    stop "$COPY_FOLDER exists but is not a copy of Threadline." \
      "Move or rename that folder, then paste the line again."
  fi
  if older_copy_wanted; then
    COPY_FOLDER="$OLDER_COPY_FOLDER"
    bring_up_to_date "$COPY_FOLDER"
    return
  fi
  download_copy
}

start_setup() {
  [ -f "$COPY_FOLDER/backend/pyproject.toml" ] || stop "$COPY_FOLDER does not hold Threadline's files." \
    "Move or rename that folder, then paste the line again."
  say "Installing Threadline's parts. The first time, this can download Python and take a few minutes."
  cd "$COPY_FOLDER/backend"
  uv sync
  say "Starting the guided set-up. From now on it asks you what it needs."
  shown_folder="$COPY_FOLDER"
  case "$COPY_FOLDER" in
    "$HOME"/*) shown_folder="~${COPY_FOLDER#"$HOME"}" ;;
  esac
  note "To come back later: open a terminal, type 'cd $shown_folder/backend', then"
  note "'uv run tracker setup'."
  # exec replaces this shell, so the exit trap would never run.
  cleanup
  exec uv run tracker setup
}

main() {
  WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/threadline-install.XXXXXX")"
  trap cleanup EXIT
  check_git
  check_curl
  install_uv
  install_github_cli
  sign_in_to_github
  get_copy
  start_setup
}

# /dev/tty exists even where no terminal is attached, so try to open it.
if ( : </dev/tty ) 2>/dev/null; then
  main "$@" </dev/tty
else
  main "$@"
fi
