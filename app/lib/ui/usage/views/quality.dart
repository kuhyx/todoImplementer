/// Quality views: levers, context files, one file, anomalies, A/B
/// (`web/src/usage/view-levers.ts`, `view-context.ts`, `view-file.ts`,
/// `view-anomalies.ts`, `view-ab.ts`).
library;

import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

String _metric(num v) => v.abs() < 10 ? v.toStringAsFixed(2) : '${v.round()}';

/// Optimisation levers and their metric series.
Future<List<UsageBlock>> leversView(ViewContext c, String _) async {
  final d = await panel(c, 'levers', ['rows']);
  final series = objOr(d, 'series') ?? const {};
  return [
    for (final (i, MapEntry(:key, :value)) in series.entries.indexed)
      if (value is Json) _lever(key, value, i),
    TableBlock(
      id: 'rows',
      semantics: 'Levers',
      icon: Icons.tune,
      rows: objs(d, 'rows'),
      columns: [
        Col.text('lever', 'Lever'),
        Col.tag('status', 'Status'),
        Col.count('actual', 'Actual'),
        Col.tag('outcome', 'Outcome'),
        Col.tag('metric', 'Metric'),
        Col.count('baseline', 'Baseline'),
        Col.count('predicted', 'Predicted'),
        Col.tag('date', 'Date'),
        Col.tag('source', 'Source'),
        Col.text('detail', 'Detail'),
      ],
    ),
  ];
}

ChartBlock _lever(String metric, Json s, int i) {
  final daily = objs(s, 'daily');
  final points = daily.length > 1 ? daily : objs(s, 'snapshots');
  return chart(
    ChartKind.line,
    metric.replaceAll('_', ' '),
    Icons.straighten,
    [for (final p in points) dayLabel(str(p, 'date'))],
    column(points, 'value'),
    _metric,
    color: i,
  );
}

UsageRoute _key(Json row) => UsageRoute(UsageView.session, str(row, 'key'));

/// Spike days, expensive sessions, loops, costly categories.
Future<List<UsageBlock>> anomaliesView(ViewContext c, String _) async {
  final d = await panel(c, 'anomalies', [
    'spikes',
    'expensive',
    'loops',
    'categories',
  ]);
  final t = objOr(d, 'totals') ?? const {};
  final spikes = objs(d, 'spikes');
  final bad = numOf(t, 'spikes') + numOf(t, 'loops') > 0;
  return [
    BannerBlock(bad ? Level.red : Level.green, str(d, 'caption')),
    TilesBlock([
      UsageTile(Icons.show_chart, 'Spike days', plain(at(t, 'spikes'))),
      UsageTile(
        Icons.attach_money,
        'Expensive sessions',
        '${plain(at(t, 'expensive'))} · ${usd(at(t, 'expensive_usd'))}',
      ),
      UsageTile(Icons.repeat, 'Loops', plain(at(t, 'loops'))),
    ]),
    ChartBlock(
      kind: ChartKind.line,
      semantics: 'Spike days against the median day',
      icon: Icons.show_chart,
      labels: [for (final r in spikes) dayLabel(str(r, 'day'))],
      series: [
        ChartSeries(
          'Spend',
          Icons.attach_money,
          column(spikes, 'usd'),
          color: 1,
        ),
        ChartSeries(
          'Median',
          Icons.align_vertical_center,
          column(spikes, 'median_usd'),
        ),
      ],
      fmt: usd,
    ),
    rank(
      'Spend by category',
      Icons.category_outlined,
      [
        for (final r in objs(d, 'category_totals'))
          (str(r, 'category'), numOf(r, 'cost_usd')),
      ],
      usd,
      color: 2,
    ),
    TableBlock(
      id: 'spikes',
      semantics: 'Spike days',
      icon: Icons.show_chart,
      rows: spikes,
      columns: [
        Col.text('day', 'Day'),
        Col.money('usd', 'USD'),
        Col.money('median_usd', 'Median'),
        Col.count('ratio', 'Ratio'),
      ],
    ),
    TableBlock(
      id: 'expensive',
      semantics: 'Expensive sessions',
      icon: Icons.attach_money,
      rows: objs(d, 'expensive'),
      columns: [
        Col.link('title', 'Session', _key),
        Col.money('usd', 'USD'),
        Col.tag('day', 'Day'),
        Col.tag('cwd', 'Directory'),
        Col.count('calls', 'Calls'),
      ],
    ),
    TableBlock(
      id: 'loops',
      semantics: 'Repeated calls',
      icon: Icons.repeat,
      rows: objs(d, 'loops'),
      columns: [
        Col.link('name', 'Tool', _key),
        Col.count('repeats', 'Repeats'),
        Col.money('cost_usd', 'USD'),
        Col.text('target', 'Target'),
      ],
    ),
    TableBlock(
      id: 'categories',
      semantics: 'Costly calls by category',
      icon: Icons.category_outlined,
      rows: objs(d, 'categories'),
      columns: [
        Col.link('category', 'Category', _key),
        Col.money('cost_usd', 'USD'),
        Col.count('calls', 'Calls'),
      ],
    ),
  ];
}
