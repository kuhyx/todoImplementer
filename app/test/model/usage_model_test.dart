import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/usage_relay.dart';

void main() {
  test('formats follow format.ts', () {
    expect(usd(null), dash);
    expect(usd(1.234), r'$1.23');
    expect(usd(123.4), r'$123');
    expect(share(null), dash);
    expect(share(0.1234), '12.3%');
    expect(compact(null), dash);
    expect(compact(12345), '12.3k');
    expect(compact(2.5e6), '2.5M');
    expect(compact(3e9), '3.0B');
    expect(compact(42), '42');
    expect(duration(null), dash);
    expect(duration(42), '42s');
    expect(duration(600), '10m');
    expect(duration(3900), '1h 05m');
    expect(stamp(null), dash);
    expect(stamp(0), matches(RegExp(r'^19(69|70)-\d\d-\d\d \d\d:\d\d$')));
    expect(plain(null), dash);
    expect(plain(3), '3');
    expect(plain(3.14159), '3.14');
    expect(cellText(null), dash);
    expect(cellText(''), dash);
    expect(cellText(2), '2');
    expect(cellText('x'), 'x');
    expect(cellText(true), '✓');
    expect(cellText(false), '✗');
    expect(cellText([1]), '[1]');
    expect(dayLabel('2026-11-05'), '11-05');
    expect(dayLabel('W1'), 'W1');
  });

  test('columns show by format; inferred columns read key names', () {
    final row = {
      'usd': 2,
      'share': 0.5,
      'a_s': 70,
      'tokens': 2000,
      'ts': 0,
      'n': 3,
      'tag': 'x',
      'obj': {'k': 1},
    };
    expect(Col.money('usd', '').show(row), r'$2.00');
    expect(Col.pct('share', '').show(row), '50.0%');
    expect(Col.secs('a_s', '').show(row), '1m');
    expect(Col.big('tokens', '').show(row), '2.0k');
    expect(Col.when('ts', '').show(row), isNot(dash));
    expect(Col.count('n', '').show(row), '3');
    expect(Col.tag('tag', '').show(row), 'x');
    expect(Col.text('obj', '').show(row), '{k: 1}');
    expect(inferColumns(const []), isEmpty);
    final cols = inferColumns([
      {
        'cost_usd': 1,
        'rate': 0.1,
        'wall_s': 1,
        'bytes': 1,
        'n': 1,
        'kind': 'a',
        'text': 'same',
      },
      {
        'cost_usd': 1,
        'rate': 0.1,
        'wall_s': 1,
        'bytes': 1,
        'n': 1,
        'kind': 'b',
        'text': 'same',
      },
    ]);
    expect(
      [for (final c in cols) c.fmt],
      [Fmt.money, Fmt.pct, Fmt.secs, Fmt.big, Fmt.plain, Fmt.plain, Fmt.plain],
    );
    expect(cols[5].kind, ColKind.tag);
    expect(cols[6].kind, ColKind.text);
  });

  test('table state sorts (nulls last), flips and filters', () {
    final cols = [Col.text('t', ''), Col.count('v', '')];
    final rows = [
      {'t': 'b', 'v': 1},
      {'t': 'A', 'v': null},
      {'t': 'c', 'v': 3},
    ];
    const s = TableState();
    expect(s.apply(cols, rows), rows);
    final byV = s.sortBy('v');
    expect(byV.apply(cols, rows).map((r) => r['t']), ['c', 'b', 'A']);
    final up = byV.sortBy('v');
    expect(up.descending, isFalse);
    expect(up.apply(cols, rows).map((r) => r['t']), ['b', 'c', 'A']);
    expect(s.sortBy('t').apply(cols, rows).map((r) => r['t']), ['c', 'b', 'A']);
    expect(byV.filtered('B').apply(cols, rows).map((r) => r['t']), ['b']);
  });

  test('filters build the API query; routes know their tab', () {
    const f = UsageFilters();
    expect(f.active, isFalse);
    expect(f.panelQuery(['x']), 't.x.limit=0');
    final g = f
        .withField('cwd', '/w')
        .withField('from', '2026-11-01')
        .withField('model', 'm')
        .withField('scope', 'sub')
        .withField('to', '2026-11-02')
        .withField('window', '7d');
    expect(g.active, isTrue);
    expect(g.query().keys, ['cwd', 'from', 'model', 'scope', 'to', 'window']);
    expect(g == f, isFalse);
    expect(g.hashCode, g.panelQuery().hashCode);
    expect(const UsageRoute(UsageView.session, 'k').tab, UsageView.sessions);
    expect(const UsageRoute(UsageView.file).tab, UsageView.context);
    expect(const UsageRoute(UsageView.panel).tab, UsageView.more);
    expect(const UsageRoute(UsageView.ab).tab, UsageView.ab);
    expect(const UsageRoute(UsageView.ab), const UsageRoute(UsageView.ab));
    expect(
      const UsageRoute(UsageView.ab).hashCode,
      const UsageRoute(UsageView.ab).hashCode,
    );
  });

  test('the RTDB usage relay reads snap/usage on each rev move', () async {
    final moves = StreamController<int>();
    final reads = <Object?>[
      {'n': 1},
      'not an object',
      {'n': 2},
    ];
    final sent = <(String, Object?)>[];
    final relay = RtdbUsageRelay(
      send: (kind, body) async {
        sent.add((kind, body));
        return const RelayOk({});
      },
      read: () async => reads.removeAt(0),
      moves: () => moves.stream,
    );
    final got = <Object?>[];
    final sub = relay.usage().listen(got.add);
    await pumpEventQueue();
    moves
      ..add(1)
      ..add(2);
    await pumpEventQueue();
    expect(got, [
      {'n': 1},
      {'n': 2},
    ]);
    unawaited(sub.cancel());
    unawaited(moves.close());
    await relay.tokens('/items', 'a=1');
    expect(sent.single.$1, 'tokens');
    expect(sent.single.$2, {'path': '/items', 'query': 'a=1'});
  });
}
