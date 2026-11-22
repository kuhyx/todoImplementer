/// The buttons a card offers, exactly as the server lists them: enabled ones
/// run, disabled ones are drawn dimmed with a block badge and keep their
/// reason as screen-reader text (textgate). `confirm` actions fire on a long
/// press only (hold-to-confirm instead of a "sure?" dialog).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

/// Runs one action; the bar shows a spinner on it until the future ends.
typedef ActionTap = Future<void> Function(CardAction action);

/// Row of action buttons.
class ActionBar extends StatefulWidget {
  /// Creates the bar.
  const new({required this.actions, required this.onRun, super.key});

  /// What the server offers.
  final List<CardAction> actions;

  /// Runs an enabled action.
  final ActionTap onRun;

  @override
  State<ActionBar> createState() => _ActionBarState();
}

class _ActionBarState extends State<ActionBar> {
  String? _busy;

  Future<void> _run(CardAction a) async {
    setState(() => _busy = a.id);
    try {
      await widget.onRun(a);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: AppSpacing.sm,
    runSpacing: AppSpacing.sm,
    children: [
      for (final a in widget.actions)
        _ActionButton(
          action: a,
          busy: _busy == a.id,
          locked: _busy != null,
          onRun: () => _run(a),
        ),
    ],
  );
}

class _ActionButton extends StatelessWidget {
  const new({
    required this.action,
    required this.busy,
    required this.locked,
    required this.onRun,
  });

  final CardAction action;
  final bool busy;
  final bool locked;
  final VoidCallback onRun;

  @override
  Widget build(BuildContext context) {
    final a = action;
    final live = a.enabled && !locked;
    final icon = busy
        ? const SizedBox.square(
            dimension: AppSpacing.md + AppSpacing.xs,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        : Icon(actionIcon(a.id));
    final button = IconButton.filledTonal(
      key: ValueKey('action-${a.id}'),
      tooltip: actionTooltip(a.id),
      onPressed: live ? (a.confirm ? HapticFeedback.heavyImpact : onRun) : null,
      onLongPress: live && a.confirm ? onRun : null,
      icon: icon,
    );
    return Semantics(
      label: a.spoken,
      button: true,
      enabled: a.enabled,
      excludeSemantics: true,
      child: a.enabled
          ? button
          : Badge(
              backgroundColor: AppPalette.danger,
              label: const Icon(Icons.block, size: AppSpacing.sm + 2),
              child: button,
            ),
    );
  }
}
