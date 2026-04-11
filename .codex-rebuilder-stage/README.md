# Codex Intel Rebuilder

This project allows you to port the official Arm64 (Apple Silicon) Codex Desktop App to run on Intel Macs.

## Prerequisites

1.  **Node.js**: Installed on your system.
2.  **Codex CLI**: You must have the official `@openai/codex` CLI installed globally, as we need its x64 binary.
    ```bash
    npm install -g @openai/codex
    ```
3.  **Codex.dmg**: The official Arm64 installer (place it in this directory).
    -   Download: [https://persistent.oaistatic.com/codex-app-prod/Codex.dmg](https://persistent.oaistatic.com/codex-app-prod/Codex.dmg)

## How to Build

Run the rebuild script:

```bash
node rebuild_codex.js
```

For a fully clean build (removes all cached and transient files first):

```bash
node rebuild_codex.js --clean
```

This script will:
1.  Mount `Codex.dmg` and extract the app logic (`app.asar`), icon, and configuration.
2.  Download the compatible x64 Electron runtime.
3.  Rebuild native modules (`better-sqlite3`, `node-pty`) for Intel architecture.
4.  Copy the x64 `codex` binary from your local CLI installation.
5.  Generate `Codex.app`.

> **Note:** The script caches the extracted resources and downloaded Electron zip to speed up subsequent builds. Use `--clean` if you've updated `Codex.dmg` or the CLI to ensure stale files aren't reused.

## How to Run

Open the generated app:

```bash
open Codex.app
```

If you see "App is damaged", run:
```bash
xattr -cr Codex.app
```

## Updates

**Note:** This is a manual port. Auto-updates will **not** work.

To update:
1.  Download the new `Codex.dmg` from OpenAI.
2.  Replace the old `Codex.dmg` in this folder.
3.  If the Codex CLI also updated, run `npm update -g @openai/codex`.
4.  Run `node rebuild_codex.js --clean` to ensure a fresh build with the new files.

## One-Command Update

If you want the repo to download the latest official installer, rebuild the Intel app, and replace the installed `/Applications/Codex.app`, `/Applications/Codex-A.app`, and `/Applications/Codex-B.app`, run:

```bash
node update_codex_intel.js
```

If you prefer to launch it from Finder, just double-click:

```bash
update_codex_intel.command
```

That `.command` file opens Terminal automatically, switches into the repo directory, runs the updater, and keeps the window open at the end so you can read the result.

Useful options:

```bash
node update_codex_intel.js --open
node update_codex_intel.js --skip-cli-update
node update_codex_intel.js --install-path="$HOME/Applications/Codex.app"
node update_codex_intel.js --install-paths="/Applications/Codex.app,/Applications/Codex-A.app,/Applications/Codex-B.app"
node update_codex_intel.js --dry-run
```

The updater will:
1. Download the latest official `Codex.dmg` from OpenAI.
2. Replace the local cached `Codex.dmg` if the contents changed.
3. Update the global `@openai/codex` CLI unless you pass `--skip-cli-update`.
4. Run `node rebuild_codex.js --clean`.
5. Backup each current installed app into `backups/`.
6. Replace all configured app targets and clear quarantine attributes.
7. Migrate the legacy `/Applications/Codex_Intel.app` main app to `/Applications/Codex.app` automatically.
8. Reapply per-app isolation so `Codex` / `Codex-A` / `Codex-B` keep their own `CODEX_HOME`, Electron user-data dir, and bundle identifier.
9. Reapply the checked-in per-app icon assets so `Codex` keeps the official icon, `A` stays champagne gold, and `B` stays emerald green.
10. If any target app was already running, quit it before install and relaunch it automatically afterward.

`--open` still works as a manual override when none of the target apps were already running before the update.

## Isolation Contract

The three installed apps are intentionally treated as **separate variants**, not interchangeable copies:

- `/Applications/Codex.app` uses `CODEX_HOME=~/.codex`
- `/Applications/Codex-A.app` uses `CODEX_HOME=~/.codex-a`
- `/Applications/Codex-B.app` uses `CODEX_HOME=~/.codex-b`

The updater preserves this isolation on every run by rewriting each app's:

1. wrapper script at `Contents/MacOS/Codex`
2. Electron `--user-data-dir`
3. `CFBundleName` / `CFBundleDisplayName`
4. `CFBundleIdentifier`
5. `electron.icns`

This means each app keeps its own:

- `config.toml`
- `auth.json`
- API key
- base URL / relay settings
- local Electron session state
- app name and visual identity

Current visual convention:

- `Codex.app`: official icon, unchanged
- `Codex-A.app`: fixed champagne-gold icon asset
- `Codex-B.app`: fixed emerald-green icon asset

The updater now prefers these saved icon files directly instead of regenerating them on every update:

- `resources/electron.icns`
- `resources/electron-a.icns`
- `resources/electron-b.icns`

`generate_variant_icons.swift` is kept as a fallback and for future manual redesigns, but normal updates now just reuse the checked-in `.icns` files.

**Important:** Do not manually duplicate one installed app over another with Finder, `cp`, or `ditto`. That can flatten the isolation layer and make multiple apps share the same relay or local profile. Always use `node update_codex_intel.js` so the per-app wrapper and metadata are re-applied correctly.

If you add another installed Codex variant in the future, add it to `APP_VARIANTS` in `update_codex_intel.js` before updating it. The script now refuses unknown `Codex*.app` targets for safety.

## Security Note

The built app launches with the `--no-sandbox` Electron flag via a wrapper script at `Contents/MacOS/Codex`. This disables Chromium's internal process sandbox, which is necessary to allow tools like **Playwright** to spawn browser subprocesses from within the integrated terminal.

This is separate from the macOS Seatbelt sandbox that Codex uses for workspace isolation. To enable network access inside the Codex terminal, set the following in your Codex `config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

## Troubleshooting

- **"Operation not permitted"**:
  - The app is self-signed/unsigned. You must remove the quarantine attribute:
    ```bash
    xattr -cr Codex.app
    ```
  - If Playwright or other tools fail, ensure you are running the app via the wrapper `Contents/MacOS/Codex` (which the `.app` bundle does by default) which adds `--no-sandbox`.

- **Build Failures (Native Modules)**:
  - If you see errors about `source_location` or C++ compilation during `npm install`:
    - Ensure your Xcode Command Line Tools are up to date (Xcode 15+ recommended for C++20 support).
    - The build script attempts to force C++20 mode (`-std=c++20`), which requires a modern compiler.
    - Try running `xcode-select --install` to update your tools.

- **"Could not find local x64 Codex binary"**:
  - The script now searches dynamically for the `codex` binary. Ensure you have the latest version of `@openai/codex` installed globally.
  - Run `npm list -g @openai/codex` to verify installation path.
-   **Blank Window**: Usually means the executable name doesn't match `Info.plist`. The script handles this via a wrapper at `Contents/MacOS/Codex` that launches `Codex.orig`.
-   **Missing Binary**: Ensure the Codex CLI is installed globally (`npm install -g @openai/codex`).
-   **No Network in Terminal**: Set `network_access = true` in your Codex `config.toml` (see Security Note above).
-   **Playwright / Browser Spawning**: Should work out of the box thanks to `--no-sandbox`. If issues persist, ensure network access is enabled.
-   **Crashes**: Check console logs. If `sparkle.node` (auto-updater) crashes, ignore it; the app should still function.
