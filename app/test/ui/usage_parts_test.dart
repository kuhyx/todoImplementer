import 'dart:async';
import 'dart:ui' show PictureRecorder;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/chart_paint.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';
import 'package:todo_implementer/ui/usage/usage_page.dart';

import '../support/fakes.dart';
import '../support/usage_fakes.dart';

Future<FakeUsageRelay> _pump(WidgetTester tester, [FakeUsageRelay? r]) async {
  pixel6a(tester);
  final relay = r ?? (FakeUsageRelay()..answers.addAll(cannedUsage()));
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
  test('every column kind has a glyph', () {
    for (final c in [
      Col.money('a', ''),
      Col.pct('a', ''),
      Col.secs('a', ''),
      Col.big('a', ''),
      Col.when('a', ''),
      Col.count('a', ''),
      Col.tag('a', ''),
      Col.text('a', ''),
    ]) {
      expect(kindGlyph(c), isA<IconData>());
      expect(columnGlyph(c), kindGlyph(c));
    }
    expect(seriesColor(9), seriesColors.last);
    expect(indexAt(0, 100, 0), -1);
  });

  test('the painter draws every kind, selected or not', () {
    for (final kind in ChartKind.values) {
      final b = ChartBlock(
        kind: kind,
        semantics: '',
        icon: Icons.abc,
        labels: const ['a', 'b'],
        series: const [
          ChartSeries('s', Icons.abc, [1, null]),
          ChartSeries('t', Icons.abc, [null, 2], color: 1),
        ],
        low: const [0, 1],
        high: const [2, 3],
        fmt: (v) => '$v',
      );
      final p = ChartPainter(b, 0);
      final rec = PictureRecorder();
      p.paint(Canvas(rec), const Size(200, 100));
      expect(p.shouldRepaint(ChartPainter(b, 1)), isTrue);
      expect(p.shouldRepaint(ChartPainter(b, 0)), isFalse);
    }
    final empty = ChartBlock(
      kind: ChartKind.bar,
      semantics: '',
      icon: Icons.abc,
      labels: const [],
      series: const [],
      fmt: (v) => '',
    );
    ChartPainter(empty, -1).paint(Canvas(PictureRecorder()), const Size(9, 9));
  });

  testWidgets('a tapped chart reads out its label; pages swipe', (
    tester,
  ) async {
    await _pump(tester);
    await tester.tapAt(
      tester.getCenter(
        find
            .byWidgetPredicate(
              (w) => w is CustomPaint && w.painter is ChartPainter,
            )
            .first,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('11-03'), findsWidgets);
    for (var i = 0; i < 6 && find.text('2026-11-01').evaluate().isEmpty; i++) {
      await tester.drag(find.byType(PageView), const Offset(-500, 0));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('2026-11-01'));
    await tester.pumpAndSettle();
    expect(find.byType(SelectableText), findsWidgets);
  });

  testWidgets('a long table counts pages; a broken snapshot shows an error', (
    tester,
  ) async {
    final relay = FakeUsageRelay()..answers.addAll(cannedUsage());
    relay.answers['/panel/sessions'] = RelayOk({
      'sessions': [
        for (var i = 0; i < 400; i++) {'key': 'k$i', 'title': 't$i'},
      ],
    });
    await _pump(tester, relay);
    await tester.tap(find.byKey(const ValueKey('usage-tab-sessions')));
    await tester.pumpAndSettle();
    expect(find.textContaining(' / '), findsOneWidget);
    final autonomy = find.byKey(const ValueKey('usage-tab-autonomy'));
    await tester.ensureVisible(autonomy);
    unawaited(relay.usageOut.close());
    await tester.tap(autonomy);
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('usage-copy-error')));
    await tester.pumpAndSettle();
  });

  testWidgets('a refusal copies its code and text', (tester) async {
    final copied = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied.add((call.arguments as Map)['text'] as String);
        }
        return null;
      },
    );
    final relay = FakeUsageRelay();
    await _pump(tester, relay);
    expect(find.byIcon(Icons.cloud_off), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('usage-copy-error')));
    await tester.pumpAndSettle();
    expect(copied.single, 'offline: no answer');
  });

  testWidgets('the filter sheet picks options and days, and clears', (
    tester,
  ) async {
    final relay = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('usage-filters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('pick-cwd')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('/w/a').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('date-from')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('clear-from')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('date-to')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('filters-apply')));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$2, contains('cwd=%2Fw%2Fa'));
    expect(relay.asked.last.$2, contains('to='));
    await tester.tap(find.byKey(const ValueKey('usage-filters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('filters-clear')));
    await tester.pumpAndSettle();
    expect(relay.asked.last.$2, isNot(contains('cwd')));
  });
}
