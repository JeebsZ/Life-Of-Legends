# flet_lumen_vision

Life of Legends' own Flet 1.x extension for **on-device food photo recognition**. It runs
Google's AIY *food_V1* TFLite classifier through the Flutter plugin
[`tflite_flutter`](https://pub.dev/packages/tflite_flutter) 0.12.1 (LiteRT 1.4.0). No network,
no cost per scan. Android (and iOS in principle); web and desktop are unsupported.

App code should not use this package directly. Use `src/lol/ui/vision.py`
(`recognizer_for(page)` / `VisionRecognizer`), which implements the core `Recognizer`
protocol and maps labels to foods with `src/lol/core/food_labels.py`.

## Layout

```
extensions/flet_lumen_vision/
  pyproject.toml                     setuptools; ships src/flutter/** (incl. the model) as package data
  src/flet_lumen_vision/             Python side: LumenVision(ft.Service)
  src/flutter/flet_lumen_vision/     Flutter side (copied into the app by `flet build`)
    pubspec.yaml                     tflite_flutter ^0.12.1, flet; declares the two assets
    lib/flet_lumen_vision.dart       exports Extension
    lib/src/extension.dart           FletExtension -> creates the "LumenVision" service
    lib/src/lumen_vision.dart        FletService: load model, decode + crop + resize, infer
    assets/food_v1.tflite            the model (21.2 MB)
    assets/food_v1_labels.txt        2,024 labels, one per line, index = output index
```

No Android module: `tflite_flutter` is an FFI plugin and brings its own native libraries.

## Python API (`flet_lumen_vision.LumenVision`, all async, never raise)

| method | returns |
|---|---|
| `ready(timeout=40)` | True when the model is loaded and can run (loads it on first call). |
| `info(timeout=40)` | `{ok, error?, labels, input:[h,w], input_type, output_type, load_ms}` |
| `classify(path, top_k=5, timeout=20)` | `[(label, probability 0..1), ...]` best first, or `[]` on any failure. |

`last_error` holds the reason for the last failure (`"unsupported"`, `"timeout"`,
`"load: ..."`, a decode error, or `RuntimeError: ... must be added to the page first` when
there is no Flet client). `last_ms` holds the device-side duration of the last classify.

## Pipeline (Dart)

1. `File(path).readAsBytes()`, then `ui.ImageDescriptor` for the size.
2. `ui.instantiateImageCodec(targetWidth, targetHeight)` so the **short side is 192 px**
   (aspect kept; the codec down-samples while decoding), then `toByteData(rawRgba)`.
3. Centre 192x192 crop, RGBA -> packed RGB `Uint8List`.
4. The input tensor is `uint8` (quantization scale 1/128, zero point 128, done inside the
   model), so raw 0..255 bytes go in as is. A float32 model would get RGB / 255.
5. The output is a `uint8` softmax over 2,024 classes (scale 1/256, zero point 0), dequantized
   as `(q - zero) * scale`. A float output gets softmax only when it isn't already a
   probability vector.
6. Top-k with labels. Python filters `__background__`, the 22 untranslated `/g/...` ids and
   weak scores.

Inference runs in an `IsolateInterpreter` (2 threads), one call at a time. The model loads
once per process; if a load fails it is retried on the next call. If a classify times out, the
model is reloaded next time (the stuck interpreter is leaked rather than closed under a
running isolate).

## Model

- **Source:** Kaggle Models `google/aiy`, instance *TfLite / vision-classifier-food-v1*,
  version 1 (formerly TF Hub `google/aiy/vision/classifier/food_V1/1`):
  https://www.kaggle.com/models/google/aiy/TfLite/vision-classifier-food-v1
- **Labels:** https://www.gstatic.com/aihub/tfhub/labelmaps/aiy_food_V1_labelmap.csv
  (identical to the label file embedded in the model's metadata; two labels had a stray
  leading `"`, which is stripped here).
- **License:** Apache License 2.0 (Kaggle model card; also `Apache-2.0`, author `Google`,
  in the TFLite metadata). © Google. Full text:
  https://www.apache.org/licenses/LICENSE-2.0. Unmodified model file.
- sha256 `food_v1.tflite` 03dd6d9129501f97be00775d9e17b5d9ad13be730149352adb8f4ca953b7a650
- MobileNet V1, input `[1,192,192,3]` uint8, output `[1,2024]` uint8.
- Model card limits: trained on mostly North American food; expects a well-cropped single
  dish; it doesn't estimate portions or nutrition.

## Size impact

About **+21 MB** for the model (quantized weights barely compress), plus the LiteRT native
library (`litert` + `litert-gpu`, a few MB per ABI). Shipping it as an asset keeps it simple
and offline. If APK size becomes a problem, the alternative is a first-use download into app
storage with `Interpreter.fromFile`.

## Wiring (in the app's pyproject.toml)

```toml
[tool.flet.android]
dependencies = ["flet-lumen-notify", "flet-lumen-vision"]

[tool.flet.dev_packages]
flet-lumen-vision = "extensions/flet_lumen_vision"
```

No permissions needed: photos come from the camera / file picker as a local path.

## Not verified yet

Nothing here has run on a device. It can only run inside a `flet build apk` build, not in
`flet run` or the Flet app. In particular, the Kaggle note for the sibling AIY models (birds,
insects, plants v3) mentions "out-of-order logit to labelmap mapping in tflite metadata",
and food_V1 has only version 1. The label order is therefore unconfirmed until real photos
classify correctly.
