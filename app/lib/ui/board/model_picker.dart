/// The model picker (action `model`): one chip per server choice, the
/// model the card runs on selected. A model shows its short name (kuhy's own
/// pick, like a title); the default model carries the default glyph inline
/// (T2470). A tap pins it and the card's stage runs again
/// on it (modelswitch on the server). A disabled picker keeps its reason as
/// screen-reader text (textgate).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';

/// Sends the picked model id.
typedef ModelPick = Future<void> Function(String id);

/// Row of model chips.
class ModelPicker extends StatelessWidget {
  /// Creates the picker.
  const new({required this.action, required this.onPick, super.key});

  /// The server's `model` action: its choices, pin (`value`) and gate.
  final CardAction action;

  /// Sends a pick.
  final ModelPick onPick;

  @override
  Widget build(BuildContext context) {
    final current = action.value;
    return Semantics(
      label: action.spoken,
      container: true,
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: [
          for (final c in action.choices)
            ChoiceChip(
              key: ValueKey('model-${c.id}'),
              label: c.isDefault
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      spacing: AppSpacing.xs,
                      children: [
                        Text(c.label),
                        const Icon(
                          Icons.auto_mode,
                          size: 16,
                          semanticLabel: 'default',
                        ),
                      ],
                    )
                  : Text(c.label),
              selected: c.id == current,
              onSelected: action.enabled && c.id != current
                  ? (_) => onPick(c.id)
                  : null,
            ),
        ],
      ),
    );
  }
}
