import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _choices = [
  {'id': 'claude-fable-5-2', 'label': 'Fable 5.2'},
  {'id': 'claude-opus-5-5', 'label': 'Opus 5.5', 'note': 'default'},
  {'id': 'claude-sonnet-5-5', 'label': 'Sonnet 5.5'},
];

Json _picker({bool enabled = true, String value = 'claude-opus-5-5'}) => {
  ...action('model', enabled: enabled, value: value),
  'choices': _choices,
};

Future<FakeRelay> _open(
  WidgetTester tester,
  Json pick, {
  String column = 'running',
  String status = 'working',
  List<Json> before = const [],
}) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  final c = {
    ...card('c1', column: column, status: status, actions: [...before, pick]),
    'model': 'Opus 5.5', // an older server's label: the app draws none
  };
  relay.push(boardJson([c]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

void main() {
  testWidgets(
    '[T2477] the sheet shows the model only on its button; a tap pins another',
    (tester) async {
      final relay = await _open(tester, _picker());
      expect(find.byKey(const Key('card-model')), findsNothing);
      expect(
        find.text('Opus 5.5'),
        findsOneWidget,
      ); // its button, no label beside it
      expect(find.byKey(const ValueKey('action-model')), findsNothing);
      final pinned = tester.widget<ChoiceChip>(
        find.byKey(const ValueKey('model-claude-opus-5-5')),
      );
      expect(pinned.selected, isTrue);
      await tester.tap(find.byKey(const ValueKey('model-claude-fable-5-2')));
      await tester.pumpAndSettle();
      expect(relay.sent.single.$1, 'task_model');
      expect(relay.sent.single.$2, {
        'card': 'c1',
        'args': {'model': 'claude-fable-5-2'},
      });
    },
  );

  testWidgets('[T2470] the default model carries the default glyph inline', (
    tester,
  ) async {
    await _open(tester, _picker(value: 'claude-sonnet-5-5'));
    expect(find.byKey(const ValueKey('model-default')), findsNothing);
    final opus = find.byKey(const ValueKey('model-claude-opus-5-5'));
    expect(
      find.descendant(of: opus, matching: find.byIcon(Icons.auto_mode)),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.auto_mode), findsOneWidget);
    final sonnet = tester.widget<ChoiceChip>(
      find.byKey(const ValueKey('model-claude-sonnet-5-5')),
    );
    expect(sonnet.selected, isTrue);
  });

  testWidgets('[T2477] the detail overview shows no model', (tester) async {
    await pumpDetail(
      tester,
      detail: {
        'card': {...card('c1'), 'model': 'claude-fable-5-2'},
      },
    );
    expect(find.byKey(const Key('detail-model')), findsNothing);
    expect(find.text('claude-fable-5-2'), findsNothing);
  });

  testWidgets('[T2478] a Backlog card offers the picker beside Start', (
    tester,
  ) async {
    final relay = await _open(
      tester,
      _picker(),
      column: 'backlog',
      status: 'backlog',
      before: [action('start')],
    );
    expect(find.byKey(const ValueKey('action-start')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('model-claude-sonnet-5-5')));
    await tester.pumpAndSettle();
    expect(relay.sent.single.$1, 'task_model');
  });

  testWidgets('[T2220] a disabled picker sends nothing', (tester) async {
    final relay = await _open(tester, _picker(enabled: false));
    await tester.tap(find.byKey(const ValueKey('model-claude-opus-5-5')));
    await tester.pumpAndSettle();
    expect(relay.sent, isEmpty);
  });
}
