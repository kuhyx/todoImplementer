import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/detail_page.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

Future<(FakeRelay, List<RelayFailed>)> _pumpStuck(WidgetTester tester) async {
  pixel6a(tester);
  final relay = FakeRelay()..gate = Completer<void>();
  final errors = <RelayFailed>[];
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: DetailPage(card: 'c1', relay: relay, onError: errors.add),
    ),
  );
  await tester.pump();
  return (relay, errors);
}

Finder _spinner() => find.byType(CircularProgressIndicator);

void main() {
  testWidgets('[T2313] a task_detail with no answer ends in a retry state', (
    tester,
  ) async {
    final (relay, errors) = await _pumpStuck(tester);
    expect(
      tester.widget<CircularProgressIndicator>(_spinner()).semanticsLabel,
      contains('PC'),
    );
    expect(find.byKey(const Key('detail-waits-on')), findsOneWidget);
    await tester.pump(const Duration(seconds: 16));
    expect(_spinner(), findsNothing);
    expect(find.byKey(const Key('detail-failure')), findsOneWidget);
    expect(errors.single.code, 'timeout');
    relay
      ..gate = null
      ..outcomes['task_detail'] = RelayOk(richDetail());
    await tester.tap(find.byKey(const Key('detail-retry')));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('overview')), findsOneWidget);
    expect(find.byKey(const Key('detail-failure')), findsNothing);
  });

  testWidgets('[T2313] a refused first load shows the retry state', (
    tester,
  ) async {
    await pumpDetail(
      tester,
      outcome: const RelayFailed(code: 'offline', error: 'down'),
    );
    expect(_spinner(), findsNothing);
    expect(find.byKey(const Key('detail-retry')), findsOneWidget);
  });
}
