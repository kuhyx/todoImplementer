/// Shared plumbing of the usage views: the context a view loads with, the
/// `tokens` fetch, chart shorthands, and the route -> loader table.
library;

import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/usage_relay.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/views/context.dart';
import 'package:todo_implementer/ui/usage/views/more.dart';
import 'package:todo_implementer/ui/usage/views/quality.dart';
import 'package:todo_implementer/ui/usage/views/session.dart';
import 'package:todo_implementer/ui/usage/views/spend.dart';
import 'package:todo_implementer/ui/usage/views/work.dart';

/// What a view loads with.
@immutable
class ViewContext {
  /// Creates the context.
  const new(this.relay, this.filters);

  /// The link to the PC.
  final UsageRelay relay;

  /// The global filters.
  final UsageFilters filters;
}

/// A refused or failed request, carried to the page's error glyph.
class UsageFailure implements Exception {
  /// Wraps [failed].
  const new(this.failed);

  /// The relay's answer.
  final RelayFailed failed;

  @override
  String toString() => '${failed.code}: ${failed.error}';
}

/// `GET /api/tokens<path>?<query>`; a refusal throws [UsageFailure].
Future<Json> fetch(ViewContext c, String path, [String query = '']) async =>
    switch (await c.relay.tokens(path, query)) {
      RelayOk(:final data) => data,
      final RelayFailed f => throw UsageFailure(f),
    };

/// A panel with the global filters, every one of [tables] in full.
Future<Json> panel(ViewContext c, String name, [List<String> t = const []]) =>
    fetch(c, '/panel/${Uri.encodeComponent(name)}', c.filters.panelQuery(t));

/// Loads one view.
typedef ViewLoad = Future<List<UsageBlock>> Function(ViewContext c, String arg);

/// The loader of [view].
ViewLoad loaderFor(UsageView view) => switch (view) {
  UsageView.overview => overviewView,
  UsageView.sessions => sessionsView,
  UsageView.session => sessionView,
  UsageView.items => itemsView,
  UsageView.efficiency => efficiencyView,
  UsageView.autonomy => autonomyView,
  UsageView.levers => leversView,
  UsageView.context => contextView,
  UsageView.file => fileView,
  UsageView.anomalies => anomaliesView,
  UsageView.ab => abView,
  UsageView.more => moreView,
  UsageView.panel => genericView,
};

/// The number at [k], or null.
num? at(Json r, String k) => r[k] is num ? r[k] as num : null;

/// The numbers at [k] of every row.
List<num?> column(List<Json> rows, String k) => [
  for (final r in rows) at(r, k),
];

/// One-series chart shorthand.
ChartBlock chart(
  ChartKind kind,
  String title,
  IconData icon,
  List<String> labels,
  List<num?> values,
  String Function(num) fmt, {
  int color = 0,
}) => ChartBlock(
  kind: kind,
  semantics: title,
  icon: icon,
  labels: labels,
  series: [ChartSeries(title, icon, values, color: color)],
  fmt: fmt,
);

/// A ranking of `(label, value)` pairs, largest first.
ChartBlock rank(
  String title,
  IconData icon,
  List<(String, num)> pairs,
  String Function(num) fmt, {
  int color = 0,
}) {
  final sorted = [...pairs]..sort((a, b) => b.$2.compareTo(a.$2));
  return chart(
    ChartKind.rank,
    title,
    icon,
    [for (final p in sorted) p.$1],
    [for (final p in sorted) p.$2],
    fmt,
    color: color,
  );
}
