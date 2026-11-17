/// A session's sheet: its details (cwd, id, last prompt, end of the last
/// reply) and its actions. Resume opens a terminal on the PC, so only a
/// wide (desktop) window offers it, as the web page hides it on a phone.
/// Delete fires on a long press only (hold-to-confirm, as the board's
/// confirm actions).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';

/// Runs a verb over ids and returns the answer (the page sends it).
typedef SessionPerform = Future<SessionOutcome> Function(
  SessionVerb verb,
  List<String> ids, {
  bool unmark,
});

/// Windows at least this wide are a desktop: resume is offered.
const desktopWidth = 600.0;

/// An icon button whose name is screen-reader text only (textgate).
Widget sessionButton(
  String id,
  IconData icon,
  VoidCallback? onPressed, {
  VoidCallback? onLongPress,
  Color? color,
}) => Semantics(
  label: spoken[id],
  button: true,
  excludeSemantics: true,
  child: IconButton.filledTonal(
    key: Key('session-$id'),
    color: color,
    onPressed: onPressed,
    onLongPress: onLongPress,
    icon: Icon(icon),
  ),
);

/// The hold-to-confirm delete button.
Widget deleteButton({required bool live, required VoidCallback onConfirm}) =>
    sessionButton(
      'delete',
      Icons.delete_outline,
      live ? HapticFeedback.heavyImpact : null,
      onLongPress: live ? onConfirm : null,
      color: AppPalette.danger,
    );

/// The bottom sheet of one session.
class SessionSheet extends StatefulWidget {
  /// Creates the sheet.
  const new({required this.session, required this.perform, super.key});

  /// The session.
  final Session session;

  /// Sends a request.
  final SessionPerform perform;

  @override
  State<SessionSheet> createState() => _SessionSheetState();
}

class _SessionSheetState extends State<SessionSheet> {
  bool _busy = false;
  bool _copied = false;
  SessionOutcome? _outcome;

  Future<void> _run(SessionVerb verb, {bool unmark = false}) async {
    setState(() {
      _busy = true;
      _outcome = null;
    });
    final out = await widget.perform(verb, [widget.session.id], unmark: unmark);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _outcome = out;
    });
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.session.resumeCommand));
    setState(() => _copied = true);
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.session;
    final wide = MediaQuery.sizeOf(context).width >= desktopWidth;
    final live = !_busy;
    final outcome = _outcome;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  statusIcon(s.status),
                  color: statusTone(s.status),
                  semanticLabel: statusName(s.status),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    s.shownTitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: AppTextSize.subtitle),
                  ),
                ),
              ],
            ),
            _line(Icons.folder_outlined, s.cwd, mono: true),
            _line(Icons.link, s.id, mono: true),
            if (s.lastUser.isNotEmpty) _line(Icons.person_outline, s.lastUser),
            if (s.lastAssistant.isNotEmpty)
              _line(Icons.notes, s.lastAssistant, lines: 6),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (wide)
                  sessionButton(
                    'resume',
                    Icons.terminal,
                    live ? () => _run(SessionVerb.resume) : null,
                  ),
                sessionButton(
                  'copy',
                  _copied ? Icons.check : Icons.content_copy,
                  _copy,
                ),
                if (s.mark == SessionMark.manual)
                  sessionButton(
                    'unmark',
                    Icons.replay,
                    live ? () => _run(SessionVerb.mark, unmark: true) : null,
                  )
                else if (!s.done)
                  sessionButton(
                    'mark',
                    Icons.task_alt,
                    live ? () => _run(SessionVerb.mark) : null,
                  ),
                deleteButton(
                  live: live,
                  onConfirm: () => _run(SessionVerb.delete),
                ),
                if (_busy)
                  SizedBox.square(
                    dimension: AppSpacing.lg,
                    child: CircularProgressIndicator(
                      semanticsLabel: spoken['wait'],
                    ),
                  ),
                if (outcome != null)
                  outcomeGlyph(outcome, key: const Key('session-outcome')),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _line(
    IconData icon,
    String text, {
    bool mono = false,
    int lines = 3,
  }) => Padding(
    padding: const EdgeInsets.only(top: AppSpacing.sm),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: AppTextSize.body, color: AppPalette.mutedOnDark),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: SelectableText(
            text,
            maxLines: lines,
            style: TextStyle(
              fontSize: AppTextSize.caption,
              fontFamily: mono ? 'monospace' : null,
            ),
          ),
        ),
      ],
    ),
  );
}
