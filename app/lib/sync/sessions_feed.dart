/// The sessions page's link to the PC: the `snap/sessions` node, re-read
/// each time `rev/sessions` moves, and the four session request kinds
/// (DOCS-native-app-relay.md, "Publishing" and "Kinds").
library;

import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/layout.dart';

/// Every new `snap/sessions`, the current one first on listen.
typedef SessionsFeed = Stream<SessionList> Function();

/// The feed over RTDB: [client] reads the sealed node, [moves] is
/// `RevWatcher.changesOf('sessions')` (a broadcast stream: each listen of
/// the feed re-listens it).
SessionsFeed rtdbSessionsFeed({
  required RtdbClient client,
  required Stream<int> moves,
}) => () async* {
  Future<SessionList?> fetch() async {
    final node = await client.get(fullPath('snap/sessions'));
    return node is Json ? SessionList.fromJson(node) : null;
  }

  final first = await fetch();
  if (first != null) yield first;
  await for (final _ in moves) {
    final next = await fetch();
    if (next != null) yield next;
  }
};

/// A session request kind (`session_<verb>`).
enum SessionVerb {
  /// Open a terminal per session on the PC.
  resume,

  /// Set (`done`) or clear (null) the manual mark.
  mark,

  /// Move the transcripts to the trash.
  delete,

  /// Hand the stalled session to the board as a started task.
  handoff;

  /// The relay kind.
  String get kind => 'session_$name';
}

/// What the server answered, as the page draws it (web `Outcome`).
enum OutcomeKind {
  /// Done.
  ok,

  /// The guard refused it; nothing changed.
  refused,

  /// It could not be attempted (or the relay failed).
  failed,
}

/// One answer: its [kind] is drawn as a glyph, [summary] is screen-reader
/// text and what copy-errors collects (textgate).
typedef SessionOutcome = ({OutcomeKind kind, String summary});

/// Maps a relay outcome of a session kind (data = the HTTP `result` body).
SessionOutcome sessionOutcome(RelayOutcome out) => switch (out) {
  RelayOk(:final data) when flag(data, 'ok') => (
    kind: OutcomeKind.ok,
    summary: str(data, 'summary'),
  ),
  RelayOk(:final data) => (
    kind: flag(data, 'refused') ? OutcomeKind.refused : OutcomeKind.failed,
    summary: [
      str(data, 'summary'),
      str(data, 'stderr'),
    ].where((s) => s.isNotEmpty).join('\n'),
  ),
  RelayFailed(:final code, :final error) => (
    kind: OutcomeKind.failed,
    summary: '$code: $error',
  ),
};

/// The body of [verb] over [ids] (one id or many, per `one_or_many`).
/// [unmark] sends `mark: null`; the sealer prunes it and the worker reads
/// the missing `mark` as null (T2041).
Json sessionBody(SessionVerb verb, List<String> ids, {bool unmark = false}) {
  final target = ids.length == 1 ? {'id': ids.single} : {'ids': ids};
  return {
    'args': {
      ...target,
      if (verb == SessionVerb.mark) 'mark': unmark ? null : 'done',
    },
  };
}
