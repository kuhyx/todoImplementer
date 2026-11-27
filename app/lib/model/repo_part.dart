/// One part of a repo card (`repotask.schema.json#/$defs/part`): its id,
/// title, state and whether kuhy may still edit it (856c0f0a).
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/json.dart';

/// A part as the board sends it; the server computes [editable].
@immutable
class RepoPart {
  /// Creates a part.
  const new({
    required this.id,
    required this.title,
    required this.state,
    required this.editable,
    this.reason,
    this.titleSource,
  });

  /// Parses one part.
  factory fromJson(Json j) {
    final edit = objOr(j, 'edit') ?? const <String, dynamic>{};
    return RepoPart(
      id: str(j, 'id'),
      title: str(j, 'title'),
      state: str(j, 'state'),
      editable: flag(edit, 'enabled'),
      reason: strOr(edit, 'reason'),
      titleSource: strOr(j, 'title_source'),
    );
  }

  /// `<note id8>-<index>`, the part's own section id.
  final String id;

  /// The shown title: kuhy's own without its image markdown (T2614).
  final String title;

  /// kuhy's own title with its image markdown, the editor's start value;
  /// null when it equals [title].
  final String? titleSource;

  /// `todo`, `working`, `done`, `human`, `held`.
  final String state;

  /// The run has not reached it and it is not ticked: the pencil works.
  final bool editable;

  /// Why the pencil is locked; null while it works.
  final String? reason;
}

/// The part texts in a `task_detail` result (`card.parts[].body`), by id.
Map<String, String> partBodies(Json detail) => {
  for (final p in objs(objOr(detail, 'card') ?? const {}, 'parts'))
    str(p, 'id'): str(p, 'body'),
};
