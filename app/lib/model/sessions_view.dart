/// Pure page logic of the sessions page, ported from
/// `web/src/sessions/model.ts`: the done/filter rules, fuzzy search, the
/// one-key sort, counts and the compact idle time.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/board_view.dart' show fuzzyMatch;
import 'package:todo_implementer/model/sessions.dart';

/// The mark filter: everything, or one [SessionMark].
typedef MarkFilter = SessionMark?;

/// The sortable keys (web `SORT_KEYS`); none keeps the server's order.
enum SessionSort {
  /// Urgency group.
  group,

  /// Idle time, youngest first.
  age,

  /// Project name.
  project,

  /// Title.
  title,

  /// Done mark rank.
  mark,
}

/// At most this many terminals open from one bulk resume.
const maxResume = 5;

/// What the toolbar and filter sheet set.
@immutable
class SessionQuery {
  /// Creates a query; the defaults are the empty query.
  const new({
    this.q = '',
    this.statuses = const {},
    this.project = '',
    this.older,
    this.mark,
    this.showDone = false,
    this.sort,
    this.desc = false,
  });

  /// Search words.
  final String q;

  /// Ticked status chips (none: all).
  final Set<SessionStatus> statuses;

  /// Only this project ('' for all).
  final String project;

  /// Only sessions idle for more than this many days.
  final int? older;

  /// Only this mark (null for all).
  final MarkFilter mark;

  /// Show done rows too.
  final bool showDone;

  /// The sort key; null keeps the server's grouped order.
  final SessionSort? sort;

  /// Sort descending.
  final bool desc;

  /// Whether this is the empty query (the reset button hides).
  bool get isEmpty =>
      q.isEmpty &&
      statuses.isEmpty &&
      project.isEmpty &&
      older == null &&
      mark == null &&
      !showDone &&
      sort == null;

  /// A copy; the `clear*` flags reset the nullable fields.
  SessionQuery copyWith({
    String? q,
    Set<SessionStatus>? statuses,
    String? project,
    int? older,
    bool clearOlder = false,
    SessionMark? mark,
    bool clearMark = false,
    bool? showDone,
  }) => SessionQuery(
    q: q ?? this.q,
    statuses: statuses ?? this.statuses,
    project: project ?? this.project,
    older: clearOlder ? null : older ?? this.older,
    mark: clearMark ? null : mark ?? this.mark,
    showDone: showDone ?? this.showDone,
    sort: sort,
    desc: desc,
  );

  /// The next sort after picking [key]: ascending, then descending, then off
  /// (web `cycleSort` without the shift-extend).
  SessionQuery cycled(SessionSort key) {
    final next = sort != key
        ? (key, false)
        : desc
        ? (null, false)
        : (key, true);
    return SessionQuery(
      q: q,
      statuses: statuses,
      project: project,
      older: older,
      mark: mark,
      showDone: showDone,
      sort: next.$1,
      desc: next.$2,
    );
  }
}

const Set<SessionStatus> _doneStatuses = {
  SessionStatus.done,
  SessionStatus.continuing,
};

bool _doneAllowed(Session s, SessionQuery q) =>
    !s.done ||
    q.showDone ||
    q.mark == SessionMark.manual ||
    q.mark == SessionMark.tag ||
    (_doneStatuses.contains(s.status) && q.statuses.contains(s.status));

bool _shown(Session s, SessionQuery q, DateTime now) {
  final idle = s.lastTs == null ? null : now.difference(s.lastTs!);
  return _doneAllowed(s, q) &&
      (q.statuses.isEmpty || q.statuses.contains(s.status)) &&
      (q.project.isEmpty || s.project == q.project) &&
      (q.mark == null || s.mark == q.mark) &&
      (q.older == null || (idle != null && idle > Duration(days: q.older!)));
}

String _searchText(Session s) => [
  s.project,
  s.title,
  s.cwd,
  s.id,
  s.status.wire.replaceAll('_', ' '),
].join(' ');

int _compare(Session a, Session b, SessionSort key) => switch (key) {
  SessionSort.group => a.group.compareTo(b.group),
  // Youngest first on ascending; an unknown time sorts last.
  SessionSort.age => (b.lastTs?.millisecondsSinceEpoch ?? -1).compareTo(
    a.lastTs?.millisecondsSinceEpoch ?? -1,
  ),
  SessionSort.project => a.project.compareTo(b.project),
  SessionSort.title => a.shownTitle.compareTo(b.shownTitle),
  SessionSort.mark => a.mark.rank.compareTo(b.mark.rank),
};

/// The rows to show: filters, then search, then the sort (stable).
List<Session> visibleSessions(List<Session> all, SessionQuery q, DateTime now) {
  final words = q.q.split(RegExp(r'\s+')).where((w) => w.isNotEmpty);
  final kept = all
      .where((s) => _shown(s, q, now))
      .where((s) => words.every((w) => fuzzyMatch(w, _searchText(s))))
      .toList();
  final key = q.sort;
  if (key == null) return kept;
  final order = {for (final (i, s) in kept.indexed) s.id: i};
  return kept..sort((a, b) {
    final c = _compare(a, b, key);
    if (c != 0) return q.desc ? -c : c;
    return order[a.id]!.compareTo(order[b.id]!);
  });
}

/// Sessions per status, over the whole list.
Map<SessionStatus, int> statusCounts(List<Session> all) => {
  for (final st in SessionStatus.values)
    st: all.where((s) => s.status == st).length,
};

/// Project names, sorted, keeping [keep] even if no session has it now.
List<String> projectsOf(List<Session> all, String keep) =>
    ({...all.map((s) => s.project), if (keep.isNotEmpty) keep}.toList()
      ..sort());

/// Compact idle time: 5m, 3h, 12d; '' when the transcript had no time.
String ageLabel(Session s, DateTime now) {
  final ts = s.lastTs;
  if (ts == null) return '';
  final minutes = now.difference(ts).inMinutes.clamp(0, 1 << 31);
  if (minutes < 60) return '${minutes}m';
  return minutes < 1440 ? '${minutes ~/ 60}h' : '${minutes ~/ 1440}d';
}
