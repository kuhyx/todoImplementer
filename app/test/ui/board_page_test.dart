import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/fakes.dart';

Json _many(int n) => boardJson([
  for (var i = 0; i < n; i++) card('b$i', updated: i),
  card(
    'n1',
    column: 'needs_you',
    status: 'needs_you',
    needs: {
      'kind': 'claude_question',
      'text': 'answer it',
      'category': 'questions',
      'effort': 1,
    },
    route: 'credits',
    cost: 1.5,
    tiers: true,
    repo: null,
  ),
  card('r1', column: 'running', status: 'working', repo: 'kuhyx/other'),
]);

Future<FakeRelay> _pump(WidgetTester tester, {double keyboard = 0}) async {
  pixel6a(tester, keyboard: keyboard);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(child: BoardPage(relay: relay)),
      ),
    ),
  );
  return relay;
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
      final relay = await _pump(tester, keyboard: keyboard);
      relay.push(_many(30));
      await tester.pumpAndSettle();
      // Needs you has cards, so it opens first.
      expect(find.byKey(const ValueKey('card-n1')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('col-backlog')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('card-b29')), findsOneWidget);
      expectNoVerticalScroll(tester);
      expect(find.byType(PageView), findsOneWidget);
    });
  }

  testWidgets('search, repo filter, sort and an empty column', (tester) async {
    final relay = await _pump(tester);
    relay.push(_many(3));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('col-done')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('empty-column')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('col-backlog')));
    await tester.enterText(find.byKey(const Key('search')), 'b2');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('card-b1')), findsNothing);
    expect(find.byKey(const ValueKey('card-b2')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('search')), '');
    await tester.tap(find.byKey(const Key('repo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('other').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('card-b1')), findsNothing);
    await tester.tap(find.byKey(const Key('repo')));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.person_outline));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('repo')));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.select_all));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sort')));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.attach_money).last);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('card-b1')), findsOneWidget);
  });

  testWidgets('credits switch, refresh and copy-errors', (tester) async {
    final relay = await _pump(tester);
    relay
      ..push(
        boardJson(
          [card('a')],
          extra: {
            'error': {'code': 'internal', 'message': 'stale'},
            'alert': {'kind': 'overage', 'text': 'over', 'until': 9},
            'api_key': {
              'state': 'invalid',
              'level': 'error',
              'text': 'bad',
              'expires': null,
            },
            'limit': {
              'active': true,
              'until': 5,
              'credits': {'enabled': true, 'state': 'ready', 'text': 't'},
            },
          },
        ),
      )
      ..outcomes['snapshot_refresh'] = const RelayFailed(
        code: 'offline',
        error: 'no net',
      );
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.key_off), findsOneWidget);
    await tester.tap(find.byKey(const Key('credits')));
    await tester.tap(find.byKey(const Key('refresh')));
    await tester.pumpAndSettle();
    expect(relay.sent.map((s) => s.$1), [
      'credits_fallback',
      'snapshot_refresh',
    ]);
    expect(relay.sent.first.$2, {
      'args': {'enabled': false},
    });
    expect(find.byKey(const Key('board-failure')), findsOneWidget);
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String;
        }
        return null;
      },
    );
    await tester.tap(find.byKey(const Key('copy-errors')));
    await tester.pumpAndSettle();
    expect(copied, 'offline: no net');
  });

  testWidgets('a key warning is amber', (tester) async {
    final relay = await _pump(tester);
    relay.push(
      boardJson(
        [card('a')],
        extra: {
          'api_key': {
            'state': 'expiring',
            'level': 'warn',
            'text': 'soon',
            'expires': null,
          },
        },
      ),
    );
    await tester.pumpAndSettle();
    final icon = tester.widget<Icon>(find.byIcon(Icons.key_off));
    expect(icon.color, AppPalette.warning);
  });
}
