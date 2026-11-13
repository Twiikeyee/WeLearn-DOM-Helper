# -*- coding: utf-8 -*-
"""
Shared UI helpers for WeLearn-DOM-Helper (theme palette, QApplication bootstrap,
macOS traffic-light fixes).

Licensed under GNU AGPLv3.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# --------------------------------------------------------------------------- #
# Palette (single place for every colour used by the GUI)
# --------------------------------------------------------------------------- #
PALETTE = {
    "bg": "#121318",
    "panel": "#1b1c24",
    "panel_border": "#282a36",
    "panel_alt": "#20222c",
    "input": "#14171b",
    "log_bg": "#1a1c23",
    "text": "#f4f7fb",
    "text_soft": "#d8dee9",
    "muted": "#8c93a0",
    "muted_strong": "#aab2c0",
    "cyan": "#30d9ef",
    "green": "#37d987",
    "orange": "#ffb25f",
    "red": "#ff6b6b",
}


def rgba(hex_color: str, alpha: float) -> str:
    """Convert `#rrggbb` to a CSS `rgba()` string with the given alpha (0~1)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


GLOBAL_QSS = f"""
QLabel#metricValue {{ color: {PALETTE['cyan']}; font-size: 20px; font-weight: 700; }}
QLabel#metricTitle {{ color: {PALETTE['muted']}; font-size: 12px; }}
QLabel#panelTitle {{ color: {PALETTE['muted_strong']}; font-size: 13px; font-weight: 600; padding: 0 0 4px 0; }}
QLabel#appTitle {{ color: {PALETTE['text']}; font-size: 24px; font-weight: 800; }}
QLabel#versionTag {{
    color: {PALETTE['cyan']}; font-size: 12px; font-weight: 700;
    padding: 4px 8px; border-radius: 4px; background: {rgba(PALETTE['cyan'], 0.12)};
}}
QLabel#authorTag {{
    color: #c9d2dd; font-size: 12px; font-weight: 500;
    padding: 4px 10px; border-radius: 4px; background: rgba(255, 255, 255, 0.05);
}}
QLabel#hintLabel {{ color: {PALETTE['muted']}; font-size: 12px; }}
QLabel#fieldTitle {{ color: {PALETTE['muted_strong']}; font-size: 13px; font-weight: 600; }}
QLabel#cardTitle {{ color: {PALETTE['cyan']}; font-size: 14px; font-weight: 700; padding-bottom: 4px; }}
QLabel#pageTitle {{ color: {PALETTE['text']}; font-size: 16px; font-weight: 700; }}
QLabel#subTag {{
    color: {PALETTE['cyan']}; font-size: 11px; font-weight: 600;
    padding: 2px 8px; border-radius: 4px; background: {rgba(PALETTE['cyan'], 0.12)};
}}
"""


_APP_INSTANCE = None


def ensure_qapp() -> QApplication:
    """Return the running QApplication, creating it (with Hi-DPI flags) if needed.

    Hi-DPI attributes must be set *before* the QApplication is constructed.
    """
    global _APP_INSTANCE
    app = QApplication.instance()
    if app is None:
        if _APP_INSTANCE is None:
            QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            _APP_INSTANCE = QApplication(sys.argv)
        app = _APP_INSTANCE
    try:
        from qfluentwidgets import Theme, qconfig, setTheme
        if qconfig.themeMode.value != Theme.DARK:
            setTheme(Theme.DARK)
    except Exception:
        pass
    return app


# --------------------------------------------------------------------------- #
# macOS traffic-light fix
# --------------------------------------------------------------------------- #
class MacTrafficLightMixin:
    """Mix into a qframelesswindow-based window (placed *before* it in the MRO).

    Fixes two upstream issues of `qframelesswindow.mac.MacFramelessWindow`:

    1. It calls `setStyleMask_` / re-positions the native buttons on *every*
       paintEvent. Any repaint while the mouse is held on a traffic light
       rebuilds the title bar and cancels the click, so the user has to press
       several times. We only touch NSWindow state when it actually differs.
    2. Buttons placed via `systemTitleBarRect` can end up partially outside the
       native title bar view (only half of each button is clickable). We always
       center them vertically inside the native title bar.
    """

    MAC_TRAFFIC_LIGHT_X = 14  # x of the close button (px)

    def _mac_ns_window(self):
        return getattr(self, "_MacFramelessWindow__nsWindow", None)

    def _hideSystemTitleBar(self, showButton=False):  # noqa: N802 (upstream name)
        ns = self._mac_ns_window()
        if sys.platform != "darwin" or ns is None:
            parent = getattr(super(), "_hideSystemTitleBar", None)
            return parent(showButton) if parent else None

        import Cocoa

        full = Cocoa.NSFullSizeContentViewWindowMask
        mask = ns.styleMask()
        if not (mask & full):
            ns.setStyleMask_(mask | full)
        if not ns.titlebarAppearsTransparent():
            ns.setTitlebarAppearsTransparent_(True)
        if ns.isMovableByWindowBackground():
            ns.setMovableByWindowBackground_(False)
        if ns.isMovable():
            ns.setMovable_(False)
        if ns.titleVisibility() != Cocoa.NSWindowTitleHidden:
            ns.setTitleVisibility_(Cocoa.NSWindowTitleHidden)

        close_btn = ns.standardWindowButton_(Cocoa.NSWindowCloseButton)
        state_changed = getattr(self, "_isSystemButtonVisible", None) != showButton
        if close_btn is not None and (bool(close_btn.isHidden()) == bool(showButton) or state_changed):
            self.setSystemTitleBarButtonVisible(showButton)
        elif showButton:
            self._updateSystemButtonRect()

    def _updateSystemButtonRect(self):  # noqa: N802 (upstream name)
        ns = self._mac_ns_window()
        if sys.platform != "darwin" or ns is None:
            parent = getattr(super(), "_updateSystemButtonRect", None)
            return parent() if parent else None
        if not self.isSystemButtonVisible():
            return

        import Cocoa

        buttons = [
            ns.standardWindowButton_(Cocoa.NSWindowCloseButton),
            ns.standardWindowButton_(Cocoa.NSWindowMiniaturizeButton),
            ns.standardWindowButton_(Cocoa.NSWindowZoomButton),
        ]
        if any(b is None for b in buttons):
            return

        titlebar = buttons[0].superview()
        if titlebar is None:
            return
        tb_height = float(titlebar.frame().size.height)
        btn_w = float(buttons[0].frame().size.width)
        btn_h = float(buttons[0].frame().size.height)
        spacing = btn_w + 6.0  # native macOS spacing (20px for 14px buttons)

        y = max(0.0, (tb_height - btn_h) / 2.0)
        for i, btn in enumerate(buttons):
            x = float(self.MAC_TRAFFIC_LIGHT_X) + i * spacing
            origin = btn.frame().origin
            if abs(origin.x - x) > 0.5 or abs(origin.y - y) > 0.5:
                btn.setFrameOrigin_(Cocoa.NSPoint(x, y))
