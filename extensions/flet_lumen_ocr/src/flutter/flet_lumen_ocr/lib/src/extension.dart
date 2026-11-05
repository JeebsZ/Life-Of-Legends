import 'package:flet/flet.dart';

import 'lumen_ocr.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "LumenOcr":
        return LumenOcrService(control: control);
      default:
        return null;
    }
  }
}
