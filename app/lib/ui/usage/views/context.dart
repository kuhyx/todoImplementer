/// Context files and one file (`web/src/usage/view-context.ts`,
/// `view-file.ts`).
library;

import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

UsageRoute _file(Json row) => UsageRoute(UsageView.file, str(row, 'path'));

String _base(String path) => path.split('/').last;

/// Always-loaded context files.
Future<List<UsageBlock>> contextView(ViewContext c, String _) async {
  final d = await panel(c, 'context', ['files']);
  final files = objs(d, 'files');
  final over = files.where((f) => str(f, 'status') != 'ok').length;
  final perDay = files.fold<double>(0, (s, f) => s + numOf(f, 'usd_per_day'));
  final costly = [
    for (final f in files) (_base(str(f, 'path')), numOf(f, 'usd_per_day')),
  ];
  return [
    TilesBlock([
      UsageTile(Icons.description_outlined, 'Files', '${files.length}'),
      UsageTile(
        Icons.report_outlined,
        'Over a limit',
        '$over',
        level: over > 0 ? Level.red : Level.green,
      ),
      UsageTile(Icons.today, 'Standing cost per day', usd(perDay)),
      UsageTile(
        Icons.call_made,
        'Calls per day',
        '${numOf(d, 'calls_per_day').round()}',
      ),
    ]),
    rank(
      'Costliest files (USD per day)',
      Icons.today,
      (costly..sort((a, b) => b.$2.compareTo(a.$2))).take(10).toList(),
      usd,
      color: 3,
    ),
    TableBlock(
      id: 'files',
      semantics: 'Context files',
      icon: Icons.description_outlined,
      rows: [
        for (final f in files)
          {
            ...f,
            'breaches': objs(f, 'breaches').length,
            'budgets': strs(f, 'budgets').join(', '),
            'history': objs(f, 'history').length,
          },
      ],
      columns: [
        Col.link('path', 'File', _file),
        Col.money('usd_per_day', 'USD / day'),
        Col.tag('status', 'Status'),
        Col.tag('kind', 'Kind'),
        Col.tag('standing', 'Loaded'),
        Col.big('tokens', 'Tokens'),
        Col.big('bytes', 'Bytes'),
        Col.count('lines', 'Lines'),
        Col.count('breaches', 'Breaches'),
        Col.text('budgets', 'Budgets'),
        Col.count('history', 'Versions'),
      ],
    ),
  ];
}

/// One context file: its numbers, breaches, size history, git log, content.
Future<List<UsageBlock>> fileView(ViewContext c, String path) async {
  final query = Uri(queryParameters: {'path': path}).query;
  final (detail, list) = await (
    fetch(c, '/context-file', query),
    panel(c, 'context', ['files']),
  ).wait;
  final row = objs(list, 'files').where((f) => str(f, 'path') == path);
  final f = row.isEmpty ? null : row.first;
  final history = f == null ? const <Json>[] : objs(f, 'history');
  return [
    if (f != null) ...[
      TilesBlock([
        UsageTile(Icons.token_outlined, 'Tokens', compact(at(f, 'tokens'))),
        UsageTile(Icons.data_usage, 'Bytes', compact(at(f, 'bytes'))),
        UsageTile(Icons.format_list_numbered, 'Lines', plain(at(f, 'lines'))),
        UsageTile(
          Icons.today,
          'Standing cost per day',
          usd(at(f, 'usd_per_day')),
          level: str(f, 'status') == 'ok' ? Level.green : Level.red,
        ),
      ]),
      TableBlock(
        id: 'breaches',
        semantics: 'Budget breaches',
        icon: Icons.report_outlined,
        rows: objs(f, 'breaches'),
        columns: [
          Col.text('measure', 'Measure'),
          Col.count('value', 'Value'),
          Col.count('limit', 'Limit'),
          Col.tag('hard', 'Hard'),
          Col.text('why', 'Why'),
        ],
      ),
    ],
    if (history.length > 1)
      chart(
        ChartKind.line,
        'Size over time',
        Icons.history,
        [for (final h in history) stamp(at(h, 'ts')).substring(0, 10)],
        column(history, 'bytes'),
        compact,
      ),
    ListBlock(Icons.commit, 'Git history', [
      for (final l in strs(detail, 'git_log')) (l, null),
    ]),
    ContentBlock(strOr(detail, 'content')),
  ];
}
