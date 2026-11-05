import 'package:flet/flet.dart';

import 'lumen_vision.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "LumenVision":
        return LumenVisionService(control: control);
      default:
        return null;
    }
  }
}
