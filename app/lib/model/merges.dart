/// The `snap/merges` node: exactly the `GET /api/merges` body
/// (`contracts/merge.schema.json`). Each suggestion carries its own
/// server-computed merge and dismiss actions.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/card_parts.dart';
import 'package:todo_implementer/model/json.dart';

/// One open note of a group.
@immutable
class MergeMember {
  /// Creates the member.
  const new(this.id, this.title, this.repo);

  /// Card id.
  final String id;

  /// Note title (kuhy's own content).
  final String title;

  /// `owner/name`.
  final String repo;
}

/// One suggested group of similar notes.
@immutable
class MergeSuggestion {
  /// Creates the suggestion.
  const new({
    required this.id,
    required this.title,
    required this.reason,
    required this.members,
    required this.actions,
  });

  /// Parses one suggestion. Merge closes notes, so it asks for a long
  /// press like ship; dismiss is one tap.
  factory fromJson(Json j) => MergeSuggestion(
    id: str(j, 'id'),
    title: str(j, 'title'),
    reason: str(j, 'reason'),
    members: [
      for (final m in objs(j, 'members'))
        MergeMember(str(m, 'id'), str(m, 'title'), str(m, 'repo')),
    ],
    actions: [
      for (final a in objs(j, 'actions'))
        CardAction.fromJson({...a, 'confirm': str(a, 'id') == 'merge'}),
    ],
  );

  /// Group fingerprint (the request's `group`).
  final String id;

  /// Title of the combined note.
  final String title;

  /// Why they belong together.
  final String reason;

  /// The notes it merges.
  final List<MergeMember> members;

  /// `[merge, dismiss]`.
  final List<CardAction> actions;
}

/// Parses the node.
List<MergeSuggestion> mergesOf(Json j) =>
    objs(j, 'suggestions').map(MergeSuggestion.fromJson).toList();

/// Relay kind of a merge action id.
String mergeKind(String actionId) => 'merge_$actionId';
