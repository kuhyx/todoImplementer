import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/model/detail.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/merges.dart';
import 'package:todo_implementer/ui/board/live_feed.dart';

import '../support/fakes.dart';

/// A full `task_detail` body.
Json fullDetail() => {
  'card': card('c1'),
  'plan_md': '# plan',
  'diff': {
    'files': [
      {'path': 'a.dart', 'added': 2, 'removed': 1},
    ],
    'patch': '@@ x\n+a\n-b',
    'truncated': true,
  },
  'checks': {
    'passed': false,
    'results': [
      {'command': 'make', 'exit': 2, 'tail': 'boom'},
    ],
  },
  'live_check': {
    'report_md': 'looks fine',
    'shots': ['s1.png'],
  },
  'lesson': {'skill': 'k', 'mistake': 'm', 'rule': 'r', 'evidence': 'e'},
  'error': 'it broke',
  'ask_items': [
    {
      'id': 'q1',
      'type': 'command',
      'title': 'run it',
      'risk': 'reversible',
      'state': 'done',
      'command': 'ls',
      'mode': 'run',
      'result': {'exit': 0, 'tail': 'ok'},
    },
    'not an object',
  ],
  'umbrella': {'round': 1, 'width': 2, 'rows': <Json>[]},
};

void main() {
  test('full detail parses every part', () {
    final d = TaskDetail.fromJson(fullDetail());
    expect(d.card.id, 'c1');
    expect(d.planMd, '# plan');
    expect(d.diff!.files.single.added, 2);
    expect(d.diff!.truncated, isTrue);
    expect(d.checks!.results.single.exit, 2);
    expect(d.liveCheck!.shots, ['s1.png']);
    expect(d.lesson!.rule, 'r');
    expect(d.error, 'it broke');
    final ask = d.asks.single;
    expect((ask.risky, ask.open, ask.exit, ask.tail), (false, false, 0, 'ok'));
    expect(d.umbrella!['width'], 2);
  });

  test('empty detail falls back to neutral values', () {
    final d = TaskDetail.fromJson({
      'diff': {
        'files': [<String, dynamic>{}],
      },
      'checks': {
        'results': [<String, dynamic>{}],
      },
      'ask_items': {'not': 'a list'},
    });
    expect(d.card.id, '');
    expect(d.diff!.files.single.removed, 0);
    expect(d.checks!.results.single.exit, -1);
    expect(d.asks, isEmpty);
    expect(
      (d.planMd, d.liveCheck, d.lesson, d.umbrella),
      (null, null, null, null),
    );
    final ask = AskItem.fromJson(const {});
    expect(
      (ask.type, ask.state, ask.risky, ask.exit),
      ('choice', 'open', true, null),
    );
  });

  test('ask requests', () {
    const ask = AskItem(
      id: 'a',
      type: 'command',
      title: 't',
      state: 'open',
      mode: 'add_run',
    );
    final (kind, args) = answerRequest(ask, 'yes');
    expect(kind, 'ask_answer');
    expect(args, {'ask': 'a', 'option': 'yes'});
    final (run, runArgs) = runRequest(ask);
    expect(run, 'ask_run');
    expect(runArgs, {'ask': 'a', 'add': true});
  });

  test('merges parse; merge needs a long press, dismiss does not', () {
    final all = mergesOf({
      'suggestions': [mergeJson('abc', mergeEnabled: false)],
    });
    final s = all.single;
    expect(
      (s.id, s.title, s.reason, s.members.length),
      ('abc', 'Combined abc', 'alike', 2),
    );
    expect(s.members.first.repo, 'kuhyx/demo');
    expect(s.actions.map((a) => (a.id, a.confirm, a.enabled)), [
      ('merge', true, false),
      ('dismiss', false, true),
    ]);
    expect(mergeKind('dismiss'), 'merge_dismiss');
  });

  test('groups: effort is flat; other sorts by repo, Yours last', () {
    final cards = [
      for (final c in [
        card('y', repo: null),
        card('b', repo: 'kuhyx/b'),
        card('a', repo: 'kuhyx/a'),
        card('a2', repo: 'kuhyx/a'),
      ])
        TaskCard.fromJson(c),
    ];
    expect(groupCards(const [], BoardSort.title), isEmpty);
    final flat = groupCards(cards, BoardSort.effort);
    expect((flat.single.flat, flat.single.cards.length), (true, 4));
    final byRepo = groupCards(cards, BoardSort.title);
    expect(byRepo.map((g) => g.repo), ['kuhyx/a', 'kuhyx/b', null]);
    expect(byRepo.first.cards.length, 2);
    expect(
      groupCards(cards.reversed.toList(), BoardSort.title).last.repo,
      isNull,
    );
  });

  test('every feed kind has its own glyph', () {
    final kinds = ['text', 'tool', 'result', 'error', 'user', 'system'];
    expect(kinds.map(feedIcon).toSet().length, kinds.length);
  });
}
