#!/usr/bin/env bash
# Install skill-only upstreams (not Claude Code plugins) into ~/.claude/skills from their own repos.
# Usage: scripts/install-upstream.sh onetake|remotion|all
set -euo pipefail

SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$SKILLS_DIR"

clone_into() { # repo dest
  local repo="$1" dest="$2"
  if [ -d "$dest/.git" ]; then
    echo "updating $dest"
    git -C "$dest" pull --ff-only
  elif [ -e "$dest" ]; then
    echo "skip: $dest exists and is not a git checkout (leaving your copy alone)"
  else
    git clone --depth 1 "https://github.com/$repo.git" "$dest"
  fi
}

install_onetake() {
  echo "onetake (feitangyuan/onetake) is licensed PolyForm Noncommercial 1.0.0:"
  echo "free for noncommercial use only. Commercial use needs the author's permission."
  clone_into feitangyuan/onetake "$SKILLS_DIR/onetake"
}

install_remotion() {
  if command -v npx >/dev/null 2>&1; then
    npx --yes skills add remotion-dev/skills
  else
    local tmp
    tmp="$(mktemp -d)"
    git clone --depth 1 https://github.com/remotion-dev/skills.git "$tmp/remotion"
    for d in "$tmp"/remotion/skills/*/; do
      local name
      name="$(basename "$d")"
      if [ -e "$SKILLS_DIR/$name" ]; then echo "skip: $SKILLS_DIR/$name exists"; else cp -R "$d" "$SKILLS_DIR/$name"; fi
    done
    rm -rf "$tmp"
  fi
}

case "${1:-all}" in
  onetake) install_onetake ;;
  remotion) install_remotion ;;
  all) install_onetake; install_remotion ;;
  *) echo "usage: $0 onetake|remotion|all" >&2; exit 2 ;;
esac
echo "done. Restart Claude Code so new skills load."
