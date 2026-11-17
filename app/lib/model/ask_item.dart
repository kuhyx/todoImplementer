/// One ask of a card (`contracts/ask.schema.json#/$defs/ask`): a choice,
/// a command to run, or a screenshot to approve. The server decides state;
/// the app maps each state to the buttons the web drawer offers.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/json.dart';

/// One ask.
@immutable
class AskItem {
  /// Creates the ask.
  const new({
    required this.id,
    required this.type,
    required this.title,
    required this.state,
    this.risky = true,
    this.options = const [],
    this.recommended,
    this.answer,
    this.command,
    this.mode,
    this.shot,
    this.exit,
    this.tail,
  });

  /// Parses one ask.
  factory fromJson(Json j) {
    final result = objOr(j, 'result');
    return AskItem(
      id: str(j, 'id'),
      type: str(j, 'type', 'choice'),
      title: str(j, 'title'),
      state: str(j, 'state', 'open'),
      risky: str(j, 'risk', 'risky') != 'reversible',
      options: strs(j, 'options'),
      recommended: strOr(j, 'recommended'),
      answer: strOr(j, 'answer'),
      command: strOr(j, 'command'),
      mode: strOr(j, 'mode'),
      shot: strOr(j, 'shot'),
      exit: result == null ? null : intOr(result, 'exit'),
      tail: result == null ? null : strOr(result, 'tail'),
    );
  }

  /// Ask id (the request's `ask`).
  final String id;

  /// `choice`, `command` or `screenshot`.
  final String type;

  /// The question (the note's own words).
  final String title;

  /// `open`, `answered`, `auto`, `done`, `approved`, `rejected`.
  final String state;

  /// Risky asks fire on a long press only.
  final bool risky;

  /// Choice options.
  final List<String> options;

  /// The recommended option.
  final String? recommended;

  /// The chosen option.
  final String? answer;

  /// Command text.
  final String? command;

  /// `run`, `add_run` or `terminal` (copy only).
  final String? mode;

  /// Screenshot name for `task_shot`.
  final String? shot;

  /// The command's exit code, once run.
  final int? exit;

  /// The command's output tail, once run.
  final String? tail;

  /// Still waits on kuhy.
  bool get open => state == 'open';
}

/// The relay request for answering [ask] with [option].
(String, Map<String, dynamic>) answerRequest(AskItem ask, String option) =>
    ('ask_answer', {'ask': ask.id, 'option': option});

/// The relay request that runs [ask]'s command (`add` lists it first).
(String, Map<String, dynamic>) runRequest(AskItem ask) =>
    ('ask_run', {'ask': ask.id, 'add': ask.mode == 'add_run'});
