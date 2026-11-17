/// The usage page (`web/src/pages/usage.astro`): a glyph tab per view, a
/// filter sheet, a back glyph for detail routes, and the view's blocks in a
/// sideways pager. Every request goes over the relay (`tokens`, `snap/usage`).
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/usage_relay.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/filter_sheet.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';
import 'package:todo_implementer/ui/usage/pager.dart';
import 'package:todo_implementer/ui/usage/views/load.dart';

/// Usage page fed by [relay].
class UsagePage extends StatefulWidget {
  /// Creates the page.
  const new({required this.relay, super.key});

  /// The link to the PC.
  final UsageRelay relay;

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> {
  final List<UsageRoute> _stack = [const UsageRoute(UsageView.overview)];
  UsageFilters _filters = const UsageFilters();
  final Map<String, TableState> _tables = {};
  late Future<List<UsageBlock>> _blocks = _load()..ignore();

  UsageRoute get _route => _stack.last;

  Future<List<UsageBlock>> _load() =>
      loaderFor(_route.view)(ViewContext(widget.relay, _filters), _route.arg);

  void _reload() => setState(() {
    _blocks = _load()..ignore();
  });

  void _go(UsageRoute r, {bool push = true}) {
    if (push) {
      _stack.add(r);
    } else {
      _stack
        ..clear()
        ..add(r);
    }
    _reload();
  }

  void _back() {
    _stack.removeLast();
    _reload();
  }

  String _tableKey(String id) => '${_route.view.name}/${_route.arg}/$id';

  Future<void> _openFilters() async {
    final index = await widget.relay.tokens('', '');
    if (!mounted) return;
    final next = await showModalBottomSheet<UsageFilters>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => FilterSheet(
        filters: _filters,
        index: index is RelayOk ? index.data : const <String, dynamic>{},
      ),
    );
    if (next != null && next != _filters) {
      _filters = next;
      _reload();
    }
  }

  Widget _bar() => SizedBox(
    height: 48,
    child: Row(
      children: [
        if (_stack.length > 1)
          IconButton(
            key: const ValueKey('usage-back'),
            icon: const Icon(Icons.arrow_back, semanticLabel: 'Back'),
            onPressed: _back,
          ),
        Expanded(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final v in tabViews)
                  IconButton(
                    key: ValueKey('usage-tab-${v.name}'),
                    isSelected: _route.tab == v,
                    color: _route.tab == v ? AppPalette.accent : null,
                    icon: Icon(
                      viewGlyphs[v]!.$1,
                      semanticLabel: viewGlyphs[v]!.$2,
                    ),
                    onPressed: () => _go(UsageRoute(v), push: false),
                  ),
              ],
            ),
          ),
        ),
        IconButton(
          key: const ValueKey('usage-filters'),
          icon: Badge(
            isLabelVisible: _filters.active,
            smallSize: 8,
            child: const Icon(
              Icons.filter_alt_outlined,
              semanticLabel: 'Filters',
            ),
          ),
          onPressed: () => unawaited(_openFilters()),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
    child: Column(
      children: [
        _bar(),
        Expanded(
          child: FutureBuilder<List<UsageBlock>>(
            future: _blocks,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return Center(
                  child: CircularProgressIndicator(
                    semanticsLabel:
                        'Waiting for ${viewGlyphs[_route.view]!.$2}',
                  ),
                );
              }
              if (snap.error case final e?) {
                return UsageError(error: e, retry: _reload);
              }
              return BlockPager(
                key: ValueKey('${_tableKey('')}?${_filters.panelQuery()}'),
                blocks: snap.data!,
                tableState: (id) =>
                    _tables[_tableKey(id)] ?? const TableState(),
                onTableState: (id, s) =>
                    setState(() => _tables[_tableKey(id)] = s),
                open: _go,
              );
            },
          ),
        ),
      ],
    ),
  );
}

/// A failed load: the code as a glyph on a red tint, retry and copy.
class UsageError extends StatelessWidget {
  /// Creates the view.
  const new({required this.error, required this.retry, super.key});

  /// What failed ([UsageFailure] or any other error).
  final Object error;

  /// Loads again.
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) {
    final code = error is UsageFailure
        ? (error as UsageFailure).failed.code
        : 'internal';
    final icon = switch (code) {
      'offline' => Icons.cloud_off,
      'disabled' => Icons.block,
      _ => Icons.error_outline,
    };
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: AppPalette.danger, semanticLabel: code),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                key: const ValueKey('usage-retry'),
                icon: const Icon(Icons.refresh, semanticLabel: 'Retry'),
                onPressed: retry,
              ),
              IconButton(
                key: const ValueKey('usage-copy-error'),
                icon: const Icon(Icons.copy, semanticLabel: 'Copy error'),
                onPressed: () =>
                    unawaited(Clipboard.setData(ClipboardData(text: '$error'))),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
