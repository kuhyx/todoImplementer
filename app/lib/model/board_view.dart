/// Filtering, sorting and grouping of the board: the Dart port of
/// `web/src/lib/board-model.ts`, so both UIs order cards the same way.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/backlog_order.dart';
import 'package:todo_implementer/model/board.dart';

/// The repo filter value for cards without a repo.
const yours = '__yours__';

/// Sort orders, as on the web board.
enum BoardSort {
  /// Least effort: open questions first, then fewest clicks.
  effort,

  /// Priority, urgent first.
  priority,

  /// Most recently updated first.
  updated,

  /// Highest cost first.
  cost,

  /// Alphabetical.
  title,
}

/// What the toolbar selects.
@immutable
class ViewState {
  /// Creates a state.
  const new({
    this.query = '',
    this.repo = '',
    this.sort = BoardSort.effort,
    this.column,
  });

  /// Search words.
  final String query;

  /// Repo filter: '' all, [yours], or `owner/name`.
  final String repo;

  /// Sort order.
  final BoardSort sort;

  /// Chosen column; null picks one (see [activeColumn]).
  final String? column;

  /// A copy with the given fields replaced.
  ViewState copyWith({
    String? query,
    String? repo,
    BoardSort? sort,
    String? column,
  }) => ViewState(
    query: query ?? this.query,
    repo: repo ?? this.repo,
    sort: sort ?? this.sort,
    column: column ?? this.column,
  );
}

const _priorityRank = {
  'urgent': 0,
  'high': 1,
  'medium': 2,
  'normal': 2,
  'low': 3,
};

/// True when every character of [needle] appears in [hay] in order
/// (case-insensitive), the web board's fuzzy match.
bool fuzzyMatch(String needle, String hay) {
  final n = needle.toLowerCase();
  final h = hay.toLowerCase();
  var at = 0;
  for (final ch in n.split('')) {
    at = h.indexOf(ch, at);
    if (at < 0) return false;
    at++;
  }
  return true;
}

/// The text a search runs over.
String searchText(TaskCard c) => [
  c.title,
  c.repo ?? 'yours',
  c.id,
  c.current,
  c.needs?.text ?? '',
].join(' ');

bool _matches(TaskCard c, ViewState s) {
  final repoOk = switch (s.repo) {
    '' => true,
    yours => c.repo == null,
    final r => c.repo == r,
  };
  if (!repoOk) return false;
  final text = searchText(c);
  return s.query
      .split(RegExp(r'\s+'))
      .where((w) => w.isNotEmpty)
      .every((w) => fuzzyMatch(w, text));
}

int _byPriority(TaskCard a, TaskCard b) =>
    (_priorityRank[a.priority] ?? 4) - (_priorityRank[b.priority] ?? 4);

int _byUpdated(TaskCard a, TaskCard b) => (b.updated ?? 0) - (a.updated ?? 0);

int _primary(BoardSort sort, TaskCard a, TaskCard b) => switch (sort) {
  BoardSort.cost => b.costUsd.compareTo(a.costUsd),
  BoardSort.effort =>
    _effortKey(a, b) != 0 ? _effortKey(a, b) : _byPriority(a, b),
  BoardSort.priority => _byPriority(a, b),
  BoardSort.title => a.title.compareTo(b.title),
  BoardSort.updated => _byUpdated(a, b),
};

int _notQuestions(TaskCard c) => c.needs?.category == 'questions' ? 0 : 1;

int _effortKey(TaskCard a, TaskCard b) {
  final q = _notQuestions(a) - _notQuestions(b);
  return q != 0 ? q : (a.needs?.effort ?? 0) - (b.needs?.effort ?? 0);
}

/// [cards] in [sort] order, ties broken like the web board.
List<TaskCard> sortCards(List<TaskCard> cards, BoardSort sort) {
  int cmp(TaskCard a, TaskCard b) {
    for (final r in [
      _primary(sort, a, b),
      _byUpdated(a, b),
      a.title.compareTo(b.title),
    ]) {
      if (r != 0) return r;
    }
    return a.id.compareTo(b.id);
  }

  return [...cards]..sort(cmp);
}

/// One column after filters: its cards in order, and how many show.
@immutable
class ColumnView {
  /// Creates the view.
  const new(this.column, this.cards);

  /// The column header.
  final BoardColumn column;

  /// Visible cards, sorted.
  final List<TaskCard> cards;
}

/// Every column with its filtered, sorted cards.
List<ColumnView> buildView(Board board, ViewState s) {
  final visible = board.tasks.where((c) => _matches(c, s)).toList();
  return [
    for (final col in board.columns)
      ColumnView(col, switch (sortCards(
        visible.where((c) => c.column == col.id).toList(),
        s.sort,
      )) {
        final sorted when col.id == 'backlog' => backlogOrder(sorted),
        final sorted => sorted,
      }),
  ];
}

/// The column to show: the chosen one, else Needs you when it has cards,
/// else the first non-empty one, else backlog.
String activeColumn(List<ColumnView> view, ViewState s) {
  if (s.column != null) return s.column!;
  for (final v in view) {
    if (v.column.id == 'needs_you' && v.cards.isNotEmpty) return v.column.id;
  }
  for (final v in view) {
    if (v.cards.isNotEmpty) return v.column.id;
  }
  return 'backlog';
}

/// Repo filter options: (value, card count), all first, then Yours.
List<(String, int)> repoOptions(Board board) {
  int count(String? r) => board.tasks.where((c) => c.repo == r).length;
  final mine = count(null);
  return [
    ('', board.tasks.length),
    if (mine > 0) (yours, mine),
    for (final r in board.repos) (r, count(r)),
  ];
}

/// One repo group of a column; [repo] null is Yours, [flat] is the
/// unlabelled Least-effort list across repos.
@immutable
class CardGroup {
  /// Creates the group.
  const new(this.repo, this.cards, {this.flat = false});

  /// `owner/name`, or null for notes without a repo.
  final String? repo;

  /// Its cards, sorted.
  final List<TaskCard> cards;

  /// No heading: the Least-effort order mixes repos.
  final bool flat;
}

/// The web board's grouping: Least effort is one flat list; every other
/// sort groups by repo, repos alphabetical, Yours last.
List<CardGroup> groupCards(List<TaskCard> cards, BoardSort sort) {
  if (cards.isEmpty) return const [];
  if (sort == BoardSort.effort) {
    return [CardGroup(null, sortCards(cards, sort), flat: true)];
  }
  final byRepo = <String?, List<TaskCard>>{};
  for (final c in cards) {
    (byRepo[c.repo] ??= []).add(c);
  }
  final keys = byRepo.keys.toList()
    ..sort((a, b) {
      if (a == null) return 1;
      if (b == null) return -1;
      return a.compareTo(b);
    });
  return [for (final k in keys) CardGroup(k, sortCards(byRepo[k]!, sort))];
}
