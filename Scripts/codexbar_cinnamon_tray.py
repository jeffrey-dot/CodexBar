#!/usr/bin/env python3
"""CodexBar Linux tray app for Cinnamon/GNOME via AppIndicator."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning, module="gi")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*Gtk.StatusIcon.*")

APP_ID = "codexbar-linux-tray"


def _load_indicator_module():
    candidates = [
        ("AyatanaAppIndicator3", "0.1"),
        ("AppIndicator3", "0.1"),
    ]
    for module_name, version in candidates:
        try:
            gi.require_version(module_name, version)
            module = __import__(f"gi.repository.{module_name}", fromlist=["Indicator"])
            return module
        except (ImportError, ValueError):
            continue
    return None


INDICATOR = _load_indicator_module()
if INDICATOR is None:
    print(
        "Unable to import AppIndicator bindings.\n"
        "Install: sudo pacman -S python-gobject libayatana-appindicator",
        file=sys.stderr,
    )
    sys.exit(2)


def _suppress_ayatana_deprecation_warning() -> None:
    domain = "libayatana-appindicator"

    def handler(_log_domain, _log_level, _message, _user_data) -> None:
        # Drop known Ayatana deprecation warning noise from stderr.
        return None

    try:
        GLib.log_set_handler(domain, GLib.LogLevelFlags.LEVEL_WARNING, handler, None)
    except Exception:
        # Fallback silently if a different GI runtime does not allow custom handlers.
        return None


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str


def run_command(args: list[str]) -> CommandResult:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return CommandResult(False, "", str(exc))
    return CommandResult(completed.returncode == 0, completed.stdout.strip(), completed.stderr.strip())


class DashboardWindow(Gtk.Window):
    def __init__(self, on_refresh, on_quit) -> None:
        super().__init__(title="CodexBar")
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.default_width = 430
        self.default_height = 560
        self.set_default_size(self.default_width, self.default_height)
        self.set_resizable(False)
        self.set_border_width(0)
        self.set_skip_taskbar_hint(False)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.get_style_context().add_class("dashboard")
        self.connect("key-press-event", self.on_key_press)
        self.connect("focus-out-event", self.on_focus_out)
        self.all_payloads: list[dict[str, Any]] = []
        self.panel_text: str = ""

        self._install_css()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.get_style_context().add_class("dashboard")
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header.set_margin_start(16)
        header.set_margin_end(16)
        header.set_margin_top(14)
        header.set_margin_bottom(10)
        header.get_style_context().add_class("header")
        root.pack_start(header, False, False, 0)

        title = Gtk.Label()
        title.set_xalign(0)
        title.set_markup("<span size='16000' weight='bold'>CodexBar</span>")
        header.pack_start(title, False, False, 0)

        self.updated_label = Gtk.Label(label="Updated just now")
        self.updated_label.set_xalign(0)
        self.updated_label.get_style_context().add_class("subtle")
        header.pack_start(self.updated_label, False, False, 0)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter providers / account")
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.search_entry.set_margin_top(8)
        header.pack_start(self.search_entry, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(420)
        root.pack_start(scroller, True, True, 0)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.content_box.set_margin_start(14)
        self.content_box.set_margin_end(14)
        self.content_box.set_margin_top(8)
        self.content_box.set_margin_bottom(8)
        scroller.add(self.content_box)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_start(14)
        footer.set_margin_end(14)
        footer.set_margin_top(6)
        footer.set_margin_bottom(14)
        root.pack_start(footer, False, False, 0)

        refresh_button = Gtk.Button.new_with_label("Refresh")
        refresh_button.connect("clicked", lambda _btn: self.on_refresh())
        refresh_button.get_style_context().add_class("suggested-action")
        footer.pack_start(refresh_button, True, True, 0)

        quit_button = Gtk.Button.new_with_label("Quit")
        quit_button.connect("clicked", lambda _btn: self.on_quit())
        footer.pack_start(quit_button, True, True, 0)

    @staticmethod
    def _install_css() -> None:
        css = b"""
        window.dashboard {
            background: rgba(24, 26, 36, 0.94);
            border-radius: 16px;
        }
        .dashboard {
            background: rgba(24, 26, 36, 0.94);
            border-radius: 16px;
        }
        .header {
            border-bottom: 1px solid rgba(255, 255, 255, 0.10);
        }
        .subtle {
            color: rgba(220, 225, 240, 0.72);
        }
        entry {
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.08);
            color: #f8fbff;
            padding: 6px 8px;
        }
        frame.provider-card {
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.04);
        }
        frame.provider-card > border {
            border: none;
            padding: 8px;
        }
        progressbar trough {
            min-height: 8px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
        }
        progressbar progress {
            border-radius: 999px;
            background: linear-gradient(90deg, #62d0ff, #7be29b);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def set_payloads(self, payloads: list[dict[str, Any]], panel_text: str) -> None:
        self.all_payloads = payloads
        self.panel_text = panel_text
        self._render_filtered()

    def _render_filtered(self) -> None:
        query = self.search_entry.get_text().strip().lower()
        payloads = self._filtered_payloads(query)
        self.updated_label.set_text(f"Updated {datetime.now().strftime('%H:%M:%S')}  •  {self.panel_text}")
        for child in self.content_box.get_children():
            self.content_box.remove(child)

        if not payloads:
            row = Gtk.Label(label="No matching providers.")
            row.set_xalign(0)
            self.content_box.pack_start(row, False, False, 0)
            self.show_all()
            return

        for payload in payloads:
            card = self._provider_card(payload)
            self.content_box.pack_start(card, False, False, 0)
        self.show_all()

    def present_near_pointer(self) -> None:
        self.show_all()
        display = Gdk.Display.get_default()
        if display is None:
            self.present()
            return

        seat = display.get_default_seat()
        if seat is None:
            self.present()
            return
        pointer = seat.get_pointer()
        if pointer is None:
            self.present()
            return

        _pointer_screen, px, py = pointer.get_position()
        monitor = display.get_monitor_at_point(px, py)
        if monitor is None:
            self.present()
            return
        monitor_geo = monitor.get_geometry()

        width, height = self.get_size()
        if width <= 1:
            width = self.default_width
        if height <= 1:
            height = self.default_height

        margin = 8
        target_x = px - width + 24
        if py > monitor_geo.y + (monitor_geo.height // 2):
            target_y = py - height - margin
        else:
            target_y = py + margin

        min_x = monitor_geo.x + margin
        max_x = monitor_geo.x + monitor_geo.width - width - margin
        min_y = monitor_geo.y + margin
        max_y = monitor_geo.y + monitor_geo.height - height - margin

        target_x = max(min_x, min(target_x, max_x))
        target_y = max(min_y, min(target_y, max_y))
        self.move(int(target_x), int(target_y))
        self.present()

    def present_from_icon_geometry(self, area: Gdk.Rectangle, _screen: Gdk.Screen | None) -> None:
        self.show_all()
        display = Gdk.Display.get_default()
        if display is None:
            self.present_near_pointer()
            return

        monitor = display.get_monitor_at_point(area.x, area.y)
        if monitor is None:
            self.present_near_pointer()
            return
        monitor_geo = monitor.get_geometry()
        width, height = self.get_size()
        if width <= 1:
            width = self.default_width
        if height <= 1:
            height = self.default_height

        margin = 8
        icon_center_x = area.x + (area.width // 2)
        target_x = icon_center_x - (width // 2)

        # Prefer opening above panel icons (common bottom panel setup); fallback below if needed.
        target_y = area.y - height - margin
        if target_y < monitor_geo.y + margin:
            target_y = area.y + area.height + margin

        min_x = monitor_geo.x + margin
        max_x = monitor_geo.x + monitor_geo.width - width - margin
        min_y = monitor_geo.y + margin
        max_y = monitor_geo.y + monitor_geo.height - height - margin
        target_x = max(min_x, min(target_x, max_x))
        target_y = max(min_y, min(target_y, max_y))
        self.move(int(target_x), int(target_y))
        self.present()

    def _filtered_payloads(self, query: str) -> list[dict[str, Any]]:
        if not query:
            return list(self.all_payloads)
        filtered: list[dict[str, Any]] = []
        for payload in self.all_payloads:
            provider_id = str(payload.get("provider", ""))
            provider_name = CodexBarTray._provider_title(provider_id).lower()
            usage = payload.get("usage") or {}
            account_email = str(usage.get("accountEmail", "")).lower()
            haystack = f"{provider_id} {provider_name} {account_email}"
            if query in haystack:
                filtered.append(payload)
        return filtered

    def on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._render_filtered()

    @staticmethod
    def on_key_press(window: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            window.hide()
            return True
        return False

    @staticmethod
    def on_focus_out(window: Gtk.Window, _event) -> bool:
        window.hide()
        return False

    def _provider_card(self, payload: dict[str, Any]) -> Gtk.Widget:
        frame = Gtk.Frame()
        frame.get_style_context().add_class("provider-card")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.set_margin_start(10)
        body.set_margin_end(10)
        body.set_margin_top(8)
        body.set_margin_bottom(8)
        frame.add(body)

        name = CodexBarTray._provider_title(str(payload.get("provider", "unknown")))
        title = Gtk.Label()
        title.set_xalign(0)
        title.set_markup(f"<span weight='bold'>{name}</span>")
        body.pack_start(title, False, False, 0)

        error = payload.get("error")
        if isinstance(error, dict):
            err = Gtk.Label(label=f"Error: {error.get('message', 'unknown')}")
            err.set_xalign(0)
            body.pack_start(err, False, False, 0)
            return frame

        usage = payload.get("usage") or {}
        body.pack_start(self._window_row("Session", usage.get("primary") or {}), False, False, 0)
        body.pack_start(self._window_row("Weekly", usage.get("secondary") or {}), False, False, 0)

        credits = payload.get("credits")
        if isinstance(credits, dict) and isinstance(credits.get("remaining"), (int, float)):
            credits_label = Gtk.Label(label=f"Credits: {credits['remaining']:.1f}")
            credits_label.set_xalign(0)
            body.pack_start(credits_label, False, False, 0)

        email = usage.get("accountEmail")
        if isinstance(email, str) and email:
            account_label = Gtk.Label(label=f"Account: {email}")
            account_label.set_xalign(0)
            body.pack_start(account_label, False, False, 0)
        return frame

    @staticmethod
    def _window_row(title: str, window: dict[str, Any]) -> Gtk.Widget:
        used = window.get("usedPercent")
        if not isinstance(used, (int, float)):
            row = Gtk.Label(label=f"{title}: --")
            row.set_xalign(0)
            return row

        remaining = max(0, min(100, float(100 - used)))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left = Gtk.Label(label=title)
        left.set_xalign(0)
        header.pack_start(left, True, True, 0)

        right = Gtk.Label(label=f"{int(round(remaining))}% left")
        right.set_xalign(1)
        header.pack_end(right, False, False, 0)
        box.pack_start(header, False, False, 0)

        bar = Gtk.ProgressBar()
        bar.set_fraction(max(0.0, min(1.0, remaining / 100.0)))
        bar.set_show_text(False)
        box.pack_start(bar, False, False, 0)

        reset_desc = window.get("resetDescription")
        if isinstance(reset_desc, str) and reset_desc:
            reset = Gtk.Label(label=f"Resets {reset_desc}")
            reset.set_xalign(0)
            reset.get_style_context().add_class("subtle")
            box.pack_start(reset, False, False, 0)

        return box


class CodexBarTray:
    def __init__(
        self,
        binary: str,
        provider: str | None,
        source: str,
        interval: int,
        icon: str | None,
        show_dashboard: bool,
        backend: str,
    ) -> None:
        self.binary = binary
        self.provider = provider
        self.source = source
        self.interval = interval
        self.backend = self._resolve_backend(backend)
        self.icon = icon or self._default_icon(self.backend)
        self.status_icon: Gtk.StatusIcon | None = None
        self.indicator = None

        self.menu = Gtk.Menu()
        if self.backend == "statusicon":
            self._setup_status_icon()
        else:
            self._setup_indicator()
        self.last_panel_text = "CodexBar"
        self.last_payloads: list[dict[str, Any]] = []
        self.show_dashboard = show_dashboard
        self.dashboard_window = DashboardWindow(on_refresh=self.manual_refresh, on_quit=self.exit_app)
        self.dashboard_window.connect("delete-event", self.on_dashboard_close)

    @staticmethod
    def _resolve_backend(backend: str) -> str:
        if backend != "auto":
            return backend
        desktop = (GLib.getenv("XDG_CURRENT_DESKTOP") or "").lower()
        if "cinnamon" in desktop:
            return "statusicon"
        return "appindicator"

    def _setup_indicator(self) -> None:
        icon_path = Path(self.icon).expanduser()
        init_icon = "utilities-terminal"
        if icon_path.exists():
            init_icon = icon_path.stem
        self.indicator = INDICATOR.Indicator.new(APP_ID, init_icon, INDICATOR.IndicatorCategory.APPLICATION_STATUS)
        if icon_path.exists():
            self.indicator.set_icon_theme_path(str(icon_path.parent))
        self._apply_icon(self.icon)
        self.indicator.set_status(INDICATOR.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.menu)

    def _setup_status_icon(self) -> None:
        icon_path = Path(self.icon).expanduser()
        if icon_path.exists():
            self.status_icon = Gtk.StatusIcon.new_from_file(str(icon_path))
        else:
            self.status_icon = Gtk.StatusIcon.new_from_icon_name(self.icon)
        self.status_icon.set_visible(True)
        self.status_icon.set_tooltip_text("CodexBar")
        self.status_icon.connect("activate", self.on_status_icon_activate)
        self.status_icon.connect("popup-menu", self.on_status_icon_popup_menu)

    @staticmethod
    def _default_icon(backend: str) -> str:
        root = Path(__file__).resolve().parent.parent
        if backend == "appindicator":
            candidates = [
                root / "Icon.icon/Assets/codexbar.png",
                root / "codexbar.png",
                root / "Sources/CodexBar/Resources/ProviderIcon-codex.svg",
            ]
        else:
            candidates = [
                root / "Sources/CodexBar/Resources/ProviderIcon-codex.svg",
                root / "Icon.icon/Assets/codexbar.png",
                root / "codexbar.png",
            ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "utilities-terminal"

    def _apply_icon(self, icon: str) -> None:
        if self.status_icon is not None:
            icon_path = Path(icon).expanduser()
            if icon_path.exists():
                self.status_icon.set_from_file(str(icon_path))
            else:
                self.status_icon.set_from_icon_name(icon)
            return

        if self.indicator is None:
            return
        icon_path = Path(icon).expanduser()
        if icon_path.exists():
            # For file-based icons, prefer theme-path mode to avoid fallback/incorrect backgrounds.
            icon_dir = str(icon_path.parent)
            icon_name = icon_path.stem
            self.indicator.set_icon_theme_path(icon_dir)
            self.indicator.set_icon_full(icon_name, "CodexBar")
            return
        # Fallback for icon-theme names (e.g. "utilities-terminal").
        self.indicator.set_icon_full(icon, "CodexBar")

    def panel_command(self) -> list[str]:
        command = [self.binary, "panel", "--source", self.source]
        if self.provider:
            command += ["--provider", self.provider]
        return command

    def usage_command(self) -> list[str]:
        command = [self.binary, "usage", "--format", "json", "--source", self.source]
        if self.provider:
            command += ["--provider", self.provider]
        return command

    def update(self) -> bool:
        panel = run_command(self.panel_command())
        if panel.ok and panel.stdout:
            self.last_panel_text = panel.stdout
            if self.indicator is not None:
                self.indicator.set_status(INDICATOR.IndicatorStatus.ACTIVE)
            self._apply_icon(self.icon)
        else:
            self.last_panel_text = "CodexBar ERR"
            if self.indicator is not None:
                self.indicator.set_status(INDICATOR.IndicatorStatus.ATTENTION)
                self.indicator.set_icon_full("dialog-warning", "CodexBar")
            if self.status_icon is not None:
                self.status_icon.set_from_icon_name("dialog-warning")

        # AppIndicator text labels are supported by Ayatana/AppIndicator on many desktops.
        if self.indicator is not None and hasattr(self.indicator, "set_label"):
            self.indicator.set_label(self.last_panel_text, "")
        if self.status_icon is not None:
            self.status_icon.set_tooltip_text(self.last_panel_text)

        usage = run_command(self.usage_command())
        payloads = self._parse_usage_payload(usage) or []
        self.last_payloads = payloads
        self.rebuild_menu(panel, usage, payloads)
        if self.dashboard_window.is_visible():
            self.dashboard_window.set_payloads(payloads, self.last_panel_text)
        return True

    def rebuild_menu(self, panel: CommandResult, usage: CommandResult, payloads: list[dict[str, Any]]) -> None:
        for child in self.menu.get_children():
            self.menu.remove(child)

        self._append_info("<b>CodexBar</b>", markup=True)
        self._append_info(f"<tt>{self.last_panel_text}</tt>", markup=True)
        self._append_info(f"Updated {datetime.now().strftime('%H:%M:%S')}")
        self._append_separator()

        if not panel.ok and panel.stderr:
            self._append_info(f"panel: {panel.stderr}")

        if not payloads:
            msg = usage.stderr or "Unable to parse usage JSON."
            self._append_info(msg)
        else:
            for payload in payloads:
                self._append_provider_block(payload)

        self._append_separator()
        self._append_action("Open Dashboard", self.on_open_dashboard)
        self._append_action("Refresh", self.on_refresh)
        self._append_action("Quit", self.on_quit)
        self.menu.show_all()

    def _parse_usage_payload(self, usage: CommandResult) -> list[dict[str, Any]] | None:
        if not usage.ok and not usage.stdout:
            return None
        try:
            data = json.loads(usage.stdout)
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None

    def _append_provider_block(self, payload: dict[str, Any]) -> None:
        name = self._provider_title(str(payload.get("provider", "unknown")))
        self._append_info(f"<b>{name}</b>", markup=True)

        error = payload.get("error")
        if isinstance(error, dict):
            self._append_info(f"  Error: {error.get('message', 'unknown')}")
            self._append_separator()
            return

        usage = payload.get("usage") or {}
        primary = usage.get("primary") or {}
        secondary = usage.get("secondary") or {}
        session = self._window_text("Session", primary)
        weekly = self._window_text("Weekly", secondary)
        self._append_info(f"<tt>{session}</tt>", markup=True)
        self._append_info(f"<tt>{weekly}</tt>", markup=True)

        credits = payload.get("credits")
        if isinstance(credits, dict) and isinstance(credits.get("remaining"), (int, float)):
            self._append_info(f"<tt>Credits  {credits['remaining']:.1f}</tt>", markup=True)

        email = usage.get("accountEmail")
        if isinstance(email, str) and email:
            self._append_info(f"<tt>Account  {email}</tt>", markup=True)
        self._append_separator()

    @staticmethod
    def _window_text(title: str, window: dict[str, Any]) -> str:
        used = window.get("usedPercent")
        if not isinstance(used, (int, float)):
            return f"{title}: --"
        remaining = max(0, min(100, int(round(100 - used))))
        filled = max(0, min(10, int(round(remaining / 10))))
        bar = "█" * filled + "·" * (10 - filled)
        reset_desc = window.get("resetDescription")
        if isinstance(reset_desc, str) and reset_desc:
            return f"{title:<8} {remaining:>3}%  {bar}  ↺ {reset_desc}"
        return f"{title:<8} {remaining:>3}%  {bar}"

    @staticmethod
    def _provider_title(provider_id: str) -> str:
        mapping = {
            "codex": "Codex",
            "claude": "Claude",
            "cursor": "Cursor",
            "opencode": "OpenCode",
            "factory": "Droid",
            "gemini": "Gemini",
            "antigravity": "Antigravity",
            "copilot": "Copilot",
            "zai": "z.ai",
            "minimax": "MiniMax",
            "kimi": "Kimi",
            "kiro": "Kiro",
            "vertexai": "Vertex AI",
            "augment": "Augment",
            "jetbrains": "JetBrains AI",
            "kimik2": "Kimi K2",
            "amp": "Amp",
            "synthetic": "Synthetic",
        }
        return mapping.get(provider_id, provider_id)

    def _append_separator(self) -> None:
        self.menu.append(Gtk.SeparatorMenuItem())

    def _append_info(self, label: str, markup: bool = False) -> None:
        item = Gtk.MenuItem()
        text = Gtk.Label(xalign=0)
        if markup:
            text.set_markup(label)
        else:
            text.set_text(label)
        item.add(text)
        item.set_sensitive(False)
        self.menu.append(item)

    def _append_action(self, label: str, callback) -> None:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", callback)
        self.menu.append(item)

    def on_refresh(self, _item: Gtk.MenuItem) -> None:
        self.update()

    def manual_refresh(self) -> None:
        self.update()

    @staticmethod
    def on_dashboard_close(_window: Gtk.Window, _event) -> bool:
        _window.hide()
        return True

    def on_open_dashboard(self, _item=None) -> None:
        self.dashboard_window.set_payloads(self.last_payloads, self.last_panel_text)
        self.dashboard_window.present_near_pointer()

    def on_status_icon_activate(self, _icon) -> None:
        # Left click: toggle dashboard (open on first click, hide on second click).
        if self.dashboard_window.is_visible():
            self.dashboard_window.hide()
            return

        self.dashboard_window.set_payloads(self.last_payloads, self.last_panel_text)
        if self.status_icon is not None:
            ok, screen, area, _orientation = self.status_icon.get_geometry()
            if ok:
                self.dashboard_window.present_from_icon_geometry(area, screen)
                return
        self.dashboard_window.present_near_pointer()

    def on_status_icon_popup_menu(self, icon, button, activate_time) -> None:
        # Right click: open context menu.
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    def exit_app(self) -> None:
        Gtk.main_quit()

    def on_quit(self, _item: Gtk.MenuItem) -> None:
        self.exit_app()

    def run(self) -> None:
        self.update()
        if self.show_dashboard:
            self.dashboard_window.set_payloads(self.last_payloads, self.last_panel_text)
            self.dashboard_window.present_near_pointer()
        GLib.timeout_add_seconds(self.interval, self.update)
        Gtk.main()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CodexBar Linux tray app for Cinnamon.")
    parser.add_argument("--binary", default="codexbar", help="Path to codexbar binary.")
    parser.add_argument("--provider", default=None, help="Provider selection, e.g. codex or all.")
    parser.add_argument("--source", default="cli", choices=["auto", "web", "cli", "oauth", "api"], help="Usage source mode.")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds.")
    parser.add_argument("--icon", default=None, help="Icon file path for tray icon.")
    parser.add_argument("--show-dashboard", action="store_true", help="Show dashboard window immediately on startup.")
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "statusicon", "appindicator"],
        help="Tray backend. auto uses statusicon on Cinnamon.",
    )
    parser.add_argument(
        "--print-once",
        action="store_true",
        help="Print panel output once (for quick validation) and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_once:
        command = [args.binary, "panel", "--source", args.source]
        if args.provider:
            command += ["--provider", args.provider]
        result = run_command(command)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return 0 if result.ok else 1

    _suppress_ayatana_deprecation_warning()
    tray = CodexBarTray(
        binary=args.binary,
        provider=args.provider,
        source=args.source,
        interval=args.interval,
        icon=args.icon,
        show_dashboard=args.show_dashboard,
        backend=args.backend,
    )
    tray.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
