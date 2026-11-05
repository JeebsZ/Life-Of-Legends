# flet_lumen_notify

Life of Legends' own Flet 1.x extension for **local phone notifications**. It wraps the
Flutter plugin [`flutter_local_notifications`](https://pub.dev/packages/flutter_local_notifications)
(22.x) and its `timezone` dependency. Android only. Nothing is sent to a server.

App code should not use this package directly. Use `src/lol/ui/notify.py`
(`init` / `ensure_permission` / `sync` / `test_now`), which adds stable ids,
permission handling and no-op behavior on web, desktop and iOS.

## Layout

```
extensions/flet_lumen_notify/
  pyproject.toml                    setuptools; ships src/flutter/** as package data
  src/flet_lumen_notify/            Python side: LumenNotify(ft.Service)
  src/flutter/flet_lumen_notify/    Flutter side (copied into the app by `flet build`)
    pubspec.yaml                    flutter_local_notifications ^22.3.3, timezone ^0.11.0,
                                    audioplayers (already in the app via flet_audio), flet
    lib/flet_lumen_notify.dart      exports Extension
    lib/src/extension.dart          FletExtension -> creates the "LumenNotify" service; its
                                    ensureInitialized() sets the global audio context
    lib/src/lumen_notify.dart       FletService: answers Python method calls
    android/                        tiny Android plugin module (see "Why an Android module")
```

It follows the same pattern as `flet_audio`. The Python class is `@ft.control("LumenNotify")`
and subclasses `ft.Service`. Each method calls `self._invoke_method(name, args)`. On the Dart
side, `LumenNotifyService` registers `control.addInvokeMethodListener` and handles each name in
a `switch`.

## Python API (`flet_lumen_notify.LumenNotify`, all async)

| method | what it does |
|---|---|
| `init(channel_id="lumen", channel_name="Lumen", channel_description=..., icon=None)` | Initializes the plugin and creates the channel. The small icon defaults to `@mipmap/ic_launcher`. Only the first call has any effect. |
| `request_permission()` | Asks for POST_NOTIFICATIONS on Android 13+ and returns True if notifications are allowed. |
| `are_enabled()` | Says whether notifications are currently allowed. It never shows a prompt. |
| `open_settings()` | Opens the system notification settings for the app. |
| `show(id, title, body, payload=None)` | Posts a notification immediately. |
| `schedule(id, when_iso_local, title, body, payload=None)` | Schedules a one-shot notification. Accepts an ISO string or a `datetime`. Returns False if the time is already past. |
| `cancel(id)` / `cancel_all()` | Cancels scheduled and shown notifications. |
| `pending()` | Lists scheduled notifications that have not fired yet, as `[{id, title, body, payload}]`. |

Ids are signed 32-bit Android notification ids.

**Time handling.** Python sends a local ISO date-time such as `2026-11-05T09:00:00`. Dart parses
it with `DateTime.parse`, so a string without an offset is read in the phone's own time zone.
Dart then converts it to a UTC `TZDateTime` and calls `zonedSchedule`. Because of this we don't
load the tz database or detect the device zone, and we don't need `flutter_timezone`. One
consequence: if the phone's time zone changes after scheduling, the reminder still fires at the
original instant. The app re-syncs on launch.

**Schedule mode.** `AndroidScheduleMode.inexactAllowWhileIdle`. This needs no SCHEDULE_EXACT_ALARM
or USE_EXACT_ALARM permission, and the reminder still fires in Doze. The cost is that Android may
deliver it a few minutes late. Delays of up to roughly 15 minutes are possible in deep Doze or
on aggressive OEM battery savers.

## Notification sounds (Settings picker)

`show(..., sound=)` and `schedule(..., sound=)` take `"notify_01"`..`"notify_08"` (or None for
the system default). The 8 files live in `android/src/main/res/raw/notify_0N.ogg` (copied there
by `tools/sfx/encode_ogg.py` from the app's normalized notification sounds) and are merged
into the app as raw resources; `res/raw/keep.xml` stops resource shrinking from removing them,
since they are only looked up by name. An Android channel's sound can't change once the
channel exists, so each sound gets its own channel `lumen_notify_0N` ("Lumen (notify 0N)"),
created on first use; no sound = the base `lumen` channel. `notify.py` reads the profile's
`notify_sound` and re-schedules pending reminders when it changes. Old channels stay listed in
the phone's app notification settings (harmless). Not verified on a device yet.

## Audio focus (Lumen's voice no longer cut off)

**Bug.** On Android, Lumen's voice clip stopped as soon as a sound effect started. Every
`flet_audio.Audio` is an audioplayers `AudioPlayer`, and audioplayers' default Android context
asks for `AUDIOFOCUS_GAIN` on every play. Inside one app, each player is a separate focus
holder. So the effect's player took focus, the voice player got `AUDIOFOCUS_LOSS`, and
`FocusManager.onLoss` stopped it (audioplayers_android 5.3.0, `player/FocusManager.kt`).

**Fix.** `Extension.ensureInitialized()` (in `lib/src/extension.dart`) sets audioplayers'
**global** audio context on Android and iOS:

```dart
AudioPlayer.global.setAudioContext(
    AudioContextConfig(focus: AudioContextConfigFocus.mixWithOthers).build());
```

- On Android this gives usage `MEDIA` and `audioFocus = AUDIOFOCUS_NONE`. A player with no
  focus request is "granted" at once and never gets a loss callback, so the voice and the
  effects mix. `mixer.py` still sequences and ducks them.
- On iOS the category is `playback` with the `mixWithOthers` option.

**Why it has to run first.** audioplayers_android copies its global context into a player
**when the player is created** (`AudioplayersPlugin` "create" → `defaultAudioContext.copy()`).
A later `setAudioContext` call doesn't change players that already exist. Flet's generated
`main.dart` calls `ext.ensureInitialized()` for every extension before `runApp()`. That is
long before Python boots and creates its `Audio` services, so all of them pick up the new
context. Running it first is also what makes the call safe: `GlobalAudioScope.ensureInitialized()`
sends the one-time `init`, which disposes existing players, and at this point there are none.

**Side effect.** The app's sounds no longer pause or duck music playing in other apps. They
play on top of it.

**Dependency.** `audioplayers: ">=6.6.0 <7.0.0"` in `pubspec.yaml`. flet_audio already pulls
this package into the app (`^6.6.0`, resolved to 6.8.1), so nothing new is downloaded.

**Not verified on a device yet.** Check on the phone: complete a quest, and Lumen's line should
play to the end while `coin` and `xp_fill` sound. If any player gets created before
`ensureInitialized()` in some future Flet version, it will keep `AUDIOFOCUS_GAIN`. The fallback
then would be a `LumenNotify` method that the voice player calls before it is created.

## Wiring (in the app's pyproject.toml)

```toml
[tool.flet.android]
dependencies = ["flet-lumen-notify"]          # Android builds only; not on PyPI

[tool.flet.dev_packages]
flet-lumen-notify = "extensions/flet_lumen_notify"   # relative to the project root

[tool.flet.android.permission]
"android.permission.POST_NOTIFICATIONS" = true
"android.permission.RECEIVE_BOOT_COMPLETED" = true
"android.permission.VIBRATE" = true
```

During `flet build apk`, serious_python pip-installs `flet-lumen-notify @ file:///.../extensions/flet_lumen_notify`.
It then copies the wheel's `flutter/flet_lumen_notify/` into `build/flutter-packages/` and adds it
to the generated app's `pubspec.yaml` as a path dependency. With dev_packages set, the package
step runs again on every build (`--no-cache-dir`), so edits to the extension are always picked up.

`flet-permission-handler` is an ordinary dependency in `[project].dependencies`.
`notify.ensure_permission()` uses it to check and request the permission, and it can tell
"permanently denied" apart from "denied". If it's missing, `notify` falls back to
`LumenNotify.request_permission()`.

## Why an Android module

`flutter_local_notifications` needs three `<receiver>` entries in the app manifest for
scheduled, boot and action broadcasts, and it doesn't declare them itself. `flet build` has
settings for permissions, features, meta-data and providers, but none for receivers. So
`pubspec.yaml` declares this package as an Android plugin with a no-op Java class
(`FletLumenNotifyPlugin`). Gradle's manifest merger then merges
`android/src/main/AndroidManifest.xml` into the app. That file holds the receivers plus
RECEIVE_BOOT_COMPLETED, VIBRATE and POST_NOTIFICATIONS.

The same module also takes care of **core library desugaring**. See "Build notes" below.

## Build notes (Flet 1.0.5, Flutter 3.44.8, AGP 8.11.1; verified 4 Nov 2026)

`flet build apk --split-per-abi` succeeds. The APK contains:

- `minSdk 26`
- POST_NOTIFICATIONS, RECEIVE_BOOT_COMPLETED and VIBRATE
- the three `com.dexterous.flutterlocalnotifications.*` receivers
- `flet_lumen_notify.Extension()` and `flet_permission_handler.Extension()` in
  `lib/flet_generated.dart`
- flutter_local_notifications 22.3.3 and timezone 0.11.2

Problems hit and how each was solved:

1. **Receivers missing from the manifest.** `flet build` has no setting for receivers. Fix: an
   Android plugin module whose manifest gets merged into the app (see above).
2. **Core library desugaring.** flutter_local_notifications enables desugaring in its own
   module. AGP's `checkAarMetadata` then requires the app to enable it as well, and the
   generated `app/build.gradle.kts` has no setting for that. The template's root build also
   configures `:app` before every plugin (`evaluationDependsOn(":app")`), so a plugin can't
   change the app's DSL. Fix: `android/build.gradle` registers an `afterEvaluate` hook on
   `:flutter_local_notifications`. Gradle configures `:flet_lumen_notify` first because it sorts
   first by path, so the hook runs before AGP finalizes that module's DSL. The hook sets
   `coreLibraryDesugaringEnabled = false`. In the build output,
   `build/flutter/build/flutter_local_notifications/.../aar-metadata.properties` reads
   `coreLibraryDesugaringEnabled=false`. This is only safe because the app sets
   **`min_sdk_version = 26`** (Android 8.0), where `java.time` is part of the OS. Do not lower
   minSdk below 26 while this workaround is in place.
3. **"Building with plugins requires symlink support. Please enable Developer Mode".** The first
   build failed at `flutter pub get`, while Flutter was creating `windows/.../.plugin_symlinks`
   for the newly added plugins. On this machine, `mklink /D` fails with "insufficient
   privilege" and the Developer Mode registry key `AppModelUnlock` was not found. The next
   build passed without any change for this problem, because the plugin list had already been
   refreshed. If it comes back, turn on Windows Developer Mode
   (Settings > System > For developers). Deleting `build/flutter/windows` and
   `build/flutter/linux` also works for an APK build, but only until the template is
   rendered again.

If a future flutter_local_notifications release changes how it handles desugaring, check
`aar-metadata.properties` again. If a future `flet build` adds an app-level desugaring switch,
use that and drop the hook.

## Limits

- **Inexact timing.** A reminder can arrive a few minutes late. Battery savers on some phones
  (Xiaomi, Huawei, Samsung "deep sleep") can delay it further or block it unless the app is
  exempt.
- **Reboot.** Scheduled reminders are saved by the plugin, and its boot receiver re-arms them
  after a reboot or app update. The phone has to be unlocked once after a reboot first. If the
  user force-stops the app, Android cancels its alarms until the app is opened again.
- **Queue size.** `notify.sync` keeps at most 50 future reminders scheduled. The app needs to be
  opened from time to time (it re-syncs on launch) to schedule reminders further out.
- **iOS** is not covered: no Darwin settings and no Info.plist work. Web and desktop are no-ops.
- **Small icon** is the launcher mipmap. Android draws the small icon from the alpha channel
  only, so a full-colour square icon shows as a white or grey blob in the status bar. A
  monochrome `ic_stat_lumen` drawable would need a way to add Android resources, which
  `flet build` does not offer yet.
