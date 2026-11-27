// T2583: the card sheet changes a card's priority, and Start asks first
// while a higher-priority card waits in Backlog.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/priority_picker.dart';

import '../support/fakes.dart';

const _levels = [
  {'id': 'high', 'label': 'High'},
  {'id': 'medium', 'label': 'Medium'},
  {'id': 'low', 'label': 'Low'},
];

Json _picker({bool enabled = true}) => {
  ...action('priority', enabled: enabled, value: 'medium'),
  'choices': _levels,
};

const _waits = {'id': 'aaaaaaaa-0', 'title': 'urgent repo', 'priority': 'high'};

Future<FakeRelay> _open(WidgetTester tester, List<Json> actions) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  relay.push(boardJson([card('c1', actions: actions)]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

// The Start button spins while the modal is open, so the frames never settle.
Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

ChoiceChip _chip(WidgetTester tester, String level) =>
    tester.widget<ChoiceChip>(find.byKey(ValueKey('priority-$level')));

void main() {
  testWidgets('[T2583] the sheet presses the priority; a tap sends another', (
    tester,
  ) async {
    final relay = await _open(tester, [_picker()]);
    expect(find.byKey(const ValueKey('action-priority')), findsNothing);
    expect(_chip(tester, 'medium').selected, isTrue);
    expect(find.text('Medium'), findsNothing); // a glyph; the name is a tooltip
    expect(_chip(tester, 'medium').onSelected, isNull);
    await tester.tap(find.byKey(const ValueKey('priority-high')));
    await tester.pumpAndSettle();
    expect(relay.sent.single.$1, 'task_priority');
    expect(relay.sent.single.$2, {
      'card': 'c1',
      'args': {'priority': 'high'},
    });
  });

  testWidgets('[T2583] a disabled picker sends nothing', (tester) async {
    final relay = await _open(tester, [_picker(enabled: false)]);
    expect(_chip(tester, 'high').onSelected, isNull);
    await tester.tap(find.byKey(const ValueKey('priority-high')));
    await tester.pumpAndSettle();
    expect(relay.sent, isEmpty);
  });

  testWidgets('[T2583] Start while a higher card waits asks; back sends '
      'nothing, start sends the Start', (tester) async {
    final start = {...action('start'), 'waits': _waits};
    final relay = await _open(tester, [start]);
    await tester.tap(find.byKey(const ValueKey('action-start')));
    await _settle(tester);
    expect(find.byKey(const Key('start-confirm')), findsOneWidget);
    expect(find.text('urgent repo'), findsOneWidget);
    expect(find.byIcon(Icons.keyboard_double_arrow_up), findsOneWidget);
    await tester.tap(find.byKey(const Key('start-confirm-back')));
    await _settle(tester);
    expect(relay.sent, isEmpty);
    await tester.tap(find.byKey(const ValueKey('action-start')));
    await _settle(tester);
    await tester.tapAt(const Offset(4, 4)); // outside: the same as back
    await _settle(tester);
    expect(relay.sent, isEmpty);
    await tester.tap(find.byKey(const ValueKey('action-start')));
    await _settle(tester);
    await tester.tap(find.byKey(const Key('start-confirm-go')));
    await _settle(tester);
    expect(relay.sent.single.$1, 'task_start');
  });

  test('[T2583] glyphs per level and the waits field', () {
    expect(priorityIcon('low'), Icons.keyboard_double_arrow_down);
    expect(priorityIcon('someday'), Icons.drag_handle);
    final a = CardAction.fromJson({...action('start'), 'waits': _waits});
    expect(a.waits, (id: 'aaaaaaaa-0', title: 'urgent repo', priority: 'high'));
    expect(CardAction.fromJson(action('start')).waits, isNull);
  });
}
