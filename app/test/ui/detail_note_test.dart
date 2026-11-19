// T2276: the drawer page offers Send to Claude next to the asks, so a note
// never waits for the questions to be answered.
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

Json _detail(List<Json> actions) => {
  ...richDetail(),
  'card': card(
    'c1',
    status: 'needs_you',
    column: 'needs_you',
    actions: actions,
    needs: {
      'kind': 'claude_question',
      'text': 'pick a logo',
      'category': 'questions',
      'effort': 1,
    },
  ),
};

final Finder _box = find.byKey(const Key('detail-send-text'));
final Finder _send = find.byKey(const Key('detail-send'));
List<String> _posts(FakeRelay r) => [
  for (final k in kinds(r))
    if (k != 'task_shot') k,
];

void main() {
  testWidgets('[T2276] a note goes out next to open asks, then reloads', (
    tester,
  ) async {
    final relay = await pumpDetail(
      tester,
      detail: _detail([action('send'), action('cancel')]),
    );
    expect(find.byKey(const ValueKey('ask-ch')), findsOneWidget);
    await seek(tester, _box, 300);
    await hit(tester, _send);
    expect(_posts(relay), ['task_detail']);
    await tester.enterText(_box, ' Thanks, now an interactive way ');
    await hit(tester, _send);
    expect(_posts(relay), ['task_detail', 'task_send', 'task_detail']);
    expect(relay.sent.firstWhere((s) => s.$1 == 'task_send').$2, {
      'card': 'c1',
      'args': {'text': 'Thanks, now an interactive way'},
    });
    expect(tester.widget<TextField>(_box).controller!.text, isEmpty);
  });

  testWidgets('[T2276] a refused note keeps its text', (tester) async {
    final relay = await pumpDetail(tester, detail: _detail([action('send')]));
    relay.outcomes['task_send'] = const RelayFailed(
      code: 'disabled',
      error: 'busy',
    );
    await seek(tester, _box, 300);
    await tester.enterText(_box, 'keep me');
    await hit(tester, _send);
    expect(tester.widget<TextField>(_box).controller!.text, 'keep me');
    expect(find.byKey(const Key('detail-failure')), findsOneWidget);
  });

  testWidgets('[T2276] a disabled send keeps the box and names why', (
    tester,
  ) async {
    await pumpDetail(tester, detail: _detail([action('send', enabled: false)]));
    await seek(tester, _send, 300);
    expect(tester.widget<IconButton>(_send).onPressed, isNull);
    expect(tester.widget<IconButton>(_send).tooltip, 'send: why send');
  });

  testWidgets('[T2276] no send offered, no box', (tester) async {
    await pumpDetail(tester, detail: _detail([action('cancel')]));
    await seek(tester, find.byKey(const Key('lesson')), 300);
    expect(_box, findsNothing);
  });
}
