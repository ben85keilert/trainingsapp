import 'package:flet/flet.dart';

import 'hochladen_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FletHochladen":
        return FletHochladenService(control: control);
      default:
        return null;
    }
  }
}
