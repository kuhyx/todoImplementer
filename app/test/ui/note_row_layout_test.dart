// T2339: the gallery and camera buttons sit in the text field's row (send
// on the right) so a phone shows them without scrolling; chips go above.
import 'dart:convert';
import 'dart:typed_data';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _screen = Rect.fromLTWH(0, 0, 540, 1200);
final Uint8List _png = base64Decode(tinyPng);

Finder _key(String k) => find.byKey(Key(k));

void _phone(WidgetTester tester) {
  tester.view
    ..physicalSize = const Size(1080, 2400)
    ..devicePixelRatio = 2
    ..padding = FakeViewPadding.zero
    ..viewInsets = FakeViewPadding.zero;
  addTearDown(tester.view.reset);
}

/// Asserts the row of [prefix]: buttons on screen, hit-testable, left of
/// the field, level with it.
void _expectRow(WidgetTester tester, String prefix, String field) {
  final box = tester.getRect(_key(field));
  for (final b in ['gallery', 'camera']) {
    final f = _key('$prefix-$b');
    expect(f.hitTestable(), findsOneWidget, reason: '$prefix-$b hit-testable');
    final r = tester.getRect(f);
    expect(_screen.contains(r.topLeft), isTrue, reason: '$b top-left');
    expect(_screen.contains(r.bottomRight), isTrue, reason: '$b bottom-right');
    expect(r.right, lessThanOrEqualTo(box.left), reason: '$b left of field');
    expect(r.center.dy, inInclusiveRange(box.top, box.bottom));
  }
}

void main() {
  testWidgets('[T2339] DetailPage: buttons visible, no scrolling', (
    tester,
  ) async {
    _phone(tester);
    imagePicker = (from, room) async => [_png, _png];
    addTearDown(() => imagePicker = pickImages);
    await pumpDetail(
      tester,
      detail: {
        ...richDetail(),
        'card': card('c1', status: 'working', actions: [action('send')]),
      },
    );
    await settle(tester);
    // Not seek/ensureVisible: the buttons must already be on screen.
    _expectRow(tester, 'detail', 'detail-send-text');
    final send = tester.getRect(_key('detail-send'));
    final box = tester.getRect(_key('detail-send-text'));
    expect(send.left, greaterThanOrEqualTo(box.right));
    expect(_screen.contains(send.bottomRight), isTrue);
    await tester.tap(_key('detail-gallery'));
    await settle(tester);
    final chip = tester.getRect(find.byKey(const ValueKey('detail-image-1')));
    expect(
      chip.bottom,
      lessThanOrEqualTo(tester.getRect(_key('detail-gallery')).top),
    );
    _expectRow(tester, 'detail', 'detail-send-text');
  });

  testWidgets('[T2339] card sheet: buttons share the text field row', (
    tester,
  ) async {
    _phone(tester);
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
        card('a1', repo: 'kuhyx/demo', actions: [action('send')]),
      ]),
    );
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('card-a1')));
    await settle(tester);
    _expectRow(tester, 'sheet', 'send-text');
  });
}
