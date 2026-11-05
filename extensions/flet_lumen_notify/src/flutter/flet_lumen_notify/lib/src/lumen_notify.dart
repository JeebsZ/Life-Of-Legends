import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/timezone.dart' as tz;

/// Flet service behind the Python `flet_lumen_notify.LumenNotify` control.
///
/// Python calls methods via `_invoke_method(name, args)`; every method is
/// answered from [_invokeMethod]. Only Android is really supported; on other
/// platforms every method is a harmless no-op that returns `null`.
///
/// Scheduling uses absolute instants: Python sends a local ISO date-time
/// ("2026-11-05T09:00:00"), Dart parses it in the device's local time zone and
/// converts it to a UTC `TZDateTime`. That avoids loading the time zone
/// database or detecting the device zone (no `flutter_timezone` needed). The
/// trade-off: a reminder keeps its absolute instant if the device zone changes
/// later; the app re-syncs reminders on every launch anyway.
class LumenNotifyService extends FletService {
  LumenNotifyService({required super.control});

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static Future<bool>? _initFuture;

  String _channelId = "lumen";
  String _channelName = "Lumen";
  String _channelDescription = "Reminders from Lumen";

  bool get _supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void init() {
    super.init();
    debugPrint("LumenNotify(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
  }

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();

  Future<bool> _ensureInit({String? icon}) {
    return _initFuture ??= () async {
      final ok = await _plugin.initialize(
        settings: InitializationSettings(
          android: AndroidInitializationSettings(icon ?? "@mipmap/ic_launcher"),
        ),
      );
      await _android?.createNotificationChannel(AndroidNotificationChannel(
        _channelId,
        _channelName,
        description: _channelDescription,
        importance: Importance.high,
      ));
      return ok ?? false;
    }();
  }

  /// Picked notification sounds: res/raw/notify_01..08.ogg in this package's Android
  /// module (merged into the app). A channel's sound can't change once it exists, so every
  /// sound gets its own channel "<channel>_<sound>"; no/unknown sound = the base channel
  /// with the system default sound.
  static final RegExp _soundName = RegExp(r"^notify_0[1-8]$");
  final Set<String> _soundChannels = {};

  String? _sound(dynamic v) {
    final s = v?.toString();
    return (s != null && _soundName.hasMatch(s)) ? s : null;
  }

  Future<void> _ensureSoundChannel(String? sound) async {
    if (sound == null || _soundChannels.contains(sound)) return;
    await _android?.createNotificationChannel(AndroidNotificationChannel(
      "${_channelId}_$sound",
      "$_channelName (${sound.replaceAll("_", " ")})",
      description: _channelDescription,
      importance: Importance.high,
      playSound: true,
      sound: RawResourceAndroidNotificationSound(sound),
    ));
    _soundChannels.add(sound);
  }

  AndroidNotificationDetails _details(String? sound) => AndroidNotificationDetails(
        sound == null ? _channelId : "${_channelId}_$sound",
        sound == null
            ? _channelName
            : "$_channelName (${sound.replaceAll("_", " ")})",
        channelDescription: _channelDescription,
        importance: Importance.high,
        priority: Priority.high,
        category: AndroidNotificationCategory.reminder,
        playSound: true,
        sound: sound == null ? null : RawResourceAndroidNotificationSound(sound),
      );

  Future<NotificationDetails> _notificationDetails(dynamic soundArg) async {
    final sound = _sound(soundArg);
    await _ensureSoundChannel(sound);
    return NotificationDetails(android: _details(sound));
  }

  int _id(dynamic v) {
    if (v is int) return v;
    return int.parse(v.toString());
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("LumenNotify.$name($args)");
    if (!_supported) return null;
    final a = (args is Map) ? args : const {};
    switch (name) {
      case "init":
        _channelId = (a["channel_id"] ?? _channelId).toString();
        _channelName = (a["channel_name"] ?? _channelName).toString();
        _channelDescription =
            (a["channel_description"] ?? _channelDescription).toString();
        return await _ensureInit(icon: a["icon"]?.toString());
      case "request_permission":
        await _ensureInit();
        return await _android?.requestNotificationsPermission();
      case "are_enabled":
        await _ensureInit();
        return await _android?.areNotificationsEnabled();
      case "open_settings":
        await _ensureInit();
        return await _android?.openAppNotificationSettings();
      case "show":
        await _ensureInit();
        await _plugin.show(
          id: _id(a["id"]),
          title: a["title"]?.toString(),
          body: a["body"]?.toString(),
          notificationDetails: await _notificationDetails(a["sound"]),
          payload: a["payload"]?.toString(),
        );
        return true;
      case "schedule":
        await _ensureInit();
        final local = DateTime.parse(a["when"].toString());
        final when = tz.TZDateTime.from(local, tz.UTC);
        if (!when.isAfter(tz.TZDateTime.now(tz.UTC))) {
          return false; // in the past: the plugin would throw
        }
        await _plugin.zonedSchedule(
          id: _id(a["id"]),
          title: a["title"]?.toString(),
          body: a["body"]?.toString(),
          scheduledDate: when,
          notificationDetails: await _notificationDetails(a["sound"]),
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          payload: a["payload"]?.toString(),
        );
        return true;
      case "cancel":
        await _ensureInit();
        await _plugin.cancel(id: _id(a["id"]));
        return true;
      case "cancel_all":
        await _ensureInit();
        await _plugin.cancelAll();
        return true;
      case "pending":
        await _ensureInit();
        final reqs = await _plugin.pendingNotificationRequests();
        return reqs
            .map((r) => {
                  "id": r.id,
                  "title": r.title,
                  "body": r.body,
                  "payload": r.payload,
                })
            .toList();
      default:
        throw Exception("Unknown LumenNotify method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("LumenNotify(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
