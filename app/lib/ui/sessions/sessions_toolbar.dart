/// The sessions toolbar (web `sessions/toolbar.ts`): search, the sort
/// picker, the filter sheet, reset and the shown count on one row, then the
/// status chips with their counts.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/model/sessions_view.dart';
import 'package:todo_implementer/ui/sessions/session_filters.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';

/// Search row and status chips.
class SessionsToolbar extends StatelessWidget {
  /// Creates the toolbar.
  const new({
    required this.all,
    required this.query,
    required this.shown,
    required this.onChanged,
    super.key,
  });

  /// Every session (counts and projects come from all of them).
  final List<Session> all;

  /// The current query.
  final SessionQuery query;

  /// How many rows the query keeps.
  final int shown;

  /// A new query.
  final ValueChanged<SessionQuery> onChanged;

  void _filters(BuildContext context) => showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) =>
        SessionFilters(all: all, query: query, onChanged: onChanged),
  );

  @override
  Widget build(BuildContext context) {
    final counts = statusCounts(all);
    final filtered =
        query.project.isNotEmpty ||
        query.older != null ||
        query.mark != null ||
        query.showDone;
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: Semantics(
                label: spoken['search'],
                textField: true,
                child: TextField(
                  key: const Key('sessions-search'),
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    isDense: true,
                  ),
                  onChanged: (q) => onChanged(query.copyWith(q: q)),
                ),
              ),
            ),
            Semantics(
              label: spoken['sort'],
              button: true,
              child: PopupMenuButton<SessionSort>(
                key: const Key('sessions-sort'),
                icon: Icon(
                  query.sort == null
                      ? Icons.sort
                      : query.desc
                      ? Icons.arrow_downward
                      : Icons.arrow_upward,
                ),
                onSelected: (k) => onChanged(query.cycled(k)),
                itemBuilder: (_) => [
                  for (final k in SessionSort.values)
                    PopupMenuItem(
                      key: ValueKey('sort-${k.name}'),
                      value: k,
                      child: Icon(
                        sortIcon(k),
                        color: query.sort == k ? AppPalette.accent : null,
                        semanticLabel: k.name,
                      ),
                    ),
                ],
              ),
            ),
            _bare(
              'filters',
              Icon(
                Icons.filter_list,
                color: filtered ? AppPalette.accent : null,
              ),
              () => _filters(context),
            ),
            if (!query.isEmpty)
              _bare(
                'reset',
                const Icon(Icons.close),
                () => onChanged(const SessionQuery()),
              ),
            Text(
              '$shown/${all.length}',
              key: const Key('sessions-count'),
              style: const TextStyle(
                color: AppPalette.mutedOnDark,
                fontSize: AppTextSize.caption,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        Row(
          children: [
            for (final st in SessionStatus.values)
              Expanded(
                child: _Chip(
                  status: st,
                  count: counts[st] ?? 0,
                  on: query.statuses.contains(st),
                  onTap: () => onChanged(
                    query.copyWith(
                      statuses: query.statuses.contains(st)
                          ? ({...query.statuses}..remove(st))
                          : {...query.statuses, st},
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

/// A plain icon button named by screen-reader text only (textgate).
Widget _bare(String id, Widget icon, VoidCallback onPressed) => Semantics(
  label: spoken[id],
  button: true,
  excludeSemantics: true,
  child: IconButton(key: Key('sessions-$id'), onPressed: onPressed, icon: icon),
);

class _Chip extends StatelessWidget {
  const new({
    required this.status,
    required this.count,
    required this.on,
    required this.onTap,
  });

  final SessionStatus status;
  final int count;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tone = statusTone(status);
    return Semantics(
      label: '${statusName(status)} ($count)',
      button: true,
      selected: on,
      excludeSemantics: true,
      child: InkWell(
        key: ValueKey('chip-${status.wire}'),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: AppSpacing.xs / 2),
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          decoration: BoxDecoration(
            color: on ? tone.withValues(alpha: 0.25) : null,
            borderRadius: BorderRadius.circular(AppRadius.lg),
            border: Border.all(color: on ? tone : AppPalette.lineDark),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(statusIcon(status), size: AppTextSize.body, color: tone),
              const SizedBox(width: AppSpacing.xs),
              Text(
                '$count',
                style: const TextStyle(fontSize: AppTextSize.caption),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
