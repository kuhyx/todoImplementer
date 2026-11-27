/// Start while a higher-priority card waits in Backlog (T2583): a modal
/// shows that card (its priority glyph and title, kuhy's own content) and
/// asks whether to start anyway. Glyph buttons with one-word tooltips
/// (textgate): back keeps the card waiting, start sends the Start.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/ui/board/priority_picker.dart';

/// True when kuhy starts anyway; false on back or a tap outside.
Future<bool> confirmStart(BuildContext context, Waits waits) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        key: const Key('start-confirm'),
        icon: const Icon(Icons.low_priority, semanticLabel: 'Start anyway?'),
        content: Row(
          key: ValueKey('start-confirm-waits-${waits.id}'),
          spacing: AppSpacing.sm,
          children: [
            Icon(priorityIcon(waits.priority), semanticLabel: waits.priority),
            Expanded(child: Text(waits.title)),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('start-confirm-back'),
            tooltip: 'back',
            icon: const Icon(Icons.close),
            onPressed: () => Navigator.of(context).pop(false),
          ),
          IconButton.filled(
            key: const Key('start-confirm-go'),
            tooltip: 'start',
            icon: const Icon(Icons.play_arrow),
            onPressed: () => Navigator.of(context).pop(true),
          ),
        ],
      ),
    ) ??
    false;
