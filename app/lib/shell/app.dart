import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:material_ui/material_ui.dart'
    as mui
    show DefaultMaterialLocalizations;
import 'package:todo_implementer/shell/night_lock.dart';
import 'package:todo_implementer/shell/shell.dart';
import 'package:todo_implementer/sync/services.dart';
import 'package:todo_implementer/ui/gate.dart';

/// Root widget: the shared dark theme around the sign-in/unlock gate and
/// the three-page shell. Without [services] (tests of the bare shell) it
/// shows the shell with placeholder pages.
class TodoImplementerApp extends StatelessWidget {
  /// Creates the app.
  const new({this.services, super.key});

  /// The production (or fake) services, built once at start.
  final Future<AppServices>? services;

  @override
  Widget build(BuildContext context) {
    final services = this.services;
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildDarkTheme(),
      builder: (context, child) => NightLock(child: child ?? const SizedBox()),
      // crdt_sync_flutter's dialogs (passphrase) are material_ui widgets: they
      // look up material_ui's MaterialLocalizations, which flutter/material's
      // MaterialApp does not provide. Without this the lock button throws.
      localizationsDelegates: const [
        mui.DefaultMaterialLocalizations.delegate,
        DefaultMaterialLocalizations.delegate,
        DefaultWidgetsLocalizations.delegate,
      ],
      home: services == null
          ? const Shell()
          : FutureBuilder<AppServices>(
              future: services,
              builder: (context, snap) => switch (snap.data) {
                final s? => AppGate(services: s),
                null => const Scaffold(
                  body: Center(child: CircularProgressIndicator()),
                ),
              },
            ),
    );
  }
}
