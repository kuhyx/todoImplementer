/// Writes made with no network (T2604): a `new_task` or `task_send` whose
/// relay PUT never reached the RTDB is kept on disk, shown on the board as
/// a card with the unsent glyph (new tasks), and sent in order on the next
/// board sync. A `timeout` is never queued: its request did land and the
/// worker serves it later, so a resend would make it twice.
library;

import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/local_copy.dart';

/// The request kinds that carry kuhy's own text and are kept offline.
const kOutboxKinds = {'new_task', 'task_send'};

/// The queue of unsent writes in [local].
class Outbox {
  /// Creates the outbox.
  new(this.local);

  /// Where the queue is kept.
  final LocalCopy local;

  bool _draining = false;

  /// Whether a [kind] request that ended in [out] belongs in the outbox.
  static bool takes(String kind, RelayOutcome out) =>
      kOutboxKinds.contains(kind) &&
      out is RelayFailed &&
      out.code == 'offline';

  /// Queues one request.
  Future<void> add(String kind, Json body) => local.saveOutbox([
    ...local.outbox(),
    {'kind': kind, 'body': body},
  ]);

  /// The queued new tasks as Backlog cards (`status: unsent`, no actions).
  List<Json> cards() => [
    for (final (i, q) in local.outbox().indexed)
      if (q['kind'] == 'new_task')
        if (objOr(objOr(q, 'body') ?? const {}, 'args') case final args?)
          {
            'id': 'queued-$i',
            'title': str(args, 'title'),
            'repo': strOr(args, 'repo'),
            'column': 'backlog',
            'status': 'unsent',
            'priority': 'normal',
            'actions': const <Json>[],
          },
  ];

  /// Sends the queue in order through [send] until one is still offline.
  /// A refusal drops the request: resending would be refused again.
  Future<void> drain(
    Future<RelayOutcome> Function(String kind, Json body) send,
  ) async {
    if (_draining) return;
    _draining = true;
    try {
      for (
        var head = local.outbox().firstOrNull;
        head != null;
        head = local.outbox().firstOrNull
      ) {
        final out = await send(str(head, 'kind'), objOr(head, 'body') ?? {});
        if (out is RelayFailed && out.code == 'offline') return;
        await local.saveOutbox(local.outbox().skip(1).toList());
      }
    } finally {
      _draining = false;
    }
  }
}
