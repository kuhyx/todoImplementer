/// A table on a phone (R7): a header of glyphs (sort, filter), then one
/// tile per row with its headline and two numbers. Tap a row: its link (or
/// its sheet); long-press: the sheet with every column.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/table_parts.dart';
import 'package:todo_implementer/ui/usage/tiles_view.dart';

/// Height of a table's header row.
const tableHeader = 48.0;

/// One page of a table: [rows] is this page's slice of the sorted rows.
class TablePage extends StatelessWidget {
  /// Creates the page.
  const new({
    required this.block,
    required this.rows,
    required this.state,
    required this.onState,
    required this.open,
    required this.page,
    super.key,
  });

  /// The table.
  final TableBlock block;

  /// This page's rows.
  final List<Json> rows;

  /// Sort and filter.
  final TableState state;

  /// New sort or filter.
  final ValueChanged<TableState> onState;

  /// Opens a route.
  final ValueChanged<UsageRoute> open;

  /// Index of this page within the table (0: the first).
  final int page;

  UsageRoute? _link(Json row) {
    for (final c in block.columns) {
      if (c.link?.call(row) case final r?) return r;
    }
    return null;
  }

  void _sheet(BuildContext context, Json row) => unawaited(
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => RowSheet(
        columns: block.columns,
        row: row,
        link: _link(row),
        open: open,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => Column(
    children: [
      SizedBox(
        height: tableHeader,
        child: TableHeader(
          block: block,
          state: state,
          onState: onState,
          page: page,
        ),
      ),
      for (final row in rows)
        SizedBox(
          height: rowHeight,
          child: _RowTile(
            block: block,
            row: row,
            onTap: () => switch (_link(row)) {
              final r? => open(r),
              null => _sheet(context, row),
            },
            onLongPress: () => _sheet(context, row),
          ),
        ),
      if (rows.isEmpty)
        const Expanded(
          child: Icon(
            Icons.inbox_outlined,
            color: AppPalette.mutedOnDark,
            semanticLabel: 'No rows',
          ),
        ),
    ],
  );
}

class _RowTile extends StatelessWidget {
  const new({
    required this.block,
    required this.row,
    required this.onTap,
    required this.onLongPress,
  });

  final TableBlock block;
  final Json row;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    final cols = block.columns;
    final rest = cols.skip(1).take(2);
    return InkWell(
      onTap: onTap,
      onLongPress: onLongPress,
      child: Row(
        children: [
          Expanded(
            child: Text(
              cols.first.show(row),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          for (final c in rest) ...[
            const SizedBox(width: AppSpacing.sm),
            Semantics(
              label: c.label,
              child: Text(
                c.show(row),
                style: const TextStyle(
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ],
          if (cols.any((c) => c.link != null))
            const Icon(Icons.chevron_right, size: 18),
        ],
      ),
    );
  }
}
