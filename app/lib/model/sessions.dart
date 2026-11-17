/// The `snap/sessions` node: exactly the `GET /api/sessions` body
/// (`contracts/sessions.schema.json`). Status, done, group and the resume
/// command come from the server; the app only filters, sorts and draws.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/json.dart';

/// A session's status tag (`$defs/status`), in the server's group order.
enum SessionStatus {
  /// The last reply ended on `A:`.
  needsAction,

  /// The last reply ended on `Q:`.
  question,

  /// The last reply carried no tag.
  untagged,

  /// The last reply ended on `R:`.
  running,

  /// The last reply ended on `D:`.
  done,

  /// The last reply ended on `C:` (continued in a new session).
  continuing;

  /// The wire spelling.
  String get wire => this == needsAction ? 'needs_action' : name;

  /// Parses [s]; an unknown tag reads as [untagged].
  static SessionStatus of(String s) =>
      values.firstWhere((v) => v.wire == s, orElse: () => untagged);
}

/// How a row stands (`mark`): done by hand, by its own tag, or open.
enum SessionMark {
  /// Marked done by hand (the only mark the app can undo).
  manual,

  /// Done by its own status tag.
  tag,

  /// Not done.
  open;

  /// Parses [s]; an unknown mark reads as [open].
  static SessionMark of(String s) =>
      values.firstWhere((v) => v.name == s, orElse: () => open);

  /// Sort rank: hand marks first, then tags, then open (web `markRank`).
  int get rank => switch (this) {
    manual => 0,
    tag => 1,
    open => 2,
  };
}

/// One session (`$defs/session`).
@immutable
class Session {
  /// Creates a session.
  const new({
    required this.id,
    required this.cwd,
    required this.project,
    required this.title,
    required this.status,
    required this.done,
    required this.group,
    required this.mark,
    required this.resumeCommand,
    this.lastTs,
    this.lastUser = '',
    this.lastAssistant = '',
  });

  /// Parses a session.
  factory fromJson(Json j) => Session(
    id: str(j, 'id'),
    cwd: str(j, 'cwd'),
    project: str(j, 'project'),
    title: str(j, 'title'),
    status: SessionStatus.of(str(j, 'status')),
    done: flag(j, 'done'),
    group: intOr(j, 'group') ?? 2,
    mark: SessionMark.of(str(j, 'mark', 'open')),
    resumeCommand: str(j, 'resume_command'),
    lastTs: DateTime.tryParse(str(j, 'last_ts')),
    lastUser: str(j, 'last_user'),
    lastAssistant: str(j, 'last_assistant'),
  );

  /// Canonical session uuid.
  final String id;

  /// Working directory of the transcript.
  final String cwd;

  /// Basename of [cwd] (`~` for home).
  final String project;

  /// The session's title (kuhy's content).
  final String title;

  /// Status tag of the last reply.
  final SessionStatus status;

  /// Done by tag or by hand.
  final bool done;

  /// The server's urgency group, 0 (needs action) to 4 (done).
  final int group;

  /// How the row stands.
  final SessionMark mark;

  /// `cd '<cwd>' && claude --resume <id>`.
  final String resumeCommand;

  /// Time of the newest prompt or reply, if the transcript had one.
  final DateTime? lastTs;

  /// The last prompt (cut to 400 characters by the server).
  final String lastUser;

  /// The end of the last reply (its last 600 characters).
  final String lastAssistant;

  /// The title, or the id's first block for an untitled session.
  String get shownTitle => title.isEmpty ? id.split('-').first : title;
}

/// The whole node (`$defs/list`).
@immutable
class SessionList {
  /// Creates the list.
  const new({required this.sessions, this.scanned = 0});

  /// Parses the node; RTDB drops an empty list, so a missing one is empty.
  factory fromJson(Json j) => SessionList(
    sessions: objs(j, 'sessions').map(Session.fromJson).toList(),
    scanned: intOr(j, 'scanned') ?? 0,
  );

  /// Sessions in the server's order (urgency group, newest first).
  final List<Session> sessions;

  /// Transcript files the server examined.
  final int scanned;
}
