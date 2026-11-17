/// Shared fixture and gestures for the detail page tests.
library;

import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/detail_page.dart';
import 'package:todo_implementer/ui/board/shot_image.dart';

import '../model/detail_test.dart' show fullDetail;
import 'fakes.dart';

// A 1x1 transparent PNG.
const tinyPng =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

Json askJson(
  String id,
  String type, {
  String state = 'open',
  Json extra = const {},
}) => {'id': id, 'type': type, 'title': 'ask $id', 'state': state, ...extra};

Json richDetail() => {
  ...fullDetail(),
  'card': card(
    'c1',
    needs: {
      'kind': 'phone',
      'text': 'plug it',
      'category': 'phone',
      'effort': 1,
      'command': 'adb devices',
    },
  ),
  'ask_items': [
    askJson(
      'ch',
      'choice',
      extra: {
        'risk': 'reversible',
        'options': ['yes', 'no'],
        'recommended': 'yes',
      },
    ),
    askJson(
      'rk',
      'choice',
      extra: {
        'options': ['go', 'stop'],
      },
    ),
    askJson('au', 'choice', state: 'auto', extra: {'answer': 'yes'}),
    askJson('an', 'choice', state: 'answered', extra: {'answer': 'no'}),
    askJson(
      'cm',
      'command',
      extra: {'risk': 'reversible', 'command': 'ls', 'mode': 'run'},
    ),
    askJson('ad', 'command', extra: {'command': 'rm x', 'mode': 'add_run'}),
    askJson('tm', 'command', extra: {'command': 'sudo x', 'mode': 'terminal'}),
    askJson(
      'dn',
      'command',
      state: 'done',
      extra: {
        'command': 'false',
        'result': {'exit': 1, 'tail': 'fail'},
      },
    ),
    askJson('sh', 'screenshot', extra: {'shot': 'a.png'}),
    askJson('ap', 'screenshot', state: 'approved'),
    askJson('rj', 'screenshot', state: 'rejected', extra: {'shot': 'bad.png'}),
  ],
  'umbrella': {
    'round': 2,
    'width': 3,
    'rows': [
      {
        'id': 'k1',
        'title': 'child',
        'repo': 'kuhyx/a',
        'status': 'done',
        'verdict': 'clean',
      },
      {'id': 'k2', 'status': 'working'},
    ],
  },
};

Future<FakeRelay> pumpDetail(
  WidgetTester tester, {
  Json? detail,
  RelayOutcome? outcome,
}) async {
  pixel6a(tester);
  final relay = FakeRelay()
    ..outcomes['task_detail'] = outcome ?? RelayOk(detail ?? richDetail())
    ..outcomes['task_shot'] = const RelayOk({'png_b64': tinyPng})
    ..outcomes['task_issues'] = const RelayOk({'text': '{"a":1}\n{"b":2}\n'});
  final errors = <RelayFailed>[];
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: DetailPage(card: 'c1', relay: relay, onError: errors.add),
    ),
  );
  await tester.pump();
  return relay;
}

final downScroll = find.byWidgetPredicate(
  (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
);

Future<void> seek(WidgetTester tester, Finder f, [double d = 200]) =>
    tester.scrollUntilVisible(f, d, scrollable: downScroll.first);

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

/// Brings [f] on screen, then taps (or long-presses) it.
Future<void> hit(WidgetTester tester, Finder f, {bool long = false}) async {
  await tester.ensureVisible(f);
  await settle(tester);
  await (long ? tester.longPress(f) : tester.tap(f));
  await settle(tester);
}

List<String> kinds(FakeRelay r) => [for (final (k, _) in r.sent) k];

Future<void> openTab(WidgetTester tester, IconData icon) async {
  await hit(
    tester,
    find.descendant(of: find.byType(TabBar), matching: find.byIcon(icon)),
  );
}
