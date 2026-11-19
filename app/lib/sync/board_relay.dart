/// What the UI needs from the relay, behind an interface so widget tests
/// run against a fake and the real one stays a thin RTDB adapter.
library;

import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/merges.dart';

export 'package:todo_implementer/model/merges.dart';

/// The answer to one request (`contracts/relay-result.schema.json`).
@immutable
sealed class RelayOutcome {
  const new();
}

/// The worker served it; [data] is the HTTP route's 200 body.
class RelayOk extends RelayOutcome {
  /// Creates the outcome.
  const new(this.data);

  /// Kind-specific result.
  final Json data;
}

/// The worker refused or failed it. [error] is for the log and the
/// copy-errors action only; the UI draws [code] as a glyph (textgate).
class RelayFailed extends RelayOutcome {
  /// Creates the outcome.
  const new({required this.code, required this.error, this.retry = false});

  /// `disabled`, `unsealed`, `rate_limited`, `offline`, ...
  final String code;

  /// The worker's (or transport's) message.
  final String error;

  /// A resend may fix it.
  final bool retry;
}

/// Maps a `requests/{rid}/result` unit to an outcome.
RelayOutcome outcomeOf(Json result) {
  if (result['ok'] == true) {
    return RelayOk(objOr(result, 'data') ?? const <String, dynamic>{});
  }
  return RelayFailed(
    code: str(result, 'code', 'internal'),
    error: str(result, 'error', 'no error text'),
    retry: flag(result, 'retry'),
  );
}

/// The board's link to the PC.
abstract interface class BoardRelay {
  /// Every new `snap/board` the worker publishes, newest first on listen.
  Stream<Board> boards();

  /// Sends one request of [kind] with [body] and waits for its result; with
  /// [timeout], no answer by then is a retryable `timeout` failure.
  Future<RelayOutcome> send(String kind, Json body, {Duration? timeout});

  /// Every new `snap/merges` the worker publishes.
  Stream<List<MergeSuggestion>> merges();

  /// [card]'s live feed (`live/{card}`), oldest first, while listened to:
  /// listening sends `live_watch` and renews it while listened to (the
  /// worker drops a watch 120 s after its last renewal); cancelling releases
  /// it.
  Stream<List<Json>> liveFeed(String card);
}

const _crockford = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/// A ULID: 48-bit milliseconds then 80 random bits, Crockford base32, so
/// request ids sort by creation time (the worker serves them in key order).
String ulid({DateTime? now, Random? random}) {
  final rng = random ?? Random.secure();
  var ms = (now ?? DateTime.now()).millisecondsSinceEpoch;
  final time = List.filled(10, '0');
  for (var i = 9; i >= 0; i--) {
    time[i] = _crockford[ms % 32];
    ms ~/= 32;
  }
  final rand = List.generate(16, (_) => _crockford[rng.nextInt(32)]);
  return time.join() + rand.join();
}
