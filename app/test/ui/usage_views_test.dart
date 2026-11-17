import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/ui/usage/usage_page.dart';

import '../support/fakes.dart';
import '../support/usage_fakes.dart';
import '../support/usage_panels.dart';

Future<FakeUsageRelay> _pump(WidgetTester tester) async {
  pixel6a(tester);
  final relay = FakeUsageRelay()
    ..answers.addAll(cannedUsage())
    ..answers.addAll(morePanels())
    ..lastUsage = usageSnap();
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

Future<void> _tab(WidgetTester tester, String name) async {
  final tab = find.byKey(ValueKey('usage-tab-$name'));
  await tester.ensureVisible(tab);
  await tester.tap(tab);
  await tester.pumpAndSettle();
}

/// Swipes through every page of the current view.
Future<void> _swipeAll(WidgetTester tester) async {
  for (var i = 0; i < 8; i++) {
    await tester.drag(find.byType(PageView), const Offset(-500, 0));
    await tester.pumpAndSettle();
  }
}

void main() {
  for (final name in [
    'items',
    'efficiency',
    'autonomy',
    'levers',
    'context',
    'anomalies',
    'ab',
  ]) {
    testWidgets('$name renders every page without vertical scroll', (
      tester,
    ) async {
      final relay = await _pump(tester);
      await _tab(tester, name);
      expect(find.byIcon(Icons.cloud_off), findsNothing, reason: name);
      expectNoVerticalScroll(tester);
      await _swipeAll(tester);
      expect(tester.takeException(), isNull);
      expect(relay.asked, isNotEmpty);
    });
  }

  testWidgets('a context file opens with its content', (tester) async {
    final relay = await _pump(tester);
    await _tab(tester, 'context');
    for (
      var i = 0;
      i < 3 && find.text('/h/CLAUDE.md').evaluate().isEmpty;
      i++
    ) {
      await tester.drag(find.byType(PageView), const Offset(-500, 0));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('/h/CLAUDE.md'));
    await tester.pumpAndSettle();
    expect(relay.asked.map((a) => a.$1), contains('/context-file'));
    await _swipeAll(tester);
    expect(find.text('# rules'), findsOneWidget);
  });

  testWidgets('more lists generic panels; one opens as tiles and tables', (
    tester,
  ) async {
    final relay = await _pump(tester);
    await _tab(tester, 'more');
    expect(find.text('Overview'), findsNothing);
    await tester.tap(find.text('Calls'));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$1, '/panel/calls');
    expect(find.text('5'), findsOneWidget);
    await _swipeAll(tester);
    expect(find.text('Bash'), findsOneWidget);
  });

  testWidgets('a long-pressed row shows every column; a banner its text', (
    tester,
  ) async {
    await _pump(tester);
    await _tab(tester, 'anomalies');
    await tester.tap(find.byIcon(Icons.warning_amber).last);
    await tester.pumpAndSettle();
    expect(find.text('two spikes'), findsOneWidget);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    for (var i = 0; i < 8 && find.text('big').evaluate().isEmpty; i++) {
      await tester.drag(find.byType(PageView), const Offset(-500, 0));
      await tester.pumpAndSettle();
    }
    await tester.longPress(find.text('big'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('row-open')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('row-open')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('usage-back')), findsOneWidget);
  });
}
