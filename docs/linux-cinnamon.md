# Linux Cinnamon Tray

CodexBar's native menu bar app is macOS-only.  
On Linux/Cinnamon, use the bundled CLI plus a tray helper script.

## 1) Install prerequisites (Arch Linux)

```bash
sudo pacman -S python python-gobject libayatana-appindicator
```

## 2) Build and install CodexBarCLI

```bash
cd /home/jeffrey/dev/CodexBar
swift build --product CodexBarCLI
mkdir -p ~/.local/bin
ln -sf /home/jeffrey/dev/CodexBar/.build/debug/CodexBarCLI ~/.local/bin/codexbar
```

## 3) Validate output quickly

```bash
Scripts/codexbar_cinnamon_tray.py --binary ~/.local/bin/codexbar --provider codex --print-once
```

## 4) Launch tray app

```bash
Scripts/codexbar_cinnamon_tray.py --binary ~/.local/bin/codexbar --provider codex --source cli --interval 30
```

Open the rounded Dashboard window immediately on startup:

```bash
Scripts/codexbar_cinnamon_tray.py --binary ~/.local/bin/codexbar --provider codex --source cli --interval 30 --show-dashboard
```

When opened from the tray menu, the Dashboard is anchored near the current mouse position (panel corner style), not centered.
On Cinnamon, prefer `--backend statusicon` to get:
- left click: open Dashboard directly
- right click: show menu

Optional: set a custom tray icon path:

```bash
Scripts/codexbar_cinnamon_tray.py --binary ~/.local/bin/codexbar --provider codex --source cli --interval 30 --icon /home/jeffrey/dev/CodexBar/Icon.icon/Assets/codexbar.png
```

What you get:
- top panel text from `codexbar panel`
- click tray icon to open a menu with Session/Weekly/Credits/account lines
- `Open Dashboard` window with rounded cards, progress bars, and provider search
- `Refresh` and `Quit` actions

## 5) Optional: autostart on login

Create `~/.config/autostart/codexbar-tray.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=CodexBar Tray
Exec=/usr/bin/env bash -lc '/home/jeffrey/dev/CodexBar/Scripts/codexbar_cinnamon_tray.py --binary /home/jeffrey/.local/bin/codexbar --provider codex --source cli --interval 30'
X-GNOME-Autostart-enabled=true
```
