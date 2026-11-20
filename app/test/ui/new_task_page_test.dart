// T2349-T2352: add task fills the screen, has no title field (the first
// line is the title), a repo chooser (none, all, some) that folds once
// picked, and the send button in the image row.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/new_task_sheet.dart';

import '../support/fakes.dart';

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

Finder _key(String k) => find.byKey(Key(k));

Future<FakeRelay> _open(WidgetTester tester, {String? filter}) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: SafeArea(child: BoardPage(relay: relay))),
    ),
  );
  relay.push(
    boardJson([
      card('a1', repo: 'kuhyx/demo'),
      card('o1', repo: 'kuhyx/other'),
    ]),
  );
  await _settle(tester);
  if (filter != null) {
    await tester.tap(_key('repo'));
    await _settle(tester);
    await tester.tap(find.text(filter).last);
    await _settle(tester);
  }
  await tester.tap(_key('new-task'));
  await _settle(tester);
  return relay;
}

List<Json> _args(FakeRelay r) => [
  for (final (k, b) in r.sent)
    if (k == 'new_task') b['args'] as Json,
];

void main() {
  test('[T2350] the first line is the title, the rest the body', () {
    expect(splitNote('  Fix it \nmore\n\nlines '), ('Fix it', 'more\n\nlines'));
    expect(splitNote('\n\nOnly'), ('Only', ''));
    expect(splitNote('x' * 300).$1.length, 200);
    expect(newTaskValid('Fix it'), isTrue);
    expect(newTaskValid(' \n '), isFalse);
  });

  testWidgets('[T2349] add task covers the whole screen, the box fills it', (
    tester,
  ) async {
    await _open(tester);
    final screen = tester.getRect(find.byType(NewTaskSheet));
    expect(screen.height, closeTo(2400 / 2.625, 1));
    expect(tester.getSize(_key('nt-body')).height, greaterThan(400));
    expect(_key('nt-title'), findsNothing); // T2350
  });

  testWidgets('[T2351] picking one repo folds the chooser; tap reopens', (
    tester,
  ) async {
    final relay = await _open(tester);
    expect(_key('nt-repos'), findsOneWidget);
    expect(tester.widget<IconButton>(_key('nt-send')).onPressed, isNull);
    await tester.tap(_key('nt-repo-kuhyx/demo'));
    await tester.pump();
    await tester.tap(_key('nt-repos-done'));
    await _settle(tester);
    expect(_key('nt-repos'), findsNothing);
    expect(_key('nt-repos-folded'), findsOneWidget);
    await tester.enterText(_key('nt-body'), 'Fix it\nmore');
    await _settle(tester);
    await tester.tap(_key('nt-send'));
    await _settle(tester);
    expect(_args(relay), [
      {'repo': 'kuhyx/demo', 'title': 'Fix it', 'body': 'more'},
    ]);
    expect(find.byType(NewTaskSheet), findsNothing);
  });

  testWidgets('[T2351] the board filter counts as picked; tap reopens it', (
    tester,
  ) async {
    await _open(tester, filter: 'other');
    expect(_key('nt-repos'), findsNothing);
    await tester.tap(_key('nt-repos-folded'));
    await _settle(tester);
    expect(_key('nt-repos'), findsOneWidget);
  });

  testWidgets('[T2351] some repos: one new_task each, a refusal stops', (
    tester,
  ) async {
    final relay = await _open(tester);
    await tester.tap(_key('nt-repo-kuhyx/demo'));
    await tester.tap(_key('nt-repo-kuhyx/other'));
    await tester.tap(_key('nt-repos-done'));
    await tester.enterText(_key('nt-body'), 'Same fix');
    await _settle(tester);
    relay.outcomes['new_task'] = const RelayFailed(code: 'conflict', error: 'x');
    await tester.tap(_key('nt-send'));
    await _settle(tester);
    expect(_key('nt-failure'), findsOneWidget);
    expect(_args(relay).length, 1);
    relay.outcomes.remove('new_task');
    await tester.tap(_key('nt-send'));
    await _settle(tester);
    expect([for (final a in _args(relay)) a['repo']], [
      'kuhyx/demo',
      'kuhyx/demo',
      'kuhyx/other',
    ]);
  });

  for (final (pick, want) in [
    ('none', <Object?>[null]),
    ('all', <Object?>['kuhyx/demo', 'kuhyx/other']),
  ]) {
    testWidgets('[T2351] $pick folds at once and sends $want', (tester) async {
      final relay = await _open(tester);
      await tester.tap(_key('nt-repo-$pick'));
      await _settle(tester);
      expect(_key('nt-repos'), findsNothing);
      await tester.enterText(_key('nt-body'), 'Idea');
      await _settle(tester);
      await tester.tap(_key('nt-send'));
      await _settle(tester);
      expect([for (final a in _args(relay)) a['repo']], want);
    });
  }

  testWidgets('[T2352] send sits in the image buttons row', (tester) async {
    await _open(tester, filter: 'other');
    final send = tester.getRect(_key('nt-send'));
    final gallery = tester.getRect(_key('nt-gallery'));
    expect(send.center.dy, closeTo(gallery.center.dy, 1));
  });
}
