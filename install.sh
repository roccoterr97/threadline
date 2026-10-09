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
#   2. Installs uv, the tool that runs Threadline, if it is missing.
#   3. Installs the GitHub command-line tool (gh) if it is missing.
#   4. Signs you in to GitHub in the browser if you are not signed in yet.
#   5. Makes your own private copy of Threadline on GitHub (from the public
#      template, as a private repository called "threadline"), waits until
#      GitHub has filled it, and downloads it to ~/threadline. A copy that
#      already exists, on GitHub or in that folder, is reused and brought up
#      to date.
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

# The official installer of uv, and where the GitHub tool is explained.
UV_INSTALLER="https://astral.sh/uv/install.sh"
GITHUB_CLI_PAGE="https://cli.github.com"

# Where uv puts itself, so it works in this very session.
UV_FOLDER="${UV_INSTALL_DIR:-$HOME/.local/bin}"

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
  curl -LsSf "$UV_INSTALLER" | sh
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

install_github_cli() {
  if has gh; then
    say "The GitHub tool (gh) is installed."
    return
  fi
  say "Installing the GitHub tool (gh)."
  case "$(operating_system)" in
    mac)
      has brew || stop "The GitHub tool needs Homebrew to be installed this way." \
        "Install Homebrew from https://brew.sh, or the GitHub tool from $GITHUB_CLI_PAGE," \
        "then paste the line again."
      brew install gh
      ;;
    linux)
      install_github_cli_linux
      ;;
    *)
      stop "This installer knows macOS and Linux only." \
        "On Windows, open PowerShell and paste the Windows line at the top of this script."
      ;;
  esac
  has gh || stop "The GitHub tool was installed but cannot be found yet." \
    "Close this terminal, open a new one, and paste the line again."
}

install_github_cli_linux() {
  if has apt-get; then
    install_with apt-get update && install_with apt-get install -y gh && return
  elif has dnf; then
    install_with dnf install -y gh && return
  fi
  stop "The GitHub tool could not be installed automatically." \
    "Install it by hand from $GITHUB_CLI_PAGE, then paste the line again."
}

sign_in_to_github() {
  if gh auth status >/dev/null 2>&1; then
    say "You are signed in to GitHub."
  else
    say "Signing you in to GitHub: a browser window opens, follow what it says."
    gh auth login --hostname github.com --web --git-protocol https
  fi
  # Lets git download and upload your private copy with the same sign-in.
  gh auth setup-git
}

# Prints the copy's full name (you/threadline) when it exists on GitHub.
existing_copy() {
  gh repo view "$COPY_NAME" --json nameWithOwner --jq .nameWithOwner 2>/dev/null
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

get_copy() {
  if [ -d "$COPY_FOLDER/.git" ]; then
    say "Your copy is already at $COPY_FOLDER; bringing it up to date."
    git -C "$COPY_FOLDER" pull --ff-only || note "It could not be updated; carrying on with what is there."
    return
  fi
  if [ -e "$COPY_FOLDER" ]; then
    stop "$COPY_FOLDER exists but is not a copy of Threadline." \
      "Move or rename that folder, then paste the line again."
  fi
  if existing_copy >/dev/null; then
    say "You already have a copy called '$COPY_NAME' on GitHub; downloading it to $COPY_FOLDER."
  else
    say "Making your private copy of Threadline on GitHub."
    gh repo create "$COPY_NAME" --template "$TEMPLATE_REPOSITORY" --private
  fi
  wait_for_copy
  say "Downloading $COPY_FULL_NAME to $COPY_FOLDER."
  gh repo clone "$COPY_FULL_NAME" "$COPY_FOLDER"
}

start_setup() {
  say "Installing Threadline's parts."
  cd "$COPY_FOLDER/backend"
  uv sync
  say "Starting the guided set-up. From now on it asks you what it needs."
  note "To come back later: open a terminal, type 'cd ~/threadline/backend', then"
  note "'uv run tracker setup'."
  exec uv run tracker setup
}

main() {
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
