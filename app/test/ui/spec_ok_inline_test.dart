// A "click Spec OK" need carries its thumb-up button in the need line itself
// (kuhy, 2026-11-20): the card sheet and the detail page both tap it there.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../model/detail_test.dart' show fullDetail;
import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _text = 'Every question is answered: click Spec OK to start the plan';

Json _specOkCard({String kind = 'spec_ok', bool enabled = true}) => card(
  'c1',
  column: 'needs_you',
  status: 'needs_you',
  needs: {'kind': kind, 'text': _text, 'category': 'action', 'effort': 1},
  actions: [
    action('spec-ok', enabled: enabled),
    action('cancel'),
  ],
);

final Finder _inline = find.byKey(const Key('needs-spec-ok'));
final Finder _thumb = find.descendant(
  of: _inline,
  matching: find.byKey(const ValueKey('action-spec-ok')),
);

Future<FakeRelay> _sheet(WidgetTester tester, Json c) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  relay.push(boardJson([c]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

void main() {
  testWidgets('[T2357] the sheet shows Spec OK as the need line thumb-up', (
    tester,
  ) async {
    final relay = await _sheet(tester, _specOkCard());
    expect(_thumb, findsOneWidget);
    expect(find.byKey(const ValueKey('action-spec-ok')), findsOneWidget);
    await tester.tap(_thumb);
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'task_spec_ok');
    expect(relay.sent.last.$2, {'card': 'c1', 'args': <String, dynamic>{}});
  });

  testWidgets('[T2357] other needs keep Spec OK in the bar', (tester) async {
    await _sheet(tester, _specOkCard(kind: 'spec_questions'));
    expect(_inline, findsNothing);
    expect(find.byKey(const ValueKey('action-spec-ok')), findsOneWidget);
  });

  testWidgets('[T2358] the detail page taps Spec OK in its need line', (
    tester,
  ) async {
    final relay = await pumpDetail(
      tester,
      detail: {...fullDetail(), 'card': _specOkCard()},
    );
    await tester.pumpAndSettle();
    expect(_thumb, findsOneWidget);
    await tester.tap(_thumb);
    await tester.pumpAndSettle();
    expect(relay.sent.map((s) => s.$1), contains('task_spec_ok'));
    final sent = relay.sent.firstWhere((s) => s.$1 == 'task_spec_ok').$2;
    expect(sent, {'card': 'c1', 'args': <String, dynamic>{}});
  });

  testWidgets('[T2358] a disabled Spec OK shows dimmed, no inline tap', (
    tester,
  ) async {
    final relay = await pumpDetail(
      tester,
      detail: {...fullDetail(), 'card': _specOkCard(enabled: false)},
    );
    await tester.pumpAndSettle();
    expect(_thumb, findsOneWidget);
    await tester.tap(_thumb, warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(relay.sent.map((s) => s.$1), isNot(contains('task_spec_ok')));
  });
}
