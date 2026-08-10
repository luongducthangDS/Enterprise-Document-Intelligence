#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

# Windows Store "App execution alias" stubs sit on PATH as python.exe/python3.exe
# but don't run Python — they either no-op or print an install prompt. Reject
# anything under WindowsApps and verify the candidate actually runs.
is_real_python() {
  case "$1" in
    *WindowsApps*) return 1 ;;
  esac
  "$1" --version >/dev/null 2>&1
}

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    resolved=$(command -v "$cand")
    if is_real_python "$resolved"; then
      PY="$cand"
      break
    fi
  fi
done

if [ -z "$PY" ] && command -v py >/dev/null 2>&1; then
  if is_real_python "$(command -v py)"; then
    PY="py -3"
  fi
fi

if [ -z "$PY" ]; then
  # PATH lookup failed or only yielded broken stubs — probe standard Windows
  # install locations directly.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && is_real_python "$cand"; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
fi

[ -n "$PY" ] || exit 0

# shellcheck disable=SC2086
exec $PY "$@"
