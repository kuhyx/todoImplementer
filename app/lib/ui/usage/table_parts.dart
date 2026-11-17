/// A table's header (sort, filter) and the sheet of one row's columns.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';

/// A table's header: its glyph, page number, filter and sort.
class TableHeader extends StatelessWidget {
  /// Creates the header.
  const new({
    required this.block,
    required this.state,
    required this.onState,
    required this.page,
    super.key,
  });

  /// The table.
  final TableBlock block;

  /// Sort and filter.
  final TableState state;

  /// New sort or filter.
  final ValueChanged<TableState> onState;

  /// Index of this page within the table.
  final int page;

  @override
  Widget build(BuildContext context) {
    final sorted = block.columns.where((c) => c.key == state.sortKey);
    return Row(
      children: [
        Icon(block.icon, semanticLabel: block.semantics),
        if (page > 0)
          Text(' ${page + 1}', style: const TextStyle(fontSize: 12)),
        const Spacer(),
        IconButton(
          key: ValueKey('filter-${block.id}'),
          isSelected: state.filter.isNotEmpty,
          icon: const Icon(Icons.search, semanticLabel: 'Filter rows'),
          onPressed: () => unawaited(_filter(context)),
        ),
        IconButton(
          key: ValueKey('sort-${block.id}'),
          icon: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.sort, semanticLabel: 'Sort rows'),
              if (sorted.isNotEmpty) ...[
                Icon(columnGlyph(sorted.first), size: 16),
                Icon(state.descending ? Icons.south : Icons.north, size: 14),
              ],
            ],
          ),
          onPressed: () => unawaited(_sort(context)),
        ),
      ],
    );
  }

  Future<void> _filter(BuildContext context) async {
    final text = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.md,
          AppSpacing.md,
          AppSpacing.md,
          MediaQuery.viewInsetsOf(ctx).bottom + AppSpacing.md,
        ),
        child: TextFormField(
          key: const ValueKey('filter-field'),
          initialValue: state.filter,
          autofocus: true,
          decoration: const InputDecoration(prefixIcon: Icon(Icons.search)),
          onFieldSubmitted: (v) => Navigator.pop(ctx, v),
        ),
      ),
    );
    if (text != null) onState(state.filtered(text));
  }

  Future<void> _sort(BuildContext context) async {
    final key = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final c in block.columns)
              ChoiceChip(
                key: ValueKey('sort-by-${c.key}'),
                selected: c.key == state.sortKey,
                label: Icon(columnGlyph(c), size: 18, semanticLabel: c.label),
                onSelected: (_) => Navigator.pop(ctx, c.key),
              ),
          ],
        ),
      ),
    );
    if (key != null) onState(state.sortBy(key));
  }
}

/// Every column of one row: glyph and value; an open button when the row
/// links somewhere. A list (R7 exemption): it may scroll.
class RowSheet extends StatelessWidget {
  /// Creates the sheet.
  const new({
    required this.columns,
    required this.row,
    required this.open,
    this.link,
    super.key,
  });

  /// The table's columns.
  final List<UsageColumn> columns;

  /// The row.
  final Json row;

  /// Where the row leads, if anywhere.
  final UsageRoute? link;

  /// Opens a route.
  final ValueChanged<UsageRoute> open;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: ListView(
      shrinkWrap: true,
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        for (final c in columns)
          ListTile(
            dense: true,
            leading: Icon(columnGlyph(c), semanticLabel: c.label),
            title: SelectableText(c.show(row)),
          ),
        if (link case final l?)
          IconButton.filled(
            key: const ValueKey('row-open'),
            icon: const Icon(Icons.open_in_new, semanticLabel: 'Open'),
            onPressed: () {
              Navigator.pop(context);
              open(l);
            },
          ),
      ],
    ),
  );
}
