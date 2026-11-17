import 'dart:async';

import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/usage_relay.dart';

/// A usage relay with canned `tokens` answers per path.
class FakeUsageRelay implements UsageRelay {
  /// Answers by path (`''`, `/panel/overview`, `/session/k1`, ...).
  final Map<String, RelayOutcome> answers = {};

  /// Requests sent: (path, query).
  final List<(String, String)> asked = [];

  /// The `snap/usage` stream.
  final usageOut = StreamController<Json>.broadcast();

  /// The newest usage snapshot, replayed on listen.
  Json? lastUsage;

  @override
  Stream<Json> usage() async* {
    if (lastUsage case final u?) yield u;
    yield* usageOut.stream;
  }

  @override
  Future<RelayOutcome> tokens(String path, String query) async {
    asked.add((path, query));
    return answers[path] ??
        const RelayFailed(code: 'offline', error: 'no answer', retry: true);
  }
}

Json _session(String key, double usd) => {
  'key': key,
  'title': 'Session $key',
  'cwd': '/w/$key',
  'usd': usd,
  'usd_main': usd / 2,
  'usd_sub': usd / 2,
  'calls': 10,
  'prompts': 2,
  'subagents': 1,
  'active_s': 120,
  'wall_s': 400,
  'first_ts': 1700000000,
  'last_ts': 1700003600,
  'final_tag': 'D',
  'models': {'claude-opus-5-5': 1, 'claude-sonnet-5-5': 2},
};

/// Canned answers for every view.
Map<String, RelayOutcome> cannedUsage() => {
  '': const RelayOk({
    'options': {
      'cwds': ['/w/a'],
      'models': ['opus'],
    },
    'coverage': {
      'snapshots': ['7d'],
    },
    'panels': [
      {'name': 'overview', 'title': 'Overview'},
      {'name': 'calls', 'title': 'Calls'},
    ],
  }),
  '/panel/overview': RelayOk({
    'tiles': {
      'usd': 12.5,
      'usd_per_day': 1.5,
      'calls': 12345,
      'usd_per_call': 0.01,
      'sessions': 4,
      'active_h': 3.25,
    },
    'daily': [
      for (var d = 1; d <= 5; d++)
        {
          'day': '2026-11-0$d',
          'usd': d * 1.0,
          'calls': d * 10,
          'usd_per_call': null,
          'sub_share': 0.5,
          'opus_share': d == 3 ? null : 0.2,
          'over_share': 0.0,
          'home_share': 0.1,
        },
    ],
    'weekly': [
      {'week': '2026-W44', 'usd': 5.0, 'calls': 50},
    ],
    'prompts': [
      {'day': '2026-11-01', 'prompts': 3},
    ],
  }),
  '/panel/sessions': RelayOk({
    'sessions': [for (var i = 0; i < 30; i++) _session('k$i', i * 1.0)],
  }),
  '/session/k1': RelayOk({
    'session': _session('k1', 2),
    'prompts': [
      {
        'idx': 2,
        'text': 'second',
        'ts': 1700000100,
        'usd': 1.0,
        'usd_own': 0.5,
        'usd_sub': 0.5,
        'calls': 3,
        'active_s': 30,
        'wall_s': 60,
        'tools': [
          {
            'name': 'Bash',
            'calls': 2,
            'result_tokens': 100,
            'usd': 0.1,
            'carry_usd': 0.01,
            'share': null,
          },
        ],
        'subagents': [
          {
            'description': 'look',
            'agent_type': 'Explore',
            'model': 'sonnet',
            'depth': 1,
            'usd': 0.2,
            'calls': 1,
            'wall_s': 5,
            'key': 's1',
            'active_s': 4,
          },
        ],
      },
      {
        'idx': 1,
        'text': 'first',
        'ts': 1700000000,
        'usd': 1.0,
        'usd_own': 1.0,
        'usd_sub': 0,
        'calls': 1,
        'active_s': 10,
        'wall_s': 20,
        'tools': [
          {
            'name': 'Bash',
            'calls': 1,
            'result_tokens': 50,
            'usd': 0.1,
            'carry_usd': 0.0,
            'share': 0.1,
          },
        ],
        'subagents': <Json>[],
      },
    ],
    'unattributed': <Json>[],
  }),
};
