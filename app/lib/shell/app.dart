import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/shell/shell.dart';

/// Root widget: the shared dark theme around the three-page shell.
///
/// Sign-in, unlock and the relay plug in here later (DOCS-native-app.md, P3
/// sign-in + unlock); the scaffold ships the shell alone.
class TodoImplementerApp extends StatelessWidget {
  /// Creates the app.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildDarkTheme(),
      home: const Shell(),
    );
  }
}
