import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/shot_image.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

void main() {
  testWidgets('overview: needs, error, lesson, umbrella and every ask', (
    tester,
  ) async {
    final relay = await pumpDetail(tester);
    expect(find.text('plug it'), findsOneWidget);
    expect(find.byKey(const Key('detail-error')), findsOneWidget);
    await seek(tester, find.byKey(const Key('lesson')), 300);
    await seek(tester, find.byKey(const Key('umbrella')), 300);
    expect(find.byKey(const ValueKey('child-k1')), findsOneWidget);
    expect(find.text('k2'), findsOneWidget);
    await seek(tester, find.byKey(const ValueKey('ask-ch')), -300);
    await hit(tester, find.byKey(const Key('ask-take-recommended')));
    await hit(tester, find.byKey(const ValueKey('ask-opt-ch-yes')));
    await hit(tester, find.byKey(const ValueKey('ask-opt-rk-go')));
    await hit(tester, find.byKey(const ValueKey('ask-opt-rk-go')), long: true);
    await hit(tester, find.byKey(const ValueKey('ask-undo-au')));
    expect(
      kinds(relay),
      containsAllInOrder([
        'task_detail',
        'ask_take_recommended',
        'ask_answer',
        'ask_answer',
        'ask_undo',
      ]),
    );
    expect(kinds(relay).where((k) => k == 'ask_answer').length, 2);
    final answer = relay.sent.firstWhere((s) => s.$1 == 'ask_answer').$2;
    expect(answer, {
      'card': 'c1',
      'args': {'ask': 'ch', 'option': 'yes'},
    });
  });

  testWidgets('commands run, copy, show results; shots approve and reject', (
    tester,
  ) async {
    final relay = await pumpDetail(tester);
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
    for (final key in [
      'ask-run-cm',
      'ask-copy-tm',
      'ask-approve-sh',
      'ask-reject-sh',
    ]) {
      await seek(tester, find.byKey(ValueKey(key)), 200);
      await hit(tester, find.byKey(ValueKey(key)));
    }
    await seek(tester, find.byKey(const ValueKey('ask-run-ad')), -200);
    await hit(tester, find.byKey(const ValueKey('ask-run-ad')), long: true);
    await settle(tester);
    expect(copied, 'sudo x');
    expect(find.byKey(const ValueKey('ask-run-tm')), findsNothing);
    expect(find.text('fail'), findsOneWidget);
    expect(
      kinds(relay),
      containsAll(['ask_run', 'ask_approve', 'ask_reject', 'task_shot']),
    );
    final runs = relay.sent
        .where((s) => s.$1 == 'ask_run')
        .map((s) => s.$2['args']);
    expect(runs, [
      {'ask': 'cm', 'add': false},
      {'ask': 'ad', 'add': true},
    ]);
  });

  testWidgets('tabs: feed, plan, diff, checks, live check, issues', (
    tester,
  ) async {
    final relay = await pumpDetail(tester);
    await openTab(tester, Icons.stream);
    expect(find.bySemanticsLabel('feed'), findsOneWidget);
    relay.feeds['c1']!.add([
      {'type': 'stage', 'stage': 'implement'},
      {'type': 'activity', 'kind': 'tool', 'tool': 'Bash', 'text': 'ls'},
      {'type': 'activity', 'kind': 'error', 'text': 'bad'},
    ]);
    await tester.pump();
    expect(find.byKey(const Key('feed-stage')), findsOneWidget);
    expect(find.text('Bash ls'), findsOneWidget);
    await openTab(tester, Icons.map_outlined);
    expect(find.byKey(const Key('plan')), findsOneWidget);
    await openTab(tester, Icons.difference_outlined);
    expect(find.text('+a'), findsOneWidget);
    expect(find.byKey(const Key('diff-cut')), findsOneWidget);
    await openTab(tester, Icons.fact_check_outlined);
    expect(find.text('boom'), findsOneWidget);
    await openTab(tester, Icons.photo_library_outlined);
    expect(find.byKey(const ValueKey('shot-s1.png')), findsOneWidget);
    await openTab(tester, Icons.bug_report_outlined);
    expect(find.text('{"b":2}'), findsOneWidget);
  });

  testWidgets('empty detail: placeholders, no issues tab, empty feed', (
    tester,
  ) async {
    final relay = await pumpDetail(tester, detail: {'card': card('c1')});
    expect(find.byIcon(Icons.bug_report_outlined), findsNothing);
    await openTab(tester, Icons.stream);
    relay.feeds['c1']!.add(const []);
    await tester.pump();
    expect(find.byKey(const Key('feed-stage')), findsNothing);
    for (final (icon, key) in [
      (Icons.map_outlined, 'plan-none'),
      (Icons.difference_outlined, 'diff-none'),
      (Icons.fact_check_outlined, 'checks-none'),
      (Icons.photo_library_outlined, 'live-none'),
    ]) {
      await openTab(tester, icon);
      expect(find.byKey(Key(key)), findsOneWidget);
    }
  });

  testWidgets('failures show; shots and issues degrade', (tester) async {
    final relay = await pumpDetail(
      tester,
      outcome: const RelayFailed(code: 'offline', error: 'down'),
    );
    expect(find.byKey(const Key('detail-failure')), findsOneWidget);
    relay
      ..outcomes['task_detail'] = RelayOk(richDetail())
      ..outcomes['task_shot'] = const RelayFailed(code: 'x', error: 'y')
      ..outcomes['task_issues'] = const RelayOk({'text': ' '})
      ..outcomes['ask_undo'] = const RelayFailed(code: 'disabled', error: 'no');
    await hit(tester, find.byKey(const Key('detail-reload')));
    await seek(tester, find.byKey(const ValueKey('ask-undo-au')), 200);
    await hit(tester, find.byKey(const ValueKey('ask-undo-au')));
    expect(find.byIcon(Icons.block), findsOneWidget);
    await seek(tester, find.byKey(const ValueKey('ask-sh')), 200);
    expect(find.byIcon(Icons.broken_image_outlined), findsWidgets);
    await openTab(tester, Icons.bug_report_outlined);
    expect(find.byKey(const Key('issues-none')), findsOneWidget);
  });
}
