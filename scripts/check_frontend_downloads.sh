#!/usr/bin/env bash
# Guard: the Windows tray-agent MSI is published out-of-band (not in git), but the
# frontend image bakes apps/frontend/public/ via `COPY public/`. If the MSI is
# missing at build time, /downloads/GreyCardinalAgent-x64.msi serves 404 in prod.
# Fail loudly here instead of shipping a broken download.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
msi="apps/frontend/public/downloads/GreyCardinalAgent-x64.msi"
msi_path="$repo_root/$msi"

if [[ ! -s "$msi_path" ]]; then
  echo "Missing $msi. Build tray MSI first or download CI artifact before building frontend image." >&2
  echo >&2
  echo "Provide it via one of:" >&2
  echo "  - CI artifact 'grey-cardinal-agent-windows-x64' (workflow: Build Windows tray agent MSI)" >&2
  echo "  - local build: ./scripts/package_windows_tray_msi.ps1 -Version 0.6.2" >&2
  exit 1
fi

echo "[check] $msi present ($(wc -c < "$msi_path") bytes)"
