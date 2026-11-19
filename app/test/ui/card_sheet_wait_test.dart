import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/fakes.dart';

void main() {
  testWidgets('[T2314] spec answers with no task_detail answer can retry', (
    tester,
  ) async {
    pixel6a(tester);
    final relay = FakeRelay();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildDarkTheme(),
        home: Scaffold(body: BoardPage(relay: relay)),
      ),
    );
    relay.push(
      boardJson([
        card(
          'c1',
          column: 'needs_you',
          status: 'needs_you',
          actions: [action('spec-answers')],
        ),
      ]),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('card-c1')));
    await tester.pumpAndSettle();
    final ask = find.byKey(const ValueKey('action-spec-answers'));
    relay.gate = Completer<void>();
    await tester.tap(ask);
    await tester.pump();
    await tester.pump(const Duration(seconds: 16));
    final glyph = tester.widget<Icon>(find.byKey(const Key('sheet-failure')));
    expect(glyph.icon, Icons.timer_off_outlined);
    relay
      ..gate = null
      ..outcomes['task_detail'] = const RelayOk({
        'questions': [
          {
            'id': 'Q1',
            'title': 'Which?',
            'body': '',
            'recommendation': 'A',
            'answer': null,
          },
        ],
      });
    await tester.tap(ask);
    await tester.pumpAndSettle();
    expect(find.text('Which?'), findsOneWidget);
    expect(find.byKey(const Key('sheet-failure')), findsNothing);
  });
}
