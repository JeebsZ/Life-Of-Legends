# flet_lumen_ocr

Life of Legends' Flet 1.x extension for **on-device text recognition** (Study → Scan notes).
It wraps Google ML Kit text recognition v2 through the Flutter plugin
[`google_mlkit_text_recognition`](https://pub.dev/packages/google_mlkit_text_recognition)
(^0.15.0), Latin script only. No network, no cost per scan. Android (and iOS in principle);
web and desktop return "" so the app falls back to paste/type.

App code should not use this package directly. Use `src/lol/ui/ocr.py`
(`recognizer_for(page)` / `OcrRecognizer`), which implements the core `TextRecognizer`
protocol (`lol.core.study`). The text goes through `study.parse_notes` and the draft review.

## Layout

```
extensions/flet_lumen_ocr/
  pyproject.toml                   setuptools; ships src/flutter/** as package data
  src/flet_lumen_ocr/              Python side: LumenOcr(ft.Service)
  src/flutter/flet_lumen_ocr/      Flutter side (copied into the app by `flet build`)
    pubspec.yaml                   google_mlkit_text_recognition, flet
    lib/flet_lumen_ocr.dart        exports Extension
    lib/src/extension.dart         FletExtension -> creates the "LumenOcr" service
    lib/src/lumen_ocr.dart         FletService: one shared Latin TextRecognizer, serial calls
```

## Python API (`flet_lumen_ocr.LumenOcr`, async, never raises)

| method | returns |
|---|---|
| `ready(timeout=15)` | True when recognition can run here. |
| `recognize(path, timeout=25)` | The text: lines joined by `\n`, blocks by a blank line. `""` on any failure. |

`last_error` ("unsupported", "timeout", ...), `last_ms`, and `last_lines`
(blocks of `(text, left, top)` for later layout-aware parsing).

## Build notes (not verified here: Dart is not compiled in this repo)

- **minSdk**: ML Kit text recognition v2 needs Android API 21+; the app is 26. OK.
- **Kotlin/Java**: the plugin's Android side is Java; the app already sets
  `kotlin.jvm.target.validation.mode=warning` for tflite.
- **Size**: the bundled Latin model + ML Kit runtime adds roughly 4 MB per ABI (Google's
  figure for bundled text recognition v2). Check the plugin's `android/build.gradle` in the
  build: if it lists `text-recognition-chinese/-devanagari/-japanese/-korean` as
  `implementation`, those add ~ +16 MB more; exclude them in the app's gradle (they are only
  needed for non-Latin scripts). Older plugin versions bundled them; recent ones do not.
- **iOS**: ML Kit pods need iOS 15.5+ and arm64 (no x86 simulator).
- Root `pyproject.toml` (not edited here):

```toml
[tool.flet.android]
dependencies = ["flet-lumen-notify", "flet-lumen-vision", "flet-lumen-ocr"]

[tool.flet.dev_packages]
flet-lumen-ocr = "extensions/flet_lumen_ocr"
```
