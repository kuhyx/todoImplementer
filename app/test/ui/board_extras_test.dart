import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/merges.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/detail_page.dart';
import 'package:todo_implementer/ui/board/new_task_sheet.dart';

import '../support/fakes.dart';

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

Future<FakeRelay> _pump(WidgetTester tester) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(child: BoardPage(relay: relay)),
      ),
    ),
  );
  relay.push(
    boardJson([
      card('a1', repo: 'kuhyx/demo'),
      card('y1', repo: null),
      card('o1', repo: 'kuhyx/other'),
    ]),
  );
  await _settle(tester);
  return relay;
}

List<String> _kinds(FakeRelay r) => [for (final (k, _) in r.sent) k];

void main() {
  test('newTaskValid follows the schema', () {
    expect(newTaskValid('kuhyx/demo', 'Fix it'), isTrue);
    expect(newTaskValid('demo', 'Fix it'), isFalse);
    expect(newTaskValid('kuhyx/demo', '  '), isFalse);
    expect(newTaskValid('kuhyx/demo', 'a\nb'), isFalse);
    expect(newTaskValid('kuhyx/demo', 'x' * 201), isFalse);
  });

  testWidgets('repo groups show for every sort but least effort', (
    tester,
  ) async {
    await _pump(tester);
    expect(find.byKey(const ValueKey('group-kuhyx/demo')), findsNothing);
    await tester.tap(find.byKey(const Key('sort')));
    await _settle(tester);
    await tester.tap(find.byIcon(Icons.sort_by_alpha).last);
    await _settle(tester);
    expect(find.byKey(const ValueKey('group-kuhyx/demo')), findsOneWidget);
    expect(find.byKey(const ValueKey('group-__yours__')), findsOneWidget);
  });

  testWidgets('merge strip: dismiss taps, merge long-presses, refusals', (
    tester,
  ) async {
    final relay = await _pump(tester);
    expect(find.byKey(const Key('merge-strip')), findsNothing);
    relay.mergesOut.add(
      mergesOf({
        'suggestions': [mergeJson('abcdefabcdef')],
      }),
    );
    await _settle(tester);
    expect(find.byKey(const Key('merge-strip')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('action-dismiss')));
    await _settle(tester);
    relay.outcomes['merge_merge'] = const RelayFailed(
      code: 'disabled',
      error: 'no',
    );
    await tester.longPress(find.byKey(const ValueKey('action-merge')));
    await _settle(tester);
    expect(_kinds(relay), ['merge_dismiss', 'merge_merge']);
    expect(relay.sent.first.$2['group'], 'abcdefabcdef');
    expect(find.byKey(const Key('board-failure')), findsOneWidget);
  });

  testWidgets('new task: filtered repo prefilled, sends, refusal shows', (
    tester,
  ) async {
    final relay = await _pump(tester);
    await tester.tap(find.byKey(const Key('repo')));
    await _settle(tester);
    await tester.tap(find.text('other').last);
    await _settle(tester);
    await tester.tap(find.byKey(const Key('new-task')));
    await _settle(tester);
    final send = find.byKey(const Key('nt-send'));
    expect(tester.widget<IconButton>(send).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('nt-title')), 'Do it');
    await tester.enterText(find.byKey(const Key('nt-body')), 'more');
    await _settle(tester);
    relay.outcomes['new_task'] = const RelayFailed(code: 'offline', error: 'x');
    await tester.tap(send);
    await _settle(tester);
    expect(find.byKey(const Key('nt-failure')), findsOneWidget);
    expect(relay.sent.last.$2, {
      'args': {'repo': 'kuhyx/other', 'title': 'Do it', 'body': 'more'},
    });
    relay.outcomes.remove('new_task');
    await tester.enterText(find.byKey(const Key('nt-repo')), 'kuhyx/de');
    await _settle(tester);
    await tester.tap(find.text('kuhyx/demo').last);
    await tester.enterText(find.byKey(const Key('nt-body')), ' ');
    await _settle(tester);
    await tester.tap(send);
    await _settle(tester);
    expect(relay.sent.last.$2, {
      'args': {'repo': 'kuhyx/demo', 'title': 'Do it'},
    });
    expect(find.byKey(const Key('nt-send')), findsNothing);
  });

  testWidgets('a card sheet opens the full detail page', (tester) async {
    final relay = await _pump(tester);
    relay.outcomes['task_detail'] = RelayOk({'card': card('a1')});
    await tester.tap(find.byKey(const ValueKey('card-a1')));
    await _settle(tester);
    await tester.tap(find.byKey(const Key('open-detail')));
    await _settle(tester);
    expect(find.byType(DetailPage), findsOneWidget);
    expect(_kinds(relay), contains('task_detail'));
  });
}
