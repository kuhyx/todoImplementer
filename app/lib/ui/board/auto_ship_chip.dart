/// The Start action's auto-ship option as a glyph chip (textgate: the name
/// is screen-reader text only). Split out of the card sheet for its size.
library;

import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';

/// The chip of [opt]; [selected] is the sheet's choice, [onChanged] sets it.
class AutoShipChip extends StatelessWidget {
  /// Creates the chip.
  const new(
    this.opt, {
    required this.selected,
    required this.onChanged,
    super.key,
  });

  /// The start action's `auto_ship` option.
  final CardAction opt;

  /// Whether auto-ship is ticked.
  final bool selected;

  /// Sets the tick.
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => Semantics(
    label: opt.spoken,
    excludeSemantics: true,
    child: Align(
      alignment: Alignment.centerLeft,
      child: FilterChip(
        key: const Key('auto-ship'),
        avatar: const Icon(Icons.rocket_launch_outlined),
        label: const SizedBox.shrink(),
        selected: selected,
        onSelected: opt.enabled ? onChanged : null,
      ),
    ),
  );
}
