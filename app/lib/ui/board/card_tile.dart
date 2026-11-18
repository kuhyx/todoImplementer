/// One card in the grid: the note's title (kuhy's own content), its repo,
/// and glyphs for status, what it needs, route and tier. Tapping opens the
/// card sheet with the actions.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

/// The grid cell of one card.
class CardTile extends StatelessWidget {
  /// Creates the tile.
  const new({required this.card, required this.onOpen, super.key});

  /// The card.
  final TaskCard card;

  /// Opens the card sheet.
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final color = statusColor(card.status);
    final needs = card.needs;
    final repo = card.repo;
    return Semantics(
      button: true,
      label: [card.title, card.current, ?needs?.text].join('. '),
      excludeSemantics: true,
      child: Material(
        color: AppPalette.inkRaised1,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          side: BorderSide(color: color, width: 2),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onOpen,
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    card.title,
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppPalette.textOnDark,
                      fontSize: AppTextSize.label,
                    ),
                  ),
                ),
                if (repo != null)
                  Text(
                    repo.split('/').last,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppPalette.mutedOnDark,
                      fontSize: AppTextSize.caption,
                    ),
                  ),
                const SizedBox(height: AppSpacing.xs),
                _Badges(card: card, color: color),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Badges extends StatelessWidget {
  const new({required this.card, required this.color});

  final TaskCard card;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final needs = card.needs;
    const size = AppTextSize.body;
    return Row(
      children: [
        Icon(Icons.circle, size: AppSpacing.sm, color: color),
        const SizedBox(width: AppSpacing.xs),
        if (needs != null) Icon(needsIcon(needs.category), size: size),
        if (card.route == 'credits')
          const Icon(
            Icons.savings_outlined,
            key: Key('route-credits'),
            size: size,
          ),
        if (card.cheap) const Icon(Icons.eco_outlined, size: size),
        if (card.free) const Icon(Icons.money_off, size: size),
        if (card.escalated) const Icon(Icons.trending_up, size: size),
        const Spacer(),
        if (card.costUsd > 0)
          Text(
            '\$${card.costUsd.toStringAsFixed(2)}',
            style: const TextStyle(
              color: AppPalette.mutedOnDark,
              fontSize: AppTextSize.caption,
            ),
          ),
      ],
    );
  }
}
