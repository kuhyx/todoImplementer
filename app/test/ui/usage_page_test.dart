import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/usage/usage_page.dart';

import '../support/fakes.dart';
import '../support/usage_fakes.dart';

Future<FakeUsageRelay> _pump(WidgetTester tester) async {
  pixel6a(tester);
  final relay = FakeUsageRelay()..answers.addAll(cannedUsage());
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(child: UsagePage(relay: relay)),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return relay;
}

void main() {
  testWidgets('overview loads over the relay and never scrolls vertically', (
    tester,
  ) async {
    final relay = await _pump(tester);
    expect(relay.asked.first.$1, '/panel/overview');
    expect(relay.asked.first.$2, contains('t.daily.limit=0'));
    expect(find.text(r'$12.50'), findsOneWidget);
    expect(find.text('12.3k'), findsOneWidget);
    expectNoVerticalScroll(tester);
  });

  testWidgets('sessions page sideways; a row opens its session, back returns', (
    tester,
  ) async {
    final relay = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('usage-tab-sessions')));
    await tester.pumpAndSettle();
    expect(find.text('30'), findsOneWidget);
    expectNoVerticalScroll(tester);
    await tester.tap(find.byType(PageView));
    await tester.drag(find.byType(PageView), const Offset(-500, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Session k1'));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$1, '/session/k1');
    expect(find.text('/w/k1'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('usage-back')));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$1, '/panel/sessions');
  });

  testWidgets('sort by a column and filter rows', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('usage-tab-sessions')));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(PageView), const Offset(-500, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sort-sessions')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sort-by-usd')));
    await tester.pumpAndSettle();
    expect(find.text('Session k29'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('filter-sessions')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('filter-field')), 'k7');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(find.text('Session k7'), findsOneWidget);
    expect(find.text('Session k29'), findsNothing);
  });

  testWidgets('a failed view shows its glyph; retry asks again', (
    tester,
  ) async {
    final relay = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('usage-tab-levers')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.cloud_off), findsOneWidget);
    relay.answers['/panel/levers'] = const RelayOk({
      'rolling_days': 7,
      'rows': [],
      'series': {},
    });
    await tester.tap(find.byKey(const ValueKey('usage-retry')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.cloud_off), findsNothing);
  });

  testWidgets('filters apply to every request', (tester) async {
    final relay = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('usage-filters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.smart_toy_outlined).last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('filters-apply')));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$2, contains('scope=sub'));
  });
}
