import 'package:audioplayers/audioplayers.dart';
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'lumen_notify.dart';

class Extension extends FletExtension {
  /// Runs once from the generated main.dart, before runApp() and long before Python creates
  /// any flet_audio.Audio. See README "Audio focus" for why.
  @override
  void ensureInitialized() {
    _mixAudio();
  }

  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "LumenNotify":
        return LumenNotifyService(control: control);
      default:
        return null;
    }
  }
}

/// Make every audioplayers player (all flet_audio.Audio services: Lumen's voice and the SFX)
/// play WITHOUT requesting audio focus, so a sound effect starting no longer makes Android
/// stop/pause Lumen's voice (AUDIOFOCUS_LOSS -> FocusManager.onLoss).
///
/// audioplayers_android copies its global ("default") context into each player when the
/// player is created (AudioplayersPlugin "create": defaultAudioContext.copy()), so this must
/// land before the first AudioPlayer exists; players created earlier keep AUDIOFOCUS_GAIN.
void _mixAudio() {
  if (kIsWeb) return;
  final platform = defaultTargetPlatform;
  if (platform != TargetPlatform.android && platform != TargetPlatform.iOS) return;
  try {
    WidgetsFlutterBinding.ensureInitialized(); // idempotent; method channels need it
    // Android: usage MEDIA, audioFocus NONE. iOS: category playback + mixWithOthers.
    final ctx = AudioContextConfig(focus: AudioContextConfigFocus.mixWithOthers).build();
    AudioPlayer.global.setAudioContext(ctx).catchError((Object e) {
      debugPrint("flet_lumen_notify: setAudioContext failed: $e");
    });
  } catch (e) {
    debugPrint("flet_lumen_notify: audio context not set: $e");
  }
}
