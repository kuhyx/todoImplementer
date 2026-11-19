import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _choices = [
  {'id': 'claude-fable-5-2', 'label': 'Fable 5.2'},
  {'id': 'claude-opus-5-5', 'label': 'Opus 5.5'},
  {'id': 'default', 'label': 'Default'},
];

Json _picker({bool enabled = true, String value = 'default'}) => {
  ...action('model', enabled: enabled, value: value),
  'choices': _choices,
};

Future<FakeRelay> _open(WidgetTester tester, Json pick) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  final c = {
    ...card('c1', column: 'running', status: 'working', actions: [pick]),
    'model': 'opus',
  };
  relay.push(boardJson([c]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

void main() {
  testWidgets('[T2220] the sheet shows the model and a tap pins another', (
    tester,
  ) async {
    final relay = await _open(tester, _picker());
    expect(find.byKey(const Key('card-model')), findsOneWidget);
    expect(find.text('opus'), findsOneWidget);
    expect(find.byKey(const ValueKey('action-model')), findsNothing);
    final pinned = tester.widget<ChoiceChip>(
      find.byKey(const ValueKey('model-default')),
    );
    expect(pinned.selected, isTrue);
    await tester.tap(find.byKey(const ValueKey('model-claude-fable-5-2')));
    await tester.pumpAndSettle();
    expect(relay.sent.single.$1, 'task_model');
    expect(relay.sent.single.$2, {
      'card': 'c1',
      'args': {'model': 'claude-fable-5-2'},
    });
  });

  testWidgets('[T2220] the detail overview shows the model', (tester) async {
    await pumpDetail(
      tester,
      detail: {
        'card': {...card('c1'), 'model': 'claude-fable-5-2'},
      },
    );
    expect(find.byKey(const Key('detail-model')), findsOneWidget);
    expect(find.text('claude-fable-5-2'), findsOneWidget);
  });

  testWidgets('[T2220] a disabled picker sends nothing', (tester) async {
    final relay = await _open(tester, _picker(enabled: false));
    await tester.tap(find.byKey(const ValueKey('model-claude-opus-5-5')));
    await tester.pumpAndSettle();
    expect(relay.sent, isEmpty);
  });
}
