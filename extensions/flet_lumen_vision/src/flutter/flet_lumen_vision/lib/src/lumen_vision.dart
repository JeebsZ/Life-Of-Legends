import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:tflite_flutter/tflite_flutter.dart';

const _modelAsset = "packages/flet_lumen_vision/assets/food_v1.tflite";
const _labelsAsset = "packages/flet_lumen_vision/assets/food_v1_labels.txt";

/// Flet service behind the Python `flet_lumen_vision.LumenVision` control.
///
/// Methods (all answer with a Map, never throw to Python):
///   ready()                       -> {ok, error?, labels, input:[h,w], input_type, output_type, load_ms}
///   classify(path, top_k, timeout_s)
///                                 -> {ok, error?, top:[[label, score, index], ...], ms}
///
/// Only Android and iOS run the model; elsewhere `ok` is false with error "unsupported".
/// The model (Google AIY food_V1, MobileNet V1, uint8-quantized, 192x192x3 in, 2024 softmax
/// probabilities out) is loaded once per process and shared by every service instance.
class LumenVisionService extends FletService {
  LumenVisionService({required super.control});

  static Future<_FoodModel>? _model;
  static String? _lastLoadError;
  static Future<void> _lock = Future.value();

  bool get _supported =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  @override
  void init() {
    super.init();
    debugPrint("LumenVision(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
  }

  /// Load (once) or return the shared model. A failed load is forgotten so a later call
  /// can retry (e.g. after a transient out-of-memory).
  Future<_FoodModel> _ensureModel() {
    final existing = _model;
    if (existing != null) return existing;
    final f = _FoodModel.load().timeout(const Duration(seconds: 30));
    _model = f;
    f.then((_) => _lastLoadError = null, onError: (Object e) {
      _lastLoadError = e.toString();
      _model = null;
    });
    return f;
  }

  /// Run [body] after every earlier classify finished (one inference at a time).
  Future<T> _serial<T>(Future<T> Function() body) {
    final result = _lock.then((_) => body());
    _lock = result.then((_) {}, onError: (_) {});
    return result;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    final a = (args is Map) ? args : const {};
    if (!_supported) {
      return {"ok": false, "error": "unsupported"};
    }
    switch (name) {
      case "ready":
        try {
          final sw = Stopwatch()..start();
          final m = await _ensureModel();
          return {
            "ok": true,
            "labels": m.labels.length,
            "input": [m.inH, m.inW],
            "input_type": m.inType.toString(),
            "output_type": m.outType.toString(),
            "load_ms": sw.elapsedMilliseconds,
          };
        } catch (e) {
          debugPrint("LumenVision: model load failed: $e");
          return {"ok": false, "error": "load: ${_lastLoadError ?? e}"};
        }
      case "classify":
        final path = (a["path"] ?? "").toString();
        final topK = _int(a["top_k"], 5).clamp(1, 50);
        final timeoutS = _int(a["timeout_s"], 20).clamp(1, 120);
        try {
          return await _serial(() async {
            final sw = Stopwatch()..start();
            final m = await _ensureModel();
            final top = await m
                .classifyFile(path, topK)
                .timeout(Duration(seconds: timeoutS));
            return {"ok": true, "top": top, "ms": sw.elapsedMilliseconds};
          });
        } on TimeoutException {
          // A stuck run would leave the isolate interpreter "busy" forever (it then
          // silently skips inference), so drop the model and load a fresh one next time.
          // The old interpreter is leaked on purpose: closing it under a running isolate
          // could crash the app.
          _model = null;
          return {"ok": false, "error": "timeout"};
        } catch (e) {
          debugPrint("LumenVision: classify failed: $e");
          return {"ok": false, "error": e.toString()};
        }
      default:
        return {"ok": false, "error": "unknown method: $name"};
    }
  }

  static int _int(dynamic v, int fallback) {
    if (v is int) return v;
    return int.tryParse(v?.toString() ?? "") ?? fallback;
  }

  @override
  void dispose() {
    debugPrint("LumenVision(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    // The model stays loaded (static) so the next screen does not pay the load again.
    super.dispose();
  }
}

class _FoodModel {
  _FoodModel._(this.interpreter, this.isolate, this.labels);

  final Interpreter interpreter;
  final IsolateInterpreter? isolate; // null -> run on the UI isolate
  final List<String> labels;

  late final int inH, inW;
  late final TensorType inType, outType;
  late final double outScale;
  late final int outZero;
  late final int outLen;

  static Future<_FoodModel> load() async {
    final raw = await rootBundle.load(_modelAsset);
    final labelsText = await rootBundle.loadString(_labelsAsset);
    final labels = labelsText
        .split("\n")
        .map((s) => s.trimRight())
        .where((s) => s.isNotEmpty)
        .toList(growable: false);

    final opts = InterpreterOptions()..threads = 2;
    final interpreter = Interpreter.fromBuffer(
      raw.buffer.asUint8List(raw.offsetInBytes, raw.lengthInBytes),
      options: opts,
    );
    IsolateInterpreter? iso;
    try {
      iso = await IsolateInterpreter.create(address: interpreter.address);
    } catch (e) {
      debugPrint("LumenVision: no isolate interpreter, running inline: $e");
    }
    final m = _FoodModel._(interpreter, iso, labels);

    final input = interpreter.getInputTensor(0);
    final output = interpreter.getOutputTensor(0);
    final ishape = input.shape; // [1, H, W, 3]
    if (ishape.length != 4 || ishape[3] != 3) {
      throw StateError("unexpected input shape $ishape");
    }
    m.inH = ishape[1];
    m.inW = ishape[2];
    m.inType = input.type;
    m.outType = output.type;
    m.outLen = output.shape.isEmpty ? 0 : output.shape.last;
    m.outScale = output.params.scale;
    m.outZero = output.params.zeroPoint;
    if (m.outLen != labels.length) {
      throw StateError("model has ${m.outLen} classes but ${labels.length} labels");
    }
    if (m.inType != TensorType.uint8 && m.inType != TensorType.float32) {
      throw StateError("unsupported input type ${m.inType}");
    }
    debugPrint("LumenVision: model ready ${m.inW}x${m.inH} ${m.inType} -> "
        "${m.outLen} ${m.outType} (scale ${m.outScale}, zero ${m.outZero})");
    return m;
  }

  Future<List<List<Object>>> classifyFile(String path, int topK) async {
    final file = File(path);
    if (!await file.exists()) throw StateError("no such file: $path");
    final encoded = await file.readAsBytes();
    final rgb = await _centerSquareRgb(encoded, inW, inH);

    final Object input;
    if (inType == TensorType.float32) {
      // Kaggle model card: RGB scaled to [0, 1].
      final f = Float32List(rgb.length);
      for (var i = 0; i < rgb.length; i++) {
        f[i] = rgb[i] / 255.0;
      }
      input = f.buffer.asUint8List();
    } else {
      input = rgb; // uint8 model: raw 0..255 (its own quantization does the scaling)
    }

    final outBytes = Uint8List(outLen * (outType == TensorType.float32 ? 4 : 1));
    final iso = isolate;
    if (iso != null) {
      await iso.run(input, outBytes.buffer);
    } else {
      interpreter.run(input, outBytes.buffer);
    }
    return _top(_scores(outBytes), topK);
  }

  /// Output tensor -> probabilities 0..1.
  Float64List _scores(Uint8List out) {
    final s = Float64List(outLen);
    if (outType == TensorType.float32) {
      final f = out.buffer.asFloat32List(0, outLen);
      var sum = 0.0;
      var inRange = true;
      for (var i = 0; i < outLen; i++) {
        s[i] = f[i];
        sum += f[i];
        if (f[i] < 0 || f[i] > 1) inRange = false;
      }
      if (!inRange || (sum - 1.0).abs() > 0.05) _softmax(s); // logits, not probabilities
    } else {
      // uint8 softmax output: p = (q - zero_point) * scale (food_V1: scale 1/256, zero 0).
      final scale = outScale > 0 ? outScale : 1.0 / 255.0;
      for (var i = 0; i < outLen; i++) {
        s[i] = math.max(0, (out[i] - outZero) * scale);
      }
    }
    return s;
  }

  static void _softmax(Float64List s) {
    var mx = -double.infinity;
    for (final v in s) {
      if (v > mx) mx = v;
    }
    var sum = 0.0;
    for (var i = 0; i < s.length; i++) {
      s[i] = math.exp(s[i] - mx);
      sum += s[i];
    }
    for (var i = 0; i < s.length; i++) {
      s[i] /= sum;
    }
  }

  List<List<Object>> _top(Float64List s, int k) {
    final idx = List<int>.generate(s.length, (i) => i);
    idx.sort((a, b) => s[b].compareTo(s[a]));
    return [
      for (final i in idx.take(k)) [labels[i], s[i], i]
    ];
  }
}

/// Decode [encoded] (JPEG/PNG/...), scale so the short side equals the model side, crop the
/// centre square and return packed RGB bytes (w*h*3). dart:ui only, no image package.
Future<Uint8List> _centerSquareRgb(Uint8List encoded, int outW, int outH) async {
  final buffer = await ui.ImmutableBuffer.fromUint8List(encoded);
  final descriptor = await ui.ImageDescriptor.encoded(buffer);
  final w = descriptor.width, h = descriptor.height;
  descriptor.dispose();
  buffer.dispose();
  if (w <= 0 || h <= 0) throw StateError("cannot read image size");

  // Short side -> the model side, keep the aspect ratio (the codec down-samples while
  // decoding, so a 12 MP photo never lands in memory at full size).
  final side = math.max(outW, outH);
  int tw, th;
  if (w <= h) {
    tw = side;
    th = math.max(side, (h * side / w).round());
  } else {
    th = side;
    tw = math.max(side, (w * side / h).round());
  }
  final codec = await ui.instantiateImageCodec(encoded, targetWidth: tw, targetHeight: th);
  final frame = await codec.getNextFrame();
  final image = frame.image;
  codec.dispose();
  try {
    final rgba = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (rgba == null) throw StateError("cannot decode image");
    // Use the decoded size (EXIF rotation may have swapped width and height).
    final iw = image.width, ih = image.height;
    final Uint8List px = rgba.buffer.asUint8List(rgba.offsetInBytes, rgba.lengthInBytes);
    final int cw = math.min<int>(outW, iw), ch = math.min<int>(outH, ih);
    final int x0 = (iw - cw) ~/ 2, y0 = (ih - ch) ~/ 2;
    final out = Uint8List(outW * outH * 3);
    for (var y = 0; y < outH; y++) {
      final int sy = y0 + math.min<int>(y, ch - 1);
      for (var x = 0; x < outW; x++) {
        final int sx = x0 + math.min<int>(x, cw - 1);
        final int si = (sy * iw + sx) * 4;
        final int di = (y * outW + x) * 3;
        out[di] = px[si].toInt();
        out[di + 1] = px[si + 1].toInt();
        out[di + 2] = px[si + 2].toInt();
      }
    }
    return out;
  } finally {
    image.dispose();
  }
}
