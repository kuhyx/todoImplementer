import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/card_sheet.dart';

import '../support/fakes.dart';

void _sent((String, Json) got, String kind, Json body) {
  expect(got.$1, kind);
  expect(got.$2, body);
}

Json _needs(String category, {String? command}) => {
  'kind': 'spec_questions',
  'text': 'needs it',
  'category': category,
  'effort': 1,
  'command': ?command,
};

/// Pumps a board with one card [c] in Needs you and opens its sheet.
Future<FakeRelay> _open(WidgetTester tester, Json c) async {
  pixel6a(tester);
  final relay = FakeRelay();
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  relay.push(boardJson([c]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(ValueKey('card-${c['id']}')));
  await tester.pumpAndSettle();
  return relay;
}

Json _card(List<Json> actions, {Json? needs}) => card(
  'c1',
  column: 'needs_you',
  status: 'needs_you',
  needs: needs ?? _needs('action'),
  actions: actions,
);

void main() {
  test('kind of an action id', () {
    expect(kindOf('spec-ok'), 'task_spec_ok');
    expect(kindOf('lesson-approve'), 'task_lesson_approve');
  });

  testWidgets('start sends auto_ship and closes on success', (tester) async {
    final relay = await _open(
      tester,
      _card([action('start', option: action('auto_ship'))]),
    );
    expect(find.text('needs it'), findsOneWidget);
    await tester.tap(find.byKey(const Key('auto-ship')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('action-start')));
    await tester.pumpAndSettle();
    _sent(relay.sent.single, 'task_start', {
      'card': 'c1',
      'args': {'auto_ship': true},
    });
    expect(find.byKey(const ValueKey('action-start')), findsNothing);
  });

  testWidgets('start without the option sends no args; spinner while busy', (
    tester,
  ) async {
    final relay = await _open(tester, _card([action('start'), action('go')]));
    relay.gate = Completer<void>();
    await tester.tap(find.byKey(const ValueKey('action-start')));
    await tester.pump();
    // The board's usage rings are determinate indicators too (T2348).
    final spinner = find.byWidgetPredicate(
      (w) => w is CircularProgressIndicator && w.value == null,
    );
    expect(spinner, findsOneWidget);
    relay.gate!.complete();
    await tester.pumpAndSettle();
    expect(relay.sent.single.$2['args'], <String, dynamic>{});
  });

  testWidgets('confirm actions fire on hold only', (tester) async {
    final relay = await _open(tester, _card([action('ship', confirm: true)]));
    await tester.tap(find.byKey(const ValueKey('action-ship')));
    await tester.pump();
    expect(relay.sent, isEmpty);
    await tester.longPress(find.byKey(const ValueKey('action-ship')));
    await tester.pumpAndSettle();
    expect(relay.sent.single.$1, 'task_ship');
  });

  testWidgets('a refusal shows its glyph and stays open', (tester) async {
    final relay = await _open(
      tester,
      _card([
        action('cancel'),
        action('rerun', enabled: false),
      ], needs: _needs('permission', command: 'grant me')),
    );
    expect(find.text('grant me'), findsOneWidget);
    relay.outcomes['task_cancel'] = const RelayFailed(
      code: 'disabled',
      error: 'no',
    );
    await tester.tap(find.byKey(const ValueKey('action-cancel')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sheet-failure')), findsOneWidget);
    // The disabled action carries its block badge and cannot be pressed.
    await tester.tap(find.byKey(const ValueKey('action-rerun')));
    await tester.pump();
    expect(relay.sent.length, 1);
    expect(find.byIcon(Icons.block), findsWidgets);
  });

  testWidgets('copy actions use the clipboard, not the PC', (tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String;
        }
        return null;
      },
    );
    final relay = await _open(
      tester,
      _card([action('copy-resume', value: 'claude -r x'), action('copy-fix')]),
    );
    await tester.tap(find.byKey(const ValueKey('action-copy-resume')));
    await tester.pumpAndSettle();
    expect(copied, 'claude -r x');
    await tester.tap(find.byKey(const ValueKey('action-copy-fix')));
    await tester.pumpAndSettle();
    expect(copied, '');
    expect(relay.sent, isEmpty);
  });

  testWidgets('send needs text, then sends it', (tester) async {
    final relay = await _open(tester, _card([action('send')]));
    await tester.tap(find.byKey(const ValueKey('action-send')));
    await tester.pump();
    expect(relay.sent, isEmpty);
    await tester.enterText(find.byKey(const Key('send-text')), ' hi ');
    await tester.tap(find.byKey(const ValueKey('action-send')));
    await tester.pumpAndSettle();
    _sent(relay.sent.single, 'task_send', {
      'card': 'c1',
      'args': {'text': 'hi'},
    });
  });

  testWidgets('spec answers: load questions, prefill, send', (tester) async {
    final relay =
        await _open(
            tester,
            _card([action('spec-answers')], needs: _needs('questions')),
          )
          ..outcomes['task_detail'] = const RelayOk({
            'questions': [
              {
                'id': 'Q1',
                'title': 'Which?',
                'body': 'Pick one',
                'recommendation': 'A',
                'answer': null,
              },
              {
                'id': 'Q2',
                'title': 'Done?',
                'body': '',
                'recommendation': 'B',
                'answer': 'B',
              },
              {
                'id': 'Q3',
                'title': 'Blank',
                'body': '',
                'recommendation': '',
                'answer': null,
              },
            ],
          });
    await tester.tap(find.byKey(const ValueKey('action-spec-answers')));
    await tester.pumpAndSettle();
    expect(find.text('Which?'), findsOneWidget);
    expect(find.text('Done?'), findsNothing);
    relay.gate = Completer<void>();
    await tester.tap(find.byKey(const Key('answers-send')));
    await tester.pump();
    relay.gate!.complete();
    await tester.pumpAndSettle();
    _sent(relay.sent.last, 'task_spec_answers', {
      'card': 'c1',
      'args': {
        'answers': {'Q1': 'A'},
      },
    });
  });

  testWidgets('spec answers: a failed detail load shows the glyph', (
    tester,
  ) async {
    final relay = await _open(tester, _card([action('spec-answers')]))
      ..outcomes['task_detail'] = const RelayFailed(
        code: 'not_found',
        error: 'gone',
      );
    await tester.tap(find.byKey(const ValueKey('action-spec-answers')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sheet-failure')), findsOneWidget);
    expect(relay.sent.single.$1, 'task_detail');
  });
}
