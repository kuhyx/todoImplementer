import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/backlog_order.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/model/json.dart';

import '../support/fakes.dart';

void main() {
  test('parses the server test fixture (contracts/board.schema.json)', () {
    final json = File('../tests/fixtures/board.json').readAsStringSync();
    final b = Board.fromJson(jsonDecode(json) as Json);
    expect(b.columns.map((c) => c.id), columnIds);
    final c = b.tasks.single;
    expect(c.column, 'running');
    expect(c.costUsd, 1.37);
    expect(c.updated, 1793880000);
    final cancel = c.actions.first;
    expect((cancel.id, cancel.confirm, cancel.enabled), ('cancel', true, true));
    expect(c.actions.last.spoken, 'Start: already running');
    expect(cancel.spoken, 'Cancel');
  });

  test('reads every optional board field', () {
    final b = Board.fromJson(
      boardJson(
        [
          card(
            'a',
            needs: {
              'kind': 'permission',
              'text': 'grant',
              'category': 'permission',
              'effort': 2,
              'command': 'cmd',
            },
            actions: [
              action('start', option: action('auto_ship', enabled: false)),
              action('copy-fix', value: 'v'),
            ],
            tiers: true,
            route: 'credits',
          ),
        ],
        extra: {
          'error': {'code': 'internal', 'message': 'stale'},
          'alert': {'kind': 'overage', 'text': 'over', 'until': 9},
          'api_key': {
            'state': 'expiring',
            'level': 'warn',
            'text': 'soon',
            'expires': null,
          },
        },
      ),
    );
    expect(
      (b.error, b.alert, b.apiKeyLevel, b.apiKeyText),
      ('stale', 'over', 'warn', 'soon'),
    );
    expect((b.slotsUsed, b.creditsEnabled, b.creditsState), (2, false, 'off'));
    final c = b.tasks.single;
    expect((c.needs!.command, c.needs!.effort), ('cmd', 2));
    expect(
      (c.cheap, c.free, c.escalated, c.route),
      (true, true, true, 'credits'),
    );
    expect(c.actions.first.option!.enabled, isFalse);
    expect(c.actions.last.local, isTrue);
    expect(c.actions.first.local, isFalse);
  });

  test('missing objects fall back to neutral values', () {
    final b = Board.fromJson(const {});
    expect((b.build, b.slotsUsed, b.apiKeyLevel), ('', 0, 'ok'));
    expect(b.tasks, isEmpty);
    expect(strs(const {'x': 1}, 'x'), isEmpty);
    expect(objs(const {'x': 1}, 'x'), isEmpty);
  });

  group('board view', () {
    final b = Board.fromJson(
      boardJson([
        card('n1', column: 'needs_you', needs: _needs('action', 3)),
        card('n2', column: 'needs_you', needs: _needs('questions', 5)),
        card('n3', column: 'needs_you', needs: _needs('action', 1)),
        card('b1', priority: 'low', cost: 2, updated: 5, title: 'zeta'),
        card('b2', priority: 'urgent', cost: 1, updated: 9, title: 'alpha'),
        card('b3', priority: 'odd', repo: null, title: 'alpha'),
        card('r1', column: 'running', repo: 'kuhyx/other'),
      ]),
    );

    List<String> ids(String col, ViewState s) => buildView(
      b,
      s,
    ).firstWhere((v) => v.column.id == col).cards.map((c) => c.id).toList();

    test('least effort: questions first, then fewest clicks', () {
      expect(ids('needs_you', const ViewState()), ['n2', 'n3', 'n1']);
    });

    test('every sort order', () {
      final backlog = b.tasks.where((c) => c.column == 'backlog').toList();
      List<String> by(BoardSort s) =>
          sortCards(backlog, s).map((c) => c.id).toList();
      expect(by(BoardSort.priority), ['b2', 'b1', 'b3']);
      expect(by(BoardSort.updated), ['b2', 'b1', 'b3']);
      expect(by(BoardSort.cost), ['b1', 'b2', 'b3']);
      expect(by(BoardSort.title), ['b2', 'b3', 'b1']);
      expect(by(BoardSort.effort), ['b2', 'b1', 'b3']);
    });

    test('[T2583] Backlog: priority first, then kuhy before automatic', () {
      final mixed = Board.fromJson(
        boardJson([
          {...card('a', priority: 'medium', title: 'a'), 'lane': 'app'},
          {...card('k', priority: 'medium', title: 'z'), 'lane': 'kuhy'},
          {...card('h', priority: 'high', title: 'y'), 'lane': 'board'},
          {...card('o', priority: 'medium', title: 'b'), 'lane': 'odd'},
          card('l', priority: 'low', title: 'c'),
        ]),
      );
      for (final s in BoardSort.values) {
        final col = buildView(mixed, ViewState(sort: s)).first;
        expect(col.cards.map((c) => c.id), ['h', 'o', 'k', 'a', 'l']);
        final groups = columnGroups('backlog', col.cards, s);
        expect((groups.single.flat, groups.single.cards), (true, col.cards));
      }
      expect(columnGroups('backlog', const [], BoardSort.title), isEmpty);
      expect(columnGroups('done', col0(mixed), BoardSort.title), isNotEmpty);
    });

    test('repo filter and fuzzy search', () {
      expect(ids('backlog', const ViewState(repo: yours)), ['b3']);
      expect(ids('running', const ViewState(repo: 'kuhyx/other')), ['r1']);
      expect(ids('backlog', const ViewState(query: 'zta  ')), ['b1']);
      expect(ids('backlog', const ViewState(query: 'qqq')), isEmpty);
      expect(fuzzyMatch('ZT', 'zeta'), isTrue);
    });

    test('active column: chosen, else needs you, else first filled', () {
      final view = buildView(b, const ViewState());
      expect(activeColumn(view, const ViewState(column: 'done')), 'done');
      expect(activeColumn(view, const ViewState()), 'needs_you');
      final noNeeds = buildView(b, const ViewState(repo: 'kuhyx/other'));
      expect(activeColumn(noNeeds, const ViewState()), 'running');
      final none = buildView(b, const ViewState(query: 'nothing'));
      expect(activeColumn(none, const ViewState()), 'backlog');
    });

    test('repo options count cards; Yours only when it has some', () {
      expect(repoOptions(b), [
        ('', 7),
        (yours, 1),
        ('kuhyx/demo', 5),
        ('kuhyx/other', 1),
      ]);
      final only = Board.fromJson(boardJson([card('x')]));
      expect(repoOptions(only).map((o) => o.$1), [
        '',
        'kuhyx/demo',
        'kuhyx/other',
      ]);
    });

    test('full ties fall back to the id', () {
      final twins = Board.fromJson(
        boardJson([card('y', title: 'same'), card('x', title: 'same')]),
      );
      final order = sortCards(twins.tasks, BoardSort.title);
      expect(order.map((c) => c.id), ['x', 'y']);
    });

    test('copyWith keeps unset fields', () {
      const s = ViewState(query: 'q', repo: 'r', sort: BoardSort.cost);
      final t = s.copyWith(column: 'done');
      expect(
        (t.query, t.repo, t.sort, t.column),
        ('q', 'r', BoardSort.cost, 'done'),
      );
    });
  });
}

List<TaskCard> col0(Board b) => b.tasks;

Json _needs(String category, int effort) => {
  'kind': 'claude_action',
  'text': 'needs $category',
  'category': category,
  'effort': effort,
};
