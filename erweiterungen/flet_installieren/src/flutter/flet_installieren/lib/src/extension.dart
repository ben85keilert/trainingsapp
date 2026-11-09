import 'package:flet/flet.dart';

import 'installieren_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FletInstallieren":
        return FletInstallierenService(control: control);
      default:
        return null;
    }
  }
}
