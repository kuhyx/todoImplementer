import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/config/firebase_config.dart';
import 'package:todo_implementer/shell/app.dart';
import 'package:todo_implementer/sync/services.dart';

// The entry point is the one line flutter_test cannot run; everything it
// builds (TodoImplementerApp, AppServices.open) is tested.
// coverage:ignore-start
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    TodoImplementerApp(services: AppServices.open(FirebaseConfig.compiled)),
  );
}
// coverage:ignore-end
