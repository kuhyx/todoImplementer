import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';

Json _metric(num? v, {String dir = 'up', num target = 80}) => {
  'value': v,
  'target': target,
  'direction': dir,
  'count': 4,
  'finished': 5,
  'weekly': [
    {'week': '2026-11-02', 'value': 3},
  ],
};

/// `snap/usage` with an autonomy block.
Json usageSnap() => {
  'autonomy': {
    'done_unassisted': _metric(90),
    'permission_asks': _metric(3, dir: 'down', target: 1),
    'questions_asked': _metric(null, dir: 'down'),
    'criteria_failed': _metric(0, dir: 'down', target: 1),
    'cards': 1200,
    'backfilled': 30,
  },
};

const _arm = {
  'n': 12,
  'usd': {'mean': 1, 'low': 0, 'high': 2},
};

/// Canned answers for the views [cannedUsage] leaves out.
Map<String, RelayOutcome> morePanels() => {
  '/items': const RelayOk({
    'total_usd': 9.5,
    'items': [
      {
        'item': 'a',
        'repo': 'r1',
        'stage': 'plan',
        'usd': 1,
        'calls': 2,
        'sessions': 1,
      },
    ],
    'repos': [
      {'repo': 'r1', 'usd': 1, 'calls': 2, 'sessions': 1},
      {'repo': 'r2', 'usd': 3, 'calls': 2, 'sessions': 1},
    ],
    'stages': [
      {'stage': 'plan', 'usd': 1, 'calls': 2, 'sessions': 1},
    ],
  }),
  '/panel/efficiency': const RelayOk({
    'captions': {'done': 'per finished', 'notes': ''},
    'done': [
      {
        'week': 'W1',
        'usd': 1.5,
        'share': 0.2,
        'wall_s': 70,
        'tokens': 5000,
        'n': 3,
        'kind': 'x',
      },
      {
        'week': 'W2',
        'usd': 2.5,
        'share': 0.3,
        'wall_s': 90,
        'tokens': 6000,
        'n': 4,
        'kind': 'y',
      },
    ],
    'commits': <Json>[],
    'estimate': <Json>[],
  }),
  '/panel/levers': const RelayOk({
    'rolling_days': 7,
    'rows': [
      {'lever': 'cache', 'status': 'applied', 'actual': 2, 'metric': 'm1'},
    ],
    'series': {
      'm1': {
        'daily': [
          {'date': '2026-11-01', 'value': 1},
          {'date': '2026-11-02', 'value': 12},
        ],
        'snapshots': <Json>[],
      },
      'm2': {
        'daily': <Json>[],
        'snapshots': [
          {'date': '2026-11-01', 'value': null},
        ],
      },
    },
  }),
  '/panel/context': const RelayOk({
    'calls_per_day': 40.4,
    'files': [
      {
        'path': '/h/CLAUDE.md',
        'status': 'over budget',
        'usd_per_day': 0.5,
        'tokens': 3000,
        'bytes': 9000,
        'lines': 100,
        'kind': 'global',
        'standing': 'always',
        'budgets': ['b1'],
        'breaches': [
          {
            'measure': 'lines',
            'value': 100,
            'limit': 80,
            'hard': false,
            'why': 'long',
          },
        ],
        'history': [
          {'ts': 1700000000, 'bytes': 8000, 'source': 'git'},
          {'ts': 1700100000, 'bytes': 9000, 'source': 'git'},
        ],
      },
      {
        'path': '/h/ok.md',
        'status': 'ok',
        'usd_per_day': 0.1,
        'tokens': 10,
        'bytes': 10,
        'lines': 1,
        'kind': 'k',
        'standing': 's',
        'budgets': <String>[],
        'breaches': <Json>[],
        'history': <Json>[],
      },
    ],
  }),
  '/context-file': const RelayOk({
    'path': '/h/CLAUDE.md',
    'kind': 'global',
    'content': '# rules',
    'git_log': ['abc first'],
  }),
  '/panel/anomalies': const RelayOk({
    'caption': 'two spikes',
    'over': 1,
    'totals': {'spikes': 1, 'loops': 0, 'expensive': 1, 'expensive_usd': 9},
    'spikes': [
      {'day': '2026-11-01', 'usd': 9, 'median_usd': 2, 'ratio': 4.5},
    ],
    'category_totals': [
      {'category': 'read', 'cost_usd': 2, 'calls': 3},
    ],
    'expensive': [
      {
        'key': 'k1',
        'title': 'big',
        'usd': 9,
        'day': 'd',
        'cwd': null,
        'calls': 3,
      },
    ],
    'loops': <Json>[],
    'categories': <Json>[],
  }),
  '/panel/ab': const RelayOk({
    'banner': {'level': 'green', 'text': 'no difference'},
    'arms': {'sonnet': _arm, 'opus': _arm},
    'diffs': {
      'error': {'diff': 0.1, 'low': -0.1, 'high': 0.2},
    },
    'metrics': [
      {'measure': 'error', 'sonnet': '1%', 'opus': '2%', 'difference': '-1'},
    ],
    'unjoined': 2,
    'build': {
      'banner': {'level': 'red', 'text': 'worse'},
      'arms': {'sonnet': _arm},
    },
  }),
  '/panel/calls': const RelayOk({
    'total': 5,
    'note': 'x',
    'filters': 'f',
    'rows': [
      {'name': 'Bash', 'calls': 3},
    ],
    'empty': <Json>[],
  }),
};
