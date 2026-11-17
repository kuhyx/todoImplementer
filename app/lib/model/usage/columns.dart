/// Table columns of the usage views (`web/src/usage/columns.ts`): the key
/// says where the value lives, the kind how it sorts and filters, [Fmt] how
/// it shows. Header glyphs live in the UI (`ui/usage/glyphs.dart`).
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/model/usage/route.dart';

/// How a column sorts and filters.
enum ColKind {
  /// Free text: contains-filter, alphabetical sort.
  text,

  /// A number: numeric sort.
  number,

  /// A small set of values: alphabetical sort.
  tag,
}

/// How a number column shows its value.
enum Fmt {
  /// As is ([cellText]).
  plain,

  /// [usd].
  money,

  /// [share].
  pct,

  /// [duration].
  secs,

  /// [compact].
  big,

  /// [stamp].
  when,
}

/// Where a row links to, or null.
typedef RowLink = UsageRoute? Function(Json row);

/// One column.
@immutable
class UsageColumn {
  /// Creates the column; [label] is its screen-reader name.
  const new(
    this.key,
    this.label, {
    this.kind = ColKind.text,
    this.fmt = Fmt.plain,
    this.link,
  });

  /// The row key.
  final String key;

  /// Screen-reader name (textgate: the header shows a glyph).
  final String label;

  /// Sort and filter behaviour.
  final ColKind kind;

  /// Number format.
  final Fmt fmt;

  /// The route a tap on this cell opens.
  final RowLink? link;

  /// The cell of [row] as display text.
  String show(Json row) {
    final v = row[key];
    if (v is! num?) return cellText(v);
    return switch (fmt) {
      Fmt.plain => cellText(v),
      Fmt.money => usd(v),
      Fmt.pct => share(v),
      Fmt.secs => duration(v),
      Fmt.big => compact(v),
      Fmt.when => stamp(v),
    };
  }
}

/// Builders, one per column kind of the web page.
abstract final class Col {
  /// Free text.
  static UsageColumn text(String key, String label) => UsageColumn(key, label);

  /// Text that opens [link].
  static UsageColumn link(String key, String label, RowLink link) =>
      UsageColumn(key, label, link: link);

  /// An enum-like value.
  static UsageColumn tag(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.tag);

  /// A plain number.
  static UsageColumn count(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number);

  /// US dollars.
  static UsageColumn money(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number, fmt: Fmt.money);

  /// A 0..1 share.
  static UsageColumn pct(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number, fmt: Fmt.pct);

  /// Seconds.
  static UsageColumn secs(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number, fmt: Fmt.secs);

  /// A large count (tokens, bytes).
  static UsageColumn big(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number, fmt: Fmt.big);

  /// Epoch seconds.
  static UsageColumn when(String key, String label) =>
      UsageColumn(key, label, kind: ColKind.number, fmt: Fmt.when);
}

const _enumMax = 12;
final _money = RegExp('usd|cost');
final _share = RegExp('share|rate');
final _big = RegExp('tokens|bytes');

/// Columns for rows nobody wrote a schema for: the first row's keys,
/// formatted by name (cost, share, seconds, tokens).
List<UsageColumn> inferColumns(List<Json> rows) {
  if (rows.isEmpty) return const [];
  return [
    for (final MapEntry(:key, value: sample) in rows.first.entries)
      _infer(rows, key, key.replaceAll('_', ' '), sample),
  ];
}

UsageColumn _infer(List<Json> rows, String key, String label, Object? s) {
  if (s is! num) {
    final kinds = rows.map((r) => '${r[key]}').toSet();
    final isTag = s is String && kinds.length > 1 && kinds.length <= _enumMax;
    return isTag ? Col.tag(key, label) : Col.text(key, label);
  }
  if (_money.hasMatch(key)) return Col.money(key, label);
  if (_share.hasMatch(key)) return Col.pct(key, label);
  if (key.endsWith('_s')) return Col.secs(key, label);
  return _big.hasMatch(key) ? Col.big(key, label) : Col.count(key, label);
}

/// Sort and filter state of one table.
@immutable
class TableState {
  /// Creates the state (no sort, no filter).
  const new({this.sortKey, this.descending = true, this.filter = ''});

  /// The sorted column, or null for the server's order.
  final String? sortKey;

  /// Largest first.
  final bool descending;

  /// Rows must contain this text in some cell (case-insensitive).
  final String filter;

  /// Sort by [key]; a second tap on the same key flips the direction.
  TableState sortBy(String key) => TableState(
    sortKey: key,
    descending: key != sortKey || !descending,
    filter: filter,
  );

  /// Filter by [text].
  TableState filtered(String text) =>
      TableState(sortKey: sortKey, descending: descending, filter: text);

  /// [rows] filtered and sorted for [columns]; nulls sort last.
  List<Json> apply(List<UsageColumn> columns, List<Json> rows) {
    final needle = filter.trim().toLowerCase();
    final out = needle.isEmpty
        ? [...rows]
        : rows
              .where(
                (r) => columns.any(
                  (c) => c.show(r).toLowerCase().contains(needle),
                ),
              )
              .toList();
    final key = sortKey;
    if (key == null) return out;
    int cmp(Json a, Json b) {
      final (x, y) = (a[key], b[key]);
      if (x == null || y == null) return x == y ? 0 : (x == null ? 1 : -1);
      final c = x is num && y is num
          ? x.compareTo(y)
          : '$x'.toLowerCase().compareTo('$y'.toLowerCase());
      return descending ? -c : c;
    }

    return out..sort(cmp);
  }
}
