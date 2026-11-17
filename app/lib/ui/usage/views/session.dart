/// One session: prompts, tools, subagents (`web/src/usage/view-session.ts`).
library;

import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

const _toolSums = ['calls', 'result_tokens', 'usd', 'carry_usd'];

/// Per-tool totals over every prompt of a session.
List<Json> toolTotals(List<Json> prompts) {
  final by = <String, Json>{};
  for (final tool in prompts.expand((p) => objs(p, 'tools'))) {
    final name = str(tool, 'name');
    final acc = by.putIfAbsent(name, () => {'name': name});
    for (final k in _toolSums) {
      acc[k] = ((acc[k] as num?) ?? 0) + numOf(tool, k);
    }
  }
  return by.values.toList();
}

/// One session.
Future<List<UsageBlock>> sessionView(ViewContext c, String key) async {
  final d = await fetch(c, '/session/${Uri.encodeComponent(key)}');
  final s = objOr(d, 'session') ?? const {};
  final prompts = objs(d, 'prompts')
    ..sort((a, b) => numOf(a, 'idx').compareTo(numOf(b, 'idx')));
  final agents = [
    ...objs(d, 'unattributed'),
    ...prompts.expand((p) => objs(p, 'subagents')),
  ];
  return [
    TilesBlock([
      UsageTile(Icons.attach_money, 'Spend', usd(numOf(s, 'usd'))),
      UsageTile(Icons.person_outline, 'Main', usd(numOf(s, 'usd_main'))),
      UsageTile(Icons.smart_toy_outlined, 'Subagents', usd(at(s, 'usd_sub'))),
      UsageTile(Icons.call_made, 'Calls', compact(at(s, 'calls'))),
      UsageTile(Icons.chat_bubble_outline, 'Prompts', plain(at(s, 'prompts'))),
      UsageTile(Icons.timer_outlined, 'Active', duration(at(s, 'active_s'))),
      UsageTile(Icons.folder_outlined, 'Directory', str(s, 'cwd', dash)),
      UsageTile(Icons.play_arrow_outlined, 'First', stamp(at(s, 'first_ts'))),
      UsageTile(Icons.stop_outlined, 'Last', stamp(at(s, 'last_ts'))),
      UsageTile(Icons.flag_outlined, 'Tag', str(s, 'final_tag', dash)),
    ]),
    ChartBlock(
      kind: ChartKind.bar,
      semantics: 'Cost per prompt',
      icon: Icons.chat_bubble_outline,
      labels: [for (final p in prompts) '#${plain(at(p, 'idx'))}'],
      series: [
        ChartSeries('Own', Icons.person_outline, column(prompts, 'usd_own')),
        ChartSeries(
          'Subagents',
          Icons.smart_toy_outlined,
          column(prompts, 'usd_sub'),
          color: 1,
        ),
      ],
      fmt: usd,
    ),
    TableBlock(
      id: 'prompts',
      semantics: 'Prompts',
      icon: Icons.chat_bubble_outline,
      rows: prompts,
      columns: [
        Col.text('text', 'Prompt'),
        Col.money('usd', 'USD'),
        Col.when('ts', 'Time'),
        Col.count('idx', '#'),
        Col.money('usd_own', 'Own'),
        Col.money('usd_sub', 'Subagents'),
        Col.count('calls', 'Calls'),
        Col.secs('active_s', 'Active'),
        Col.secs('wall_s', 'Wall'),
      ],
    ),
    TableBlock(
      id: 'tools',
      semantics: 'Tools',
      icon: Icons.build_outlined,
      rows: toolTotals(prompts),
      columns: [
        Col.text('name', 'Tool'),
        Col.money('usd', 'USD'),
        Col.count('calls', 'Calls'),
        Col.big('result_tokens', 'Result tokens'),
        Col.money('carry_usd', 'Carry USD'),
      ],
    ),
    TableBlock(
      id: 'subagents',
      semantics: 'Subagents',
      icon: Icons.hub_outlined,
      rows: agents,
      columns: [
        Col.text('description', 'Task'),
        Col.money('usd', 'USD'),
        Col.tag('agent_type', 'Type'),
        Col.tag('model', 'Model'),
        Col.count('depth', 'Depth'),
        Col.count('calls', 'Calls'),
        Col.secs('wall_s', 'Wall'),
      ],
    ),
  ];
}
