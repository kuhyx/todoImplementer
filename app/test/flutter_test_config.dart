import 'dart:async';

import 'package:todo_implementer/shell/night_lock.dart';

/// Every test runs at noon: the night lock never hides the app under test.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  nightClock = () => DateTime(2026, 11, 21, 12);
  await testMain();
}
