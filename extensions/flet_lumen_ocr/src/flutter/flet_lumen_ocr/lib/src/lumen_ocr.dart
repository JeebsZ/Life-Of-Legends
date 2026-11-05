import 'dart:async';
import 'dart:io';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

/// Flet service behind the Python `flet_lumen_ocr.LumenOcr` control.
///
/// Methods (all answer with a Map, never throw to Python):
///   ready()                    -> {ok, error?}
///   recognize(path, timeout_s) -> {ok, error?, text, blocks:[[[line, left, top], ...], ...], ms}
///
/// Only Android and iOS run ML Kit; elsewhere `ok` is false with error "unsupported".
/// One Latin-script TextRecognizer is created per process and shared; calls run one at a
/// time.
class LumenOcrService extends FletService {
  LumenOcrService({required super.control});

  static TextRecognizer? _recognizer;
  static Future<void> _lock = Future<void>.value();

  bool get _supported =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  @override
  void init() {
    super.init();
    debugPrint("LumenOcr(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
  }

  static TextRecognizer _ensureRecognizer() {
    final TextRecognizer? existing = _recognizer;
    if (existing != null) return existing;
    final TextRecognizer created =
        TextRecognizer(script: TextRecognitionScript.latin);
    _recognizer = created;
    return created;
  }

  /// Run [body] after every earlier call finished (one recognition at a time).
  Future<T> _serial<T>(Future<T> Function() body) {
    final Future<T> result = _lock.then((_) => body());
    _lock = result.then((_) {}, onError: (Object _) {});
    return result;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    final Map<dynamic, dynamic> a =
        (args is Map) ? args : const <dynamic, dynamic>{};
    if (!_supported) {
      return <String, dynamic>{"ok": false, "error": "unsupported"};
    }
    switch (name) {
      case "ready":
        try {
          _ensureRecognizer();
          return <String, dynamic>{"ok": true};
        } catch (e) {
          return <String, dynamic>{"ok": false, "error": "init: $e"};
        }
      case "recognize":
        final String path = (a["path"] ?? "").toString();
        final int timeoutS = _int(a["timeout_s"], 25).clamp(1, 120).toInt();
        try {
          return await _serial<Map<String, dynamic>>(() async {
            final Stopwatch sw = Stopwatch()..start();
            if (path.isEmpty || !await File(path).exists()) {
              return <String, dynamic>{"ok": false, "error": "no such file: $path"};
            }
            final TextRecognizer rec = _ensureRecognizer();
            final InputImage input = InputImage.fromFilePath(path);
            final RecognizedText result = await rec
                .processImage(input)
                .timeout(Duration(seconds: timeoutS));
            final List<List<List<Object>>> blocks = <List<List<Object>>>[];
            for (final TextBlock block in result.blocks) {
              final List<List<Object>> lines = <List<Object>>[];
              for (final TextLine line in block.lines) {
                final int left = line.boundingBox.left.round();
                final int top = line.boundingBox.top.round();
                lines.add(<Object>[line.text, left, top]);
              }
              blocks.add(lines);
            }
            return <String, dynamic>{
              "ok": true,
              "text": result.text,
              "blocks": blocks,
              "ms": sw.elapsedMilliseconds,
            };
          });
        } on TimeoutException {
          return <String, dynamic>{"ok": false, "error": "timeout"};
        } catch (e) {
          debugPrint("LumenOcr: recognize failed: $e");
          return <String, dynamic>{"ok": false, "error": e.toString()};
        }
      default:
        return <String, dynamic>{"ok": false, "error": "unknown method: $name"};
    }
  }

  static int _int(dynamic v, int fallback) {
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse(v?.toString() ?? "") ?? fallback;
  }

  @override
  void dispose() {
    debugPrint("LumenOcr(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    // The recognizer stays alive (static) so the next scan does not pay the setup again.
    super.dispose();
  }
}
