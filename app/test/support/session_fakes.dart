import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';

/// The fixed "now" of the sessions tests.
final sessionsNow = DateTime.utc(2026, 11, 17, 12);

int _n = 0;

/// One session JSON (`sessions.schema.json#/$defs/session`).
Json sessionJson({
  String? id,
  String project = 'demo',
  String title = 'Fix it',
  String status = 'needs_action',
  bool done = false,
  int group = 0,
  String mark = 'open',
  Duration? idle = const Duration(minutes: 5),
  String lastUser = 'please',
  String lastAssistant = 'A: do the thing',
  bool movable = false,
  String? moveReason = 'waits for your action',
}) {
  final sid =
      id ?? '0000000${_n++ % 10}-0000-4000-8000-${'$_n'.padLeft(12, '0')}';
  return {
    'id': sid,
    'cwd': '/home/u/src/$project',
    'project': project,
    'title': title,
    'status': status,
    'done': done,
    'group': group,
    'manual_mark': mark == 'manual' ? 'done' : null,
    'mark': mark,
    'last_ts': idle == null
        ? null
        : sessionsNow.subtract(idle).toIso8601String(),
    'last_user': lastUser,
    'last_assistant': lastAssistant,
    'resume_command': "cd '/home/u/src/$project' && claude --resume $sid",
    'movable': movable,
    // RTDB keeps no null: a movable row arrives without the key.
    if (moveReason != null && !movable) 'move_reason': moveReason,
  };
}

/// A list node around [sessions].
Json listJson(List<Json> sessions) => {
  'sessions': sessions,
  'scanned': sessions.length,
  'scan_ms': 1,
};

/// A feed the test pushes lists into.
class FakeSessionsFeed {
  /// The stream behind the feed.
  final out = StreamController<SessionList>.broadcast();

  /// The feed function the page takes.
  SessionsFeed get feed =>
      () => out.stream;

  /// Publishes [sessions].
  void push(List<Json> sessions) =>
      out.add(SessionList.fromJson(listJson(sessions)));
}

/// Records every clipboard write of [tester]; the last text is `.value`.
ValueNotifier<String?> mockClipboard(WidgetTester tester) {
  final copied = ValueNotifier<String?>(null);
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (call) async {
      if (call.method == 'Clipboard.setData') {
        copied.value = (call.arguments as Map)['text'] as String;
      }
      return null;
    },
  );
  return copied;
}
