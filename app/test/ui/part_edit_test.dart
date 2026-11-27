import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/fakes.dart';

const Json _open = {'enabled': true, 'reason': null};
const Json _done = {'enabled': false, 'reason': 'ticked: Ship closes it'};

Json _part(String id, String title, Json edit, {String? body}) => {
  'id': id,
  'title': title,
  'state': 'todo',
  'steps': null,
  'edit': edit,
  'body': ?body,
};

final List<Json> _parts = [
  _part('aaaa1111-0', 'Old title', _open),
  _part('aaaa1111-1', 'Shipped', _done),
];

/// Pumps a board with one backlog repo card holding [_parts], opens its sheet.
Future<FakeRelay> _sheet(WidgetTester tester, {List<Json>? parts}) async {
  pixel6a(tester);
  final relay = FakeRelay();
  relay.outcomes['task_detail'] = RelayOk({
    'card': {
      'parts': [
        _part('aaaa1111-0', 'Old title', _open, body: 'old text'),
        _part('aaaa1111-1', 'Shipped', _done, body: 'x'),
      ],
    },
  });
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  relay.push(boardJson([card('c1')..['parts'] = parts ?? _parts]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

Finder _key(String k) => find.byKey(ValueKey(k));

String? _name(WidgetTester tester, String id) =>
    tester.widget<Text>(_key('part-name-$id')).data;

void main() {
  testWidgets('a pencil per part; a locked one says why and cannot open', (
    tester,
  ) async {
    final relay = await _sheet(tester);
    final locked = tester.widget<IconButton>(_key('part-edit-aaaa1111-1'));
    expect(locked.onPressed, isNull);
    expect(
      find.bySemanticsLabel('Edit Shipped: ticked: Ship closes it'),
      findsOneWidget,
    );
    expect(
      tester.widget<IconButton>(_key('part-edit-aaaa1111-0')).onPressed,
      isNotNull,
    );
    expect(_name(tester, 'aaaa1111-0'), 'Old title');
    expect(relay.sent, isEmpty);
  });

  testWidgets('opens prefilled from the detail, shows the title at once', (
    tester,
  ) async {
    final relay = await _sheet(tester);
    await tester.tap(_key('part-edit-aaaa1111-0'));
    await tester.pumpAndSettle();
    expect(relay.sent.single.$1, 'task_detail');
    final title = tester.widget<TextField>(_key('part-title-aaaa1111-0'));
    final body = tester.widget<TextField>(_key('part-body-aaaa1111-0'));
    expect(
      [title.controller!.text, body.controller!.text],
      ['Old title', 'old text'],
    );
    await tester.enterText(_key('part-title-aaaa1111-0'), 'New title');
    await tester.enterText(_key('part-body-aaaa1111-0'), 'new text');
    relay.gate = Completer<void>();
    await tester.tap(_key('part-save-aaaa1111-0'));
    await tester.pump();
    expect(_name(tester, 'aaaa1111-0'), 'New title');
    expect(
      find.byWidgetPredicate(
        (w) => w is CircularProgressIndicator && w.value == null,
      ),
      findsOneWidget,
    );
    relay.gate!.complete();
    await tester.pumpAndSettle();
    expect(relay.sent.last.$1, 'task_part_edit');
    expect(relay.sent.last.$2, {
      'card': 'c1',
      'args': {'part': 'aaaa1111-0', 'title': 'New title', 'body': 'new text'},
    });
    expect(_key('part-title-aaaa1111-0'), findsNothing);
    expect(_name(tester, 'aaaa1111-0'), 'New title');
  });

  testWidgets('a refusal puts the old title back and shows its glyph', (
    tester,
  ) async {
    final relay = await _sheet(tester);
    relay.outcomes['task_part_edit'] = const RelayFailed(
      code: 'disabled',
      error: 'the run is on this part',
    );
    await tester.tap(_key('part-edit-aaaa1111-0'));
    await tester.pumpAndSettle();
    await tester.enterText(_key('part-title-aaaa1111-0'), 'Nope');
    await tester.tap(_key('part-save-aaaa1111-0'));
    await tester.pumpAndSettle();
    expect(_name(tester, 'aaaa1111-0'), 'Old title');
    expect(_key('part-failure'), findsOneWidget);
    expect(_key('part-title-aaaa1111-0'), findsOneWidget);
  });

  testWidgets('an empty title sends nothing; cancel closes the editor', (
    tester,
  ) async {
    final relay = await _sheet(tester);
    await tester.tap(_key('part-edit-aaaa1111-0'));
    await tester.pumpAndSettle();
    await tester.enterText(_key('part-title-aaaa1111-0'), '  ');
    await tester.tap(_key('part-save-aaaa1111-0'));
    await tester.pumpAndSettle();
    expect(relay.sent.map((s) => s.$1), ['task_detail']);
    await tester.tap(_key('part-cancel-aaaa1111-0'));
    await tester.pumpAndSettle();
    expect(_key('part-title-aaaa1111-0'), findsNothing);
  });

  testWidgets('a detail that does not come opens no editor', (tester) async {
    final relay = await _sheet(tester);
    relay.outcomes['task_detail'] = const RelayFailed(
      code: 'timeout',
      error: 'no task_detail',
      retry: true,
    );
    await tester.tap(_key('part-edit-aaaa1111-0'));
    await tester.pumpAndSettle();
    expect(_key('part-title-aaaa1111-0'), findsNothing);
    expect(_key('part-failure'), findsOneWidget);
  });

  testWidgets(
    '[T2614] shows the title without image markdown, edits the source',
    (tester) async {
      const source =
          'Fix ![](https://kuhy-cloud.duckdns.org/todo-images/f1/1.jpg)';
      await _sheet(
        tester,
        parts: [
          {..._part('aaaa1111-0', 'Fix', _open), 'title_source': source},
          _part('aaaa1111-1', 'Shipped', _done),
        ],
      );
      expect(_name(tester, 'aaaa1111-0'), 'Fix');
      await tester.tap(_key('part-edit-aaaa1111-0'));
      await tester.pumpAndSettle();
      final title = tester.widget<TextField>(_key('part-title-aaaa1111-0'));
      expect(title.controller!.text, source);
    },
  );

  testWidgets(
    '[T2619] a saved source shows the server title, not image markdown',
    (tester) async {
      const source =
          'Fix ![](https://kuhy-cloud.duckdns.org/todo-images/f1/1.jpg)';
      final relay = await _sheet(
        tester,
        parts: [
          {..._part('aaaa1111-0', 'Fix', _open), 'title_source': source},
          _part('aaaa1111-1', 'Shipped', _done),
        ],
      );
      relay.outcomes['task_part_edit'] = const RelayOk({});
      await tester.tap(_key('part-edit-aaaa1111-0'));
      await tester.pumpAndSettle();
      await tester.tap(_key('part-save-aaaa1111-0'));
      await tester.pumpAndSettle();
      expect(relay.sent.last.$1, 'task_part_edit');
      expect(_name(tester, 'aaaa1111-0'), 'Fix'); // live C12p: stayed raw
    },
  );
}
