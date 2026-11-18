/// The bar over the grid while sessions are selected (web `bulkBar`):
/// count, mark, unmark, copy every resume command, resume (desktop, at most
/// five), move to the board (at most five) and hold-to-delete, then
/// select-all and clear.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/sessions_view.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';
import 'package:todo_implementer/ui/sessions/session_sheet.dart';

/// The bulk bar.
class BulkBar extends StatelessWidget {
  /// Creates the bar.
  const new({
    required this.ids,
    required this.commands,
    required this.busy,
    required this.moveBlock,
    required this.outcome,
    required this.onRun,
    required this.onSelectAll,
    required this.onClear,
    super.key,
  });

  /// Selected ids still listed, in list order.
  final List<String> ids;

  /// Their resume commands, one per line.
  final String commands;

  /// A request is in flight.
  final bool busy;

  /// The server's reason the first selected session cannot move to the
  /// board, or null when every one can.
  final String? moveBlock;

  /// The last bulk answer.
  final SessionOutcome? outcome;

  /// Runs a verb over [ids].
  final void Function(SessionVerb verb, {bool unmark}) onRun;

  /// Selects every listed session (or clears when all are).
  final VoidCallback onSelectAll;

  /// Clears the selection.
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final live = !busy && ids.isNotEmpty;
    final wide = MediaQuery.sizeOf(context).width >= desktopWidth;
    final tooMany = ids.length > maxResume;
    final last = outcome;
    return Material(
      key: const Key('bulk-bar'),
      color: AppPalette.inkRaised2,
      borderRadius: BorderRadius.circular(AppRadius.md),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            const SizedBox(width: AppSpacing.sm),
            Text(
              '${ids.length}',
              key: const Key('bulk-count'),
              style: const TextStyle(
                fontSize: AppTextSize.body,
                fontWeight: FontWeight.bold,
              ),
            ),
            sessionButton(
              'mark',
              Icons.task_alt,
              live ? () => onRun(SessionVerb.mark) : null,
            ),
            sessionButton(
              'unmark',
              Icons.replay,
              live ? () => onRun(SessionVerb.mark, unmark: true) : null,
            ),
            sessionButton(
              'copy-all',
              Icons.content_copy,
              ids.isEmpty
                  ? null
                  : () => Clipboard.setData(ClipboardData(text: commands)),
            ),
            if (wide)
              sessionButton(
                tooMany ? 'resume-max' : 'resume',
                Icons.terminal,
                live && !tooMany ? () => onRun(SessionVerb.resume) : null,
              ),
            handoffButton(
              id: tooMany ? 'handoff-max' : 'handoff',
              live: live,
              blocked: tooMany ? spoken['handoff-max'] : moveBlock,
              onRun: () => onRun(SessionVerb.handoff),
            ),
            deleteButton(
              live: live,
              onConfirm: () => onRun(SessionVerb.delete),
            ),
            sessionButton('select-all', Icons.select_all, onSelectAll),
            sessionButton('clear', Icons.close, onClear),
            if (busy)
              SizedBox.square(
                dimension: AppSpacing.lg,
                child: CircularProgressIndicator(
                  semanticsLabel: spoken['wait'],
                ),
              ),
            if (last != null)
              outcomeGlyph(last, key: const Key('bulk-outcome')),
            const SizedBox(width: AppSpacing.sm),
          ],
        ),
      ),
    );
  }
}
