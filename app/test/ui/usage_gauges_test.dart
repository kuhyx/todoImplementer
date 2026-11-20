// T2348: the piggy beside the credits switch said nothing, and the plan
// usage limit was not on the board at all.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/board_header.dart';

import '../support/fakes.dart';

Json _credits({bool enabled = true, bool over = false, String state = 'ready'}) => {
  'enabled': enabled,
  'state': state,
  'text': 't',
  'cap_usd': 95.0,
  'spent_period_usd': over ? 95.26 : 23.75,
  'remaining_usd': 94.7,
  'over_cap': over,
};

Board _board({Json credits = const {}, bool active = false}) => Board.fromJson(
  boardJson(
    const [],
    extra: {
      'limit': {
        'active': active,
        'until': active ? 1795165200 : null,
        'credits': credits.isEmpty ? _credits() : credits,
      },
    },
  ),
);

const Json _usage = {
  'five_hour': {'utilization': 0.12, 'resets_at': 1795160000, 'status': 'allowed'},
  'seven_day': {'utilization': 0.93, 'resets_at': 1795165199, 'status': 'allowed'},
};

Future<void> _pump(WidgetTester tester, Board board, {Json? usage}) async {
  pixel6a(tester);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: StatusStrip(
          board: board,
          usage: usage,
          errors: 0,
          onCredits: (_) {},
          onRefresh: () {},
          onCopyErrors: () {},
        ),
      ),
    ),
  );
}

ProgressIndicator _ring(WidgetTester tester, String key) => tester
    .widget<CircularProgressIndicator>(
      find.descendant(
        of: find.byKey(Key(key)),
        matching: find.byType(CircularProgressIndicator),
      ),
    );

void main() {
  testWidgets('[T2348] the piggy is gone; two rings show plan and credits use', (
    tester,
  ) async {
    await _pump(tester, _board(), usage: _usage);
    expect(find.byIcon(Icons.savings_outlined), findsNothing);
    final plan = _ring(tester, 'gauge-plan');
    expect(plan.value, closeTo(0.93, 1e-9)); // the fuller window wins
    expect(plan.valueColor?.value, AppPalette.warning);
    final credits = _ring(tester, 'gauge-credits');
    expect(credits.value, closeTo(0.25, 1e-9));
    expect(credits.valueColor?.value, AppPalette.accent);
  });

  testWidgets('a tap shows the numbers and the resets', (tester) async {
    await _pump(tester, _board(active: true), usage: _usage);
    await tester.tap(find.byKey(const Key('gauge-plan')));
    await tester.pumpAndSettle();
    expect(find.text('12%'), findsOneWidget);
    expect(find.text('93%'), findsOneWidget);
    expect(find.text(r'$23.75 / $95.00'), findsOneWidget);
    expect(find.byKey(const Key('gauge-limit-until')), findsOneWidget);
  });

  testWidgets('credits at the cap are red; switched off they dim', (
    tester,
  ) async {
    await _pump(tester, _board(credits: _credits(over: true)));
    expect(_ring(tester, 'gauge-credits').value, 1.0);
    expect(
      _ring(tester, 'gauge-credits').valueColor?.value,
      AppPalette.danger,
    );
    expect(_ring(tester, 'gauge-plan').value, 0.0); // no usage read yet
    await _pump(tester, _board(credits: _credits(enabled: false)));
    final dim = tester.widget<Opacity>(
      find.descendant(
        of: find.byKey(const Key('gauge-credits')),
        matching: find.byType(Opacity),
      ),
    );
    expect(dim.opacity, lessThan(1));
  });

  testWidgets('a plan at its limit is red', (tester) async {
    await _pump(
      tester,
      _board(),
      usage: const {
        'five_hour': {'utilization': 1.0, 'resets_at': 1, 'status': 'rejected'},
        'seven_day': null,
      },
    );
    expect(_ring(tester, 'gauge-plan').valueColor?.value, AppPalette.danger);
  });
}
