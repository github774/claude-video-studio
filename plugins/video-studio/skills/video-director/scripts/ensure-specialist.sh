#!/usr/bin/env bash
# Make sure a specialist is installed, installing it over HTTPS if it isn't, then print where its
# SKILL.md files are so the director can read and follow them in the same session.
#
# Usage: ensure-specialist.sh <brag|brag-slim|lemo-opuscar|hyperframes|watch|onetake|remotion>
# Last lines of output: one "SKILL=<path to SKILL.md>" per skill the specialist provides.
# Exit codes: 0 ready, 2 unknown name, 3 cannot be installed automatically, 4 install failed.
set -uo pipefail

MARKETPLACE="claude-video-studio"
MARKETPLACE_URL="https://github.com/github774/claude-video-studio.git"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_DIR/skills"

name="${1:-}"
case "$name" in
  brag|brag-slim) kind=plugin; plugin=brag; repo=https://github.com/latent-spaces/brag.git; subdir=skills ;;
  lemo-opuscar)   kind=plugin; plugin=lemo-opuscar; repo=https://github.com/lemomo-ai/lemo-opuscar.git; subdir=plugin/skills ;;
  hyperframes)    kind=plugin; plugin=hyperframes; repo=https://github.com/heygen-com/hyperframes.git; subdir=skills ;;
  watch)          kind=plugin; plugin=watch; repo=https://github.com/bradautomates/claude-video.git; subdir=skills ;;
  onetake)        kind=skill ;;
  remotion)       kind=skill ;;
  collage-broll-explainers)
    echo "collage-broll-explainers has no public source or license, so it can't be installed automatically."
    echo "Install it from wherever you got it, and connect the MaxFusion MCP it needs."
    exit 3 ;;
  *) echo "unknown specialist: '$name'"; echo "known: brag brag-slim lemo-opuscar hyperframes watch onetake remotion"; exit 2 ;;
esac

print_skills() { # dir...
  local found=0
  for d in "$@"; do
    [ -d "$d" ] || continue
    while IFS= read -r f; do echo "SKILL=$f"; found=1; done < <(find "$d" -name SKILL.md -not -path '*/node_modules/*' 2>/dev/null | sort)
  done
  [ "$found" = 1 ]
}

plugin_dirs() { # newest installed copies of the plugin, from any marketplace
  find "$CLAUDE_DIR/plugins/cache" -mindepth 3 -maxdepth 3 -type d -path "*/$plugin/*" 2>/dev/null
}

if [ "$kind" = plugin ]; then
  if command -v claude >/dev/null 2>&1 && claude plugin list 2>/dev/null | grep -qE "❯ $plugin@"; then
    echo "$plugin is already installed."
    print_skills $(plugin_dirs) && exit 0
  fi
  if command -v claude >/dev/null 2>&1; then
    if ! claude plugin marketplace list 2>/dev/null | grep -q "❯ $MARKETPLACE"; then
      echo "adding the $MARKETPLACE marketplace"
      claude plugin marketplace add "$MARKETPLACE_URL" || true
    else
      claude plugin marketplace update "$MARKETPLACE" >/dev/null 2>&1 || true
    fi
    echo "installing $plugin@$MARKETPLACE"
    if claude plugin install "$plugin@$MARKETPLACE"; then
      echo "installed. It loads as a skill in new sessions; for this session, read the SKILL.md below."
      print_skills $(plugin_dirs) && exit 0
    fi
    echo "plugin install failed; falling back to a plain skill install"
  fi
  # Fallback without the claude CLI (or if the plugin install failed): copy the skills from upstream.
  tmp="$(mktemp -d)"
  if ! git clone --depth 1 -q "$repo" "$tmp/src"; then rm -rf "$tmp"; echo "could not clone $repo"; exit 4; fi
  mkdir -p "$SKILLS_DIR"
  for d in "$tmp/src/$subdir"/*/; do
    s="$(basename "$d")"
    if [ -e "$SKILLS_DIR/$s" ]; then echo "keeping existing $SKILLS_DIR/$s"; else cp -R "$d" "$SKILLS_DIR/$s"; echo "installed skill $s"; fi
    echo "SKILL=$SKILLS_DIR/$s/SKILL.md"
  done
  rm -rf "$tmp"
  exit 0
fi

# Skill-only upstreams
mkdir -p "$SKILLS_DIR"
case "$name" in
  onetake)
    echo "note: onetake is PolyForm Noncommercial 1.0.0 (free for noncommercial use only)."
    if [ -d "$SKILLS_DIR/onetake/.git" ]; then git -C "$SKILLS_DIR/onetake" pull -q --ff-only || true
    elif [ ! -e "$SKILLS_DIR/onetake" ]; then
      git clone --depth 1 -q https://github.com/feitangyuan/onetake.git "$SKILLS_DIR/onetake" || exit 4
    fi
    echo "SKILL=$SKILLS_DIR/onetake/SKILL.md" ;;
  remotion)
    tmp="$(mktemp -d)"
    git clone --depth 1 -q https://github.com/remotion-dev/skills.git "$tmp/src" || { rm -rf "$tmp"; exit 4; }
    for d in "$tmp/src/skills"/*/; do
      s="$(basename "$d")"
      [ -e "$SKILLS_DIR/$s" ] || cp -R "$d" "$SKILLS_DIR/$s"
      echo "SKILL=$SKILLS_DIR/$s/SKILL.md"
    done
    rm -rf "$tmp" ;;
esac
exit 0
