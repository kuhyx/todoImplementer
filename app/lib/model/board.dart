/// The `snap/board` node: exactly the `GET /api/board` body
/// (`contracts/board.schema.json`). Status, columns and the offered actions
/// are computed on the server; the app never recomputes them.
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/card_parts.dart';
import 'package:todo_implementer/model/json.dart';

export 'package:todo_implementer/model/card_parts.dart';

/// The four board columns, in board order.
const columnIds = ['backlog', 'running', 'needs_you', 'done'];

/// One board card (`common.schema.json#/$defs/task_card`).
@immutable
class TaskCard {
  /// Creates a card.
  const new({
    required this.id,
    required this.title,
    required this.repo,
    required this.priority,
    required this.status,
    required this.column,
    required this.current,
    required this.costUsd,
    required this.actions,
    this.stage,
    this.needs,
    this.route,
    this.updated,
    this.cheap = false,
    this.free = false,
    this.escalated = false,
    this.model,
  });

  /// Parses a card.
  factory fromJson(Json j) {
    final needs = objOr(j, 'needs');
    final tier = objOr(j, 'tier') ?? const <String, dynamic>{};
    return TaskCard(
      id: str(j, 'id'),
      title: str(j, 'title'),
      repo: strOr(j, 'repo'),
      priority: str(j, 'priority'),
      status: str(j, 'status'),
      column: str(j, 'column'),
      current: str(j, 'current'),
      costUsd: numOf(j, 'cost_usd'),
      actions: objs(j, 'actions').map(CardAction.fromJson).toList(),
      stage: strOr(j, 'stage'),
      needs: needs == null ? null : Needs.fromJson(needs),
      route: strOr(j, 'route'),
      updated: intOr(j, 'updated'),
      cheap: flag(tier, 'cheap'),
      free: flag(tier, 'free'),
      escalated: flag(tier, 'escalated'),
      model: strOr(j, 'model'),
    );
  }

  /// Item id.
  final String id;

  /// The note's title (kuhy's own content).
  final String title;

  /// `owner/name`; null = the note has no repo (Yours).
  final String? repo;

  /// Note priority.
  final String priority;

  /// The single server-computed status.
  final String status;

  /// Column id.
  final String column;

  /// One line on what it does or waits on.
  final String current;

  /// Run cost so far.
  final double costUsd;

  /// Buttons the server offers.
  final List<CardAction> actions;

  /// Run stage; null before a run.
  final String? stage;

  /// Why it needs kuhy; null outside Needs you.
  final Needs? needs;

  /// Latest turn's route: plan, credits or null.
  final String? route;

  /// Last change (epoch s).
  final int? updated;

  /// Sonnet manager.
  final bool cheap;

  /// Free models allowed.
  final bool free;

  /// Opus took over.
  final bool escalated;

  /// The model its turns run on: kuhy's pin, else the latest turn's.
  final String? model;
}

/// A column header: id, the server's label (spoken) and its card count.
@immutable
class BoardColumn {
  /// Creates the header.
  const new(this.id, this.label, this.count);

  /// `backlog`, `running`, `needs_you`, `done`.
  final String id;

  /// Spoken label.
  final String label;

  /// Cards in the column (before filters).
  final int count;
}

/// The whole board snapshot.
@immutable
class Board {
  /// Creates a board.
  const new({
    required this.build,
    required this.columns,
    required this.repos,
    required this.tasks,
    required this.autoClose,
    required this.slotsUsed,
    required this.limitActive,
    required this.creditsEnabled,
    this.creditsState = 'off',
    this.credits = const {},
    this.limitUntil,
    this.error,
    this.alert,
    this.apiKeyLevel = 'ok',
    this.apiKeyText,
  });

  /// Parses the `snap/board` unit.
  factory fromJson(Json j) {
    final limit = objOr(j, 'limit') ?? const <String, dynamic>{};
    final credits = objOr(limit, 'credits') ?? const <String, dynamic>{};
    final key = objOr(j, 'api_key');
    return Board(
      build: str(j, 'build'),
      columns: [
        for (final c in objs(j, 'columns'))
          BoardColumn(str(c, 'id'), str(c, 'label'), intOr(c, 'count') ?? 0),
      ],
      repos: strs(j, 'repos'),
      tasks: objs(j, 'tasks').map(TaskCard.fromJson).toList(),
      autoClose: flag(j, 'auto_close'),
      slotsUsed: intOr(objOr(j, 'slots') ?? const {}, 'used') ?? 0,
      limitActive: flag(limit, 'active'),
      creditsEnabled: flag(credits, 'enabled'),
      creditsState: str(credits, 'state', 'off'),
      credits: credits,
      limitUntil: intOr(limit, 'until'),
      error: strOr(objOr(j, 'error') ?? const {}, 'message'),
      alert: strOr(objOr(j, 'alert') ?? const {}, 'text'),
      apiKeyLevel: key == null ? 'ok' : str(key, 'level', 'ok'),
      apiKeyText: key == null ? null : strOr(key, 'text'),
    );
  }

  /// Server build id.
  final String build;

  /// The five columns.
  final List<BoardColumn> columns;

  /// Known repos.
  final List<String> repos;

  /// Every card.
  final List<TaskCard> tasks;

  /// Auto close setting.
  final bool autoClose;

  /// Running slots in use.
  final int slotsUsed;

  /// A Claude plan limit is active.
  final bool limitActive;

  /// The free API credits fallback setting.
  final bool creditsEnabled;

  /// `off`, `ready`, `exhausted`, `unavailable`.
  final String creditsState;

  /// The `limit.credits` object as sent (cap, spend, over_cap).
  final Json credits;

  /// Epoch seconds the plan limit lifts, while one is active.
  final int? limitUntil;

  /// Board-level error (stale cards); spoken.
  final String? error;

  /// Overage alert; spoken.
  final String? alert;

  /// API key banner level: ok, warn, error.
  final String apiKeyLevel;

  /// API key banner text; spoken.
  final String? apiKeyText;
}
