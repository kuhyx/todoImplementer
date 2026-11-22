// T2493: the add-task page keeps its draft (text, repo picks, images) when a
// send is refused, the page is closed or the app is killed; only a task that
// went out clears it.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/draft_images.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';
import 'package:todo_implementer/ui/board/new_task_draft.dart';
import 'package:todo_implementer/ui/board/repo_chooser.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _badToken = RelayFailed(code: 'forbidden', error: 'bad token');

Finder _key(String k) => find.byKey(Key(k));

Future<FakeRelay> _board(WidgetTester tester) async {
  imagePicker = (from, room) async => [base64Decode(tinyPng)];
  addTearDown(() => imagePicker = pickImages);
  pixel6a(tester);
  final relay = FakeRelay()..outcomes['new_task'] = _badToken;
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(child: BoardPage(relay: relay)),
      ),
    ),
  );
  relay.push(boardJson([card('a1'), card('o1', repo: 'kuhyx/other')]));
  await settle(tester);
  return relay;
}

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pump();
  await tester.tap(f);
  await settle(tester);
}

/// Opens the page, picks kuhyx/demo, types, adds an image, sends (refused).
Future<FakeRelay> _refused(WidgetTester tester) async {
  final relay = await _board(tester);
  await _tap(tester, _key('new-task'));
  await _tap(tester, _key('nt-repo-kuhyx/demo'));
  await _tap(tester, _key('nt-repos-done'));
  await tester.enterText(_key('nt-body'), 'Logo\nbigger');
  await _tap(tester, _key('nt-gallery'));
  await _tap(tester, _key('nt-send'));
  expect(_key('nt-failure'), findsOneWidget);
  return relay;
}

String _text(WidgetTester tester) =>
    tester.widget<TextField>(_key('nt-body')).controller!.text;

void main() {
  testWidgets('[T2493] a bad-token refusal, a kill and a reopen give back '
      'the text, the picks and the image', (tester) async {
    await _refused(tester);
    // The app is killed: a new widget tree on the same stored draft.
    await tester.pumpWidget(const SizedBox());
    final relay = await _board(tester);
    relay.outcomes.remove('new_task');
    await _tap(tester, _key('new-task'));
    expect(_text(tester), 'Logo\nbigger [Image #1] ');
    expect(_key('nt-image-1'), findsOneWidget);
    expect(_key('nt-repos-folded'), findsOneWidget);
    await _tap(tester, _key('nt-send'));
    final kinds = relay.sent.map((s) => s.$1);
    expect(kinds, ['image_upload', 'new_task']); // the image goes up again
    expect(relay.sent.last.$2['args'], containsPair('repo', 'kuhyx/demo'));
    expect(await newTaskDrafts.load(), isNull); // sent: no draft left
  });

  testWidgets('[T2493] closing keeps the draft; a typed box wins over a '
      'draft that loads late', (tester) async {
    await _refused(tester);
    await _tap(tester, find.byType(CloseButton));
    await _tap(tester, _key('new-task'));
    expect(_text(tester), 'Logo\nbigger [Image #1] ');
    await _tap(tester, find.byType(CloseButton));
    final late = Completer<NewTaskDraft?>();
    newTaskDrafts = _Slow(late.future);
    await _tap(tester, _key('new-task'));
    await tester.enterText(_key('nt-body'), 'Mine');
    late.complete(
      const NewTaskDraft(text: 'Old', scope: RepoScope.all, picked: []),
    );
    await settle(tester);
    expect(_text(tester), 'Mine');
  });

  test(
    '[T2493] the prefs store keeps text and picks, the images apart',
    () async {
      SharedPreferences.setMockInitialValues({});
      final store = PrefsNewTaskDrafts(images: PrefsDraftImages());
      expect(await store.load(), isNull);
      const draft = NewTaskDraft(
        text: 'Fix',
        scope: RepoScope.some,
        picked: ['kuhyx/demo'],
        open: true,
      );
      await store.saveState(draft);
      await store.saveImages([
        Uint8List.fromList([1, 2]),
      ]);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('newtask.draft'), isNot(contains('AQI')));
      final back = await store.load();
      expect(back?.text, 'Fix');
      expect(back?.scope, RepoScope.some);
      expect(back?.picked, ['kuhyx/demo']);
      expect(back?.open, isTrue);
      expect(back?.images.single, [1, 2]);
      await store.clear();
      expect(await store.load(), isNull);
      expect(prefs.getKeys(), isEmpty);
    },
  );

  test(
    '[T2493] bad stored data and a failing store read as no draft',
    () async {
      SharedPreferences.setMockInitialValues({'newtask.draft': '{"text": 1}'});
      expect(await PrefsNewTaskDrafts().load(), isNull);
      SharedPreferences.setMockInitialValues({
        'newtask.draft': '{"text": "T", "scope": "odd", "picked": [3]}',
      });
      final odd = await PrefsNewTaskDrafts().load();
      expect((odd?.text, odd?.scope), ('T', null));
      expect(odd?.picked, isEmpty);
      expect(odd?.images, isEmpty); // no support directory in a test
      Future<SharedPreferences> fail() => Future.error(StateError('no prefs'));
      final broken = PrefsNewTaskDrafts(
        prefs: fail,
        images: PrefsDraftImages(prefs: fail),
      );
      expect(await broken.load(), isNull);
      await broken.saveState(const NewTaskDraft(text: 'x', picked: []));
      await broken.saveImages(const []);
      await broken.clear();
    },
  );
}

class _Slow extends MemoryNewTaskDrafts {
  _Slow(this._later);

  final Future<NewTaskDraft?> _later;

  @override
  Future<NewTaskDraft?> load() => _later;
}
