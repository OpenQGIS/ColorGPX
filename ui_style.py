# -*- coding: utf-8 -*-
"""Shared QGIS-palette UI tokens for ColorGPX dialogs and overlays."""

from qgis.PyQt.QtGui import QPalette


def _palette_role(name):
    try:
        return getattr(QPalette, name)
    except AttributeError:
        return getattr(QPalette.ColorRole, name)


def qgis_ui_tokens(widget):
    """Return semantic colors from the active QGIS/Qt palette."""
    palette = widget.palette()

    def color(name):
        return palette.color(_palette_role(name)).name()

    return {
        "window": color("Window"),
        "base": color("Base"),
        "text": color("Text"),
        "button": color("Button"),
        "button_text": color("ButtonText"),
        "muted": color("Mid"),
        "accent": color("Highlight"),
        "accent_text": color("HighlightedText"),
    }


def rgba_css(hex_color, alpha):
    """Convert #RRGGBB plus an integer alpha to broadly supported CSS rgba()."""
    value = str(hex_color).lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    try:
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    except (TypeError, ValueError):
        red, green, blue = 255, 255, 255
    return "rgba(%d, %d, %d, %d)" % (red, green, blue, int(alpha))


def style_primary_button(button):
    """Give one dialog action clear priority while retaining the QGIS accent."""
    colors = qgis_ui_tokens(button)
    button.setStyleSheet(
        "QPushButton {"
        " background-color: %(accent)s; color: %(accent_text)s;"
        " border: 1px solid %(accent)s; border-radius: 3px;"
        " min-height: 24px; padding: 2px 14px; font-weight: 600;"
        "}"
        "QPushButton:pressed { padding-top: 3px; padding-bottom: 1px; }"
        "QPushButton:disabled { background-color: %(button)s;"
        " color: %(muted)s; border-color: %(muted)s; }" % colors
    )
