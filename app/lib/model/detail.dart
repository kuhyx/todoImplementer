/// The `task_detail` result: exactly the `GET /api/task/<card>` body
/// (`contracts/task.schema.json`), read leniently like the board.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/ask_item.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';

export 'package:todo_implementer/model/ask_item.dart';

/// One changed file of the diff.
@immutable
class DiffFile {
  /// Creates the row.
  const new(this.path, this.added, this.removed);

  /// Repo-relative path.
  final String path;

  /// Lines added.
  final int added;

  /// Lines removed.
  final int removed;
}

/// The worktree diff.
@immutable
class Diff {
  /// Creates the diff.
  const new({required this.files, required this.patch, this.truncated = false});

  /// Parses `diff`.
  factory fromJson(Json j) => Diff(
    files: [
      for (final f in objs(j, 'files'))
        DiffFile(
          str(f, 'path'),
          intOr(f, 'added') ?? 0,
          intOr(f, 'removed') ?? 0,
        ),
    ],
    patch: str(j, 'patch'),
    truncated: flag(j, 'truncated'),
  );

  /// Changed files.
  final List<DiffFile> files;

  /// The unified patch.
  final String patch;

  /// The server cut the patch.
  final bool truncated;
}

/// One check command's outcome.
@immutable
class CheckResult {
  /// Creates the result.
  const new(this.command, this.exit, this.tail);

  /// The command run.
  final String command;

  /// Its exit code.
  final int exit;

  /// The output's tail.
  final String tail;
}

/// The checks stage.
@immutable
class Checks {
  /// Creates the checks.
  const new({required this.passed, required this.results});

  /// Parses `checks`.
  factory fromJson(Json j) => Checks(
    passed: flag(j, 'passed'),
    results: [
      for (final r in objs(j, 'results'))
        CheckResult(str(r, 'command'), intOr(r, 'exit') ?? -1, str(r, 'tail')),
    ],
  );

  /// Every command exited 0.
  final bool passed;

  /// Per command.
  final List<CheckResult> results;
}

/// Claude's live-check report and its screenshots.
@immutable
class LiveCheck {
  /// Creates the report.
  const new({required this.reportMd, required this.shots});

  /// Parses `live_check`.
  factory fromJson(Json j) =>
      LiveCheck(reportMd: str(j, 'report_md'), shots: strs(j, 'shots'));

  /// Report (markdown, shown as text).
  final String reportMd;

  /// Screenshot names for `task_shot`.
  final List<String> shots;
}

/// A drafted skill lesson.
@immutable
class Lesson {
  /// Creates the lesson.
  const new({
    required this.skill,
    required this.mistake,
    required this.rule,
    required this.evidence,
  });

  /// Parses `lesson`.
  factory fromJson(Json j) => Lesson(
    skill: str(j, 'skill'),
    mistake: str(j, 'mistake'),
    rule: str(j, 'rule'),
    evidence: str(j, 'evidence'),
  );

  /// Target skill.
  final String skill;

  /// What went wrong.
  final String mistake;

  /// The proposed rule.
  final String rule;

  /// Its evidence.
  final String evidence;
}

/// Everything the card drawer shows.
@immutable
class TaskDetail {
  /// Creates the detail.
  const new({
    required this.card,
    this.planMd,
    this.diff,
    this.checks,
    this.liveCheck,
    this.lesson,
    this.error,
    this.asks = const [],
    this.umbrella,
  });

  /// Parses the `task_detail` result data.
  factory fromJson(Json j) {
    final diff = objOr(j, 'diff');
    final checks = objOr(j, 'checks');
    final live = objOr(j, 'live_check');
    final lesson = objOr(j, 'lesson');
    final asks = j['ask_items'];
    return TaskDetail(
      card: TaskCard.fromJson(objOr(j, 'card') ?? const {}),
      planMd: strOr(j, 'plan_md'),
      diff: diff == null ? null : Diff.fromJson(diff),
      checks: checks == null ? null : Checks.fromJson(checks),
      liveCheck: live == null ? null : LiveCheck.fromJson(live),
      lesson: lesson == null ? null : Lesson.fromJson(lesson),
      error: strOr(j, 'error'),
      asks: asks is List
          ? asks.whereType<Json>().map(AskItem.fromJson).toList()
          : const [],
      umbrella: objOr(j, 'umbrella'),
    );
  }

  /// The card as on the board.
  final TaskCard card;

  /// The plan, once written.
  final String? planMd;

  /// The worktree diff, once implemented.
  final Diff? diff;

  /// Check output, once run.
  final Checks? checks;

  /// The live-check report, once made.
  final LiveCheck? liveCheck;

  /// A drafted lesson.
  final Lesson? lesson;

  /// The run's error.
  final String? error;

  /// The note's `ask` block buttons.
  final List<AskItem> asks;

  /// Umbrella detail (`umbrella.schema.json#/$defs/detail`), if any.
  final Json? umbrella;
}
