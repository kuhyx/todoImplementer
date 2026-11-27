/// Offline-first around any [BoardRelay] (T2603): the kept board shows
/// before the first read and stays when the network drops (the live stream
/// reconnects with backoff), every board sync stores the details of the
/// cards that changed (one request at a time, a running card at most once
/// per [kPrefetchGap], so the PC worker and mobile data are spared), and
/// every `task_detail` answer is kept, so a drawer opens at once.
library;

import 'dart:async';
import 'dart:collection';

import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/local_copy.dart';
import 'package:todo_implementer/sync/outbox.dart';

/// How long one prefetch waits for the PC worker's answer.
const kPrefetchPatience = Duration(seconds: 15);

/// The least time between two prefetches of one card.
const kPrefetchGap = Duration(seconds: 60);

/// The first reconnect wait after the live board stream fails; it doubles
/// up to [kRetryMax] and resets with the next board.
const kRetryFirst = Duration(seconds: 2);

/// The longest reconnect wait.
const kRetryMax = Duration(seconds: 60);

/// [inner] plus the on-device [local] copy.
class OfflineRelay implements BoardRelay {
  /// Creates the relay; [retryAfter] is the first reconnect wait.
  new(
    this.inner,
    this.local, {
    this.retryAfter = kRetryFirst,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now,
       _outbox = Outbox(local);

  /// The live link to the PC.
  final BoardRelay inner;

  /// The kept board and details.
  final LocalCopy local;

  /// The first reconnect wait.
  final Duration retryAfter;

  final DateTime Function() _clock;

  /// Writes made offline, sent on the next sync (T2604).
  final Outbox _outbox;

  /// Each card's `updated` on the newest board.
  final _updated = <String, int?>{};

  /// When each card was last prefetched.
  final _fetchedAt = <String, DateTime>{};

  final _queue = Queue<String>();
  String? _inFlight;
  bool _draining = false;

  @override
  Stream<Board> boards() {
    // A controller, not async*: a cancelled `await for` generator waits for
    // the next live board, which may never come offline.
    StreamSubscription<Board>? sub;
    Timer? retry;
    var wait = retryAfter;
    late final StreamController<Board> out;
    void connect() {
      // The real stream ends after an offline error; the kept board stays
      // on screen and the stream is opened again later.
      void again() {
        retry = Timer(wait, connect);
        final doubled = wait * 2;
        wait = doubled > kRetryMax ? kRetryMax : doubled;
      }

      sub = inner.boards().listen(
        (board) {
          wait = retryAfter;
          unawaited(_keep(() => local.saveBoard(board.raw)));
          _prefetch(board);
          out.add(_withQueued(board.raw) ?? board);
          // The bare relay: an offline resend must not queue itself again.
          unawaited(_outbox.drain(inner.send));
        },
        onError: (Object _) {},
        onDone: again,
      );
    }

    out = StreamController<Board>(
      onListen: () {
        if (local.board() case final kept?) {
          out.add(_withQueued(kept) ?? Board.fromJson(kept));
        }
        connect();
      },
      onCancel: () {
        retry?.cancel();
        return sub?.cancel();
      },
    );
    return out.stream;
  }

  /// [raw] plus the queued new tasks, or null when none are queued.
  Board? _withQueued(Json raw) {
    final queued = _outbox.cards();
    if (queued.isEmpty) return null;
    return Board.fromJson({
      ...raw,
      'tasks': [...objs(raw, 'tasks'), ...queued],
    });
  }

  void _prefetch(Board board) {
    final now = _clock();
    for (final task in board.tasks) {
      _updated[task.id] = task.updated;
      final kept = local.stamp(task.id);
      final stale = task.updated == null
          ? local.detail(task.id) == null
          : kept != task.updated;
      final last = _fetchedAt[task.id];
      final recent = last != null && now.difference(last) < kPrefetchGap;
      final waiting = _queue.contains(task.id) || _inFlight == task.id;
      if (stale && !recent && !waiting) _queue.add(task.id);
    }
    unawaited(_drain());
  }

  Future<void> _drain() async {
    if (_draining) return;
    _draining = true;
    while (_queue.isNotEmpty) {
      final card = _inFlight = _queue.removeFirst();
      _fetchedAt[card] = _clock();
      await send('task_detail', {'card': card}, timeout: kPrefetchPatience);
    }
    _inFlight = null;
    _draining = false;
  }

  /// Runs one write to the kept copy; a full disk (the web build's
  /// localStorage quota) costs the copy, never the live answer.
  static Future<void> _keep(Future<void> Function() write) async {
    try {
      await write();
    } on Object {
      // `on Object`: platform storage throws Errors as well as Exceptions.
    }
  }

  @override
  Json? cachedDetail(String card) => local.detail(card);

  @override
  Future<RelayOutcome> send(String kind, Json body, {Duration? timeout}) async {
    // The stamp as sent: a card that moves meanwhile is fetched again.
    final card = str(body, 'card');
    final stamp = _updated[card];
    final out = await inner.send(kind, body, timeout: timeout);
    if (Outbox.takes(kind, out)) return await _keepOffline(kind, body, out);
    if (kind == 'task_detail' && out is RelayOk) {
      await _keep(() => local.saveDetail(card, out.data, stamp: stamp));
    }
    return out;
  }

  /// Keeps an offline write; a full disk returns the [failed] outcome so
  /// the sheet keeps the text and shows the refusal.
  Future<RelayOutcome> _keepOffline(
    String kind,
    Json body,
    RelayOutcome failed,
  ) async {
    try {
      await _outbox.add(kind, body);
    } on Object {
      return failed;
    }
    return const RelayOk({'queued': true});
  }

  @override
  Stream<List<MergeSuggestion>> merges() => inner.merges();

  @override
  Stream<List<Json>> liveFeed(String card) => inner.liveFeed(card);
}
