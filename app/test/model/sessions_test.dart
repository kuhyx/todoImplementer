import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/model/sessions_view.dart';

import '../support/session_fakes.dart';

List<Session> _parse(List<Map<String, dynamic>> js) =>
    SessionList.fromJson(listJson(js)).sessions;

void main() {
  test('parses every field; unknown tags and marks fall back', () {
    final s = Session.fromJson(
      sessionJson(id: 'abcd1234-0000-4000-8000-000000000001', mark: 'manual'),
    );
    expect(s.status, SessionStatus.needsAction);
    expect(s.mark, SessionMark.manual);
    expect(s.cwd, '/home/u/src/demo');
    expect(s.lastTs, isNotNull);
    expect(s.resumeCommand, contains('--resume'));
    final odd = Session.fromJson({'status': 'weird', 'mark': 'x'});
    expect(odd.status, SessionStatus.untagged);
    expect(odd.mark, SessionMark.open);
    expect(odd.group, 2);
    expect(odd.lastTs, isNull);
    expect(
      Session.fromJson({'id': 'abcd1234-ffff', 'title': ''}).shownTitle,
      'abcd1234',
    );
    expect(SessionList.fromJson(const {}).sessions, isEmpty);
    expect(SessionStatus.continuing.wire, 'continuing');
    expect(SessionStatus.of('needs_action'), SessionStatus.needsAction);
    expect([for (final m in SessionMark.values) m.rank], [0, 1, 2]);
  });

  test('done rows hide unless asked for, by switch, mark or own status', () {
    final all = _parse([
      sessionJson(title: 'open'),
      sessionJson(title: 'tagged', status: 'done', done: true, mark: 'tag'),
      sessionJson(title: 'cont', status: 'continuing', done: true, mark: 'tag'),
      sessionJson(title: 'hand', status: 'running', done: true, mark: 'manual'),
    ]);
    List<String> titles(SessionQuery q) => [
      for (final s in visibleSessions(all, q, sessionsNow)) s.title,
    ];
    expect(titles(const SessionQuery()), ['open']);
    expect(titles(const SessionQuery(showDone: true)), hasLength(4));
    expect(titles(const SessionQuery(mark: SessionMark.manual)), ['hand']);
    expect(titles(const SessionQuery(mark: SessionMark.tag)), [
      'tagged',
      'cont',
    ]);
    expect(titles(const SessionQuery(mark: SessionMark.open)), ['open']);
    expect(titles(const SessionQuery(statuses: {SessionStatus.continuing})), [
      'cont',
    ]);
    expect(titles(const SessionQuery(statuses: {SessionStatus.running})), []);
  });

  test('project, idle days and fuzzy search narrow the rows', () {
    final all = _parse([
      sessionJson(title: 'alpha', project: 'one'),
      sessionJson(title: 'beta', project: 'two', idle: const Duration(days: 3)),
      sessionJson(title: 'gamma', project: 'two', idle: null),
    ]);
    List<String> titles(SessionQuery q) => [
      for (final s in visibleSessions(all, q, sessionsNow)) s.title,
    ];
    expect(titles(const SessionQuery(project: 'two')), ['beta', 'gamma']);
    expect(titles(const SessionQuery(older: 2)), ['beta']);
    expect(titles(const SessionQuery(q: 'bt  two')), ['beta']);
    expect(titles(const SessionQuery(q: 'needs action')), hasLength(3));
    expect(titles(const SessionQuery(q: 'zzz')), isEmpty);
  });

  test('sort cycles ascending, descending, off; ties keep server order', () {
    final all = _parse([
      sessionJson(title: 'b', project: 'p2', group: 1, mark: 'open'),
      sessionJson(title: 'a', project: 'p1', idle: null, group: 0),
      sessionJson(
        title: 'c',
        project: 'p1',
        idle: const Duration(days: 1),
        group: 1,
      ),
    ]);
    List<String> titles(SessionQuery q) => [
      for (final s in visibleSessions(all, q, sessionsNow)) s.title,
    ];
    var q = const SessionQuery().cycled(SessionSort.title);
    expect((q.sort, q.desc), (SessionSort.title, false));
    expect(titles(q), ['a', 'b', 'c']);
    q = q.cycled(SessionSort.title);
    expect(titles(q), ['c', 'b', 'a']);
    q = q.cycled(SessionSort.title);
    expect(q.sort, isNull);
    expect(titles(q), ['b', 'a', 'c']);
    expect(titles(q.cycled(SessionSort.age)), ['b', 'c', 'a']);
    expect(titles(q.cycled(SessionSort.project)), ['a', 'c', 'b']);
    expect(titles(q.cycled(SessionSort.group)), ['a', 'b', 'c']);
    expect(titles(q.cycled(SessionSort.mark)), ['b', 'a', 'c']);
  });

  test('query copies, reset flags and emptiness', () {
    const q = SessionQuery();
    expect(q.isEmpty, isTrue);
    final full = q.copyWith(
      q: 'x',
      statuses: {SessionStatus.done},
      project: 'p',
      older: 3,
      mark: SessionMark.tag,
      showDone: true,
    );
    expect(full.isEmpty, isFalse);
    expect(full.copyWith().older, 3);
    final cleared = full.copyWith(clearOlder: true, clearMark: true);
    expect((cleared.older, cleared.mark, cleared.q), (null, null, 'x'));
    expect(q.cycled(SessionSort.age).isEmpty, isFalse);
  });

  test('counts, projects and compact ages', () {
    final all = _parse([
      sessionJson(project: 'b'),
      sessionJson(
        project: 'a',
        status: 'running',
        idle: const Duration(hours: 3),
      ),
      sessionJson(project: 'a', idle: const Duration(days: 12)),
      sessionJson(project: 'a', idle: null),
    ]);
    final counts = statusCounts(all);
    expect(counts[SessionStatus.needsAction], 3);
    expect(counts[SessionStatus.running], 1);
    expect(counts[SessionStatus.done], 0);
    expect(projectsOf(all, ''), ['a', 'b']);
    expect(projectsOf(all, 'gone'), ['a', 'b', 'gone']);
    expect(
      [for (final s in all) ageLabel(s, sessionsNow)],
      ['5m', '3h', '12d', ''],
    );
  });
}
