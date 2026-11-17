/// The usage page's link to the PC: `tokens` read requests for the panels
/// and the sealed `snap/usage` node for the autonomy view
/// (DOCS-native-app-relay.md, "Kinds" and "Publishing").
library;

import 'dart:async';

import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';

/// What the usage page needs from the relay.
abstract interface class UsageRelay {
  /// The newest `snap/usage` (the `GET /api/usage` body), then every
  /// later one.
  Stream<Json> usage();

  /// `GET /api/tokens<path>?<query>` through the `tokens` read kind.
  Future<RelayOutcome> tokens(String path, String query);
}

/// Sends one request (production: `BoardRelay.send`).
typedef Send = Future<RelayOutcome> Function(String kind, Json body);

/// Reads one sealed node (production: `RtdbClient.get` of `snap/usage`).
typedef ReadNode = Future<Object?> Function();

/// [UsageRelay] over the board relay's request path and the `rev/usage`
/// change signal.
class RtdbUsageRelay implements UsageRelay {
  /// Creates the relay.
  const new({required this.send, required this.read, required this.moves});

  /// Request sender.
  final Send send;

  /// `snap/usage` reader.
  final ReadNode read;

  /// Emits when `rev/usage` moves.
  final Stream<int> Function() moves;

  Future<Json?> _fetch() async {
    final node = await read();
    return node is Json ? node : null;
  }

  @override
  Stream<Json> usage() async* {
    final first = await _fetch();
    if (first != null) yield first;
    await for (final _ in moves()) {
      final next = await _fetch();
      if (next != null) yield next;
    }
  }

  @override
  Future<RelayOutcome> tokens(String path, String query) =>
      send('tokens', {'path': path, 'query': query});
}
