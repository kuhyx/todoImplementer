// T2603: the app was online-only. A cold start with no network showed an
// empty board, and every card drawer waited on the PC worker (a spinner,
// then a retry glyph). Offline-first now: the last board and every card
// detail seen or prefetched on a sync are kept on disk and shown at once.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/board.dart';
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

  OfflineRelay restart(FakeRelay inner) =>
      OfflineRelay(inner, PrefsLocalCopy(prefs));

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
    inner.push(boardJson([card('c1', updated: 1)]));
    await pumpEventQueue();
    await sub.cancel();
    expect(relay.cachedDetail('c1'), {'n': 1});
  });

  test('[T2603] the details stay under the storage budget', () async {
    final copy = PrefsLocalCopy(prefs, budget: 100);
    await copy.saveDetail('old', {'t': 'a' * 40}, stamp: 1);
    await copy.saveDetail('mid', {'t': 'b' * 40}, stamp: 1);
    await copy.saveDetail('new', {'t': 'c' * 40}, stamp: 1);
    await copy.saveDetail('huge', {'t': 'd' * 400}, stamp: 1);
    final fresh = PrefsLocalCopy(prefs, budget: 100);
    expect(fresh.detail('old'), isNull);
    expect(fresh.detail('huge'), isNull);
    expect(fresh.detail('mid'), isNotNull);
    expect(fresh.detail('new'), isNotNull);
    expect(fresh.stamp('new'), 1);
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

  test('[T2603] feeds, merges, errors and the end pass through', () async {
    final inner = FakeRelay();
    final relay = restart(inner);
    expect(relay.liveFeed('c1'), isNotNull);
    expect(inner.feeds.keys, ['c1']);
    final merges = relay.merges().first;
    inner.mergesOut.add(const []);
    expect(await merges, isEmpty);
    final errors = <Object>[];
    final done = Completer<void>();
    relay.boards().listen((_) {}, onError: errors.add, onDone: done.complete);
    await pumpEventQueue();
    inner.boardsOut.addError(StateError('down'));
    await inner.boardsOut.close();
    await done.future;
    expect(errors.single, isA<StateError>());
  });

  test('[T2603] a corrupt saved copy reads as nothing', () async {
    SharedPreferences.setMockInitialValues({
      'local.board': '{oops',
      'local.detail.c1': '[1]',
      'local.details': '{"c1": "x"}',
    });
    final copy = PrefsLocalCopy(await SharedPreferences.getInstance());
    expect(copy.board(), isNull);
    expect(copy.detail('c1'), isNull);
    expect(copy.stamp('c1'), isNull);
  });
}

const _offline = RelayFailed(code: 'offline', error: 'down', retry: true);
