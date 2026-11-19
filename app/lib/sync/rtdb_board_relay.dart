/// The real [BoardRelay]: sealed REST reads of `snap/board`, the `rev`
/// counter as the change signal, and requests through the shared `requests`
/// listen (DOCS-native-app-relay.md, "Publishing" and "Kinds").
library;

import 'dart:async';

import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/layout.dart';

/// Follows `requests/<rid>` (production: `RequestHub.watch`).
typedef RequestWatch = Stream<Object?> Function(String rid);

/// Emits when `rev/board` moves (production: `RevWatcher.changesOf`).
typedef BoardMoves = Stream<int> Function();

/// Emits when `rev/<key>` moves.
typedef RevMoves = Stream<int> Function(String key);

/// Streams the events of one full path (production: `RtdbStream.listen`).
typedef NodeListen = Stream<RtdbEvent> Function(String path);

Stream<int> _still(String _) => const Stream.empty();

Stream<RtdbEvent> _quiet(String _) => const Stream.empty();

/// How often an open feed renews its `live_watch`; the worker keeps a watch
/// for 120 s after the last one (`server/todoimpl/relay/live.py`).
const kLiveRenew = Duration(seconds: 60);

/// The live events under a streamed `live/{card}` tree, in key order.
List<Json> feedOf(Object? tree) {
  if (tree is! Map) return const [];
  final keys = tree.keys.whereType<String>().toList()..sort();
  return [for (final k in keys) ?(tree[k] is Json ? tree[k] as Json : null)];
}

/// Board relay over Firebase RTDB.
class RtdbBoardRelay implements BoardRelay {
  /// Creates the relay for this install's device [dev].
  new({
    required this.client,
    required this.dev,
    required this.watch,
    required this.moves,
    RevMoves? revOf,
    NodeListen? listen,
    DateTime Function()? clock,
    this.renewEvery = kLiveRenew,
  }) : revOf = revOf ?? _still,
       listen = listen ?? _quiet,
       _clock = clock ?? DateTime.now;

  /// Wires the relay to one shared stream, as the app runs it.
  factory live({
    required RtdbClient client,
    required RtdbStream stream,
    required String dev,
  }) {
    final hub = RequestHub(stream, fullPath('requests'));
    final rev = RevWatcher(stream, fullPath('rev'), yieldTo: hub.inFlight);
    return RtdbBoardRelay(
      client: client,
      dev: dev,
      watch: hub.watch,
      moves: () => rev.changesOf('board'),
      revOf: rev.changesOf,
      listen: stream.listen,
    );
  }

  /// REST client (seals and opens).
  final RtdbClient client;

  /// This install's device id.
  final String dev;

  /// Request follower.
  final RequestWatch watch;

  /// Board change signal.
  final BoardMoves moves;

  /// Change signal of any `rev/<key>` (merges).
  final RevMoves revOf;

  /// Streams one node (the live feed).
  final NodeListen listen;

  /// Renewal period of an open feed's `live_watch`.
  final Duration renewEvery;

  final DateTime Function() _clock;

  Future<Board?> _fetch() async {
    final node = await client.get(fullPath('snap/board'));
    return node is Json ? Board.fromJson(node) : null;
  }

  @override
  Stream<Board> boards() async* {
    // First start: ask the worker to republish every node, then show what
    // is there now; later boards arrive with each `rev/board` move.
    unawaited(send('snapshot_refresh', const {}));
    final first = await _fetch();
    if (first != null) yield first;
    await for (final _ in moves()) {
      final next = await _fetch();
      if (next != null) yield next;
    }
  }

  Future<List<MergeSuggestion>> _fetchMerges() async {
    final node = await client.get(fullPath('snap/merges'));
    return node is Json ? mergesOf(node) : const [];
  }

  @override
  Stream<List<MergeSuggestion>> merges() async* {
    yield await _fetchMerges();
    await for (final _ in revOf('merges')) {
      yield await _fetchMerges();
    }
  }

  @override
  Stream<List<Json>> liveFeed(String card) {
    StreamSubscription<RtdbEvent>? sub;
    Timer? renew;
    Object? tree;
    late final StreamController<List<Json>> out;
    void watchIt() => unawaited(send('live_watch', {'card': card}));
    out = StreamController<List<Json>>(
      onListen: () {
        watchIt();
        renew = Timer.periodic(renewEvery, (_) => watchIt());
        sub = listen(fullPath('live/$card')).listen((event) {
          if (event is! RtdbPut && event is! RtdbPatch) return;
          tree = applyEvent(tree, event);
          out.add(feedOf(tree));
        });
      },
      onCancel: () async {
        renew?.cancel();
        await sub?.cancel();
        // RTDB drops the null: the worker reads a missing card as release.
        unawaited(send('live_watch', {'card': null}));
      },
    );
    return out.stream;
  }

  @override
  Future<RelayOutcome> send(String kind, Json body, {Duration? timeout}) async {
    final now = _clock();
    final rid = ulid(now: now);
    final result = Completer<Json>();
    final sub = watch(rid).listen((node) {
      final r = node is Json ? objOr(node, 'result') : null;
      if (r != null && !result.isCompleted) result.complete(r);
    });
    try {
      await client.put(fullPath('requests/$rid/req'), {
        'kind': kind,
        'dev': dev,
        'created': {'.sv': 'timestamp'},
        'sent_at': now.millisecondsSinceEpoch,
        'body': body,
      });
      final answer = timeout == null
          ? result.future
          : result.future.timeout(timeout);
      return outcomeOf(await answer);
    } on TimeoutException {
      return RelayFailed(
        code: 'timeout',
        error: 'no answer to $kind from the PC worker in $timeout',
        retry: true,
      );
    } on Object catch (error) {
      // `on Object`: transport Errors and Exceptions both reach the user.
      return RelayFailed(code: 'offline', error: '$error', retry: true);
    } finally {
      await sub.cancel();
    }
  }
}
