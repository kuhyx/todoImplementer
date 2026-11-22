// T2472: a note whose image upload fails is not sent; the sheet stays open
// for a retry (card sheet and new-task sheet).
import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _down = RelayFailed(code: 'offline', error: 'down', retry: true);

Finder _key(String k) => find.byKey(Key(k));

Future<FakeRelay> _board(WidgetTester tester, Json c) async {
  imagePicker = (from, room) async => [base64Decode(tinyPng)];
  addTearDown(() => imagePicker = pickImages);
  pixel6a(tester);
  final relay = FakeRelay()..outcomes['image_upload'] = _down;
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
  testWidgets('[T2472] card sheet: a failed upload sends no note', (
    tester,
  ) async {
    final relay = await _board(tester, card('c1', actions: [action('send')]));
    await tester.tap(find.byKey(const ValueKey('card-c1')));
    await settle(tester);
    await tester.enterText(_key('send-text'), 'see');
    await _tap(tester, _key('sheet-gallery'));
    await _tap(tester, find.byKey(const ValueKey('action-send')));
    expect(relay.sent.map((s) => s.$1), ['image_upload']);
  });

  testWidgets('[T2472] new task: a failed upload sends no note', (
    tester,
  ) async {
    final relay = await _board(tester, card('a1'));
    await tester.tap(_key('new-task'));
    await settle(tester);
    await tester.tap(_key('nt-repo-kuhyx/demo'));
    await tester.tap(_key('nt-repos-done'));
    await tester.enterText(_key('nt-body'), 'Logo');
    await _tap(tester, _key('nt-gallery'));
    await _tap(tester, _key('nt-send'));
    expect(relay.sent.map((s) => s.$1), ['image_upload']);
    expect(_key('nt-send'), findsOneWidget);
  });
}
