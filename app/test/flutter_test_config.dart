import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/shell/night_lock.dart';
import 'package:todo_implementer/ui/board/new_task_draft.dart';

/// Every test runs at noon: the night lock never hides the app under test.
/// Each test gets an empty add-task draft (T2493): no draft leaks from the
/// test before it, and none reaches the device's preferences.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  nightClock = () => DateTime(2026, 11, 21, 12);
  setUp(() => newTaskDrafts = MemoryNewTaskDrafts());
  await testMain();
}
