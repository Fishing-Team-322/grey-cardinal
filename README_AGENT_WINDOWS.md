# Grey Cardinal Daemon — Windows (tray + account pairing)

This covers the account-aware daemon flow: the user pairs a device to their
workspace from the cockpit, the daemon lives in the tray, and Start/Stop
recording uploads to that workspace.

> **Build status.** The pairing **backend + cockpit UI + ownership flow are
> implemented and verified end-to-end** (`scripts/daemon_sim.py`). The Windows
> **tray app** (`native/desktop-agent/src/tray/tray_app.cpp`) and the **MSI
> tray/autostart additions** below are written but must be **compiled and signed
> on a Windows build machine** — they are not compiled/tray-tested in the Linux
> CI/dev container.

## 1. How account pairing works

```
Cockpit (your workspace)                 Daemon (your PC)
  POST /api/agents/pairing-code   ──►   pairing code GC-123456 (15 min, one-time)
                                        Pair device → POST /api/agents/register
                                          { pairing_code, device_name, os, version }
                                  ◄──   { agent_id, workspace_id, agent_token, backend_url }
                                        agent_token saved in local config only
  GET /api/agents                 ◄──   POST /api/agents/heartbeat (X-Agent-Token, 30s)
  GET /api/daemon/uploads         ◄──   POST /api/daemon/uploads   (X-Agent-Token)
```

- The **pairing code** is one-time and expires in 15 minutes.
- The **agent_token** is a per-device bearer token. It lives **only** in
  `%LOCALAPPDATA%\GreyCardinal\Daemon\config.toml` — never in the MSI, never in
  the frontend. It is stored hashed on the server.
- Every heartbeat/upload carries the token, so the backend attributes data to
  the right `agent_id` + `workspace_id`. Other workspaces never see it.

## 2. Get a pairing code

1. Open <https://fishingteam.su/> → **Войти** → cockpit → **Daemon**.
2. Note **Workspace number** (e.g. `GC-EFDSWB`).
3. Click **«Сгенерировать код привязки»** → you get e.g. `GC-714283` (15 min).
   Do not share the code.

## 3. Install the MSI

```powershell
# download from the cockpit ("Скачать Windows MSI") or:
#   https://fishingteam.su/downloads/grey-cardinal-daemon-windows-x64.msi
msiexec /i .\grey-cardinal-daemon-windows-x64.msi
```

Installs to `C:\Program Files\Grey Cardinal Daemon\`. Config/logs live in
`%LOCALAPPDATA%\GreyCardinal\Daemon\`. The MSI is **unsigned** today, so
SmartScreen shows a warning — see Limitations.

## 4. Pair + record from the tray

1. The daemon appears in the **system tray**. Tooltip: `Grey Cardinal Daemon — Idle`.
2. Right-click → **Pair device** → paste the pairing code → it registers and
   stores the token. Tooltip stays Idle.
3. **Начать запись** → status becomes `Recording 00:00:12`.
4. **Остановить запись** → the WAV uploads; you get a toast
   *"Recording uploaded to Grey Cardinal"*. On failure: *"Upload failed — open logs"*.
5. Other menu items: **Open Cockpit**, **Settings** (opens config.toml),
   **Open Logs**, **Quit**.

The daemon records **only** between explicit Start and Stop — there is no
always-on listening.

## 5. Build the tray app (Windows)

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
# produces grey-cardinal-daemon.exe (CLI) and grey-cardinal-tray.exe (tray)
```

Add a CMake target for the tray (Windows-only):

```cmake
if (WIN32)
  add_executable(grey-cardinal-tray WIN32 src/tray/tray_app.cpp app.rc)
  target_link_libraries(grey-cardinal-tray PRIVATE winhttp shell32)
  set_target_properties(grey-cardinal-tray PROPERTIES OUTPUT_NAME "grey-cardinal-tray")
endif()
```

`app.rc` provides the tray icon (`101 ICON "assets/gc.ico"`) and a small pairing
`DIALOG` (id 200 with an edit control id 100 + OK/Cancel).

## 6. MSI additions to ship the tray (apply when grey-cardinal-tray.exe is staged)

Add to `installer/windows/wix/GreyCardinalDaemon.wxs` (kept out of the current
`.wxs` so the existing MSI build doesn't fail on a missing binary):

```xml
<!-- tray exe + autostart Run key -->
<Component Id="TrayExe" Guid="{NEW-GUID}">
  <File Id="TrayExeFile" Source="$(StageDir)\grey-cardinal-tray.exe" KeyPath="yes" />
  <RegistryValue Root="HKLM"
      Key="Software\Microsoft\Windows\CurrentVersion\Run"
      Name="GreyCardinalDaemon" Type="string"
      Value="&quot;[INSTALLFOLDER]grey-cardinal-tray.exe&quot;" />
</Component>
```

Point the Start Menu shortcut `Target="[#TrayExeFile]"` (launch the tray, not the
CLI). Bump `ProductVersion` to `0.4.0` in `scripts/package_windows_msi.ps1`.
`CMakeLists.txt` project version is already `0.4.0`.

## 7. What is / isn't sent

- **Sent:** the recorded WAV, recording metadata (duration, source), an optional
  transcript line, and `X-Agent-Token` (→ agent_id/workspace_id). Heartbeats with
  status + version + device name.
- **Not sent:** anything while not recording; no continuous audio; no keystrokes;
  no screen. No `INTERNAL_API_TOKEN`.

## 8. Reset / unpair

- Cockpit → Daemon → **Unpair** on the device (`POST /api/agents/{id}/unpair`):
  the server drops the agent and its token stops working.
- On the device: tray → **Settings**, clear `agent_token`/`workspace_id` in
  config.toml, or re-run **Pair device** with a fresh code.

## 9. Verify without a Windows build

The whole chain (pairing → upload → workspace ownership → cockpit) can be
exercised with the simulator:

```bash
CODE=$(curl -s -X POST https://fishingteam.su/api/agents/pairing-code -H 'Content-Type: application/json' -d '{}' | python -c "import sys,json;print(json.load(sys.stdin)['pairing_code'])")
python scripts/daemon_sim.py --base-url https://fishingteam.su --pairing-code "$CODE" --transcript "Максим, сделай сайт до пятницы"
```

Then check the cockpit **Daemon** panel (device online + upload) and **Задачи**
(the proposal).
