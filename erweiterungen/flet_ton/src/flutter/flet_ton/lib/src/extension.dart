import 'package:flet/flet.dart';

import 'ton_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FletTon":
        return FletTonService(control: control);
      default:
        return null;
    }
  }
}
