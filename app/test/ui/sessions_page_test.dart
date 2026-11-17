import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/sessions/sessions_page.dart';

import '../support/fakes.dart';
import '../support/session_fakes.dart';

const _a = 'aaaaaaaa-0000-4000-8000-000000000001';
const _b = 'bbbbbbbb-0000-4000-8000-000000000002';
const _m = 'cccccccc-0000-4000-8000-000000000003';

List<Json> _rows([int extra = 0]) => [
  sessionJson(id: _a, title: 'alpha', project: 'one'),
  sessionJson(id: _b, title: 'beta', project: 'two', status: 'running'),
  sessionJson(
    id: _m,
    title: 'hand',
    status: 'done',
    done: true,
    mark: 'manual',
  ),
  for (var i = 0; i < extra; i++) sessionJson(title: 'more $i'),
];

Future<(FakeRelay, FakeSessionsFeed)> _pump(
  WidgetTester tester, {
  double keyboard = 0,
  bool desktop = false,
}) async {
  pixel6a(tester, keyboard: keyboard);
  if (desktop) tester.view.physicalSize = const Size(2400, 1600);
  final relay = FakeRelay();
  for (final verb in ['resume', 'mark', 'delete']) {
    relay.outcomes['session_$verb'] = const RelayOk({
      'ok': true,
      'refused': false,
      'summary': 'ok',
    });
  }
  final feed = FakeSessionsFeed();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(
          child: SessionsPage(
            feed: feed.feed,
            relay: relay,
            clock: () => sessionsNow,
          ),
        ),
      ),
    ),
  );
  return (relay, feed);
}

Finder _tile(String id) => find.byKey(ValueKey('session-$id'));

Future<void> _openSheet(WidgetTester tester, String id) async {
  await tester.tap(_tile(id));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('waits for the PC with a loader', (tester) async {
    await _pump(tester);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  for (final keyboard in [0.0, 300.0]) {
    testWidgets('fits one Pixel 6a screen, pages sideways (kb $keyboard)', (
      tester,
    ) async {
      final (_, feed) = await _pump(tester, keyboard: keyboard);
      feed.push(_rows(40));
      await tester.pumpAndSettle();
      expect(_tile(_a), findsOneWidget);
      expect(_tile(_m), findsNothing); // done rows hide by default
      expect(find.text('42/43'), findsOneWidget);
      expectNoVerticalScroll(tester);
      expect(find.byType(PageView), findsOneWidget);
    });
  }

  testWidgets('chips, search, sort, filters and reset', (tester) async {
    final (_, feed) = await _pump(tester);
    feed.push(_rows());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('chip-running')));
    await tester.pumpAndSettle();
    expect(_tile(_a), findsNothing);
    expect(_tile(_b), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('chip-running')));
    await tester.enterText(find.byKey(const Key('sessions-search')), 'alp');
    await tester.pumpAndSettle();
    expect(_tile(_b), findsNothing);
    await tester.enterText(find.byKey(const Key('sessions-search')), '');
    await tester.tap(find.byKey(const Key('sessions-sort')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sort-title')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.arrow_upward), findsOneWidget);
    await tester.tap(find.byKey(const Key('sessions-sort')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sort-title')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.arrow_downward), findsOneWidget);
    // Filter sheet: project, idle days, mark, show done.
    await tester.tap(find.byKey(const Key('sessions-filters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('filter-project')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('two').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('filter-idle')), '0');
    await tester.enterText(find.byKey(const Key('filter-idle')), '2');
    await tester.enterText(find.byKey(const Key('filter-idle')), '');
    await tester.tap(find.byIcon(Icons.person_outline));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.select_all).last);
    await tester.tap(find.byKey(const Key('filter-done')));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(10, 10)); // close the sheet
    await tester.pumpAndSettle();
    expect(_tile(_b), findsOneWidget);
    expect(_tile(_a), findsNothing);
    await tester.tap(find.byKey(const Key('sessions-reset')));
    await tester.pumpAndSettle();
    expect(_tile(_a), findsOneWidget);
    expect(find.byKey(const Key('sessions-reset')), findsNothing);
  });

  testWidgets('an empty result shows the page glyph', (tester) async {
    final (_, feed) = await _pump(tester);
    feed.push(const []);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sessions-empty')), findsOneWidget);
  });

  testWidgets('sheet: details, copy, mark, hold-to-delete, refusal', (
    tester,
  ) async {
    final copied = mockClipboard(tester);
    final (relay, feed) = await _pump(tester);
    feed.push(_rows());
    await tester.pumpAndSettle();
    await _openSheet(tester, _a);
    expect(find.text('/home/u/src/one'), findsOneWidget);
    expect(find.byKey(const Key('session-resume')), findsNothing); // phone
    await tester.tap(find.byKey(const Key('session-copy')));
    await tester.pumpAndSettle();
    expect(copied.value, contains('--resume $_a'));
    await tester.tap(find.byKey(const Key('session-mark')));
    await tester.pumpAndSettle();
    expect(relay.sent[0].$1, 'session_mark');
    expect(relay.sent[0].$2, {
      'args': {'id': _a, 'mark': 'done'},
    });
    expect(relay.sent[1].$1, 'snapshot_refresh');
    expect(find.byKey(const Key('session-outcome')), findsOneWidget);
    // A tap on delete only buzzes; the long press sends.
    await tester.tap(find.byKey(const Key('session-delete')));
    expect(relay.sent, hasLength(2));
    relay.outcomes['session_delete'] = const RelayOk({
      'ok': false,
      'refused': true,
      'summary': 'written in the last 10 minutes',
    });
    await tester.longPress(find.byKey(const Key('session-delete')));
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'session_delete');
    expect(find.byIcon(Icons.lock_outline), findsWidgets);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sessions-failure')), findsOneWidget);
    await tester.tap(find.byKey(const Key('sessions-copy-errors')));
    expect(copied.value, 'written in the last 10 minutes');
  });

  testWidgets('sheet: unmark a hand mark, resume on a desktop', (tester) async {
    final (relay, feed) = await _pump(tester, desktop: true);
    feed.push(_rows());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sessions-filters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('filter-done')));
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    await _openSheet(tester, _m);
    expect(find.byKey(const Key('session-mark')), findsNothing);
    relay.gate = Completer();
    await tester.tap(find.byKey(const Key('session-unmark')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    relay.gate!.complete();
    await tester.pumpAndSettle();
    expect(relay.sent.first.$2, {
      'args': {'id': _m, 'mark': null},
    });
    await tester.tap(find.byKey(const Key('session-resume')));
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'session_resume');
    expect(relay.sent.where((s) => s.$1 == 'snapshot_refresh'), hasLength(1));
  });
}
