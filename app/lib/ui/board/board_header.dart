/// The strip over the board: health glyphs (stale board, overage alert, API
/// key, plan limit), running slots, the free-credits switch, copy-errors and
/// refresh; then the search field and the repo and sort pickers. Every
/// server sentence is screen-reader text only (textgate).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

/// Status glyphs and global switches.
class StatusStrip extends StatelessWidget {
  /// Creates the strip.
  const new({
    required this.board,
    required this.errors,
    required this.onCredits,
    required this.onRefresh,
    required this.onCopyErrors,
    super.key,
  });

  /// The board.
  final Board board;

  /// Failures recorded this session.
  final int errors;

  /// Turns the credits fallback on or off.
  final ValueChanged<bool> onCredits;

  /// Asks the worker to republish.
  final VoidCallback onRefresh;

  /// Copies the failures to the clipboard.
  final VoidCallback onCopyErrors;

  @override
  Widget build(BuildContext context) {
    final b = board;
    final keyColor = b.apiKeyLevel == 'error'
        ? AppPalette.danger
        : AppPalette.warning;
    return Row(
      children: [
        if (b.error case final e?)
          Icon(Icons.cloud_off, color: AppPalette.danger, semanticLabel: e),
        if (b.alert case final a?)
          Icon(Icons.money_off, color: AppPalette.danger, semanticLabel: a),
        if (b.apiKeyLevel != 'ok')
          Icon(Icons.key_off, color: keyColor, semanticLabel: b.apiKeyText),
        if (b.limitActive)
          const Icon(Icons.hourglass_bottom, color: AppPalette.warning),
        Badge.count(
          count: b.slotsUsed,
          isLabelVisible: b.slotsUsed > 0,
          child: const Icon(Icons.memory),
        ),
        const Spacer(),
        if (errors > 0)
          IconButton(
            key: const Key('copy-errors'),
            onPressed: onCopyErrors,
            icon: Badge.count(
              count: errors,
              child: const Icon(Icons.bug_report_outlined),
            ),
          ),
        const Icon(Icons.savings_outlined),
        Switch(
          key: const Key('credits'),
          value: b.creditsEnabled,
          onChanged: onCredits,
        ),
        IconButton(
          key: const Key('refresh'),
          onPressed: onRefresh,
          icon: const Icon(Icons.refresh),
        ),
      ],
    );
  }
}

/// Search, repo filter and sort.
class Toolbar extends StatelessWidget {
  /// Creates the toolbar.
  const new({
    required this.board,
    required this.state,
    required this.onChanged,
    super.key,
  });

  /// The board (for the repo list).
  final Board board;

  /// Current selection.
  final ViewState state;

  /// Reports a new selection.
  final ValueChanged<ViewState> onChanged;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: TextField(
          key: const Key('search'),
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            isDense: true,
          ),
          onChanged: (q) => onChanged(state.copyWith(query: q)),
        ),
      ),
      PopupMenuButton<String>(
        key: const Key('repo'),
        icon: Icon(
          Icons.filter_list,
          color: state.repo.isEmpty ? null : AppPalette.accent,
        ),
        onSelected: (r) => onChanged(state.copyWith(repo: r)),
        itemBuilder: (_) => [
          for (final (value, count) in repoOptions(board))
            PopupMenuItem(
              value: value,
              child: _RepoRow(value: value, count: count),
            ),
        ],
      ),
      PopupMenuButton<BoardSort>(
        key: const Key('sort'),
        icon: Icon(sortIcon(state.sort)),
        onSelected: (s) => onChanged(state.copyWith(sort: s)),
        itemBuilder: (_) => [
          for (final s in BoardSort.values)
            PopupMenuItem(value: s, child: Icon(sortIcon(s))),
        ],
      ),
    ],
  );
}

class _RepoRow extends StatelessWidget {
  const new({required this.value, required this.count});

  final String value;
  final int count;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      if (value.isEmpty)
        const Icon(Icons.select_all)
      else if (value == yours)
        const Icon(Icons.person_outline)
      else
        Text(value.split('/').last),
      const Spacer(),
      Text('$count', style: const TextStyle(color: AppPalette.mutedOnDark)),
    ],
  );
}

/// The five column tabs: glyph and visible-card count each.
class ColumnTabs extends StatelessWidget {
  /// Creates the tabs.
  const new({
    required this.view,
    required this.active,
    required this.onPick,
    super.key,
  });

  /// Filtered columns.
  final List<ColumnView> view;

  /// The shown column.
  final String active;

  /// Picks a column.
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (final v in view)
        Expanded(
          child: Semantics(
            label: v.column.label,
            selected: v.column.id == active,
            excludeSemantics: true,
            child: IconButton(
              key: ValueKey('col-${v.column.id}'),
              isSelected: v.column.id == active,
              onPressed: () => onPick(v.column.id),
              icon: Badge.count(
                count: v.cards.length,
                isLabelVisible: v.cards.isNotEmpty,
                backgroundColor: v.column.id == 'needs_you'
                    ? AppPalette.warning
                    : AppPalette.inkRaised2,
                textColor: v.column.id == 'needs_you'
                    ? AppPalette.onFill
                    : AppPalette.textOnDark,
                child: Icon(columnIcon(v.column.id)),
              ),
            ),
          ),
        ),
    ],
  );
}
