// Emulator/screenshot entry point: the real shell and board page over an
// in-memory relay with a canned board, so the layout can be checked with no
// Firebase, no PC and no real data. Build with `--target demo/main.dart`.
// Outside lib/: it ships in no release build.
import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/shell/shell.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

void main() => runApp(
  MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: buildDarkTheme(),
    home: Shell(board: BoardPage(relay: _DemoRelay())),
  ),
);

class _DemoRelay implements BoardRelay {
  @override
  Stream<Board> boards() => Stream.value(Board.fromJson(_board));

  @override
  Future<RelayOutcome> send(String kind, Json body) async {
    await Future<void>.delayed(const Duration(milliseconds: 600));
    if (kind == 'task_detail') {
      return const RelayOk({
        'questions': [
          {
            'id': 'Q1',
            'title': 'Store the cache on disk?',
            'body': 'Memory only loses it on restart.',
            'recommendation': 'Yes, under ~/.cache',
            'answer': null,
          },
        ],
      });
    }
    return const RelayOk({});
  }
}

Json _action(String id, {bool enabled = true, bool confirm = false}) => {
  'id': id,
  'label': id,
  'enabled': enabled,
  'reason': enabled ? null : 'not now',
  'confirm': confirm,
};

Json _card(
  int i,
  String column,
  String status,
  String title, {
  String? repo = 'kuhyx/demo-app',
  Json? needs,
  List<Json> actions = const [],
  double cost = 0,
  String? route,
}) => {
  'id': 'card$i-0',
  'title': title,
  'repo': repo,
  'priority': 'normal',
  'status': status,
  'column': column,
  'current': 'review round 2/5',
  'needs': needs,
  'cost_usd': cost,
  'route': route,
  'tier': {'cheap': i.isEven, 'free': false, 'escalated': i % 5 == 0},
  'updated': 1794800000 + i,
  'actions': actions,
};

final _titles = [
  'Add dark mode to the settings page',
  'Fix crash when the list is empty',
  'Export history as CSV',
  'Speed up the startup by caching icons',
  'Show sync status in the header',
  'Retry uploads on flaky networks',
  'Move strings into the ledger file',
  'Pin dependencies to newest stable',
];

final Json _board = {
  'build': 'demo',
  'slots': {'used': 2},
  'limit': {
    'active': false,
    'credits': {'enabled': true, 'state': 'ready'},
  },
  'auto_close': false,
  'columns': [
    for (final c in columnIds) {'id': c, 'label': c, 'count': 0},
  ],
  'repos': ['kuhyx/demo-app', 'kuhyx/other-tool'],
  'tasks': [
    _card(
      1,
      'needs_you',
      'needs_you',
      'Decide the cache location',
      needs: {
        'kind': 'spec_questions',
        'text': 'Answer 1 spec question',
        'category': 'questions',
        'effort': 1,
      },
      actions: [_action('spec-answers'), _action('cancel', confirm: true)],
      cost: 0.42,
    ),
    _card(
      2,
      'needs_you',
      'needs_you',
      'Grant the screenshot permission',
      needs: {
        'kind': 'permission',
        'text': 'Run the grant command',
        'category': 'permission',
        'effort': 1,
        'command': 'allow_rules.sh Bash(adb shell screencap:*)',
      },
      actions: [_action('go'), _action('rerun', enabled: false)],
      route: 'credits',
    ),
    for (var i = 0; i < 8; i++)
      _card(10 + i, 'backlog', 'backlog', _titles[i], actions: [
        _action('start'),
      ]),
    _card(
      30,
      'running',
      'working',
      'Retry uploads on flaky networks',
      repo: 'kuhyx/other-tool',
      actions: [_action('send'), _action('cancel', confirm: true)],
      cost: 1.37,
    ),
    _card(
      40,
      'ready',
      'ready_to_ship',
      'Show sync status in the header',
      actions: [_action('ship', confirm: true), _action('copy-resume')],
      cost: 2.1,
    ),
  ],
};
