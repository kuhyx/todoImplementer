/// Work views: per todo item, efficiency, autonomy (`web/src/usage/
/// view-items.ts`, `view-efficiency.ts`, `view-autonomy.ts`).
library;

import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

List<UsageColumn> _cost(String key, String label) => [
  Col.text(key, label),
  Col.money('usd', 'USD'),
  Col.count('calls', 'Calls'),
  Col.count('sessions', 'Sessions'),
];

/// Cost per todo item, repo and stage.
Future<List<UsageBlock>> itemsView(ViewContext c, String _) async {
  final query = Uri(queryParameters: c.filters.query()).query;
  final d = await fetch(c, '/items', query);
  final items = objs(d, 'items');
  final repos = objs(d, 'repos');
  final stages = objs(d, 'stages');
  List<(String, num)> pairs(List<Json> rows, String k) => [
    for (final r in rows) (str(r, k), numOf(r, 'usd')),
  ];
  return [
    TilesBlock([
      UsageTile(Icons.attach_money, 'Spend', usd(numOf(d, 'total_usd'))),
      UsageTile(
        Icons.checklist,
        'Items',
        '${items.map((r) => r['item']).toSet().length}',
      ),
      UsageTile(Icons.source_outlined, 'Repos', '${repos.length}'),
    ]),
    rank('USD per repo', Icons.source_outlined, pairs(repos, 'repo'), usd),
    rank(
      'USD per stage',
      Icons.stairs_outlined,
      pairs(stages, 'stage'),
      usd,
      color: 1,
    ),
    TableBlock(
      id: 'items',
      semantics: 'Cost per item',
      icon: Icons.checklist,
      rows: items,
      columns: [
        Col.text('item', 'Item'),
        Col.money('usd', 'USD'),
        Col.tag('repo', 'Repo'),
        Col.tag('stage', 'Stage'),
        Col.count('calls', 'Calls'),
        Col.count('sessions', 'Sessions'),
      ],
    ),
    TableBlock(
      id: 'repos',
      semantics: 'Per repo',
      icon: Icons.source_outlined,
      rows: repos,
      columns: _cost('repo', 'Repo'),
    ),
    TableBlock(
      id: 'stages',
      semantics: 'Per stage',
      icon: Icons.stairs_outlined,
      rows: stages,
      columns: _cost('stage', 'Stage'),
    ),
  ];
}

const _efficiency = <(String, String, IconData)>[
  ('done', 'Spend per finished session', Icons.task_alt),
  ('commits', 'Spend per surviving commit', Icons.commit),
  ('estimate', 'Spend per estimated call', Icons.calculate_outlined),
  ('notes_weekly', 'Notes per week', Icons.date_range),
  ('notes', 'Spend per todo note', Icons.sticky_note_2_outlined),
];

/// Spend per finished session, commit, estimate and note.
Future<List<UsageBlock>> efficiencyView(ViewContext c, String _) async {
  final d = await panel(c, 'efficiency', [
    'done',
    'commits',
    'estimate',
    'notes',
    'notes_weekly',
  ]);
  final captions = objOr(d, 'captions') ?? const {};
  return [
    for (final (id, name, icon) in _efficiency) ...[
      if (str(captions, id.replaceAll('_weekly', '')) case final cap
          when cap.isNotEmpty)
        BannerBlock(Level.grey, cap),
      TableBlock(
        id: id,
        semantics: name,
        icon: icon,
        rows: objs(d, id),
        columns: inferColumns(objs(d, id)),
      ),
    ],
  ];
}

/// Green on the right side of the target, grey with no value
/// (`view-autonomy.ts` `levelOf`).
Level levelOf(Json metric) {
  final v = metric['value'];
  if (v is! num) return Level.grey;
  final target = numOf(metric, 'target');
  final up = str(metric, 'direction') == 'up';
  return (up ? v >= target : v <= target) ? Level.green : Level.red;
}

String _pct(num v) => '${plain(v)}%';

UsageTile _metric(IconData icon, String name, Json m, String Function(num) f) {
  final v = m['value'];
  return UsageTile(
    icon,
    name,
    v is num ? f(v) : dash,
    level: levelOf(m),
    target: f(numOf(m, 'target')),
    higherIsBetter: str(m, 'direction') == 'up',
  );
}

const _autonomy = <(String, String, IconData)>[
  ('done_unassisted', 'Done unassisted', Icons.task_alt),
  ('permission_asks', 'Permissions asked', Icons.lock_open_outlined),
  ('questions_asked', 'Questions asked', Icons.help_outline),
  ('criteria_failed', 'Criteria failed', Icons.rule),
];

/// How much of the work ran without kuhy, from `snap/usage`.
Future<List<UsageBlock>> autonomyView(ViewContext c, String _) async {
  final a = objOr(await c.relay.usage().first, 'autonomy') ?? const {};
  String Function(num) fmtOf(String k) => k == 'done_unassisted' ? _pct : plain;
  final done = objOr(a, 'done_unassisted') ?? const {};
  return [
    TilesBlock([
      for (final (k, name, icon) in _autonomy)
        _metric(icon, name, objOr(a, k) ?? const {}, fmtOf(k)),
      UsageTile(Icons.done_all, 'Finished cards', plain(at(done, 'finished'))),
      UsageTile(Icons.style_outlined, 'Cards read', compact(at(a, 'cards'))),
      UsageTile(
        Icons.restore,
        'Rebuilt from disk',
        compact(at(a, 'backfilled')),
      ),
    ]),
    for (final (i, (k, name, icon)) in _autonomy.indexed)
      _weekly(name, icon, objOr(a, k) ?? const {}, fmtOf(k), i),
  ];
}

ChartBlock _weekly(
  String name,
  IconData icon,
  Json m,
  String Function(num) f,
  int color,
) {
  final weeks = objs(m, 'weekly');
  return chart(
    ChartKind.bar,
    '$name per week',
    icon,
    [for (final w in weeks) dayLabel(str(w, 'week'))],
    [for (final w in weeks) at(w, 'value')],
    f,
    color: color,
  );
}
