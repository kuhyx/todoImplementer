import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/sessions/sessions_page.dart';

import '../support/fakes.dart';
import '../support/session_fakes.dart';

String _id(int i) => '${'$i'.padLeft(8, '0')}-0000-4000-8000-000000000000';

/// Rows 0-5 can move; row 6 waits for kuhy (A:).
List<Json> _rows() => [
  for (var i = 0; i < 6; i++)
    sessionJson(id: _id(i), title: 's$i', status: 'untagged', movable: true),
  sessionJson(id: _id(6), title: 's6', moveReason: 'waits for your action'),
];

Future<FakeRelay> _pump(WidgetTester tester) async {
  pixel6a(tester);
  final relay = FakeRelay();
  relay.outcomes['session_handoff'] = const RelayOk({
    'ok': true,
    'refused': false,
    'summary': 'Moved s0 to the board',
  });
  final feed = FakeSessionsFeed();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SessionsPage(
          feed: feed.feed,
          relay: relay,
          clock: () => sessionsNow,
        ),
      ),
    ),
  );
  feed.push(_rows());
  await tester.pumpAndSettle();
  return relay;
}

Finder _tile(int i) => find.byKey(ValueKey('session-${_id(i)}'));

Finder _bulk(String id) => find.descendant(
  of: find.byKey(const Key('bulk-bar')),
  matching: find.byKey(Key('session-$id')),
);

IconButton _button(WidgetTester tester, Finder f) =>
    tester.widget<IconButton>(f);

void main() {
  testWidgets('the sheet moves a movable session to the board', (tester) async {
    final relay = await _pump(tester);
    await tester.tap(_tile(0));
    await tester.pumpAndSettle();
    final button = find.byKey(const Key('session-handoff'));
    expect(button, findsOneWidget);
    expect(find.byIcon(Icons.smart_toy_outlined), findsOneWidget);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(relay.sent.first.$1, 'session_handoff');
    expect(relay.sent.first.$2, {
      'args': {'id': _id(0)},
    });
    expect(relay.sent[1].$1, 'snapshot_refresh');
    expect(find.byKey(const Key('session-outcome')), findsOneWidget);
  });

  testWidgets('an unmovable session offers it disabled, saying why', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    final relay = await _pump(tester);
    await tester.tap(_tile(6));
    await tester.pumpAndSettle();
    final button = find.byKey(const Key('session-handoff'));
    expect(tester.widget<IconButton>(button).onPressed, isNull);
    expect(find.bySemanticsLabel('waits for your action'), findsOneWidget);
    await tester.tap(button, warnIfMissed: false);
    expect(relay.sent, isEmpty);
    handle.dispose();
  });

  testWidgets('bulk: moves the selection, blocked by an unmovable row, max 5', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    final relay = await _pump(tester);
    for (final i in [0, 1]) {
      await tester.longPress(_tile(i));
      await tester.pumpAndSettle();
    }
    await tester.tap(_bulk('handoff'));
    await tester.pumpAndSettle();
    expect(relay.sent.first.$1, 'session_handoff');
    expect(relay.sent.first.$2, {
      'args': {
        'ids': [_id(0), _id(1)],
      },
    });
    for (final i in [1, 6]) {
      await tester.longPress(_tile(i));
      await tester.pumpAndSettle();
    }
    expect(_button(tester, _bulk('handoff')).onPressed, isNull);
    expect(find.bySemanticsLabel('waits for your action'), findsOneWidget);
    await tester.longPress(_tile(6));
    await tester.pumpAndSettle();
    for (final i in [0, 2, 3, 4, 5]) {
      await tester.longPress(_tile(i));
      await tester.pumpAndSettle();
    }
    expect(_bulk('handoff-max'), findsOneWidget);
    expect(_button(tester, _bulk('handoff-max')).onPressed, isNull);
    handle.dispose();
  });
}
