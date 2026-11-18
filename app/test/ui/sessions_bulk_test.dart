import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/sessions/sessions_page.dart';

import '../support/fakes.dart';
import '../support/session_fakes.dart';

String _id(int i) => '${'$i'.padLeft(8, '0')}-0000-4000-8000-000000000000';

List<Json> _rows(int n) => [
  for (var i = 0; i < n; i++) sessionJson(id: _id(i), title: 's$i'),
];

Future<(FakeRelay, FakeSessionsFeed)> _pump(
  WidgetTester tester, {
  bool desktop = false,
}) async {
  pixel6a(tester);
  if (desktop) tester.view.physicalSize = const Size(2400, 1600);
  final relay = FakeRelay();
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
  feed.push(_rows(7));
  await tester.pumpAndSettle();
  return (relay, feed);
}

Future<void> _select(WidgetTester tester, int i) async {
  await tester.longPress(find.byKey(ValueKey('session-${_id(i)}')));
  await tester.pumpAndSettle();
}

Finder _bulk(String id) => find.descendant(
  of: find.byKey(const Key('bulk-bar')),
  matching: find.byKey(Key('session-$id')),
);

void main() {
  testWidgets('long press selects; bulk mark, unmark, copy, clear', (
    tester,
  ) async {
    final copied = mockClipboard(tester);
    final (relay, _) = await _pump(tester);
    expect(find.byKey(const Key('bulk-bar')), findsNothing);
    await _select(tester, 0);
    await _select(tester, 1);
    expect(find.byKey(const Key('tile-selected')), findsNWidgets(2));
    expect(find.text('2'), findsWidgets);
    expect(_bulk('resume'), findsNothing); // phone: no terminals
    await tester.tap(_bulk('copy-all'));
    await tester.pumpAndSettle();
    expect(copied.value!.split('\n'), hasLength(2));
    relay.outcomes['session_mark'] = const RelayOk({'ok': true});
    await tester.tap(_bulk('mark'));
    await tester.pumpAndSettle();
    expect(relay.sent.first.$2, {
      'args': {
        'ids': [_id(0), _id(1)],
        'mark': 'done',
      },
    });
    // Success clears the selection; the answer stays until cleared.
    expect(find.byKey(const Key('tile-selected')), findsNothing);
    expect(find.byKey(const Key('bulk-outcome')), findsOneWidget);
    await tester.tap(_bulk('clear'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('bulk-bar')), findsNothing);
    // A second long press deselects.
    await _select(tester, 2);
    await _select(tester, 2);
    expect(find.byKey(const Key('bulk-bar')), findsNothing);
    await _select(tester, 3);
    relay.outcomes['session_mark'] = const RelayFailed(
      code: 'offline',
      error: 'net',
    );
    relay.gate = Completer();
    await tester.tap(_bulk('unmark'));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    relay.gate!.complete();
    await tester.pumpAndSettle();
    expect(relay.sent.last.$2, {
      'args': {'id': _id(3), 'mark': null},
    });
    expect(find.byKey(const Key('sessions-failure')), findsOneWidget);
  });

  testWidgets('desktop: select all, resume capped at five, delete', (
    tester,
  ) async {
    final (relay, _) = await _pump(tester, desktop: true);
    await _select(tester, 0);
    await tester.tap(_bulk('select-all'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('tile-selected')), findsNWidgets(7));
    expect(_bulk('resume-max'), findsOneWidget);
    await tester.tap(_bulk('select-all'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('tile-selected')), findsNothing);
    await _select(tester, 4);
    await tester.tap(_bulk('resume'));
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'session_resume');
    await tester.longPress(_bulk('delete'));
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'session_delete');
  });
}
