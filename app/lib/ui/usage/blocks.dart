/// What a usage view is made of. A view loads its data and returns a list of
/// blocks; the pager lays them out across sideways pages (R7: no vertical
/// scroll), so a view never builds widgets itself.
library;

import 'package:flutter/widgets.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';

/// Good, neutral or bad: a shape, a colour and a screen-reader word.
enum Level {
  /// On target / fine.
  green,

  /// No data yet.
  grey,

  /// Off target / over a limit.
  red,
}

/// One block of a view.
@immutable
sealed class UsageBlock {
  const new();
}

/// One headline number.
@immutable
class UsageTile {
  /// Creates the tile; [label] is its screen-reader name.
  const new(
    this.icon,
    this.label,
    this.value, {
    this.level,
    this.target,
    this.higherIsBetter,
  });

  /// What the number is.
  final IconData icon;

  /// Screen-reader name.
  final String label;

  /// The number, formatted.
  final String value;

  /// On or off target, when the number has one.
  final Level? level;

  /// The target, formatted.
  final String? target;

  /// Which way is good (null: no direction).
  final bool? higherIsBetter;
}

/// A row of headline numbers.
class TilesBlock extends UsageBlock {
  /// Creates the block.
  const new(this.tiles);

  /// The tiles.
  final List<UsageTile> tiles;
}

/// A server message (verdict, caption): a level glyph that shows the text
/// on tap, so the page itself stays text-free.
class BannerBlock extends UsageBlock {
  /// Creates the block.
  const new(this.level, this.text);

  /// Good, neutral or bad.
  final Level level;

  /// The server's words.
  final String text;
}

/// Bars, lines, intervals or a ranking.
enum ChartKind {
  /// Grouped bars over [ChartSpec.labels].
  bar,

  /// Lines over [ChartSpec.labels].
  line,

  /// One horizontal bar per label, largest first.
  rank,

  /// A point with a low..high whisker per label, around zero.
  interval,
}

/// One series of a chart.
@immutable
class ChartSeries {
  /// Creates the series; [name] is its screen-reader name.
  const new(this.name, this.icon, this.values, {this.color = 0});

  /// Screen-reader name.
  final String name;

  /// Legend glyph.
  final IconData icon;

  /// One value per label; null is a gap.
  final List<num?> values;

  /// Categorical slot (fixed order, never cycled past the palette).
  final int color;
}

/// A chart.
class ChartBlock extends UsageBlock {
  /// Creates the chart; [semantics] is its screen-reader name.
  const new({
    required this.kind,
    required this.semantics,
    required this.icon,
    required this.labels,
    required this.series,
    required this.fmt,
    this.low = const [],
    this.high = const [],
  });

  /// The form.
  final ChartKind kind;

  /// Screen-reader title.
  final String semantics;

  /// Title glyph.
  final IconData icon;

  /// Category or x labels (data: days, repos, stages).
  final List<String> labels;

  /// The series.
  final List<ChartSeries> series;

  /// Value format.
  final String Function(num) fmt;

  /// Interval charts: lower bound per label.
  final List<num> low;

  /// Interval charts: upper bound per label.
  final List<num> high;
}

/// A sortable, filterable table; on a phone its rows are tiles that open a
/// sheet with every column.
class TableBlock extends UsageBlock {
  /// Creates the table.
  const new({
    required this.id,
    required this.semantics,
    required this.icon,
    required this.columns,
    required this.rows,
  });

  /// Stable id (its sort/filter state is kept per view and id).
  final String id;

  /// Screen-reader title.
  final String semantics;

  /// Title glyph.
  final IconData icon;

  /// The columns, the first is the row's headline.
  final List<UsageColumn> columns;

  /// The rows.
  final List<Json> rows;
}

/// A list of entries, each maybe opening a route (panel index, git log).
class ListBlock extends UsageBlock {
  /// Creates the list.
  const new(this.icon, this.semantics, this.entries);

  /// Title glyph.
  final IconData icon;

  /// Screen-reader title.
  final String semantics;

  /// Text (data) and where it leads.
  final List<(String, UsageRoute?)> entries;
}

/// A long text (a context file's content); the only block that scrolls.
class ContentBlock extends UsageBlock {
  /// Creates the block.
  const new(this.text);

  /// The text, or null when the file is not readable.
  final String? text;
}
