// T2603: a card drawer opened with no network waited on the PC worker and
// ended in the retry glyph, though the app had seen the detail before. The
// kept copy now shows at once; the live answer replaces it when it comes.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/detail_page.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

Future<FakeRelay> _open(WidgetTester tester, RelayOutcome live) async {
  pixel6a(tester);
  final relay = FakeRelay()
    ..kept['c1'] = richDetail()
    ..outcomes['task_detail'] = live;
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: DetailPage(card: 'c1', relay: relay, onError: (_) {}),
    ),
  );
  return relay;
}

void main() {
  testWidgets('[T2603] an offline drawer shows the kept detail at once', (
    tester,
  ) async {
    await _open(
      tester,
      const RelayFailed(code: 'offline', error: 'down', retry: true),
    );
    expect(find.byKey(const Key('overview')), findsOneWidget);
    await tester.pump();
    expect(find.byKey(const Key('overview')), findsOneWidget);
    expect(find.byKey(const Key('detail-failure')), findsOneWidget);
    expect(find.byKey(const Key('detail-retry')), findsNothing);
  });

  testWidgets('[T2603] a corrupt kept detail falls back to the wait', (
    tester,
  ) async {
    pixel6a(tester);
    final relay = FakeRelay()..kept['c1'] = {'card': 'not a card'};
    await tester.pumpWidget(
      MaterialApp(
        theme: buildDarkTheme(),
        home: DetailPage(card: 'c1', relay: relay, onError: (_) {}),
      ),
    );
    expect(find.byKey(const Key('detail-waits-on')), findsOneWidget);
  });
}
