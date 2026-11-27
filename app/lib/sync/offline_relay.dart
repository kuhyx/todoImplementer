/// Offline-first around any [BoardRelay] (T2603): the kept board shows
/// before the first read, every board sync stores the details of the cards
/// that changed (one request at a time, so the PC worker is never flooded),
/// and every `task_detail` answer is kept, so a drawer opens at once.
library;

import 'dart:async';
import 'dart:collection';

import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/local_copy.dart';

/// How long one prefetch waits for the PC worker's answer.
const kPrefetchPatience = Duration(seconds: 15);

/// [inner] plus the on-device [local] copy.
class OfflineRelay implements BoardRelay {
  /// Creates the relay.
  new(this.inner, this.local);

  /// The live link to the PC.
  final BoardRelay inner;

  /// The kept board and details.
  final LocalCopy local;

  /// Each card's `updated` on the newest board.
  final _updated = <String, int?>{};

  final _queue = Queue<String>();
  String? _inFlight;
  bool _draining = false;

  @override
  Stream<Board> boards() {
    // A controller, not async*: a cancelled `await for` generator waits for
    // the next live board, which may never come offline.
    StreamSubscription<Board>? sub;
    late final StreamController<Board> out;
    out = StreamController<Board>(
      onListen: () {
        if (local.board() case final kept?) out.add(Board.fromJson(kept));
        sub = inner.boards().listen(
          (board) {
            unawaited(local.saveBoard(board.raw));
            _prefetch(board);
            out.add(board);
          },
          onError: out.addError,
          onDone: out.close,
        );
      },
      onCancel: () => sub?.cancel(),
    );
    return out.stream;
  }

  void _prefetch(Board board) {
    for (final task in board.tasks) {
      _updated[task.id] = task.updated;
      final kept = local.stamp(task.id);
      final stale = task.updated == null
          ? local.detail(task.id) == null
          : kept != task.updated;
      final waiting = _queue.contains(task.id) || _inFlight == task.id;
      if (stale && !waiting) _queue.add(task.id);
    }
    unawaited(_drain());
  }

  Future<void> _drain() async {
    if (_draining) return;
    _draining = true;
    while (_queue.isNotEmpty) {
      final card = _inFlight = _queue.removeFirst();
      await send('task_detail', {'card': card}, timeout: kPrefetchPatience);
    }
    _inFlight = null;
    _draining = false;
  }

  @override
  Json? cachedDetail(String card) => local.detail(card);

  @override
  Future<RelayOutcome> send(String kind, Json body, {Duration? timeout}) async {
    // The stamp as sent: a card that moves meanwhile is fetched again.
    final card = str(body, 'card');
    final stamp = _updated[card];
    final out = await inner.send(kind, body, timeout: timeout);
    if (kind == 'task_detail' && out is RelayOk) {
      await local.saveDetail(card, out.data, stamp: stamp);
    }
    return out;
  }

  @override
  Stream<List<MergeSuggestion>> merges() => inner.merges();

  @override
  Stream<List<Json>> liveFeed(String card) => inner.liveFeed(card);
}
