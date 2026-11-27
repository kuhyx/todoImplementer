/// Backlog order (T2583): one list, high priority first, kuhy's cards before
/// automatic ones at equal priority; the picked sort only breaks ties. The
/// Dart port of `backlogGroups` in `web/src/lib/board-model.ts`.
library;

import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';

const _priorityRank = {
  'urgent': 0,
  'high': 1,
  'medium': 2,
  'normal': 2,
  'low': 3,
};
const _laneRank = {'kuhy': 0, 'board': 1, 'app': 2};

int _rank(TaskCard c) => _priorityRank[c.priority] ?? 4;

/// [sorted] (already in the picked sort) reordered for the Backlog column.
List<TaskCard> backlogOrder(List<TaskCard> sorted) {
  final at = {for (final (i, c) in sorted.indexed) c.id: i};
  int cmp(TaskCard a, TaskCard b) {
    for (final r in [
      _rank(a) - _rank(b),
      (_laneRank[a.lane] ?? 0) - (_laneRank[b.lane] ?? 0),
      at[a.id]! - at[b.id]!,
    ]) {
      if (r != 0) return r;
    }
    return 0;
  }

  return [...sorted]..sort(cmp);
}

/// The groups a column draws: Backlog (already in [backlogOrder], see
/// `buildView`) is one flat list, the rest group as the picked sort says.
List<CardGroup> columnGroups(
  String column,
  List<TaskCard> cards,
  BoardSort sort,
) => column == 'backlog'
    ? [if (cards.isNotEmpty) CardGroup(null, cards, flat: true)]
    : groupCards(cards, sort);
