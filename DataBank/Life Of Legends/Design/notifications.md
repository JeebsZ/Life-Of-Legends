# Notifications: how they work

Built 4 Nov 2026 for the v1.3 spec's Notifications section. Engineering details are in
`extensions/flet_lumen_notify/README.md`.

## In one paragraph
Reminders are **local notifications scheduled on the phone**. There's no server and they work
offline. The app works out the upcoming reminders (bills, daily quest, water, focus timer and
so on) and hands them to `lol.ui.notify.sync()`. That function schedules the next 50 with
Android and cancels any that no longer apply. Android then shows each one at about the right
time, even if the app is closed.

## Pieces
- **`flet_lumen_notify`** is our own Flet extension in `extensions/flet_lumen_notify`. It wraps
  the Flutter plugin `flutter_local_notifications`. The user approved this on 4 Nov.
- **`flet-permission-handler`** is the official Flet package. It handles the Android 13+
  "Allow notifications?" prompt.
- **`src/lol/ui/notify.py`** is the only part the app talks to:
  - `init(page)` runs once at startup.
  - `ensure_permission()` asks the user once if needed. It returns False when the user has
    refused; offer `open_settings()` in that case.
  - `sync(reminders)` takes objects with `id`, `when`, `title`, `body` and `category`.
  - `test_now()` shows a test notification immediately. `test_in(60)` schedules one for a
    minute from now.
  - `cancel_all()` is for the master toggle.
  - Every function quietly does nothing on PC, web and iOS.
- Each reminder's text id becomes a **stable number** through a hash, so syncing again replaces
  a reminder instead of creating a duplicate.

## Permissions (Android)
- **POST_NOTIFICATIONS:** Android 13+ asks the user. Older versions allow notifications by
  default.
- **RECEIVE_BOOT_COMPLETED:** lets the app re-arm reminders after a reboot.
- **VIBRATE**
- We do **not** use exact alarms (SCHEDULE_EXACT_ALARM), so no extra scary permission is needed.

## Limits to tell the user about
- **Timing is approximate.** A reminder can arrive a few minutes late. That's the price of not
  using exact alarms. Some phones' battery savers delay or block reminders unless the app is
  allowed to run in the background.
- **Reboot:** reminders come back after a restart, once the phone has been unlocked. If the user
  **force-stops** the app, Android drops its reminders until the app is opened again.
- **Open the app now and then.** Only the next 50 reminders are queued, and opening the app tops
  the queue up.
- **The app now needs Android 8.0 or newer** (minSdk 26). This was needed to build the
  notification plugin under `flet build`.
- **iOS** is not covered.
- The status-bar icon uses the app icon, so it may show as a plain white shape.

## Fallback
Export reminders as an **.ics calendar file** and import it into the phone's calendar. This
gives exact, server-free alerts on any device, including iOS. It's not built yet.

## Phone test checklist
1. Install `build/apk/lifeoflegends-arm64-v8a.apk`.
2. Trigger `notify.test_now()`, for example from a Settings button. Allow the prompt. A
   "Luma" notification should appear.
3. Trigger `notify.test_in(60)`, then lock the phone. The notification should arrive within a
   few minutes.
4. Schedule a reminder about 10 minutes ahead with `sync`, then reboot. Unlock the phone. It
   should still fire.
5. Deny the permission (or turn it off in system settings). `ensure_permission()` should return
   False, and `open_settings()` should open the app's notification page.
