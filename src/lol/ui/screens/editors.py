"""Edit sheets shared by the screens: quests (and templates), rewards, bills and side quests.

Draw + wire only: every rule (reward caps, history kept, schedule re-anchoring) lives in Game.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.game import clamp_rewards, reward_limits
from lol.ui import components as ui
from lol.ui import sfx, voice
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

DIFFS = [("1", "Easy"), ("2", "Medium"), ("3", "Hard")]
REPEATS = [("none", "Once"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("yearly", "Yearly")]


# --------------------------------------------------------------------------- quest / template
def quest_form(app: App, sheet_title: str, initial: dict, on_save: Callable[[dict], Any], *,
               save_text: str = "Save", extra: list[ft.Control] | None = None,
               intro: str | None = None) -> ft.BottomSheet:
    """Title, Path, difficulty, kind, note and an optional custom XP/coin reward (sliders capped
    by reward_limits for the difficulty, cap shown). on_save(values) returns False to keep the
    sheet open. values: title, path_id, difficulty, kind, note, xp, coins."""
    st: dict[str, Any] = {
        "path": initial.get("path_id") or "warrior",
        "diff": int(initial.get("difficulty") or 1),
        "kind": initial.get("kind") or "once",
    }
    d0 = st["diff"]
    xp0, coins0 = initial.get("xp"), initial.get("coins")
    st["custom"] = (xp0, coins0) != clamp_rewards(d0, None, None) and xp0 is not None
    st["xp"], st["coins"] = clamp_rewards(d0, xp0, coins0)

    title = common.text_field("Quest title", autofocus=not initial.get("title"))
    title.value = initial.get("title", "")
    title.max_length = 60
    note = common.text_field("Note (optional)")
    note.multiline, note.min_lines, note.max_lines = True, 1, 4
    note.value = initial.get("note", "")
    paths = common.ChoicePills(common.path_options(), st["path"],
                               on_change=lambda v: st.update(path=v))
    kind = common.segmented([("once", "Once"), ("daily", "Daily")], st["kind"],
                            on_change=lambda v: (sfx.play("toggle"), st.update(kind=v)))

    xp_label = ft.Text("", size=Type.LABEL, color=C.TEXT, weight=ft.FontWeight.W_600)
    coin_label = ft.Text("", size=Type.LABEL, color=C.TEXT, weight=ft.FontWeight.W_600)
    xp_slider = ft.Slider(min=0, max=1, value=0, active_color=C.PRIMARY,
                          inactive_color=C.a(C.TEXT, 0.12), expand=True)
    coin_slider = ft.Slider(min=0, max=1, value=0, active_color=C.ACCENT,
                            inactive_color=C.a(C.TEXT, 0.12), expand=True)
    default_hint = common.hint("")
    custom_box = ft.Column([
        ft.Row([ft.Icon(ui.XP_ICON, color=C.PRIMARY, size=18), xp_slider, xp_label],
               spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([ft.Icon(ui.COIN_ICON, color=C.ACCENT, size=18), coin_slider, coin_label],
               spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=0, tight=True, visible=st["custom"])

    def paint_rewards() -> None:
        max_xp, max_coins = reward_limits(st["diff"])
        dxp, dcoins = clamp_rewards(st["diff"], None, None)
        if not st["custom"]:
            st["xp"], st["coins"] = dxp, dcoins
        st["xp"], st["coins"] = min(st["xp"], max_xp), min(st["coins"], max_coins)
        xp_slider.max, xp_slider.divisions = max_xp, max(1, max_xp // 5)
        coin_slider.max, coin_slider.divisions = max_coins, max(1, max_coins)
        xp_slider.value, coin_slider.value = st["xp"], st["coins"]
        xp_label.value = f"{st['xp']} XP · cap {max_xp}"
        coin_label.value = f"{st['coins']} · cap {max_coins}"
        default_hint.value = ("Custom reward, capped for this difficulty." if st["custom"]
                              else f"Default reward: +{dxp} XP, +{dcoins} coins.")
        custom_box.visible = st["custom"]

    def set_diff(v: str) -> None:
        sfx.play("toggle")
        st["diff"] = int(v)
        paint_rewards()
        ui.refresh(custom_box, default_hint)

    def set_custom(on: bool) -> None:
        st["custom"] = on
        paint_rewards()
        ui.refresh(custom_box, default_hint)

    def slide_xp(e: Any) -> None:
        st["xp"] = round(float(e.control.value))
        xp_label.value = f"{st['xp']} XP · cap {reward_limits(st['diff'])[0]}"
        ui.refresh(xp_label)

    def slide_coins(e: Any) -> None:
        st["coins"] = round(float(e.control.value))
        coin_label.value = f"{st['coins']} · cap {reward_limits(st['diff'])[1]}"
        ui.refresh(coin_label)

    xp_slider.on_change = slide_xp
    coin_slider.on_change = slide_coins
    diff = common.segmented(DIFFS, str(st["diff"]), on_change=set_diff)
    paint_rewards()

    def save(_: Any = None) -> None:
        text = (title.value or "").strip()
        if not text:
            sfx.play("error_soft")
            title.error_text = "Give it a short name"
            title.update()
            return
        values = {"title": text, "path_id": st["path"], "difficulty": st["diff"],
                  "kind": st["kind"], "note": (note.value or "").strip(),
                  "xp": st["xp"], "coins": st["coins"]}
        if on_save(values) is False:
            return
        common.close(sheet)

    title.on_submit = save
    body: list[ft.Control] = []
    if intro:
        body.append(common.hint(intro))
    body += [title, common.hint("Path"), paths, common.hint("How often"), kind,
             common.hint("Difficulty"), diff, default_hint,
             common.switch_row("Custom reward", "Set XP and coins yourself (capped)",
                               st["custom"], set_custom),
             custom_box, note,
             ft.Row([common.primary_button(save_text, save, icon=ft.Icons.CHECK)])]
    if extra:
        body += extra
    sheet = common.open_sheet(app.page, sheet_title, body)
    return sheet


def locked_row(items: list[tuple[ft.IconData, str]]) -> ft.Container:
    """Read-only facts that can't change after creation (Path, kind, price, amount...)."""
    chips = [ft.Container(ft.Row([ft.Icon(icon, size=14, color=C.TEXT_DIM),
                                  ft.Text(text, size=Type.CAPTION, color=C.TEXT_DIM,
                                          weight=ft.FontWeight.W_600)],
                                 spacing=4, tight=True),
                          bgcolor=C.a(C.TEXT, 0.06), border_radius=Radius.PILL,
                          padding=ft.Padding.symmetric(horizontal=Space.SM, vertical=4))
             for icon, text in items]
    return ft.Container(ft.Column([
        ft.Row([ft.Icon(ft.Icons.LOCK, size=14, color=C.TEXT_DIM),
                common.hint("Set when it was created")], spacing=4),
        ft.Row(chips, spacing=Space.XS + 2, run_spacing=Space.XS, wrap=True),
    ], spacing=Space.XS, tight=True), padding=ft.Padding.only(bottom=Space.XS))


def edit_quest(app: App, quest_id: str, on_saved: Callable[[], Any]) -> None:
    """v1.3: a quest's name, note and difficulty can change; Path, kind and the reward are
    fixed after creation (a difficulty change sets the default reward for that difficulty)."""
    from lol.ui import theme as th

    g = app.game
    q = g.quest(quest_id)
    st = {"diff": q.difficulty}
    title = common.text_field("Quest title")
    title.value, title.max_length = q.title, 60
    note = common.text_field("Note (optional)")
    note.multiline, note.min_lines, note.max_lines = True, 1, 4
    note.value = q.note
    reward_hint = common.hint("")

    def paint_reward() -> None:
        if st["diff"] == q.difficulty:
            reward_hint.value = f"Reward: +{q.xp} XP, +{q.coins} coins."
        else:
            dxp, dcoins = clamp_rewards(st["diff"], None, None)
            reward_hint.value = f"New reward from now on: +{dxp} XP, +{dcoins} coins."

    def set_diff(v: str) -> None:
        sfx.play("toggle")
        st["diff"] = int(v)
        paint_reward()
        ui.refresh(reward_hint)

    paint_reward()

    def save(_: Any = None) -> None:
        text = (title.value or "").strip()
        if not text:
            sfx.play("error_soft")
            title.error_text = "Give it a short name"
            title.update()
            return
        try:
            g.rename_quest(quest_id, title=text, note=(note.value or "").strip(),
                           difficulty=st["diff"])
        except ValueError as exc:
            app.error(f"Couldn't save: {exc}")
            return
        app.save()
        common.close(sheet)
        on_saved()
        app.toast("Quest updated. History kept.", ft.Icons.EDIT)

    title.on_submit = save
    done = len(q.done_on)
    body: list[ft.Control] = []
    if done:
        body.append(common.hint(f"Done {done} time{'s' if done != 1 else ''}. Past XP and "
                                "coins stay; changes apply from now on."))
    body += [
        title,
        locked_row([(th.path_icon(q.path_id), f"{th.path_name(q.path_id)} Path"),
                    (ft.Icons.EVENT_REPEAT if q.kind == "daily" else ft.Icons.LOOKS_ONE,
                     "Daily" if q.kind == "daily" else "Once")]),
        common.hint("Difficulty"), common.segmented(DIFFS, str(q.difficulty), on_change=set_diff),
        reward_hint, note,
        ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
    ]
    sheet = common.open_sheet(app.page, "Edit quest", body)


def save_as_template(app: App, quest_id: str) -> None:
    t = app.game.template_from_quest(quest_id)
    app.save()
    sfx.play("tap")
    app.toast(f"Saved as template: {t.title}", ft.Icons.BOOKMARK_ADD)


# --------------------------------------------------------------------------- rewards
def edit_reward(app: App, reward_id: str, on_saved: Callable[[], Any]) -> None:
    """v1.3: name and note only - the price is fixed once created."""
    g = app.game
    r = g.reward(reward_id)
    title = common.text_field("Reward name")
    title.value = r.title
    note = common.text_field("Note (optional)")
    note.multiline, note.min_lines, note.max_lines = True, 1, 4
    note.value = r.note

    def save(_: Any = None) -> None:
        text = (title.value or "").strip()
        title.error_text = None if text else "Name your reward"
        if not text:
            sfx.play("error_soft")
            ui.refresh(title)
            return
        g.rename_reward(reward_id, title=text, note=(note.value or "").strip())
        app.save()
        common.close(sheet)
        on_saved()
        app.toast("Reward updated", ft.Icons.CARD_GIFTCARD)

    async def archive(_: Any = None) -> None:
        g.archive_reward(reward_id)
        app.save()
        common.close(sheet)
        on_saved()
        app.toast(f"{r.title} archived. Restore it from Archived.", ft.Icons.ARCHIVE)

    async def delete(_: Any = None) -> None:
        common.close(sheet)
        msg = ("It was redeemed before, so it is archived with its history instead."
               if r.redeemed else "It leaves your shop. Your coins stay.")
        if not await common.confirm(app.page, f"Remove {r.title}?", msg, "Remove",
                                    danger=True):
            return
        g.delete_reward(reward_id)
        app.save()
        on_saved()
        app.toast("Reward archived" if r.redeemed else "Reward removed", ft.Icons.DELETE_OUTLINE)

    hist = (f"Redeemed {len(r.redeemed)} time{'s' if len(r.redeemed) != 1 else ''}. "
            "Past redemptions keep the price you paid.") if r.redeemed else \
        "A treat you promise yourself. Not a real coupon."
    sheet = common.open_sheet(app.page, "Edit reward", [
        common.hint(hist), title,
        locked_row([(ui.COIN_ICON, f"{r.cost:,} coins")]), note,
        ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ft.Row([common.secondary_button("Archive", archive, icon=ft.Icons.ARCHIVE),
                common.secondary_button("Remove", delete, icon=ft.Icons.DELETE_OUTLINE,
                                        color=C.DANGER)], spacing=Space.SM),
    ])


# --------------------------------------------------------------------------- bills
def edit_bill(app: App, bill_id: str, on_saved: Callable[[], Any]) -> None:
    """v1.3: name, note and paid / unpaid only. Amount, due date and repeat are fixed."""
    g, today = app.game, app.today()
    b = g.bill(bill_id)
    status = g.bill_status(b, today)
    name = common.text_field("Bill name")
    name.value = b.name
    note = common.text_field("Note (optional)")
    note.multiline, note.min_lines, note.max_lines = True, 1, 4
    note.value = b.note

    def keep_text() -> bool:
        n = (name.value or "").strip()
        name.error_text = None if n else "Give it a name"
        if not n:
            sfx.play("error_soft")
            ui.refresh(name)
            return False
        g.update_bill(bill_id, name=n, note=(note.value or "").strip())
        return True

    def save(_: Any = None) -> None:
        if not keep_text():
            return
        app.save()
        common.close(sheet)
        on_saved()
        app.toast(f"{b.name} updated", ft.Icons.RECEIPT_LONG)

    async def mark_paid(_: Any = None) -> None:
        if not keep_text():
            return
        common.close(sheet)
        c = await app.award(lambda: g.mark_bill_paid(bill_id, today),
                            line=lambda c: voice.say("bill_paid", bill=b.name, xp=c.xp))
        if not (c.xp or c.coins):
            app.lumen("bill_marked", ft.Icons.TASK_ALT, bill=b.name)
        app.update_badges()
        on_saved()

    def mark_unpaid(_: Any = None) -> None:
        if not keep_text():
            return
        if g.mark_bill_unpaid(bill_id):
            app.save()
            app.toast(f"{b.name}: last payment undone. Earned XP stays.", ft.Icons.UNDO)
        else:
            app.error("Nothing paid yet")
        common.close(sheet)
        app.update_badges()
        on_saved()

    async def archive(_: Any = None) -> None:
        common.close(sheet)
        if not await common.confirm(
                app.page, f"Archive {b.name}?",
                "It stops showing in Bills, totals and the calendar, and no more due "
                "reminders. Payment history is kept and you can restore it.", "Archive"):
            return
        g.archive_bill(bill_id)
        app.save()
        app.update_badges()
        on_saved()
        app.toast(f"{b.name} archived", ft.Icons.ARCHIVE)

    async def delete(_: Any = None) -> None:
        common.close(sheet)
        if not await common.confirm(
                app.page, f"Delete {b.name}?",
                "This removes the bill, all future due reminders and its payment history "
                "for good. Steward XP you earned stays. (Archive keeps the history.)",
                "Delete", danger=True):
            return
        g.delete_bill(bill_id)
        app.save()
        app.update_badges()
        on_saved()
        app.toast("Bill deleted", ft.Icons.DELETE_OUTLINE)

    paid = len(b.paid)
    repeat = dict(REPEATS).get(b.repeat, "Once")
    due = g.next_due(b)
    pay_buttons: list[ft.Control] = []
    if status != "paid":
        pay_buttons.append(common.secondary_button("Mark paid", mark_paid,
                                                   icon=ft.Icons.TASK_ALT, color=C.SUCCESS))
    if paid:
        pay_buttons.append(common.secondary_button("Mark unpaid", mark_unpaid,
                                                   icon=ft.Icons.UNDO, color=C.TEXT_DIM))
    sheet = common.open_sheet(app.page, "Edit bill", [
        common.hint(f"Paid {paid} time{'s' if paid != 1 else ''}. Payment history is kept."
                    if paid else "Not paid yet."),
        name,
        locked_row([(ft.Icons.PAYMENTS, ui.peso(b.amount)),
                    (ft.Icons.EVENT, f"Next due {common.short_date(due)}"),
                    (ft.Icons.REPEAT, repeat)]),
        note,
        ft.Row(pay_buttons, spacing=Space.SM),
        ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ft.Row([common.secondary_button("Archive", archive, icon=ft.Icons.ARCHIVE),
                common.secondary_button("Delete", delete, icon=ft.Icons.DELETE_OUTLINE,
                                        color=C.DANGER)], spacing=Space.SM),
    ])


# --------------------------------------------------------------------------- side quests
def manage_side_quest(app: App, sq_id: str, on_changed: Callable[[], Any],
                      on_set_aside: Callable[[], Any]) -> None:
    """Ordered toggle, target date, pause/resume, reorder (up/down), edit and skip steps."""
    g, today = app.game, app.today()
    sq = g.side_quest(sq_id)
    steps_col = ft.Column(spacing=Space.XS, tight=True)
    fields: list[ft.TextField] = []
    pause_btn = ft.Container(expand=True)

    def changed() -> None:
        app.save()
        on_changed()

    def paint_steps() -> None:
        nonlocal fields
        fields = []
        rows: list[ft.Control] = []
        n = len(sq.steps)
        for i, s in enumerate(sq.steps):
            f = common.text_field(f"Step {i + 1}")
            f.value = s.title
            f.max_length = 60
            f.disabled = bool(s.done_on)
            fields.append(f)
            state = ("Done" if s.done_on else "Skipped" if s.skipped_on else "")
            tools: list[ft.Control] = [
                ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18, width=40, height=40,
                              tooltip="Move up", disabled=i == 0,
                              on_click=lambda e, k=i: move(k, -1)),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18, width=40, height=40,
                              tooltip="Move down", disabled=i == n - 1,
                              on_click=lambda e, k=i: move(k, 1)),
            ]
            if s.skipped_on and not sq.finished:
                tools.append(ft.TextButton("Unskip", on_click=lambda e, k=i: unskip(k),
                                           height=40))
            elif not s.resolved:
                tools.append(ft.TextButton("Skip", icon=ft.Icons.SKIP_NEXT, height=40,
                                           on_click=lambda e, k=i: app.page.run_task(skip, k)))
            rows.append(ft.Container(ft.Column([
                f,
                ft.Row([common.hint(state) if state else ft.Container(),
                        ft.Container(expand=True), *tools], spacing=0,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=0, tight=True), bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
                padding=ft.Padding.only(left=Space.SM, right=Space.XS, top=Space.SM)))
        steps_col.controls = rows

    def move(i: int, d: int) -> None:
        sfx.play("tap")
        j = i + d
        order = list(range(len(sq.steps)))
        order[i], order[j] = order[j], order[i]
        keep_titles()
        g.reorder_steps(sq_id, order)
        changed()
        paint_steps()
        ui.refresh(steps_col)

    def keep_titles() -> None:
        """Apply typed step titles before a reorder repaints the fields."""
        for k, f in enumerate(fields):
            t = (f.value or "").strip()
            if t and t != sq.steps[k].title and not sq.steps[k].done_on:
                g.edit_step(sq_id, k, title=t)

    async def skip(i: int) -> None:
        sfx.play("tap")
        keep_titles()
        c = g.skip_step(sq_id, i, today)
        app.save()
        paint_steps()
        ui.refresh(steps_col)
        on_changed()
        app.toast("Step skipped. No XP for it, and that's fine.", ft.Icons.SKIP_NEXT)
        if c.skill_unlocked:
            common.close(sheet)
            await app.skill_banner(c.skill_unlocked, c.skill_rank or 1, sq.path_id)

    def unskip(i: int) -> None:
        sfx.play("tap")
        g.unskip_step(sq_id, i)
        changed()
        paint_steps()
        ui.refresh(steps_col)

    def set_ordered(on: bool) -> None:
        g.edit_side_quest(sq_id, ordered=on)
        changed()

    def set_target(d: date | None) -> None:
        g.edit_side_quest(sq_id, target_date=d)
        changed()

    def paint_pause() -> None:
        label = "Resume chain" if sq.paused else "Pause chain"
        pause_btn.content = common.secondary_button(
            label, toggle_pause, icon=ft.Icons.PLAY_ARROW if sq.paused else ft.Icons.PAUSE)

    def toggle_pause(_: Any = None) -> None:
        if sq.paused:
            g.resume_side_quest(sq_id)
            app.toast(f"{sq.skill_name} resumed", ft.Icons.PLAY_ARROW)
        else:
            g.pause_side_quest(sq_id)
            app.toast(f"{sq.skill_name} paused. Earned XP stays.", ft.Icons.PAUSE)
        changed()
        paint_pause()
        ui.refresh(pause_btn)

    def save(_: Any = None) -> None:
        for k, f in enumerate(fields):
            t = (f.value or "").strip()
            if not t:
                sfx.play("error_soft")
                f.error_text = "A step needs a title"
                f.update()
                return
            if not sq.steps[k].done_on and t != sq.steps[k].title:
                g.edit_step(sq_id, k, title=t)
        changed()
        common.close(sheet)
        app.toast("Chain updated", ft.Icons.ROUTE)

    async def set_aside(_: Any = None) -> None:
        common.close(sheet)
        await on_set_aside()

    paint_steps()
    paint_pause()
    target = date.fromisoformat(sq.target_date) if sq.target_date else None
    sheet = common.open_sheet(app.page, sq.skill_name, [
        common.switch_row("Steps in order", "Only the next step can be completed",
                          sq.ordered, set_ordered, icon=ft.Icons.FORMAT_LIST_NUMBERED),
        common.date_row(app.page, "Target", target, today, set_target, clearable=True,
                        help_text="A soft goal, never a penalty"),
        common.hint("Steps: rename, move or skip. Skipped steps give no XP."),
        steps_col,
        ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ft.Row([pause_btn, common.secondary_button("Set aside", set_aside,
                                                   icon=ft.Icons.BEDTIME, color=C.TEXT_DIM)],
               spacing=Space.SM),
    ])


def quest_menu(app: App, quest_id: str, *, on_edited, on_delete=None) -> ft.PopupMenuButton:
    """The dots menu on a quest card: edit, save as template, focus on it (+ remove)."""
    items: list[tuple] = [
        ("Edit", ft.Icons.EDIT, lambda: edit_quest(app, quest_id, on_edited)),
        ("Save as template", ft.Icons.BOOKMARK_ADD,
         lambda: save_as_template(app, quest_id)),
        ("Focus on this", ft.Icons.TIMER, lambda: app.open_sub("focus", quest_id=quest_id)),
    ]
    if on_delete is not None:
        items.append(("Remove", ft.Icons.DELETE_OUTLINE, on_delete, True))
    return common.menu_button(items, tooltip="Quest options")
