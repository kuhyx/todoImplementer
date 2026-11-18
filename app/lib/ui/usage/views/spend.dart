/// Spend views: overview, sessions, one session (`web/src/usage/
/// view-overview.ts`, `view-sessions.ts`, `view-session.ts`).
library;

import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

String _pct0(num v) => '${(v * 100).toStringAsFixed(0)}%';

/// Spend over time.
Future<List<UsageBlock>> overviewView(ViewContext c, String _) async {
  final d = await panel(c, 'overview', ['daily', 'weekly']);
  final daily = objs(d, 'daily');
  final days = [for (final r in daily) dayLabel(str(r, 'day'))];
  final t = objOr(d, 'tiles') ?? const {};
  final weekly = objs(d, 'weekly');
  final prompts = objs(d, 'prompts');
  const shares = [
    ('sub_share', 'Subagents share of spend', Icons.smart_toy_outlined),
    ('opus_share', 'Opus share of spend', Icons.auto_awesome),
    ('over_share', 'Over budget share of spend', Icons.trending_up),
    ('home_share', 'Home dir share of spend', Icons.home_outlined),
  ];
  return [
    TilesBlock([
      UsageTile(Icons.attach_money, 'Spend', usd(at(t, 'usd'))),
      UsageTile(Icons.today, 'Per day', usd(at(t, 'usd_per_day'))),
      UsageTile(Icons.call_made, 'Calls', compact(at(t, 'calls'))),
      UsageTile(
        Icons.price_change_outlined,
        'Per call',
        usd(at(t, 'usd_per_call')),
      ),
      UsageTile(Icons.terminal, 'Sessions', compact(at(t, 'sessions'))),
      UsageTile(
        Icons.timer_outlined,
        'Active',
        '${numOf(t, 'active_h').toStringAsFixed(1)} h',
      ),
    ]),
    chart(
      ChartKind.bar,
      'Spend per day',
      Icons.calendar_today,
      days,
      column(daily, 'usd'),
      usd,
    ),
    chart(
      ChartKind.line,
      'Calls per day',
      Icons.call_made,
      days,
      column(daily, 'calls'),
      compact,
      color: 1,
    ),
    chart(
      ChartKind.bar,
      'Spend per week',
      Icons.date_range,
      [for (final r in weekly) str(r, 'week')],
      column(weekly, 'usd'),
      usd,
    ),
    chart(
      ChartKind.line,
      'Prompts per day',
      Icons.chat_bubble_outline,
      [for (final r in prompts) dayLabel(str(r, 'day'))],
      column(prompts, 'prompts'),
      compact,
      color: 2,
    ),
    for (final (i, (key, name, icon)) in shares.indexed)
      chart(
        ChartKind.line,
        name,
        icon,
        days,
        column(daily, key),
        _pct0,
        color: i,
      ),
    TableBlock(
      id: 'daily',
      semantics: 'Daily spend',
      icon: Icons.calendar_today,
      rows: daily,
      columns: [
        Col.text('day', 'Day'),
        Col.money('usd', 'USD'),
        Col.count('calls', 'Calls'),
        Col.money('usd_per_call', 'USD / call'),
        Col.pct('sub_share', 'Subagents'),
        Col.pct('opus_share', 'Opus'),
        Col.pct('over_share', 'Over budget'),
        Col.pct('home_share', 'Home dir'),
      ],
    ),
  ];
}

UsageRoute _session(Json row) => UsageRoute(UsageView.session, str(row, 'key'));

String _models(Json row) {
  final names =
      (objOr(row, 'models') ?? const {}).keys
          .map((n) => n.replaceFirst('claude-', ''))
          .toList()
        ..sort();
  return names.join(', ');
}

/// Every session.
Future<List<UsageBlock>> sessionsView(ViewContext c, String _) async {
  final rows = objs(await panel(c, 'sessions', ['sessions']), 'sessions');
  double sum(String k) => rows.fold(0, (s, r) => s + numOf(r, k));
  return [
    TilesBlock([
      UsageTile(Icons.terminal, 'Sessions', '${rows.length}'),
      UsageTile(Icons.attach_money, 'Spend', usd(sum('usd'))),
      UsageTile(
        Icons.smart_toy_outlined,
        'Subagent spend',
        usd(sum('usd_sub')),
      ),
    ]),
    TableBlock(
      id: 'sessions',
      semantics: 'Sessions',
      icon: Icons.terminal,
      rows: [
        for (final r in rows) {...r, 'models': _models(r)},
      ],
      columns: [
        Col.link('title', 'Title', _session),
        Col.money('usd', 'USD'),
        Col.when('last_ts', 'Last active'),
        Col.text('cwd', 'Directory'),
        Col.money('usd_main', 'Main'),
        Col.money('usd_sub', 'Subagents'),
        Col.count('calls', 'Calls'),
        Col.count('prompts', 'Prompts'),
        Col.count('subagents', 'Agents'),
        Col.secs('active_s', 'Active'),
        Col.secs('wall_s', 'Wall'),
        Col.tag('final_tag', 'Tag'),
        Col.text('models', 'Models'),
      ],
    ),
  ];
}
