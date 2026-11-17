/// The card grid of one column with the web board's repo groups: every
/// sort but Least effort puts a repo head tile (repo name and count) before
/// that repo's cards. The grid pages sideways, never vertically (R7).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/ui/board/card_tile.dart';

/// One grid cell: a group head or a card.
typedef GridItem = ({CardGroup? head, TaskCard? card});

/// The cells for [groups], heads first in each labelled group.
List<GridItem> gridItems(List<CardGroup> groups) => [
  for (final g in groups) ...[
    if (!g.flat) (head: g, card: null),
    for (final c in g.cards) (head: null, card: c),
  ],
];

/// The column grid.
class BoardGrid extends StatelessWidget {
  /// Creates the grid.
  const new({required this.groups, required this.onOpen, super.key});

  /// The column's groups.
  final List<CardGroup> groups;

  /// Opens a card's sheet.
  final ValueChanged<TaskCard> onOpen;

  @override
  Widget build(BuildContext context) {
    final items = gridItems(groups);
    return FitGrid(
      itemCount: items.length,
      columns: MediaQuery.sizeOf(context).width < 600 ? 2 : 4,
      minSquare: 0.6,
      itemBuilder: (_, i) {
        final item = items[i];
        if (item.card case final card?) {
          return CardTile(
            key: ValueKey('card-${card.id}'),
            card: card,
            onOpen: () => onOpen(card),
          );
        }
        return _GroupHead(group: item.head!);
      },
    );
  }
}

class _GroupHead extends StatelessWidget {
  const new({required this.group});

  final CardGroup group;

  @override
  Widget build(BuildContext context) {
    final repo = group.repo;
    return Container(
      key: ValueKey('group-${repo ?? yours}'),
      decoration: BoxDecoration(
        border: Border.all(color: AppPalette.lineDark),
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      padding: const EdgeInsets.all(AppSpacing.sm),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(repo == null ? Icons.person_outline : Icons.folder_outlined),
          if (repo != null)
            Text(
              repo.split('/').last,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          Badge.count(
            count: group.cards.length,
            child: const SizedBox.square(dimension: AppSpacing.md),
          ),
        ],
      ),
    );
  }
}
