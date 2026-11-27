/// The priority picker (action `priority`, T2583): one glyph chip per level,
/// the card's priority selected. Names live in tooltips and semantics only
/// (textgate). A tap sends {priority}; the PC sets it on every note behind
/// the card. A disabled picker keeps its reason as screen-reader text.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';

/// Glyph of a priority level.
IconData priorityIcon(String level) => switch (level) {
  'high' => Icons.keyboard_double_arrow_up,
  'low' => Icons.keyboard_double_arrow_down,
  _ => Icons.drag_handle,
};

/// Sends the picked level.
typedef PriorityPick = Future<void> Function(String level);

/// The picker of a card's `priority` offer, or nothing when it has none.
Widget? priorityRow(CardAction? offer, PriorityPick onPick) =>
    offer == null ? null : PriorityPicker(action: offer, onPick: onPick);

/// Row of priority chips.
class PriorityPicker extends StatelessWidget {
  /// Creates the picker.
  const new({required this.action, required this.onPick, super.key});

  /// The server's `priority` action: its levels, value and gate.
  final CardAction action;

  /// Sends a pick.
  final PriorityPick onPick;

  @override
  Widget build(BuildContext context) => Semantics(
    label: action.spoken,
    container: true,
    child: Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: [
        for (final c in action.choices)
          Tooltip(
            message: c.label,
            child: ChoiceChip(
              key: ValueKey('priority-${c.id}'),
              avatar: Icon(priorityIcon(c.id), semanticLabel: c.label),
              label: const SizedBox.shrink(),
              labelPadding: EdgeInsets.zero,
              showCheckmark: false,
              selected: c.id == action.value,
              onSelected: action.enabled && c.id != action.value
                  ? (_) => onPick(c.id)
                  : null,
            ),
          ),
      ],
    ),
  );
}
