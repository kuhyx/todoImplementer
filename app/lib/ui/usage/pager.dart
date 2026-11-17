/// Lays a view's blocks out across sideways pages that each fit the box, so
/// the usage page never scrolls vertically (R7). Tiles, banners and charts
/// stack while they fit; a table or list takes whole pages, as many rows per
/// page as fit; a file's content gets a page of its own.
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/chart_view.dart';
import 'package:todo_implementer/ui/usage/table_view.dart';
import 'package:todo_implementer/ui/usage/tiles_view.dart';

const double _gap = AppSpacing.sm;
const _dotsHeight = 20.0;
const _maxDots = 12;

/// Height a stackable block needs at [width] (null: it takes whole pages).
double? stackHeight(UsageBlock b, double width) => switch (b) {
  TilesBlock() => tilesHeight(b, width),
  BannerBlock() => bannerHeight,
  ChartBlock() => chartHeight,
  _ => null,
};

/// The pages of [blocks] in a box of [size]; table rows come from [rowsOf].
List<Widget Function()> paginate(
  List<UsageBlock> blocks,
  Size size, {
  required List<Json> Function(TableBlock) rowsOf,
  required Widget Function(TableBlock, List<Json>, int) table,
  required Widget Function(ListBlock, List<(String, UsageRoute?)>) list,
}) {
  final pages = <Widget Function()>[];
  var stack = <UsageBlock>[];
  var used = 0.0;
  void flush() {
    if (stack.isEmpty) return;
    final mine = stack;
    pages.add(() => _StackPage(mine));
    stack = [];
    used = 0;
  }

  int per(double row, double header) =>
      math.max(1, ((size.height - header) / row).floor());
  for (final b in blocks) {
    final h = stackHeight(b, size.width);
    if (h != null) {
      if (stack.isNotEmpty && used + _gap + h > size.height) flush();
      used += (stack.isEmpty ? 0 : _gap) + h;
      stack.add(b);
      continue;
    }
    flush();
    if (b is TableBlock) {
      final rows = rowsOf(b);
      final n = per(rowHeight, tableHeader);
      for (var i = 0; i == 0 || i * n < rows.length; i++) {
        final slice = rows.skip(i * n).take(n).toList();
        final page = i;
        pages.add(() => table(b, slice, page));
      }
    } else if (b is ListBlock) {
      final n = per(rowHeight, 0);
      for (var i = 0; i == 0 || i * n < b.entries.length; i++) {
        final slice = b.entries.skip(i * n).take(n).toList();
        pages.add(() => list(b, slice));
      }
    } else if (b is ContentBlock) {
      pages.add(() => ContentView(b));
    }
  }
  flush();
  return pages;
}

class _StackPage extends StatelessWidget {
  const new(this.blocks);

  final List<UsageBlock> blocks;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final (i, b) in blocks.indexed) ...[
        if (i > 0) const SizedBox(height: _gap),
        switch (b) {
          final TilesBlock t => TilesView(t),
          final BannerBlock t => BannerView(t),
          final ChartBlock t => ChartView(t),
          _ => const SizedBox.shrink(),
        },
      ],
    ],
  );
}

/// The pager: a [PageView] of [paginate]'s pages with dots (or `n / N`).
class BlockPager extends StatefulWidget {
  /// Creates the pager.
  const new({
    required this.blocks,
    required this.tableState,
    required this.onTableState,
    required this.open,
    super.key,
  });

  /// The view's blocks.
  final List<UsageBlock> blocks;

  /// Sort/filter state of a table by id.
  final TableState Function(String id) tableState;

  /// A table's new state.
  final void Function(String id, TableState state) onTableState;

  /// Opens a route.
  final ValueChanged<UsageRoute> open;

  @override
  State<BlockPager> createState() => _BlockPagerState();
}

class _BlockPagerState extends State<BlockPager> {
  final _controller = PageController();
  int _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final size = Size(box.maxWidth, box.maxHeight - _dotsHeight);
      final pages = paginate(
        widget.blocks,
        size,
        rowsOf: (t) => widget.tableState(t.id).apply(t.columns, t.rows),
        table: (t, rows, i) => TablePage(
          block: t,
          rows: rows,
          state: widget.tableState(t.id),
          onState: (s) => widget.onTableState(t.id, s),
          open: widget.open,
          page: i,
        ),
        list: (l, entries) => ListPage(l, entries, open: widget.open),
      );
      final at = _page.clamp(0, pages.length - 1);
      return Column(
        children: [
          SizedBox(
            height: size.height,
            child: PageView.builder(
              controller: _controller,
              itemCount: pages.length,
              onPageChanged: (i) => setState(() => _page = i),
              itemBuilder: (_, i) => pages[i](),
            ),
          ),
          SizedBox(
            height: _dotsHeight,
            child: pages.length > _maxDots
                ? Center(child: Text('${at + 1} / ${pages.length}'))
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      if (pages.length > 1)
                        for (var i = 0; i < pages.length; i++)
                          Padding(
                            padding: const EdgeInsets.all(3),
                            child: Icon(
                              Icons.circle,
                              size: 7,
                              color: i == at
                                  ? AppPalette.accent
                                  : AppPalette.lineDark,
                            ),
                          ),
                    ],
                  ),
          ),
        ],
      );
    },
  );
}
