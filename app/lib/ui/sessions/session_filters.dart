/// The filters that do not fit the toolbar row: project, idle days, mark
/// and show-done (web toolbar's select, number field, mark choices and eye
/// toggle). Every change applies at once; the sheet keeps its own copy so
/// it redraws while open.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/model/sessions_view.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';

/// The filter sheet.
class SessionFilters extends StatefulWidget {
  /// Creates the sheet.
  const new({
    required this.all,
    required this.query,
    required this.onChanged,
    super.key,
  });

  /// Every session (for the project list).
  final List<Session> all;

  /// The query when the sheet opened.
  final SessionQuery query;

  /// A new query.
  final ValueChanged<SessionQuery> onChanged;

  @override
  State<SessionFilters> createState() => _SessionFiltersState();
}

class _SessionFiltersState extends State<SessionFilters> {
  late SessionQuery _q = widget.query;

  void _set(SessionQuery next) {
    setState(() => _q = next);
    widget.onChanged(next);
  }

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.md,
        right: AppSpacing.md,
        bottom: MediaQuery.viewInsetsOf(context).bottom + AppSpacing.md,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _row(
            Icons.folder_outlined,
            'project',
            DropdownButton<String>(
              key: const Key('filter-project'),
              isExpanded: true,
              value: _q.project,
              items: [
                const DropdownMenuItem(
                  value: '',
                  child: Icon(Icons.select_all),
                ),
                for (final p in projectsOf(widget.all, _q.project))
                  DropdownMenuItem(value: p, child: Text(p)),
              ],
              onChanged: (p) => _set(_q.copyWith(project: p)),
            ),
          ),
          _row(
            Icons.hourglass_empty,
            'idle',
            TextFormField(
              key: const Key('filter-idle'),
              initialValue: _q.older?.toString() ?? '',
              keyboardType: TextInputType.number,
              onChanged: (v) {
                final days = int.tryParse(v);
                _set(
                  days != null && days > 0
                      ? _q.copyWith(older: days)
                      : _q.copyWith(clearOlder: true),
                );
              },
            ),
          ),
          _row(
            Icons.done_all,
            'marks',
            SegmentedButton<SessionMark?>(
              key: const Key('filter-mark'),
              showSelectedIcon: false,
              segments: [
                for (final m in <SessionMark?>[null, ...SessionMark.values])
                  ButtonSegment(
                    value: m,
                    icon: Icon(markIcon(m), semanticLabel: markName(m)),
                  ),
              ],
              selected: {_q.mark},
              onSelectionChanged: (s) => _set(
                s.single == null
                    ? _q.copyWith(clearMark: true)
                    : _q.copyWith(mark: s.single),
              ),
            ),
          ),
          _row(
            Icons.visibility_outlined,
            'show-done',
            Align(
              alignment: Alignment.centerLeft,
              child: Switch(
                key: const Key('filter-done'),
                value: _q.showDone,
                onChanged: (on) => _set(_q.copyWith(showDone: on)),
              ),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _row(IconData icon, String id, Widget control) => Semantics(
    label: spoken[id],
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(icon, color: AppPalette.mutedOnDark),
          const SizedBox(width: AppSpacing.md),
          Expanded(child: control),
        ],
      ),
    ),
  );
}
