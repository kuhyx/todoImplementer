/// A/B, the panel index and any generic panel (`web/src/usage/view-ab.ts`,
/// `view-more.ts`).
library;

import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

/// The server's `banner.level`.
Level levelNamed(String name) => switch (name) {
  'green' => Level.green,
  'red' => Level.red,
  _ => Level.grey,
};

List<UsageBlock> _experiment(String id, String name, Json d) {
  final banner = objOr(d, 'banner') ?? const {};
  final arms = objOr(d, 'arms') ?? const {};
  final diffs = (objOr(d, 'diffs') ?? const {}).entries
      .where((e) => e.value is Json)
      .map((e) => (e.key, e.value as Json))
      .toList();
  return [
    BannerBlock(levelNamed(str(banner, 'level')), str(banner, 'text')),
    TilesBlock([
      for (final MapEntry(:key, :value) in arms.entries)
        if (value is Json)
          UsageTile(Icons.groups_outlined, key, 'n=${plain(at(value, 'n'))}'),
      if (at(d, 'unjoined') case final n?)
        UsageTile(Icons.link_off, 'Unjoined', plain(n)),
    ]),
    ChartBlock(
      kind: ChartKind.interval,
      semantics: 'Sonnet minus Opus, with confidence interval',
      icon: Icons.difference_outlined,
      labels: [for (final (k, _) in diffs) k],
      series: [
        ChartSeries('Difference', Icons.difference_outlined, [
          for (final (_, v) in diffs) numOf(v, 'diff'),
        ]),
      ],
      low: [for (final (_, v) in diffs) numOf(v, 'low')],
      high: [for (final (_, v) in diffs) numOf(v, 'high')],
      fmt: share,
    ),
    TableBlock(
      id: id,
      semantics: name,
      icon: Icons.compare_arrows,
      rows: objs(d, 'metrics'),
      columns: [
        Col.text('measure', 'Measure'),
        Col.text('sonnet', 'Sonnet'),
        Col.text('opus', 'Opus'),
        Col.text('difference', 'Difference'),
      ],
    ),
  ];
}

/// Sonnet against Opus, judgment agents and (all time) build agents.
Future<List<UsageBlock>> abView(ViewContext c, String _) async {
  final d = await panel(c, 'ab');
  final build = objOr(d, 'build');
  return [
    ..._experiment('metrics', 'Judgment agents', d),
    if (build != null) ..._experiment('build', 'Build agents', build),
  ];
}

const _dedicated = {
  'ab',
  'anomalies',
  'context',
  'efficiency',
  'levers',
  'overview',
  'sessions',
};

/// The panels without a dedicated view.
Future<List<UsageBlock>> moreView(ViewContext c, String _) async {
  final index = await fetch(c, '');
  return [
    ListBlock(Icons.table_chart_outlined, 'More panels', [
      for (final p in objs(index, 'panels'))
        if (!_dedicated.contains(str(p, 'name')))
          (
            str(p, 'title', str(p, 'name')),
            UsageRoute(UsageView.panel, str(p, 'name')),
          ),
    ]),
  ];
}

bool _isRows(Object? v) =>
    v is List && v.isNotEmpty && v.every((r) => r is Json);

/// Any panel: scalar fields become tiles, every list of objects a table.
Future<List<UsageBlock>> genericView(ViewContext c, String name) async {
  final d = await panel(c, name);
  final scalars = [
    for (final MapEntry(:key, :value) in d.entries)
      if (key != 'filters' && (value is num || value is String)) (key, value),
  ];
  return [
    if (scalars.isNotEmpty)
      TilesBlock([
        for (final (k, v) in scalars)
          UsageTile(Icons.numbers, k.replaceAll('_', ' '), cellText(v)),
      ]),
    for (final MapEntry(:key, :value) in d.entries)
      if (_isRows(value))
        TableBlock(
          id: key,
          semantics: key.replaceAll('_', ' '),
          icon: Icons.table_rows_outlined,
          rows: (value as List).cast<Json>(),
          columns: inferColumns(value.cast<Json>()),
        ),
  ];
}
