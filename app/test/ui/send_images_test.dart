// T2332-T2336: the note box (drawer page and card sheet) and the new-task
// sheet take images from the gallery, the camera or a paste as #N chips
// that put `[Image #N]` at the caret, and send them as inline `{data_b64}`.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

final Uint8List _png = base64Decode(tinyPng);
final Uint8List _png2 = Uint8List.fromList([..._png, 7]);
final Uint8List _heic = Uint8List.fromList([
  0,
  0,
  0,
  24,
  ...'ftypheic'.codeUnits,
]);
Json _ref(Uint8List b) => {'data_b64': base64Encode(b)};

/// Swaps the platform picker for one that answers [out] and records calls.
List<(PickFrom, int)> _fakePicker(List<Uint8List> Function() out) {
  final calls = <(PickFrom, int)>[];
  imagePicker = (from, room) async {
    calls.add((from, room));
    return out();
  };
  addTearDown(() => imagePicker = pickImages);
  return calls;
}

Finder _key(String k) => find.byKey(Key(k));
Finder _chip(String prefix, int n) => find.byKey(ValueKey('$prefix-image-$n'));

Json _sendDetail() => {
  ...richDetail(),
  'ask_items': <Json>[],
  'card': card('c1', status: 'working', actions: [action('send')]),
};

Future<FakeRelay> _board(WidgetTester tester, Json c, {double kb = 0}) async {
  pixel6a(tester, keyboard: kb);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SafeArea(child: BoardPage(relay: relay)),
      ),
    ),
  );
  relay.push(boardJson([c]));
  await settle(tester);
  return relay;
}

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pump();
  await tester.tap(f);
  await settle(tester);
}

void main() {
  testWidgets('[T2332] note box: pick, remove renumbers, send clears', (
    tester,
  ) async {
    final calls = _fakePicker(() => [_png, _png2]);
    final relay = await pumpDetail(tester, detail: _sendDetail());
    await seek(tester, _key('detail-gallery'), 300);
    await hit(tester, _key('detail-gallery'));
    expect(calls.single, (PickFrom.gallery, 8));
    expect(_chip('detail', 2), findsOneWidget);
    final box = _key('detail-send-text');
    expect(
      tester.widget<TextField>(box).controller!.text,
      '[Image #1] [Image #2] ',
    );
    await hit(
      tester,
      find.descendant(
        of: _chip('detail', 1),
        matching: find.byIcon(Icons.close),
      ),
    );
    expect(_chip('detail', 2), findsNothing);
    expect(tester.widget<TextField>(box).controller!.text, '[Image #1] ');
    relay.outcomes['task_send'] = const RelayFailed(
      code: 'disabled',
      error: 'x',
    );
    await hit(tester, _key('detail-send'));
    expect(_chip('detail', 1), findsOneWidget);
    relay.outcomes.remove('task_send');
    await hit(tester, _key('detail-send'));
    expect(relay.sent.lastWhere((s) => s.$1 == 'task_send').$2, {
      'card': 'c1',
      'args': {
        'text': '[Image #1]',
        'images': [_ref(_png2)],
      },
    });
    expect(_chip('detail', 1), findsNothing);
    expect(tester.widget<TextField>(box).controller!.text, isEmpty);
  });

  testWidgets('[T2333] card sheet: a photo goes with the note', (tester) async {
    final calls = _fakePicker(() => [_png]);
    final relay = await _board(
      tester,
      card(
        'c1',
        column: 'needs_you',
        status: 'needs_you',
        actions: [action('send')],
      ),
    );
    await tester.tap(find.byKey(const ValueKey('card-c1')));
    await settle(tester);
    await tester.enterText(_key('send-text'), 'see');
    await _tap(tester, _key('sheet-camera'));
    expect(calls.single, (PickFrom.camera, 8));
    expect(_chip('sheet', 1), findsOneWidget);
    await _tap(tester, find.byKey(const ValueKey('action-send')));
    expect(relay.sent.single.$2, {
      'card': 'c1',
      'args': {
        'text': 'see [Image #1]',
        'images': [_ref(_png)],
      },
    });
  });

  testWidgets('[T2334] new task: images ride in new_task, tags in the body', (
    tester,
  ) async {
    _fakePicker(() => [_png]);
    final relay = await _board(tester, card('a1', repo: 'kuhyx/demo'));
    await tester.tap(_key('new-task'));
    await settle(tester);
    await tester.enterText(_key('nt-repo'), 'kuhyx/demo');
    await tester.enterText(_key('nt-title'), 'Logo');
    await tester.enterText(_key('nt-body'), 'like this');
    await _tap(tester, _key('nt-gallery'));
    await _tap(tester, _key('nt-send'));
    expect(relay.sent.single.$2, {
      'args': {
        'repo': 'kuhyx/demo',
        'title': 'Logo',
        'body': 'like this [Image #1] ',
        'images': [_ref(_png)],
      },
    });
  });

  testWidgets('[T2335] a refused image or a failed picker shows its glyph', (
    tester,
  ) async {
    var answer = () => [_heic];
    _fakePicker(() => answer());
    await _board(tester, card('a1', repo: 'kuhyx/demo'));
    await tester.tap(_key('new-task'));
    await settle(tester);
    await _tap(tester, _key('nt-gallery'));
    final problem = _key('nt-image-problem');
    expect(tester.widget<Icon>(problem).icon, Icons.broken_image_outlined);
    expect(tester.widget<Icon>(problem).semanticLabel, contains('PNG'));
    expect(_chip('nt', 1), findsNothing);
    answer = () => throw PlatformException(code: 'camera_access_denied');
    await _tap(tester, _key('nt-camera'));
    expect(tester.widget<Icon>(problem).icon, Icons.no_photography_outlined);
  });

  testWidgets('[T2337] a slow pick or shrink shows a loader until done', (
    tester,
  ) async {
    final picked = Completer<List<Uint8List>>();
    imagePicker = (_, _) => picked.future;
    addTearDown(() => imagePicker = pickImages);
    await _board(tester, card('a1', repo: 'kuhyx/demo'));
    await tester.tap(_key('new-task'));
    await settle(tester);
    final busy = _key('nt-image-busy');
    expect(busy, findsNothing);
    await tester.tap(_key('nt-gallery'));
    await tester.pump();
    expect(busy, findsOneWidget);
    picked.complete([_png]);
    await settle(tester);
    expect(busy, findsNothing);
    expect(_chip('nt', 1), findsOneWidget);
    final shrunk = Completer<Uint8List?>();
    final paste = ImageAttach(
      TextEditingController(),
      shrink: (_, _) => shrunk.future,
    );
    final added = paste.add(_png);
    expect(paste.busy, isTrue);
    shrunk.complete(_png);
    await added;
    expect(paste.busy, isFalse);
  });

  for (final (name, open) in [
    ('new task', (WidgetTester t) => t.tap(_key('new-task'))),
    (
      'card sheet',
      (WidgetTester t) => t.tap(find.byKey(const ValueKey('card-a1'))),
    ),
  ]) {
    testWidgets('[T2336] $name: 8 chips and the keyboard keep send visible', (
      tester,
    ) async {
      _fakePicker(() => List.filled(8, _png));
      await _board(
        tester,
        card('a1', repo: 'kuhyx/demo', actions: [action('send')]),
        kb: 300 * 2.625,
      );
      await open(tester);
      await settle(tester);
      final prefix = name == 'new task' ? 'nt' : 'sheet';
      await _tap(tester, _key('$prefix-gallery'));
      expect(_chip(prefix, 8), findsOneWidget);
      final send = name == 'new task'
          ? _key('nt-send')
          : find.byKey(const ValueKey('action-send'));
      await tester.ensureVisible(send);
      await tester.pump();
      final keyboardTop = 2400 / 2.625 - 300;
      expect(tester.getRect(send).bottom, lessThanOrEqualTo(keyboardTop));
      expect(tester.takeException(), isNull);
    });
  }
}
