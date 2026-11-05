"""More -> Study: flashcard decks, notes -> cards (paste, CSV/TSV file, or a photo scan) with a
draft review, and study sessions (exam simulator, learn, flip cards with self-rating, due
review, weak cards) ending in Luma's graded results.

Screens on the More stack (keys): "study" deck list · "study_deck" one deck · "study_drafts"
review parsed drafts · "study_run" a session + results. Draw + wire only: rules live in
lol.core.study (parser, question generators, StudyRun, spaced repetition, XP).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import storage, study
from lol.core.study import Draft, Question, StudyRun
from lol.ui import components as ui
from lol.ui import ocr, sfx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

STUDY = "#8EA2FF"  # the Study tile colour (more.TILES)
MISS = "#FFB347"  # a missed answer: warm amber, never red (Never guilt)
RIGHT_HEX = "#5EEAB0"  # success mint as hex (glass tints need hex, not a colour role)
CONF_COLORS = {"high": "#5EEAB0", "medium": "#FFC857", "low": "#B9C3D6"}
CONF_LABELS = {"high": "Sure", "medium": "Check", "low": "Guess"}
STATE_COLORS = {"new": "#B9C3D6", "learning": "#FFB347", "reviewing": "#7FB2FF",
                "confident": "#5EEAB0"}
KIND_OPTIONS = (("mc", "Multiple choice", ft.Icons.LIST, STUDY),
                ("tf", "True / false", ft.Icons.RULE, STUDY),
                ("fill", "Fill blank", ft.Icons.SHORT_TEXT, STUDY),
                ("type", "Type answer", ft.Icons.KEYBOARD, STUDY))
CATEGORY_OPTIONS = (("course", "Course", ft.Icons.SCHOOL, STUDY),
                    ("project", "Project", ft.Icons.WORK, STUDY),
                    ("skill", "Skill", ft.Icons.HANDYMAN, STUDY),
                    ("path", "Path", ft.Icons.MENU_BOOK, STUDY))
CATEGORY_LABELS = {v: lbl for v, lbl, _, _ in CATEGORY_OPTIONS}
RATING_OPTIONS = (("again", "Again", MISS), ("hard", "Hard", "#FFC857"),
                  ("good", "Good", "#7FB2FF"), ("easy", "Easy", "#5EEAB0"))
TIMERS = (0, 5, 10, 20)  # exam time limits, minutes (0 = none)
PARSE_STAGES = ("READING NOTES…", "FINDING TERMS…", "DRAFTS READY")
SCAN_STAGES = ("SCANNING PAGE…", "READING TEXT…", "FINDING TERMS…", "DRAFTS READY")
RESULT_STAGES = ("GRADING…", "FINDING WEAK SPOTS…", "RESULTS READY")
SCAN_TMP = "study_scan_tmp.jpg"
ADVANCE_S = 0.75  # a right answer moves on by itself after this long
SWIPE_PX = 80  # a flip card dragged this far sideways counts as a rating
FORMATS_HINT = ("Luma spots: term - definition · term: definition · term = definition · "
                "Q: … A: … · numbered lists · a heading with its text below · "
                "term<TAB>definition (spreadsheet copy).")


def make(app: App, key: str) -> Any:
    """More registry hook: every Study key builds here."""
    screens = {"study": StudyScreen, "study_deck": DeckScreen, "study_drafts": DraftsScreen,
               "study_run": RunScreen}
    return screens[key](app)


# --- shared bits -----------------------------------------------------------------------------------
def state_bar(deck: Any, height: int = 8) -> ft.Control:
    """Deck progress: one segment per card state (new -> confident)."""
    counts = study.deck_progress(deck)
    total = sum(counts.values())
    if not total:
        return ft.Container(height=height, border_radius=height // 2, bgcolor=C.a(C.TEXT, 0.08))
    segs = [ft.Container(bgcolor=STATE_COLORS[s], expand=n, height=height)
            for s, n in counts.items() if n]
    return ft.Container(ft.Row(segs, spacing=1), border_radius=height // 2, height=height,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def state_legend(deck: Any) -> ft.Control:
    counts = study.deck_progress(deck)
    return ft.Row([
        ft.Row([ft.Container(width=8, height=8, border_radius=4, bgcolor=STATE_COLORS[s]),
                ft.Text(f"{study.STATE_LABELS[s]} {n}", size=11, color=C.TEXT_DIM)],
               spacing=4, tight=True)
        for s, n in counts.items()], spacing=Space.MD, wrap=True, run_spacing=2)


def exam_chip(deck: Any, today: date) -> ft.Control | None:
    left = study.days_to_exam(deck, today)
    if left is None:
        return None
    text = "Exam today" if left == 0 else ("Exam tomorrow" if left == 1 else f"Exam in {left} d")
    return ui.chip(text, icon=ft.Icons.EVENT, color=C.ACCENT if left <= 3 else STUDY)


def _paste_field(value: str = "") -> ft.TextField:
    return ft.TextField(value=value, multiline=True, min_lines=6, max_lines=14, filled=True,
                        border_radius=Radius.SM, color=C.TEXT, fill_color=C.SURFACE_HI,
                        text_size=Type.BODY - 1, hint_text="Mitochondria - powerhouse of the cell\n"
                        "Q: Capital of France? A: Paris", autofocus=True)


_picker: ft.FilePicker | None = None


def picker() -> ft.FilePicker:
    global _picker
    if _picker is None:
        _picker = ft.FilePicker()  # a service: registers itself with the page
    return _picker


async def save_bytes(app: App, name: str, data: bytes, ext: str) -> None:
    """Save / download a file (desktop dialog, web download, phone system dialog)."""
    try:
        path = await picker().save_file(dialog_title="Export deck", file_name=name,
                                        file_type=ft.FilePickerFileType.CUSTOM,
                                        allowed_extensions=[ext], src_bytes=data)
    except Exception as exc:  # noqa: BLE001
        app.error(f"Couldn't save the file ({exc.__class__.__name__}).")
        return
    if app.page.web:
        app.toast(f"Downloading {name}", ft.Icons.DOWNLOAD)
        return
    if not path:
        app.toast("Export cancelled", ft.Icons.INFO_OUTLINE)
        return
    p = Path(path)
    with contextlib.suppress(OSError):
        if not p.exists() or p.stat().st_size == 0:
            p.write_bytes(data)  # desktop pickers that only return a path
    app.toast(f"Saved {p.name}", ft.Icons.TASK_ALT)


def _big_button(text: str, on_click: Any, *, icon: ft.IconData | None = None,
                color: str = C.PRIMARY, expand: bool = True, filled: bool = True) -> ft.Control:
    """Thumb-sized (56 px) action, silent tap (the screen plays the meaningful sound)."""
    style = ft.ButtonStyle(bgcolor=color if filled else None,
                           color=C.ON_PRIMARY if filled else color,
                           side=None if filled else ft.BorderSide(1, C.a(color, 0.5)),
                           shape=ft.RoundedRectangleBorder(radius=Radius.MD))
    cls = ft.FilledButton if filled else ft.OutlinedButton
    return cls(text, icon=icon, on_click=on_click, height=56, expand=expand, style=style)


# --- deck list ---------------------------------------------------------------------------------------
class StudyScreen:
    title = "Study"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="study")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._new,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="New deck")

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        items: list[ft.Control] = []
        if not g.decks:
            items.append(ui.EmptyState(
                "Your study desk is ready",
                "Make a deck for a class, a course at work or a skill. Paste your notes and "
                "Luma turns them into cards you check.",
                icon=ft.Icons.STYLE, action_text="Create a deck", on_action=self._new,
                color=STUDY))
        else:
            due = sum(len(g.due_today(d.id, today)) for d in g.decks)
            cards = sum(len(d.cards) for d in g.decks)
            items.append(common.card(ft.Row([
                ui.path_avatar(ft.Icons.STYLE, STUDY, 44),
                ft.Column([
                    ft.Text(f"{due} card{'s' if due != 1 else ''} due today" if due
                            else "All caught up for today",
                            size=Type.TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT),
                    common.hint(f"{len(g.decks)} deck{'s' if len(g.decks) != 1 else ''} · "
                                f"{cards} cards · sessions grow your Scholar Path"),
                ], spacing=2, tight=True, expand=True),
            ], spacing=Space.MD), padding=Space.MD, tint=STUDY))
            items.append(ui.SectionHeader("Decks", count=len(g.decks)))
            items += [self._deck_card(d, today) for d in g.decks]
        items.append(common.section("Daily review limit"))
        items.append(common.card(ft.Row([
            ft.Column([ft.Text("Due cards per deck per day", size=Type.BODY, color=C.TEXT),
                       common.hint("0 = no limit. A deck can set its own.")],
                      spacing=0, tight=True, expand=True),
            common.stepper(g.data.study_settings.daily_limit, self._set_limit, lo=0,
                           hi=study.MAX_DAILY_LIMIT, step=5, width=44),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=Space.MD))
        self.list.controls = items

    def _set_limit(self, n: int) -> None:
        self.app.game.set_study_limit(n)
        self.app.save()

    def _deck_card(self, deck: Any, today: date) -> ft.Control:
        g = self.app.game
        due = len(g.due_today(deck.id, today))
        sub = " · ".join(x for x in (CATEGORY_LABELS.get(deck.category, ""), deck.subject) if x)
        chips: list[ft.Control] = [ui.chip(f"{len(deck.cards)} cards", color=C.TEXT_DIM)]
        if due:
            chips.append(ui.chip(f"{due} due", icon=ft.Icons.SCHEDULE, color=deck.color))
        if (ex := exam_chip(deck, today)) is not None:
            chips.append(ex)
        if deck.quest_id:
            chips.append(ui.chip("Quest", icon=ft.Icons.FLAG, color=C.PRIMARY))
        box = common.card(ft.Column([
            ft.Row([
                ft.Container(width=4, height=40, border_radius=2, bgcolor=deck.color),
                ft.Column([
                    ft.Text(deck.title, size=Type.TITLE, weight=ft.FontWeight.BOLD,
                            color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    common.hint(sub or "Deck"),
                ], spacing=0, tight=True, expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=C.TEXT_DIM),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            state_bar(deck),
            ft.Row(chips, spacing=Space.XS, wrap=True, run_spacing=Space.XS),
        ], spacing=Space.SM, tight=True), padding=Space.MD, tint=deck.color)
        box.scale = 1
        box.animate_scale = Motion.anim(Motion.POP_MS, Motion.BACK)

        async def tap(_: Any) -> None:
            await ui.pop(box, 1.03)
            self.app.more.open("study_deck", deck_id=deck.id)

        box.on_click = tap
        return box

    def _new(self, _: Any = None) -> None:
        deck_sheet(self.app, None, self._created)

    def _created(self, deck_id: str) -> None:
        self.app.more.open("study_deck", deck_id=deck_id)


def deck_sheet(app: App, deck: Any | None, on_done: Any) -> None:
    """New / edit deck: name, what it is for (course / project / skill / Path), subject,
    exam date, its own daily limit."""
    g, today = app.game, app.today()
    name = common.text_field("Deck name", autofocus=deck is None)
    name.value = deck.title if deck else ""
    subject = common.text_field("Course, project or skill (optional)")
    subject.value = deck.subject if deck else ""
    cat = common.ChoicePills(CATEGORY_OPTIONS, deck.category if deck else "course",
                             grid_cols=2)
    state: dict[str, Any] = {"exam": deck.exam_date if deck else "",
                             "limit": deck.daily_limit if deck else 0}
    exam_value = date.fromisoformat(state["exam"]) if state["exam"] else None
    extra: list[ft.Control] = []
    if deck is not None:
        extra = [
            common.date_row(app.page, "Exam", exam_value, today,
                            lambda d: state.update(exam=d.isoformat() if d else ""),
                            clearable=True, help_text="Exam date"),
            ft.Row([ft.Column([ft.Text("Daily limit for this deck", color=C.TEXT),
                               common.hint("0 = use the global limit")], spacing=0,
                              tight=True, expand=True),
                    common.stepper(state["limit"], lambda n: state.update(limit=n), lo=0,
                                   hi=study.MAX_DAILY_LIMIT, step=5, width=44)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]

    async def save(_: Any = None) -> None:
        try:
            if deck is None:
                d = g.add_deck(name.value or "", today, subject.value or "", category=cat.value)
            else:
                d = g.edit_deck(deck.id, title=name.value or "", subject=subject.value or "",
                                category=cat.value, exam_date=state["exam"],
                                daily_limit=state["limit"])
        except ValueError as exc:
            app.error(str(exc).capitalize())
            return
        app.save()
        common.close(sheet)
        sfx.play("objective_new" if deck is None else "granted", 0.7)
        await ui.buzz("medium")
        app.toast("Deck created" if deck is None else "Deck saved", ft.Icons.STYLE)
        on_done(d.id)

    name.on_submit = save
    sheet = common.open_sheet(app.page, "New deck" if deck is None else "Edit deck", [
        name, subject, common.hint("What is it for?"), cat, *extra,
        ft.Row([_big_button("Create deck" if deck is None else "Save", save,
                            icon=ft.Icons.CHECK)]),
    ])


# --- one deck -------------------------------------------------------------------------------------
class DeckScreen:
    title = "Deck"

    def __init__(self, app: App) -> None:
        self.app = app
        self.deck_id = ""
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="study_deck")
        self.trailing: ft.Control | None = None
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._add_card,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Add card")

    def prepare(self, deck_id: str = "", **_: object) -> None:
        self.deck_id = deck_id or self.deck_id

    def _deck(self) -> Any | None:
        try:
            return self.app.game.deck(self.deck_id)
        except KeyError:
            return None

    def _refresh(self) -> None:
        self.app.more.refresh_top()

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def render(self) -> None:
        deck = self._deck()
        if deck is None:
            self.title = "Deck"
            self.list.controls = [common.empty_card("Deck not found", "It may have been "
                                                    "deleted.", ft.Icons.STYLE)]
            return
        g, today = self.app.game, self.app.today()
        self.title = deck.title
        quest = g.linked_quest(deck.id)
        self.trailing = common.menu_button([
            ("Edit deck", ft.Icons.EDIT, self._edit),
            ("Unlink quest" if quest else "Make it a daily quest", ft.Icons.FLAG,
             self._toggle_quest),
            ("Import CSV / TSV file", ft.Icons.UPLOAD_FILE, self._import_file),
            ("Export as CSV", ft.Icons.DOWNLOAD, lambda: self._export(",")),
            ("Export as TSV", ft.Icons.DOWNLOAD, lambda: self._export("\t")),
            ("Delete deck", ft.Icons.DELETE_OUTLINE, self._delete, True),
        ])
        due = g.due_today(deck.id, today)
        weak = study.weak_cards(deck)
        sub = " · ".join(x for x in (CATEGORY_LABELS.get(deck.category, ""), deck.subject) if x)
        chips: list[ft.Control] = [ui.chip(f"{len(due)} due today", icon=ft.Icons.SCHEDULE,
                                           color=deck.color)]
        if (ex := exam_chip(deck, today)) is not None:
            chips.append(ex)
        if quest is not None:
            done = g.is_done(quest, today)
            chips.append(ui.chip("Quest done today" if done else "Daily quest",
                                 icon=ft.Icons.TASK_ALT if done else ft.Icons.FLAG,
                                 color=C.SUCCESS if done else C.PRIMARY))
        n = len(deck.cards)
        hero = common.card(ft.Column([
            common.hint(sub or "Deck"),
            ft.Row(chips, spacing=Space.XS, wrap=True, run_spacing=Space.XS),
            state_bar(deck, 10), state_legend(deck),
            ft.Row([_big_button("Study", self._mode_sheet, icon=ft.Icons.PLAY_ARROW,
                                color=deck.color)]),
            ft.Row([
                _big_button(f"Review ({len(due)})", self._review_due, icon=ft.Icons.STYLE,
                            color=deck.color, filled=False),
                _big_button(f"Weak ({len(weak)})", self._weak, icon=ft.Icons.TRENDING_DOWN,
                            color=MISS, filled=False),
            ], spacing=Space.SM),
        ], spacing=Space.SM, tight=True), padding=Space.MD, tint=deck.color)
        adders = ft.Row([
            self._adder("Paste notes", ft.Icons.CONTENT_PASTE, self._paste),
            self._adder("Scan notes", ft.Icons.DOCUMENT_SCANNER, self._scan),
            self._adder("Add card", ft.Icons.ADD_CARD, self._add_card),
        ], spacing=Space.SM)
        items: list[ft.Control] = [hero, adders, ui.SectionHeader("Cards", count=n)]
        if not deck.cards:
            items.append(common.empty_card(
                "No cards yet", "Paste or scan your notes and Luma drafts the cards, or add "
                "one by hand.", ft.Icons.STYLE))
        items += [self._card_row(c) for c in deck.cards]
        self.list.controls = items

    @staticmethod
    def _adder(label: str, icon: ft.IconData, fn: Any) -> ft.Control:
        box = ft.Container(
            ft.Column([ft.Icon(icon, color=STUDY, size=24),
                       ft.Text(label, size=Type.CAPTION, color=C.TEXT,
                               weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)],
                      spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, height=76, border_radius=Radius.MD, alignment=ft.Alignment.CENTER,
            bgcolor=C.a(STUDY, 0.12), border=ft.Border.all(1, C.a(STUDY, 0.4)), scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))

        async def tap(_: Any) -> None:
            await ui.pop(box, 1.06)
            res = fn()
            if asyncio.iscoroutine(res):
                await res

        box.on_click = tap
        return box

    def _card_row(self, c: Any) -> ft.Control:
        st = study.card_state(c)
        row = ft.Container(ft.Column([
            ft.Row([ft.Text(c.term, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT,
                            expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ui.chip(study.STATE_LABELS[st], color=STATE_COLORS[st])],
                   vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Text(c.definition, size=Type.LABEL, color=C.TEXT_DIM, max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=4, tight=True), bgcolor=C.SURFACE_HI, border_radius=Radius.MD, ink=True,
            padding=Space.MD, on_click=lambda e, cid=c.id: self._edit_card(cid))
        return row

    # actions
    def _edit(self) -> None:
        deck = self._deck()
        if deck is not None:
            deck_sheet(self.app, deck, lambda _id: self._refresh())

    async def _toggle_quest(self) -> None:
        g, deck = self.app.game, self._deck()
        if deck is None:
            return
        if g.linked_quest(deck.id):
            g.unlink_quest(deck.id)
            self.app.save()
            self.app.toast("Quest unlinked. It stays in your quest list.", ft.Icons.FLAG)
        else:
            q = g.link_quest(deck.id, self.app.today())
            self.app.save()
            sfx.play("objective_new")
            await ui.buzz("medium")
            self.app.toast(f"New daily quest: {q.title}. A finished session completes it.",
                           ft.Icons.FLAG)
        with contextlib.suppress(Exception):
            self.app.update_badges()
        self._refresh()

    async def _delete(self) -> None:
        deck = self._deck()
        if deck is None:
            return
        ok = await common.confirm(self.app.page, "Delete this deck?",
                                  f"{deck.title} and its {len(deck.cards)} cards are removed. "
                                  "XP you earned stays.", "Delete", danger=True)
        if not ok:
            return
        self.app.game.delete_deck(deck.id)
        self.app.save()
        self.app.toast("Deck deleted", ft.Icons.DELETE_OUTLINE)
        self.app.more.back()

    async def _export(self, delim: str) -> None:
        deck = self._deck()
        if deck is None:
            return
        if not deck.cards:
            self.app.error("This deck has no cards to export yet.")
            return
        ext = "csv" if delim == "," else "tsv"
        safe = "".join(ch if ch.isalnum() else "-" for ch in deck.title.lower()).strip("-")
        text = study.deck_to_text(deck.cards, delim)
        await save_bytes(self.app, f"{safe or 'deck'}.{ext}", text.encode("utf-8-sig"), ext)

    async def _import_file(self) -> None:
        app = self.app
        try:
            files = await picker().pick_files(
                dialog_title="Choose a CSV or TSV file", file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv", "tsv", "txt"], with_data=True)
        except Exception as exc:  # noqa: BLE001
            app.error(f"Couldn't open the file picker ({exc.__class__.__name__}).")
            return
        if not files:
            return
        f = files[0]
        try:
            raw = f.bytes if f.bytes is not None else Path(f.path or "").read_bytes()
            text = bytes(raw).decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            app.error(f"Couldn't read that file: {exc.__class__.__name__}")
            return
        await self._to_drafts(text, table=True, source=f.name)

    def _paste(self, text: str = "") -> None:
        field = _paste_field(text)

        async def find(_: Any = None) -> None:
            if not (field.value or "").strip():
                self.app.error("Paste or type some notes first.")
                return
            common.close(sheet)
            await self._to_drafts(field.value or "", source="notes")

        sheet = common.open_sheet(self.app.page, "Paste your notes", [
            common.hint(FORMATS_HINT), field,
            ft.Row([_big_button("Find cards", find, icon=ft.Icons.AUTO_AWESOME)]),
        ])

    async def _scan(self) -> None:
        app = self.app
        rec = ocr.recognizer_for(app.page)
        if isinstance(rec, study.ManualTextRecognizer):
            app.toast("Text scan runs on the phone app. Paste or type the notes here.",
                      ft.Icons.DOCUMENT_SCANNER)
            self._paste()
            return
        from lol.ui import ads  # premium limits: note scans (typing/pasting stays free)
        from lol.ui.screens.meal import capture  # camera sheet / photo picker

        if not await ads.limit_gate(app, "note_scan", manual=self._paste,
                                    manual_label="Paste or type the notes"):
            return
        data = await capture(app)
        if not data:
            return
        ads.spend(app, "note_scan")
        sfx.play("shutter")
        path = storage.data_dir() / SCAN_TMP
        await asyncio.to_thread(path.write_bytes, data)

        async def work() -> tuple[str, study.ParseResult]:
            try:
                text = await rec.recognize_async(str(path))  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                text = ""
            return text, study.parse_notes(text)

        try:
            text, parsed = await ui.lumen_analyze(app.page, SCAN_STAGES, work, seconds=2.4)
        finally:
            with contextlib.suppress(OSError):
                path.unlink()
        if not text.strip():
            app.error("Luma couldn't read text in that photo. Paste or type it instead.")
            self._paste()
            return
        self._open_drafts(parsed, text, "scan")

    async def _to_drafts(self, text: str, *, table: bool = False, source: str = "") -> None:
        def work() -> study.ParseResult:
            return study.parse_table(text) if table else study.parse_notes(text)

        parsed = await ui.lumen_analyze(self.app.page, PARSE_STAGES, work, seconds=1.8)
        self._open_drafts(parsed, text, source)

    def _open_drafts(self, parsed: study.ParseResult, text: str, source: str) -> None:
        deck = self._deck()
        if deck is None:
            return
        study.mark_duplicates(parsed.drafts, [c.term for c in deck.cards])
        if not parsed.drafts:
            self.app.error("No term/definition pairs found. Try 'term - definition' lines.")
            self._paste(text)
            return
        sfx.play("scan_done")
        self.app.more.open("study_drafts", deck_id=deck.id, drafts=parsed.drafts,
                           skipped=parsed.skipped, text=text, source=source)

    def _add_card(self, _: Any = None) -> None:
        card_sheet(self.app, self.deck_id, None, self._refresh)

    def _edit_card(self, card_id: str) -> None:
        card_sheet(self.app, self.deck_id, card_id, self._refresh)

    # sessions
    def _mode_sheet(self, _: Any = None) -> None:
        deck = self._deck()
        if deck is None:
            return
        if not deck.cards:
            self.app.error("Add a few cards first.")
            return
        n = len(deck.cards)
        st: dict[str, Any] = {"mode": "exam", "kinds": {"mc", "tf", "fill"},
                              "count": min(10, n), "timer": 0}
        kinds = common.ToggleChips(KIND_OPTIONS, st["kinds"],
                                   lambda sel: st.update(kinds=set(sel)))
        timer = common.ChoicePills([(str(m), f"{m} min" if m else "No timer", None, STUDY)
                                    for m in TIMERS], "0", grid_cols=2,
                                   on_change=lambda v: st.update(timer=int(v)))
        quiz_opts = ft.Column([common.hint("Question types"), kinds, common.hint("Time limit"),
                               timer], spacing=Space.SM, tight=True)
        mode_hint = common.hint("")
        hints = {"exam": "Each card once, scored like a test. Missed cards come back sooner.",
                 "learn": "Missed cards repeat until you get them right.",
                 "flip": "Classic cards: flip, then rate Again / Hard / Good / Easy."}
        mode_hint.value = hints["exam"]

        def set_mode(v: str) -> None:
            st["mode"] = v
            mode_hint.value = hints[v]
            quiz_opts.visible = v != "flip"
            timer.visible = v == "exam"
            ui.refresh(mode_hint, quiz_opts)

        mode = common.segmented([("exam", "Exam"), ("learn", "Learn"), ("flip", "Flip cards")],
                                "exam", set_mode)

        def start(_: Any = None) -> None:
            if st["mode"] != "flip" and not st["kinds"]:
                self.app.error("Pick at least one question type.")
                return
            common.close(sheet)
            self.app.more.open("study_run", deck_id=deck.id, mode=st["mode"],
                               kinds=sorted(st["kinds"]) if st["mode"] != "flip" else ["flip"],
                               count=st["count"], timer_min=st["timer"] if st["mode"] == "exam"
                               else 0)

        sheet = common.open_sheet(self.app.page, f"Study {deck.title}", [
            mode, mode_hint, quiz_opts,
            ft.Row([ft.Text("Cards", color=C.TEXT, expand=True),
                    common.stepper(st["count"], lambda v: st.update(count=v), lo=1, hi=n,
                                   width=44)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([_big_button("Start", start, icon=ft.Icons.PLAY_ARROW, color=deck.color)]),
        ])

    def _review_due(self, _: Any = None) -> None:
        deck = self._deck()
        if deck is None:
            return
        due = self.app.game.due_today(deck.id, self.app.today())
        if not due:
            sfx.play("error_soft")
            self.app.toast("Nothing due today. Come back tomorrow or try a quiz.",
                           ft.Icons.EVENT_AVAILABLE)
            return
        self.app.more.open("study_run", deck_id=deck.id, mode="review", kinds=["flip"],
                           count=len(due), card_ids=[c.id for c in due])

    def _weak(self, _: Any = None) -> None:
        deck = self._deck()
        if deck is None:
            return
        weak = study.weak_cards(deck)
        if not weak:
            sfx.play("error_soft")
            self.app.toast("No weak cards right now. Nice work.", ft.Icons.TRENDING_UP)
            return
        self.app.more.open("study_run", deck_id=deck.id, mode="weak",
                           kinds=["mc", "tf", "fill", "type"], count=len(weak),
                           card_ids=[c.id for c in weak])


def card_sheet(app: App, deck_id: str, card_id: str | None, on_done: Any) -> None:
    g = app.game
    card = g.card(deck_id, card_id) if card_id else None
    term = common.text_field("Term or question", autofocus=card is None)
    term.value = card.term if card else ""
    definition = common.text_field("Definition or answer")
    definition.multiline, definition.min_lines, definition.max_lines = True, 2, 6
    definition.value = card.definition if card else ""
    hint = common.text_field("Hint (optional)")
    hint.value = card.hint if card else ""
    example = common.text_field("Example (optional)")
    example.value = card.example if card else ""
    tags = common.text_field("Tags, comma separated (optional)")
    tags.value = ", ".join(card.tags) if card else ""

    async def save(_: Any = None) -> None:
        tag_list = [t for t in (tags.value or "").split(",") if t.strip()]
        try:
            if card is None:
                g.add_card(deck_id, term.value or "", definition.value or "",
                           hint=hint.value or "", example=example.value or "", tags=tag_list)
            else:
                g.edit_card(deck_id, card.id, term=term.value or "",
                            definition=definition.value or "", hint=hint.value or "",
                            example=example.value or "", tags=tag_list)
        except ValueError as exc:
            app.error(str(exc).capitalize())
            return
        app.save()
        common.close(sheet)
        sfx.play("granted", 0.6)
        await ui.buzz("light")
        app.toast("Card added" if card is None else "Card saved", ft.Icons.ADD_CARD)
        on_done()

    async def delete(_: Any = None) -> None:
        common.close(sheet)
        if card is None:
            return
        g.delete_card(deck_id, card.id)
        app.save()
        app.toast("Card deleted", ft.Icons.DELETE_OUTLINE)
        on_done()

    buttons: list[ft.Control] = [_big_button("Add card" if card is None else "Save", save,
                                             icon=ft.Icons.CHECK)]
    if card is not None:
        buttons.insert(0, _big_button("Delete", delete, icon=ft.Icons.DELETE_OUTLINE,
                                      color=C.DANGER, filled=False, expand=False))
    sheet = common.open_sheet(app.page, "New card" if card is None else "Edit card", [
        term, definition, hint, example, tags, ft.Row(buttons, spacing=Space.SM)])


# --- draft review ("final checking with the user") --------------------------------------------
class DraftsScreen:
    title = "Check the cards"

    def __init__(self, app: App) -> None:
        self.app = app
        self.deck_id = ""
        self.drafts: list[Draft] = []
        self.keep: list[bool] = []
        self.skipped: list[str] = []
        self.text = ""
        self.source = ""
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="study_drafts")
        self.save_btn = _big_button("Save cards", self._save, icon=ft.Icons.CHECK)

    def prepare(self, deck_id: str = "", drafts: list[Draft] | None = None,
                skipped: list[str] | None = None, text: str = "", source: str = "",
                **_: object) -> None:
        self.deck_id = deck_id
        self.drafts = list(drafts or [])
        self.keep = [d.confidence != "low" and not d.duplicate for d in self.drafts]
        self.skipped = list(skipped or [])
        self.text, self.source = text, source

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _count(self) -> int:
        return sum(1 for d, k in zip(self.drafts, self.keep, strict=True)
                   if k and d.term.strip() and d.definition.strip())

    def _paint_save(self) -> None:
        n = self._count()
        self.save_btn.content = f"Save {n} card{'s' if n != 1 else ''}"
        self.save_btn.disabled = n == 0
        ui.refresh(self.save_btn)

    def render(self) -> None:
        by = {k: sum(d.confidence == k for d in self.drafts) for k in study.CONFIDENCES}
        where = {"scan": "your photo", "notes": "your notes"}.get(self.source, self.source
                                                                  or "your notes")
        summary = common.card(ft.Column([
            ft.Row([ui.path_avatar(ft.Icons.AUTO_AWESOME, "#4FE3F0", 40),
                    ft.Text(f"Luma found {len(self.drafts)} cards in {where}", size=Type.TITLE,
                            weight=ft.FontWeight.BOLD, color=C.TEXT, expand=True)],
                   spacing=Space.MD),
            common.hint("Check each one before it is saved: fix the text, untick what's "
                        "wrong. Guesses and repeats start unticked."),
            ft.Row([ui.chip(f"{by[k]} {CONF_LABELS[k].lower()}", color=CONF_COLORS[k])
                    for k in study.CONFIDENCES if by[k]], spacing=Space.XS, wrap=True),
            ft.Row([ft.TextButton("Tick all", height=Size.TAP,
                                  on_click=lambda e: self._all(True)),
                    ft.TextButton("Untick all", height=Size.TAP,
                                  on_click=lambda e: self._all(False)),
                    ft.TextButton("Edit text", icon=ft.Icons.EDIT_NOTE, height=Size.TAP,
                                  on_click=self._edit_text)], spacing=0, wrap=True),
        ], spacing=Space.SM, tight=True), padding=Space.MD, tint="#4FE3F0")
        items: list[ft.Control] = [summary]
        items += [self._row(i) for i in range(len(self.drafts))]
        if self.skipped:
            items.append(common.section(f"{len(self.skipped)} lines became no card"))
            items.append(common.card(ft.Column(
                [ft.Text(s, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=2,
                         overflow=ft.TextOverflow.ELLIPSIS) for s in self.skipped[:30]],
                spacing=4, tight=True), padding=Space.MD))
        items.append(ft.Row([self.save_btn]))
        self.list.controls = items
        self._paint_save()

    def _row(self, i: int) -> ft.Control:
        d = self.drafts[i]
        col = CONF_COLORS[d.confidence]
        term = ft.TextField(value=d.term, label="Term", dense=True, filled=True,
                            fill_color=C.SURFACE_HI, color=C.TEXT, text_size=Type.BODY,
                            border_radius=Radius.SM)
        dfn = ft.TextField(value=d.definition, label="Definition", dense=True, filled=True,
                           multiline=True, min_lines=1, max_lines=5, fill_color=C.SURFACE_HI,
                           color=C.TEXT, text_size=Type.LABEL + 1, border_radius=Radius.SM)

        def edited(_: Any) -> None:
            d.term, d.definition = term.value or "", dfn.value or ""
            self._paint_save()

        term.on_change = dfn.on_change = edited
        box = common.card(ft.Column([], spacing=Space.SM, tight=True), padding=Space.MD,
                          tint=col)
        check = ft.Checkbox(value=self.keep[i], fill_color=STUDY, scale=1.2)
        tags = [ui.chip(CONF_LABELS[d.confidence], color=col)]
        if d.duplicate:
            tags.append(ui.chip("Already in deck", icon=ft.Icons.CONTENT_COPY, color=MISS))
        tags.append(ft.Text(f"line {d.line}", size=11, color=C.TEXT_DIM))

        def paint() -> None:
            box.opacity = 1 if self.keep[i] else 0.5

        def toggle(e: Any) -> None:
            self.keep[i] = bool(check.value)
            paint()
            ui.refresh(box)
            self._paint_save()
            self.app.page.run_task(ui.buzz, "select")

        check.on_change = toggle
        box.content.controls = [  # type: ignore[union-attr]
            ft.Row([ft.Container(check, width=Size.TAP, height=Size.TAP,
                                 alignment=ft.Alignment.CENTER),
                    ft.Row(tags, spacing=Space.XS, expand=True, wrap=True)],
                   spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            term, dfn]
        box.animate_opacity = Motion.anim(Motion.FADE_MS)
        paint()
        return box

    def _all(self, on: bool) -> None:
        self.keep = [on] * len(self.drafts)
        self.render()
        ui.refresh(self.list)

    def _edit_text(self, _: Any = None) -> None:
        deck_screen = self.app.more.sub("study_deck")
        self.app.more.back()
        deck_screen._paste(self.text)

    async def _save(self, _: Any = None) -> None:
        picked = [d for d, k in zip(self.drafts, self.keep, strict=True) if k]
        try:
            added = self.app.game.add_cards(self.deck_id, picked)
        except KeyError:
            self.app.error("That deck is gone.")
            return
        if not added:
            self.app.error("Tick at least one card with a term and a definition.")
            return
        self.app.save()
        sfx.play("granted")
        await ui.buzz("medium")
        self.app.juice(STUDY, None, 0.5)
        self.app.toast(f"Saved {len(added)} card{'s' if len(added) != 1 else ''}",
                       ft.Icons.ADD_CARD)
        self.app.more.back()


# --- a study session ---------------------------------------------------------------------------
class RunScreen:
    title = "Study"

    def __init__(self, app: App) -> None:
        self.app = app
        self.deck_id = ""
        self.mode = "exam"
        self.kinds: list[str] = ["mc"]
        self.count = 10
        self.timer_min = 0
        self.card_ids: list[str] | None = None
        self.run: StudyRun | None = None
        self.gen = 0  # bumps on every start/leave: stale timers and advances stop
        self.started = 0.0
        self.locked = False
        self.done = False
        self.progress = ft.ProgressBar(value=0, color=STUDY, bgcolor=C.a(C.TEXT, 0.1),
                                       height=8, border_radius=4, expand=True)
        self.counter = ft.Text("", size=Type.LABEL, color=C.TEXT_DIM,
                               weight=ft.FontWeight.BOLD)
        self.clock = ui.chip("", icon=ft.Icons.TIMER, color=STUDY)
        self.clock.visible = False
        self.header = ft.Container(ft.Row([self.progress, self.counter, self.clock],
                                          spacing=Space.SM,
                                          vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                   padding=ft.Padding.symmetric(horizontal=Space.GUTTER,
                                                                vertical=Space.SM))
        self.body = ft.Container(ft.Container(), opacity=1, offset=ft.Offset(0, 0))
        self.scroll = ft.ListView([self.body], expand=True, padding=ft.Padding.only(
            left=Space.GUTTER, right=Space.GUTTER, bottom=Space.XXL))
        self.view = ft.Container(ft.Column([self.header, self.scroll], spacing=0, expand=True),
                                 expand=True, key="study_run")

    def prepare(self, deck_id: str = "", mode: str = "exam", kinds: list[str] | None = None,
                count: int = 10, timer_min: int = 0, card_ids: list[str] | None = None,
                **_: object) -> None:
        self.deck_id, self.mode = deck_id, mode
        self.kinds = list(kinds or study.QUIZ_KINDS)
        self.count, self.timer_min = int(count), int(timer_min)
        self.card_ids = list(card_ids) if card_ids else None
        self._start()

    def _cards(self) -> list[Any]:
        deck = self.app.game.deck(self.deck_id)
        if self.card_ids is None:
            return list(deck.cards)
        want = set(self.card_ids)
        return [c for c in deck.cards if c.id in want]

    def _start(self) -> None:
        self.gen += 1
        try:
            deck = self.app.game.deck(self.deck_id)
        except KeyError:
            self.run = None
            return
        self.title = {"review": "Due review", "weak": "Weak cards"}.get(self.mode, deck.title)
        cards = self._cards()
        qs = study.build_quiz(cards, self.kinds, self.count, self.app.today(), random.Random())
        if self.card_ids is not None:  # keep the given order (most urgent / weakest first)
            order = {cid: i for i, cid in enumerate(self.card_ids)}
            qs.sort(key=lambda q: order.get(q.card_id, 0))
        self.run = StudyRun(qs, learn=self.mode in ("learn", "weak"),
                            time_limit_s=self.timer_min * 60)
        self.started = time.monotonic()
        self.locked = self.done = False
        self.progress.color = deck.color
        self.clock.visible = bool(self.run.time_limit_s)
        self.header.visible = True

    def render(self) -> None:
        if self.run is None:
            self.body.content = common.empty_card("Nothing to study", "The deck is gone.",
                                                  ft.Icons.STYLE)
            return
        if self.done:
            return  # results stay on screen
        self._show_question(update=False)

    def on_enter(self) -> None:
        if self.run is not None and self.run.time_limit_s and not self.done:
            self.app.page.run_task(self._tick, self.gen)

    def on_leave(self) -> None:
        self.gen += 1  # stops the timer; an unfinished run is dropped (nothing saved)

    def restyle(self) -> None:
        ui.refresh(self.view)

    # header
    def _paint_header(self) -> None:
        run = self.run
        if run is None:
            return
        self.progress.value = run.progress
        shown = min(len(run.first) + (0 if run.finished else 1), run.total)
        self.counter.value = (f"{len(run.mastered)}/{run.total} learned" if run.learn
                              else f"{shown}/{run.total}")
        if run.time_limit_s:
            left = max(0, run.time_limit_s - int(time.monotonic() - self.started))
            self.clock.content.controls[-1].value = f"{left // 60}:{left % 60:02d}"  # type: ignore[union-attr]
            self.clock.border = ft.Border.all(1, C.a(MISS if left <= 30 else STUDY, 0.6))

    async def _tick(self, gen: int) -> None:
        while gen == self.gen and self.run is not None and not self.run.finished:
            self._paint_header()
            ui.refresh(self.header)
            if time.monotonic() - self.started >= self.run.time_limit_s:
                sfx.play("timer_done", 0.6)
                self.app.toast("Time's up. Unanswered cards count as missed.", ft.Icons.TIMER)
                self.run.expire()
                await self._finish()
                return
            await asyncio.sleep(1)

    # questions
    def _show_question(self, update: bool = True) -> None:
        run = self.run
        if run is None:
            return
        q = run.current
        self._paint_header()
        if q is None:
            return
        self.locked = False
        builders = {"mc": self._mc, "tf": self._tf, "fill": self._typed, "type": self._typed,
                    "flip": self._flip}
        view = builders[q.kind](q)
        view.key = f"q{len(run.answers)}"
        if isinstance(view, ft.Column):
            view.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self.body.content = view
        if update:
            self.app.page.run_task(self._slide_in)

    async def _slide_in(self) -> None:
        """New question: a short slide + fade in from the right."""
        b = self.body
        b.animate_opacity = b.animate_offset = ui.SNAP
        b.opacity, b.offset = 0, ft.Offset(0.06, 0)
        ui.refresh(self.view)
        await asyncio.sleep(0.03)
        b.animate_opacity = Motion.anim(180)
        b.animate_offset = Motion.anim(220, Motion.EASE_CUBIC)
        b.opacity, b.offset = 1, ft.Offset(0, 0)
        ui.refresh(b)

    def _prompt(self, q: Question, size: int = Type.HEADLINE) -> ft.Control:
        parts: list[ft.Control] = []
        if q.context:
            parts.append(ft.Text(th.label(q.context), size=Type.CAPTION, color=C.TEXT_DIM,
                                 weight=ft.FontWeight.BOLD,
                                 style=ft.TextStyle(letter_spacing=th.label_spacing())))
        parts.append(ft.Text(q.prompt, size=size, weight=ft.FontWeight.BOLD, color=C.TEXT,
                             selectable=False))
        return common.card(ft.Column(parts, spacing=Space.SM, tight=True), padding=Space.LG,
                           tint=STUDY)

    def _option(self, text: str, badge: str, on_tap: Any) -> ft.Container:
        return ft.Container(
            ft.Row([ft.Container(ft.Text(badge, size=Type.LABEL, weight=ft.FontWeight.BOLD,
                                         color=STUDY),
                                 width=30, height=30, border_radius=15,
                                 alignment=ft.Alignment.CENTER, bgcolor=C.a(STUDY, 0.14)),
                    ft.Text(text, size=Type.BODY, color=C.TEXT, expand=True)],
                   spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.MD),
            border_radius=Radius.MD, bgcolor=C.SURFACE_HI,
            border=ft.Border.all(1.5, C.a(C.TEXT, 0.1)), ink=True, on_click=on_tap,
            scale=1, animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            animate=Motion.anim(Motion.FADE_MS))

    @staticmethod
    def _mark(box: ft.Container, ok: bool) -> None:
        col = C.SUCCESS if ok else MISS
        box.bgcolor = C.a(col, 0.18)
        box.border = ft.Border.all(2, col)
        row = box.content
        if isinstance(row, ft.Row) and len(row.controls) == 2:
            row.controls.append(ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL,
                                        color=col, size=22))

    def _mc(self, q: Question) -> ft.Control:
        boxes: list[ft.Container] = []

        async def pick(i: int) -> None:
            if self.locked:
                return
            self.locked = True
            g = self.run.answer(i)  # type: ignore[union-attr]
            self._mark(boxes[i], g.correct)
            if not g.correct:
                self._mark(boxes[q.correct], True)
            for b in boxes:
                b.on_click = None
            await self._feedback(g.correct, boxes[i], q)

        for i, opt in enumerate(q.options):
            boxes.append(self._option(opt, "ABCD"[i] if i < 4 else str(i + 1),
                                      lambda e, i=i: self.app.page.run_task(pick, i)))
        self.next_slot = ft.Container()
        return ft.Column([self._prompt(q), *boxes, self.next_slot], spacing=Space.SM,
                         tight=True)

    def _tf(self, q: Question) -> ft.Control:
        statement = common.card(ft.Text(q.statement, size=Type.TITLE, color=C.TEXT),
                                padding=Space.LG)
        boxes: list[ft.Container] = []

        async def pick(i: int) -> None:
            if self.locked:
                return
            self.locked = True
            g = self.run.answer(i)  # type: ignore[union-attr]
            self._mark(boxes[i], g.correct)
            if not g.correct:
                self._mark(boxes[q.correct], True)
            for b in boxes:
                b.on_click = None
            await self._feedback(g.correct, boxes[i], q)

        for i, (label, icon) in enumerate((("True", ft.Icons.CHECK), ("False", ft.Icons.CLOSE))):
            box = ft.Container(
                ft.Row([ft.Icon(icon, color=STUDY), ft.Text(label, size=Type.TITLE,
                                                             weight=ft.FontWeight.BOLD,
                                                             color=C.TEXT)],
                       spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER),
                height=72, expand=True, border_radius=Radius.MD, bgcolor=C.SURFACE_HI,
                border=ft.Border.all(1.5, C.a(C.TEXT, 0.1)), ink=True,
                alignment=ft.Alignment.CENTER, scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                animate=Motion.anim(Motion.FADE_MS),
                on_click=lambda e, i=i: self.app.page.run_task(pick, i))
            boxes.append(box)
        self.next_slot = ft.Container()
        return ft.Column([self._prompt(q), common.hint("Is this the right definition?"),
                          statement, ft.Row(boxes, spacing=Space.SM), self.next_slot],
                         spacing=Space.SM, tight=True)

    def _typed(self, q: Question) -> ft.Control:
        field = ft.TextField(label="Your answer", filled=True, fill_color=C.SURFACE_HI,
                             color=C.TEXT, text_size=Type.TITLE, border_radius=Radius.SM,
                             autofocus=True, capitalization=ft.TextCapitalization.NONE,
                             autocorrect=False)
        result = ft.Container()

        async def check(_: Any = None) -> None:
            if self.locked:
                return
            if not (field.value or "").strip():
                sfx.play("error_soft")
                await ui.nudge(field_box)
                return
            self.locked = True
            g = self.run.answer(field.value)  # type: ignore[union-attr]
            field.read_only = True
            col = C.SUCCESS if g.correct else MISS
            field.border_color = col
            line = ("Correct!" if g.correct and not g.close
                    else f"Right, with a typo forgiven: {q.answer}" if g.correct
                    else f"Answer: {q.answer}")
            result.content = ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if g.correct else ft.Icons.CANCEL, color=col),
                ft.Text(line, size=Type.BODY, color=C.TEXT, weight=ft.FontWeight.W_600,
                        expand=True)], spacing=Space.SM)
            check_btn.visible = False
            ui.refresh(field, check_btn, result)
            await self._feedback(g.correct, field_box, q)

        field.on_submit = check
        field_box = ft.Container(field, scale=1,
                                 animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))
        check_btn = ft.Row([_big_button("Check", check, icon=ft.Icons.KEYBOARD_RETURN)])
        self.next_slot = ft.Container()
        tip = common.hint("Case, accents and small typos don't count against you.")
        return ft.Column([self._prompt(q, Type.TITLE + 2 if q.kind == "fill" else Type.HEADLINE),
                          field_box, tip, result, check_btn, self.next_slot],
                         spacing=Space.SM, tight=True)

    def _flip(self, q: Question) -> ft.Control:
        state = {"back": False}
        face = ft.Text(q.prompt, size=Type.HEADLINE, weight=ft.FontWeight.BOLD, color=C.TEXT,
                       text_align=ft.TextAlign.CENTER)
        side = ft.Text("TERM", size=Type.CAPTION, color=C.TEXT_DIM, weight=ft.FontWeight.BOLD)
        tap_hint = common.hint("Tap to flip · swipe right = Good, left = Again")
        card = ft.Container(
            ft.Column([side, face] + ([common.hint(f"Hint: {q.context}")] if q.context else []),
                      spacing=Space.MD, tight=True,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            height=260, border_radius=Radius.LG, alignment=ft.Alignment.CENTER,
            padding=Space.XL, bgcolor=C.a(STUDY, 0.1), border=ft.Border.all(1.5, C.a(STUDY,
                                                                                    0.5)),
            scale=1, animate_scale=Motion.anim(120, Motion.EASE), offset=ft.Offset(0, 0),
            animate=Motion.anim(Motion.FADE_MS))
        ratings = ft.Row(spacing=Space.XS, visible=False)

        async def flip(_: Any = None) -> None:
            if self.locked:
                return
            sfx.play("holo_flicker", 0.5)
            card.scale = 0.92
            ui.refresh(card)
            await asyncio.sleep(0.12)
            state["back"] = not state["back"]
            face.value = q.back if state["back"] else q.prompt
            face.size = Type.TITLE if state["back"] else Type.HEADLINE
            side.value = "DEFINITION" if state["back"] else "TERM"
            card.bgcolor = C.a(STUDY, 0.18 if state["back"] else 0.1)
            card.scale = 1
            ratings.visible = True
            ui.refresh(card, ratings)

        async def rate(r: str) -> None:
            if self.locked:
                return
            if not state["back"]:  # rating straight from the front: show the answer first
                await flip()
            self.locked = True
            g = self.run.answer(r)  # type: ignore[union-attr]
            await self._feedback(g.correct, card, q, auto=True)

        for r, label, col in RATING_OPTIONS:
            ratings.controls.append(ft.FilledButton(
                label, height=56, expand=True,
                style=ft.ButtonStyle(bgcolor=C.a(col, 0.22), color=C.TEXT,
                                     padding=ft.Padding.symmetric(horizontal=2),
                                     side=ft.BorderSide(1, C.a(col, 0.7)),
                                     shape=ft.RoundedRectangleBorder(radius=Radius.MD)),
                on_click=lambda e, r=r: self.app.page.run_task(rate, r)))

        drag = {"dx": 0.0}

        def drag_start(_: Any) -> None:
            drag["dx"] = 0.0
            card.animate_offset = ui.SNAP

        def dragging(e: ft.DragUpdateEvent) -> None:
            drag["dx"] += float(e.primary_delta or 0)
            card.offset = ft.Offset(max(-0.25, min(0.25, drag["dx"] / 600)), 0)
            ui.refresh(card)

        def swiped(_: ft.DragEndEvent) -> None:
            dx = drag["dx"]
            card.animate_offset = Motion.anim(200, Motion.EASE_CUBIC)
            card.offset = ft.Offset(0, 0)
            ui.refresh(card)
            if abs(dx) >= SWIPE_PX and not self.locked:
                self.app.page.run_task(rate, "good" if dx > 0 else "again")

        gesture = ft.GestureDetector(card, on_tap=lambda e: self.app.page.run_task(flip),
                                     on_horizontal_drag_start=drag_start,
                                     on_horizontal_drag_update=dragging,
                                     on_horizontal_drag_end=swiped)
        self.next_slot = ft.Container()
        return ft.Column([gesture, tap_hint, ratings, self.next_slot], spacing=Space.MD,
                         tight=True)

    async def _feedback(self, ok: bool, target: ft.Control, q: Question, *,
                        auto: bool = False) -> None:
        """Right: chime + pop + medium haptic, moves on by itself. Missed: soft tone + light
        haptic, the right answer stays up until Next (flip ratings always move on)."""
        gen = self.gen
        sfx.play("granted" if ok else "error_soft", 0.8 if ok else 0.6)
        self.app.page.run_task(ui.buzz, "medium" if ok else "light")
        self._paint_header()
        ui.refresh(self.view)
        await ui.pop(target, 1.04 if ok else 0.98)
        if ok or auto:
            await asyncio.sleep(ADVANCE_S if not auto else 0.25)
            if gen == self.gen:
                await self._next()
            return
        self.next_slot.content = ft.Row([_big_button("Next", lambda e: self.app.page.run_task(
            self._next), icon=ft.Icons.ARROW_FORWARD)])
        ui.refresh(self.next_slot)

    async def _next(self) -> None:
        run = self.run
        if run is None or self.done:
            return
        if run.finished:
            await self._finish()
            return
        self._show_question()

    # results
    async def _finish(self) -> None:
        run, app = self.run, self.app
        if run is None or self.done:
            return
        self.done = True
        self.gen += 1
        seconds = int(time.monotonic() - self.started)
        right, total = run.score()
        strong = study.is_strong(right, total)
        deck = app.game.deck(self.deck_id)
        await ui.lumen_analyze(app.page, RESULT_STAGES, seconds=1.8)
        self.header.visible = False
        self.body.content = self._results(run, right, total, seconds, deck)
        await self._slide_in()
        c = await app.award(
            lambda: app.game.finish_study(self.deck_id, self.mode, run.results(), app.today(),
                                          seconds, run.ratings),
            line=lambda c: f"Notice: Study session complete. +{c.xp} XP to "
                           f"{th.path_name(c.path_id)} Path.",
            cleared="Strong score" if strong else None)
        self.xp_line.value = (f"+{c.xp} XP · +{c.coins} coins" if c.coins
                              else f"+{c.xp} XP" if c.xp
                              else f"Progress saved. Sessions of {study.STUDY_MIN_CARDS}+ cards "
                                   "earn XP." if total < study.STUDY_MIN_CARDS
                              else "Progress saved. Today's XP for this deck is earned.")
        ui.refresh(self.xp_line)
        if not c.xp:
            sfx.play("scan_done")
            if strong:
                app.juice(deck.color, None, 0.6)
        with contextlib.suppress(Exception):
            app.update_badges()

    def _results(self, run: StudyRun, right: int, total: int, seconds: int,
                 deck: Any) -> ft.Control:
        pct = right / total if total else 0
        strong = study.is_strong(right, total)
        col = RIGHT_HEX if strong else (STUDY if pct >= 0.5 else MISS)
        by_id = {c.id: c for c in deck.cards}
        missed = [by_id[cid] for cid in run.missed() if cid in by_id]
        verdict = ("Strong score. Those cards move up." if strong
                   else "Good work. Missed cards come back sooner." if pct >= 0.5
                   else "Every miss is a card you'll see again soon. That's how it sticks.")
        if run.timed_out:
            verdict = "Time ran out. " + verdict
        self.xp_line = ft.Text("Saving…", size=Type.LABEL, color=C.PRIMARY,
                               weight=ft.FontWeight.BOLD)
        mins, secs = divmod(seconds, 60)
        head = common.card(ft.Column([
            common.progress_ring(pct, ft.Column([
                ft.Text(f"{round(pct * 100)}%", size=Type.DISPLAY, weight=ft.FontWeight.BOLD,
                        color=C.TEXT),
                ft.Text(f"{right} / {total}", size=Type.LABEL, color=C.TEXT_DIM)],
                spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                color=col),
            ft.Text(verdict, size=Type.BODY, color=C.TEXT, text_align=ft.TextAlign.CENTER),
            ft.Row([ui.chip(f"{mins}:{secs:02d}", icon=ft.Icons.TIMER, color=C.TEXT_DIM),
                    ui.chip({"exam": "Exam", "learn": "Learn", "flip": "Flip cards",
                             "review": "Due review", "weak": "Weak cards"}[self.mode],
                            color=STUDY)],
                   spacing=Space.XS, alignment=ft.MainAxisAlignment.CENTER),
            self.xp_line,
        ], spacing=Space.MD, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=Space.LG, tint=col)
        items: list[ft.Control] = [head]
        if missed:
            items.append(common.section(f"Weak spots ({len(missed)})"))
            items += [common.card(ft.Column([
                ft.Text(c.term, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                ft.Text(c.definition, size=Type.LABEL, color=C.TEXT_DIM)],
                spacing=2, tight=True), padding=Space.MD, tint=MISS) for c in missed[:20]]
            items.append(ft.Row([_big_button(f"Retry missed ({len(missed)})",
                                             lambda e: self._retry([c.id for c in missed]),
                                             icon=ft.Icons.REPLAY, color=MISS)]))
        items.append(ft.Row([
            _big_button("Again", lambda e: self._retry(self.card_ids), icon=ft.Icons.REFRESH,
                        filled=False),
            _big_button("Done", lambda e: self.app.more.back(), icon=ft.Icons.CHECK),
        ], spacing=Space.SM))
        return ft.Column(items, spacing=Space.SM, tight=True, key="results",
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def _retry(self, card_ids: list[str] | None) -> None:
        self.card_ids = list(card_ids) if card_ids else None
        if card_ids:
            self.count = len(card_ids)
            if self.mode in ("exam", "learn", "flip"):
                self.mode = "learn" if self.mode != "flip" else "flip"
        self._start()
        if self.run is None:
            return
        self._show_question()
        if self.run.time_limit_s:
            self.app.page.run_task(self._tick, self.gen)
