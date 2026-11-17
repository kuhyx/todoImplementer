/// One session in the grid: its title and project (kuhy's own content),
/// the status and mark glyphs and the idle time. Tap opens the sheet,
/// long press selects it for the bulk bar.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';

/// The grid cell of one session.
class SessionTile extends StatelessWidget {
  /// Creates the tile.
  const new({
    required this.session,
    required this.age,
    required this.selected,
    required this.onOpen,
    required this.onSelect,
    super.key,
  });

  /// The session.
  final Session session;

  /// Compact idle time ('' when unknown).
  final String age;

  /// Selected for a bulk action.
  final bool selected;

  /// Opens the session sheet.
  final VoidCallback onOpen;

  /// Toggles the selection.
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    final tone = statusTone(session.status);
    final muted = session.done;
    return Semantics(
      button: true,
      selected: selected,
      label: [
        session.shownTitle,
        session.project,
        statusName(session.status),
        markName(session.mark),
      ].join('. '),
      excludeSemantics: true,
      child: Material(
        color: selected ? AppPalette.inkRaised2 : AppPalette.inkRaised1,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          side: BorderSide(
            color: selected ? AppPalette.accent : tone,
            width: selected ? 3 : 2,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onOpen,
          onLongPress: onSelect,
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    session.shownTitle,
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: muted
                          ? AppPalette.mutedOnDark
                          : AppPalette.textOnDark,
                      fontSize: AppTextSize.label,
                    ),
                  ),
                ),
                Text(
                  session.project,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppPalette.mutedOnDark,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Row(
                  children: [
                    Icon(
                      statusIcon(session.status),
                      size: AppTextSize.body,
                      color: tone,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    Icon(
                      markIcon(session.mark),
                      size: AppTextSize.body,
                      color: AppPalette.mutedOnDark,
                    ),
                    const Spacer(),
                    if (selected)
                      const Icon(
                        Icons.check_box,
                        key: Key('tile-selected'),
                        size: AppTextSize.body,
                        color: AppPalette.accent,
                      ),
                    Text(
                      age,
                      style: const TextStyle(
                        color: AppPalette.mutedOnDark,
                        fontSize: AppTextSize.caption,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
