#!/usr/bin/env bash
# FH5 DualSense — Linux/macOS stub launcher. Downloads the latest release into ./app and runs it.
set -e

GAME_ARGC=$#
trap '_c=$?; echo; echo "App exited with code $_c."; [ "$GAME_ARGC" -eq 0 ] && read -r -p "Press Enter to close this window..." _ || true; exit "$_c"' EXIT

REPO="HamzaYslmn/Forza-Horizon-DualSense-Python"
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/app"
PYPROJECT="$APP/src/pyproject.toml"

need() { command -v "$1" >/dev/null 2>&1; }
fetch() {
    if need curl; then curl -fsSL "$1"
    elif need wget; then wget -qO- "$1"
    fi
}

# --- Resolve latest release tag ---
LATEST=$(fetch "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | grep -E '"tag_name"' | head -n1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/')

SOURCE="release"
if [ -z "$LATEST" ]; then
    echo "No release found. Falling back to 'main' branch."
    LATEST="main"
    SOURCE="branch"
fi

# --- Read installed version from pyproject.toml ---
CURRENT=""
if [ -f "$PYPROJECT" ]; then
    v=$(grep -E '^version\s*=' "$PYPROJECT" | head -n1 | sed -E 's/version\s*=\s*"([^"]+)".*/\1/')
    [ -n "$v" ] && CURRENT="v$v"
fi

install_release() {
    local tag="$1" kind="$2"
    local zip="$ROOT/fh5ds.zip" extract="$ROOT/_extract" url
    if [ "$kind" = "branch" ]; then
        url="https://github.com/$REPO/archive/refs/heads/$tag.zip"
    else
        url="https://github.com/$REPO/archive/refs/tags/$tag.zip"
    fi
    echo "Downloading $tag..."
    fetch "$url" > "$zip"
    rm -rf "$extract"; mkdir -p "$extract"
    if need unzip; then
        unzip -q "$zip" -d "$extract"
    else
        python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$zip" "$extract"
    fi
    rm -rf "$APP"
    mv "$extract"/*/ "$APP"
    rm -rf "$extract" "$zip"
    echo "Installed $tag."
}

if [ -z "$CURRENT" ]; then
    echo "Installing $LATEST..."
    install_release "$LATEST" "$SOURCE"
elif [ "$SOURCE" = "branch" ]; then
    echo "Refreshing 'main' branch (installed: $CURRENT)..."
    install_release "$LATEST" "$SOURCE"
elif [ "$CURRENT" != "$LATEST" ]; then
    echo "Update available: $CURRENT -> $LATEST"
    read -r -p "Update now? [Y/n] " ans
    case "${ans:-Y}" in
        [Nn]*) ;;
        *) install_release "$LATEST" "$SOURCE" ;;
    esac
else
    echo "Up to date ($CURRENT)."
fi

# --- Ensure uv is available ---
if ! need uv; then
    echo "uv was not found. Installing from https://astral.sh/uv/ ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if ! need uv; then
        echo "uv installed but not on PATH. Restart your shell or add ~/.local/bin to PATH."
        exit 1
    fi
fi

cd "$APP/src"
if [ "$#" -gt 0 ]; then
    echo "Launching game: $*"
    "$@" &
fi
uv run main.py
