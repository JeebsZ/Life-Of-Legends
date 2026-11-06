"""Design tokens + live theme switching for Life of Legends.

How colors work (read this before styling anything):
- Theme-wide colors are *roles* (`C.PRIMARY`, `C.SURFACE`, ...). They map to Material
  ColorScheme slots, so Flutter resolves them at paint time: `apply_theme(page, id)` swaps
  the page theme and every control using a role recolors instantly, no rebuild.
- Glow (Arcane, Rose Arcana): panels registered with `glow(ctrl)` get a faint primary border + outer glow
  while the active palette has `glow=True`; other themes keep their flat look. Labels made with
  `label(text)` go uppercase + letter-spaced under Arcane too.
- Path colors are concrete hex values (7 Paths don't fit in a ColorScheme). Read them with
  `path_color(path_id)`. Components that use them register via `on_theme_change`, and
  `apply_theme` restyles them before the single `page.update()`, so they switch live too.

No game rules here - only how things look and move.
"""

from __future__ import annotations

import contextlib
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft

# --------------------------------------------------------------------------- tokens


class Space:
    """Spacing scale (px). Use these, not loose numbers."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    GUTTER = 16  # screen side padding at phone width


class Radius:
    SM = 8
    MD = 18  # chunky cards, rows
    LG = 26  # chunky sheets, banners, modals
    XL = 32  # extra large ceremonial containers
    PILL = 999


class Type:
    """Type scale (font size px)."""

    CAPTION = 12
    LABEL = 13
    BODY = 15
    TITLE = 17
    HEADLINE = 22
    DISPLAY = 28
    HERO = 34


class Size:
    TAP = 48  # minimum tap target
    ICON_SM = 18
    ICON = 24
    ICON_LG = 28
    BAR = 14  # main XP bar height
    BAR_MINI = 6  # Path mini bar height
    STRIPE = 4  # Path color stripe on cards


class Motion:
    """Feel tuning - durations in ms. Same numbers as the original app.py juice."""

    FILL_MS = 450  # XP bar fill per step
    POP_MS = 140  # tap pop (scale up, back)
    FLOAT_MS = 700  # +XP / +coins floater rise
    BANNER_MS = 450  # level-up banner in/out
    BANNER_HOLD_S = 1.3  # banner stays this long
    FADE_MS = 250  # state changes (done fade, chip color)
    DONE_FADE_MS = 400
    COUNT_MS = 600  # coin count-up total
    SWAP_MS = 220  # quest board reroll slide

    POP_SCALE = 1.06
    PRESS_SCALE = 0.97

    EASE = ft.AnimationCurve.EASE_OUT
    EASE_CUBIC = ft.AnimationCurve.EASE_OUT_CUBIC
    BACK = ft.AnimationCurve.EASE_OUT_BACK  # overshoot: pops, chips
    ELASTIC = ft.AnimationCurve.ELASTIC_OUT  # banners only - big moments

    @staticmethod
    def anim(ms: int, curve: ft.AnimationCurve = ft.AnimationCurve.EASE_OUT) -> ft.Animation:
        return ft.Animation(ms, curve)


class C:
    """Color roles. Resolved live by Flutter from the current page theme."""

    BG = ft.Colors.SURFACE
    SURFACE = ft.Colors.SURFACE_CONTAINER
    SURFACE_HI = ft.Colors.SURFACE_CONTAINER_HIGHEST
    PRIMARY = ft.Colors.PRIMARY
    ON_PRIMARY = ft.Colors.ON_PRIMARY
    ACCENT = ft.Colors.TERTIARY  # coins
    ON_ACCENT = ft.Colors.ON_TERTIARY
    SUCCESS = ft.Colors.SECONDARY
    ON_SUCCESS = ft.Colors.ON_SECONDARY
    DANGER = ft.Colors.ERROR
    ON_DANGER = ft.Colors.ON_ERROR
    TEXT = ft.Colors.ON_SURFACE
    TEXT_DIM = ft.Colors.ON_SURFACE_VARIANT
    OUTLINE = ft.Colors.OUTLINE_VARIANT
    SCRIM = ft.Colors.SCRIM

    @staticmethod
    def a(color: str, opacity: float) -> str:
        """Color with opacity; works with roles and hex."""
        return ft.Colors.with_opacity(opacity, color)


# --------------------------------------------------------------------------- Paths

PATH_IDS = ("chef", "warrior", "scholar", "artisan", "ranger", "steward", "monk")

PATH_NAMES = {
    "chef": "Chef",
    "warrior": "Warrior",
    "scholar": "Scholar",
    "artisan": "Artisan",
    "ranger": "Ranger",
    "steward": "Steward",
    "monk": "Monk",
}

PATH_ICONS = {
    "chef": ft.Icons.RESTAURANT,
    "warrior": ft.Icons.FITNESS_CENTER,
    "scholar": ft.Icons.MENU_BOOK,
    "artisan": ft.Icons.PALETTE,
    "ranger": ft.Icons.HIKING,
    "steward": ft.Icons.ACCOUNT_BALANCE_WALLET,
    "monk": ft.Icons.SELF_IMPROVEMENT,
}

# --------------------------------------------------------------------------- themes


@dataclass(frozen=True)
class Palette:
    id: str
    name: str
    bg: str
    surface: str
    surface_hi: str
    primary: str
    on_primary: str
    accent: str  # coins
    success: str
    danger: str
    text: str
    text_dim: str
    paths: dict[str, str] = field(default_factory=dict)
    glow: bool = False  # Arcane / Rose Arcana: glowing panels, tracked-out uppercase labels


THEMES: dict[str, Palette] = {
    "arcane": Palette(
        id="arcane", name="Arcane",
        # panels read as translucent navy over the near-black bg (solid hex: dialogs, sheets
        # and the nav bar use these slots too and must stay opaque)
        bg="#070B14", surface="#0D1524", surface_hi="#131F35",
        primary="#4FE3F0", on_primary="#02181C",
        accent="#A78BFA", success="#5EEAB0", danger="#FB7C93",
        text="#E4F0FF", text_dim="#8FA4C2",
        paths={"chef": "#FFA071", "warrior": "#FF6F91", "scholar": "#6BB8FF",
               "artisan": "#C99BFF", "ranger": "#5EEAB0", "steward": "#FFD36E",
               "monk": "#9FD8B8"},
        glow=True,
    ),
    # Free for everyone. Arcane's mind-space in rose: deep plum night, hot-rose light, lilac and
    # peach nebula, champagne coins and mint success (mint is the complement, so it still reads
    # as "done" against all the pink). Contrast (WCAG): text 16.1:1 on panels, dim text 7.8:1
    # on the brightest panel, dark-on-rose buttons 7.2:1.
    "rose": Palette(
        id="rose", name="Rose Arcana",
        bg="#120814", surface="#1C0D21", surface_hi="#27142E",
        primary="#FF6FB1", on_primary="#2B0418",
        accent="#FFC08A", success="#6EE7BF", danger="#FF8063",
        text="#FCEAF3", text_dim="#C7A6BC",
        # warrior leans red and artisan lilac so neither is lost in the rose primary
        paths={"chef": "#FFA066", "warrior": "#FF5E68", "scholar": "#7DB6FF",
               "artisan": "#C29BFF", "ranger": "#5FE0B0", "steward": "#FFD66E",
               "monk": "#B3D99A"},
        glow=True,
    ),
    "ember": Palette(
        id="ember", name="Ember",
        bg="#14110F", surface="#1F1A16", surface_hi="#2B241F",
        primary="#FFA53A", on_primary="#2B1500",
        accent="#FFD54A", success="#5BD68A", danger="#FF6B5B",
        text="#F7EFE6", text_dim="#B5A99C",
        paths={"chef": "#FF8A4C", "warrior": "#FF5D5D", "scholar": "#5DA9FF",
               "artisan": "#C77DFF", "ranger": "#5BD68A", "steward": "#FFC94A",
               "monk": "#A8C69F"},
    ),
    "ocean": Palette(
        id="ocean", name="Ocean",
        bg="#0B141A", surface="#122029", surface_hi="#1B2D3A",
        primary="#3EC6E0", on_primary="#00262E",
        accent="#FFD54A", success="#5BD6A0", danger="#FF6B6B",
        text="#EAF4F8", text_dim="#9AB2BF",
        paths={"chef": "#FF9966", "warrior": "#FF6B81", "scholar": "#7FB8FF",
               "artisan": "#B794FF", "ranger": "#4FD8A8", "steward": "#FFD166",
               "monk": "#84C9B4"},
    ),
    "forest": Palette(
        id="forest", name="Forest",
        bg="#0E140F", surface="#162019", surface_hi="#203024",
        primary="#9BD46A", on_primary="#132600",
        accent="#FFD54A", success="#3FD8B0", danger="#FF6F5E",
        text="#EDF5EA", text_dim="#A3B5A0",
        paths={"chef": "#FF9A5A", "warrior": "#F2665A", "scholar": "#6FB3E8",
               "artisan": "#D08CF0", "ranger": "#7FD65A", "steward": "#E8C547",
               "monk": "#84A98C"},
    ),
    "royal": Palette(
        id="royal", name="Royal",
        bg="#110E19", surface="#1A1626", surface_hi="#252036",
        primary="#A98BFF", on_primary="#1C0E45",
        accent="#FFD54A", success="#5BD68A", danger="#FF6B8A",
        text="#F2EEFB", text_dim="#ABA3C4",
        paths={"chef": "#FF9466", "warrior": "#FF6B8A", "scholar": "#6FA8FF",
               "artisan": "#E08CFF", "ranger": "#5BD6A0", "steward": "#FFCC55",
               "monk": "#9CC5A8"},
    ),
}

DEFAULT_THEME = "arcane"
_current: list[str] = [DEFAULT_THEME]  # mutable cell; read via current()
_listeners: weakref.WeakSet = weakref.WeakSet()  # objects with .restyle()
_callbacks: list[Callable[[Palette], None]] = []
_glowing: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()  # ctrl -> manages border?


def current() -> Palette:
    return THEMES[_current[0]]


def path_color(path_id: str | None) -> str:
    """Concrete hex for a Path in the current theme (falls back to primary)."""
    pal = current()
    return pal.paths.get(path_id or "", pal.primary)


def path_icon(path_id: str | None) -> ft.IconData:
    return PATH_ICONS.get(path_id or "", ft.Icons.STAR)


def tr(text: str) -> str:
    """Translate a UI label using the active language (core/i18n.py)."""
    from lol.core.i18n import tr as _tr

    return _tr(text)


def path_name(path_id: str | None) -> str:
    return tr(PATH_NAMES.get(path_id or "", (path_id or "Quest").title()))


def glowing() -> bool:
    """True while the active theme draws glowing panels (Arcane)."""
    return current().glow


def panel_border(color: str | None = None) -> ft.Border | None:
    """1px low-opacity border for a glowing panel, or None on flat themes."""
    pal = current()
    return ft.Border.all(1, ft.Colors.with_opacity(0.30, color or pal.primary)) if pal.glow         else None


def panel_shadow(color: str | None = None, strength: float = 1.0) -> ft.BoxShadow | None:
    """Soft outer glow for a glowing panel, or None on flat themes."""
    pal = current()
    if not pal.glow:
        return None
    return ft.BoxShadow(blur_radius=18 * strength, spread_radius=0,
                        color=ft.Colors.with_opacity(0.10 * strength, color or pal.primary))


def glow(ctrl: ft.Container, *, border: bool = True) -> ft.Container:
    """Make a panel glow under Arcane (and go flat again on other themes, live).
    border=False: the control owns its border (status/Path colors); only the glow is set."""
    _glowing[ctrl] = border
    _apply_glow(ctrl, border)
    return ctrl


def _apply_glow(ctrl: ft.Container, border: bool) -> None:
    if border:
        ctrl.border = panel_border()
    ctrl.shadow = panel_shadow()


def label(text: str) -> str:
    """Label/eyebrow casing: translated, then uppercase under Arcane, as written elsewhere."""
    t = tr(text)
    return t.upper() if current().glow else t


def label_spacing() -> float | None:
    """Letter spacing for labels made with label()."""
    return 1.4 if current().glow else None


def build_theme(pal: Palette) -> ft.Theme:
    """Material theme whose ColorScheme slots carry our roles (see class C)."""
    scheme = ft.ColorScheme(
        primary=pal.primary, on_primary=pal.on_primary,
        primary_container=pal.surface_hi, on_primary_container=pal.primary,
        secondary=pal.success, on_secondary=pal.bg,
        secondary_container=ft.Colors.with_opacity(0.22, pal.primary),
        on_secondary_container=pal.text,
        tertiary=pal.accent, on_tertiary=pal.bg,
        error=pal.danger, on_error=pal.bg,
        surface=pal.bg, on_surface=pal.text, on_surface_variant=pal.text_dim,
        surface_container_lowest=pal.bg, surface_container_low=pal.surface,
        surface_container=pal.surface, surface_container_high=pal.surface_hi,
        surface_container_highest=pal.surface_hi,
        outline=pal.text_dim, outline_variant=ft.Colors.with_opacity(0.14, pal.text),
        scrim="#000000", shadow="#000000", surface_tint=pal.primary,
    )
    return ft.Theme(
        color_scheme=scheme,
        use_material3=True,
        scaffold_bgcolor=pal.bg,
        canvas_color=pal.bg,
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=pal.surface,
            indicator_color=ft.Colors.with_opacity(0.22, pal.primary),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            height=68,
        ),
    )


def on_theme_change(obj: object = None, callback: Callable[[Palette], None] | None = None):
    """Subscribe to theme switches.

    - `on_theme_change(obj)`: obj.restyle() is called (weakly held - no leaks).
    - `on_theme_change(callback=fn)`: fn(palette) is called (strongly held; for screens).
    """
    if obj is not None:
        _listeners.add(obj)
    if callback is not None:
        _callbacks.append(callback)


def apply_theme(page: ft.Page, theme_id: str, *, update: bool = True) -> Palette:
    """Switch theme live. Restyles registered components, then one page.update()."""
    if theme_id not in THEMES:
        theme_id = DEFAULT_THEME
    _current[0] = theme_id
    pal = THEMES[theme_id]
    t = build_theme(pal)
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = t
    page.dark_theme = t
    page.bgcolor = pal.bg
    for ctrl, border in list(_glowing.items()):
        with contextlib.suppress(Exception):
            _apply_glow(ctrl, border)
    for obj in list(_listeners):
        with contextlib.suppress(Exception):  # a dead control must never break the switch
            obj.restyle()
    for cb in _callbacks:
        cb(pal)
    if update:
        page.update()
    return pal
