// T2603: the app was online-only. A cold start with no network showed an
// empty board, and every card drawer waited on the PC worker (a spinner,
// then a retry glyph). Offline-first now: the last board and every card
// detail seen or prefetched on a sync are kept on disk and shown at once.
import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/local_copy.dart';
import 'package:todo_implementer/sync/offline_relay.dart';

import '../support/fakes.dart';

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  var now = DateTime(2026);

  /// A fresh relay over the same disk; [later] moves the clock a gap on.
  OfflineRelay restart(FakeRelay inner) =>
      OfflineRelay(inner, PrefsLocalCopy(prefs), clock: () => now);

  void later() => now = now.add(kPrefetchGap);

  final board = boardJson([card('c1', updated: 1), card('c2', updated: 5)]);

  test(
    '[T2603] a restarted app shows the last board with no network',
    () async {
      final first = FakeRelay();
      final seen = <Board>[];
      final sub = restart(first).boards().listen(seen.add);
      await pumpEventQueue();
      first.push(board);
      await pumpEventQueue();
      await sub.cancel();
      final offline = FakeRelay();
      final shown = await restart(offline).boards().first;
      expect(shown.tasks.map((t) => t.id), ['c1', 'c2']);
      expect(offline.sent.where((s) => s.$1 == 'task_detail'), isEmpty);
    },
  );

  test('[T2603] every sync stores the changed cards details', () async {
    final inner = FakeRelay()
      ..outcomes['task_detail'] = const RelayOk({
        'card': {'id': 'x'},
      });
    final relay = restart(inner);
    final sub = relay.boards().listen((_) {});
    await pumpEventQueue();
    inner.push(board);
    await pumpEventQueue();
    expect(
      [
        for (final s in inner.sent)
          if (s.$1 == 'task_detail') s.$2['card'],
      ],
      ['c1', 'c2'],
    );
    later();
    inner.push(boardJson([card('c1', updated: 1), card('c2', updated: 6)]));
    await pumpEventQueue();
    await sub.cancel();
    final asked = [
      for (final s in inner.sent)
        if (s.$1 == 'task_detail') s.$2['card'],
    ];
    expect(asked, ['c1', 'c2', 'c2']);
    final cold = restart(FakeRelay()..outcomes['task_detail'] = _offline);
    expect(cold.cachedDetail('c1'), {
      'card': {'id': 'x'},
    });
    expect(cold.cachedDetail('c3'), isNull);
  });

  test('[T2603] an opened detail is kept even when offline later', () async {
    final inner = FakeRelay()
      ..outcomes['task_detail'] = const RelayOk({'plan_md': 'p'});
    await restart(inner).send('task_detail', {'card': 'c9'});
    final cold = restart(FakeRelay()..outcomes['task_detail'] = _offline);
    expect(cold.cachedDetail('c9'), {'plan_md': 'p'});
    expect(await cold.send('task_detail', {'card': 'c9'}), isA<RelayFailed>());
    expect(cold.cachedDetail('c9'), {'plan_md': 'p'});
  });

  test('[T2603] a failed prefetch is retried on the next sync', () async {
    final inner = FakeRelay()..outcomes['task_detail'] = _offline;
    final relay = restart(inner);
    final sub = relay.boards().listen((_) {});
    await pumpEventQueue();
    inner.push(boardJson([card('c1', updated: 1)]));
    await pumpEventQueue();
    inner.outcomes['task_detail'] = const RelayOk({'n': 1});
    later();
    inner.push(boardJson([card('c1', updated: 1)]));
    await pumpEventQueue();
    await sub.cancel();
    expect(relay.cachedDetail('c1'), {'n': 1});
  });

  test('[T2603] a card with no stamp is fetched once, then kept', () async {
    final inner = FakeRelay();
    final relay = restart(inner);
    final sub = relay.boards().listen((_) {});
    inner
      ..push(boardJson([card('c1')]))
      ..push(boardJson([card('c1')]));
    await pumpEventQueue();
    await sub.cancel();
    expect(inner.sent.where((s) => s.$1 == 'task_detail'), hasLength(1));
    expect(PrefsLocalCopy(prefs).stamp('c1'), isNull);
  });

  test('[T2603] feeds and merges pass through', () async {
    final inner = FakeRelay();
    final relay = restart(inner);
    expect(relay.liveFeed('c1'), isNotNull);
    expect(inner.feeds.keys, ['c1']);
    final merges = relay.merges().first;
    inner.mergesOut.add(const []);
    expect(await merges, isEmpty);
  });

  test('[T2603] an offline error keeps the board and reconnects', () async {
    await prefs.setString('local.board', jsonEncode(board));
    final inner = _Flaky();
    final relay = OfflineRelay(
      inner,
      PrefsLocalCopy(prefs),
      retryAfter: Duration.zero,
    );
    final seen = <Board>[];
    final errors = <Object>[];
    final sub = relay.boards().listen(seen.add, onError: errors.add);
    await pumpEventQueue();
    inner.live.last
      ..addError(StateError('offline'))
      ..close();
    await pumpEventQueue();
    expect(inner.live, hasLength(2));
    inner.live.last.add(Board.fromJson(boardJson([card('c7')])));
    await pumpEventQueue();
    await sub.cancel();
    expect(errors, isEmpty);
    expect(seen.map((b) => b.tasks.first.id), ['c1', 'c7']);
  });

  test('[T2603] a running card is prefetched at most once a gap', () async {
    final inner = FakeRelay();
    final relay = restart(inner);
    final sub = relay.boards().listen((_) {});
    inner.push(boardJson([card('c1', updated: 1)]));
    await pumpEventQueue();
    inner.push(boardJson([card('c1', updated: 2)]));
    await pumpEventQueue();
    later();
    inner.push(boardJson([card('c1', updated: 3)]));
    await pumpEventQueue();
    await sub.cancel();
    expect(inner.sent.where((s) => s.$1 == 'task_detail'), hasLength(2));
    expect(relay.cachedDetail('c1'), isNotNull);
  });

  test('[T2603] a full disk never fails a live answer', () async {
    final inner = FakeRelay()..outcomes['task_detail'] = const RelayOk({});
    final relay = OfflineRelay(inner, _FullDisk());
    expect(await relay.send('task_detail', {'card': 'c1'}), isA<RelayOk>());
    inner.outcomes['new_task'] = _offline;
    expect(await relay.send('new_task', const {}), isA<RelayFailed>());
  });
}

const _offline = RelayFailed(code: 'offline', error: 'down', retry: true);

/// A relay whose board stream is new on every listen, like the real one.
class _Flaky extends FakeRelay {
  final live = <StreamController<Board>>[];

  @override
  Stream<Board> boards() {
    live.add(StreamController<Board>());
    return live.last.stream;
  }
}

/// A store whose writes fail (the web build's localStorage quota).
class _FullDisk implements LocalCopy {
  @override
  Json? board() => null;

  @override
  Future<void> saveBoard(Json node) async => throw StateError('quota');

  @override
  Json? detail(String card) => null;

  @override
  int? stamp(String card) => null;

  @override
  Future<void> saveDetail(String card, Json data, {int? stamp}) async =>
      throw StateError('quota');

  @override
  List<Json> outbox() => const [];

  @override
  Future<void> saveOutbox(List<Json> items) async => throw StateError('quota');
}
