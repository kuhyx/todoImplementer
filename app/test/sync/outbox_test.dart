// T2604: a new task or a note written with no network was lost: the relay
// PUT failed, the sheet showed a refusal and kuhy had to type it again. A
// write whose PUT never reached the RTDB now lands in an on-disk outbox,
// shows on the board at once as a queued card, and is sent on the next sync.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/local_copy.dart';
import 'package:todo_implementer/sync/offline_relay.dart';

import '../support/fakes.dart';

const _offline = RelayFailed(code: 'offline', error: 'down', retry: true);

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  OfflineRelay restart(FakeRelay inner) =>
      OfflineRelay(inner, PrefsLocalCopy(prefs));

  Json task(String title) => {
    'args': {'repo': 'kuhyx/demo', 'title': title},
  };

  test('[T2604] an offline new task is kept, shown and sent later', () async {
    final offline = FakeRelay()..outcomes['new_task'] = _offline;
    final out = await restart(offline).send('new_task', task('buy milk'));
    expect(out, isA<RelayOk>());
    expect((out as RelayOk).data['queued'], isTrue);
    final back = FakeRelay();
    final relay = restart(back);
    final seen = <Board>[];
    final sub = relay.boards().listen(seen.add);
    back.push(boardJson([card('c1')]));
    await pumpEventQueue();
    final sent = [
      for (final s in back.sent)
        if (s.$1 == 'new_task') s.$2,
    ];
    expect(sent, [task('buy milk')]);
    back.push(boardJson([card('c1')]));
    await pumpEventQueue();
    await sub.cancel();
    final queued = seen.first.tasks.where((t) => t.status == 'unsent');
    expect(queued.single.title, 'buy milk');
    expect(seen.last.tasks.where((t) => t.status == 'unsent'), isEmpty);
    expect(back.sent.where((s) => s.$1 == 'new_task'), hasLength(1));
  });

  test('[T2604] a kept board shows the queued task with no network', () async {
    final offline = FakeRelay()..outcomes['task_send'] = _offline;
    final relay = restart(offline);
    await relay.send('new_task', task('a'));
    offline.outcomes['new_task'] = _offline;
    await relay.send('new_task', task('b'));
    expect(
      await relay.send('task_send', {
        'card': 'c1',
        'args': {'text': 'hi'},
      }),
      isA<RelayOk>(),
    );
    await prefs.setString('local.board', '{"tasks": []}');
    final shown = await restart(FakeRelay()).boards().first;
    expect(shown.tasks.map((t) => t.title), ['b']);
  });

  test('[T2604] a refusal or a timeout is never queued', () async {
    final inner = FakeRelay()
      ..outcomes['new_task'] = const RelayFailed(code: 'timeout', error: 't');
    final relay = restart(inner);
    expect(await relay.send('new_task', task('x')), isA<RelayFailed>());
    inner.outcomes['start'] = _offline;
    expect(await relay.send('start', {'card': 'c1'}), isA<RelayFailed>());
    expect(PrefsLocalCopy(prefs).outbox(), isEmpty);
  });

  test('[T2604] a send still offline stays queued, in order', () async {
    final inner = FakeRelay()..outcomes['new_task'] = _offline;
    final relay = restart(inner);
    await relay.send('new_task', task('one'));
    await relay.send('new_task', task('two'));
    final sub = relay.boards().listen((_) {});
    inner.push(boardJson(const []));
    await pumpEventQueue();
    expect(PrefsLocalCopy(prefs).outbox().map((q) => q['kind']), [
      'new_task',
      'new_task',
    ]);
    inner.outcomes['new_task'] = const RelayFailed(code: 'bad', error: 'no');
    inner.push(boardJson(const []));
    await pumpEventQueue();
    await sub.cancel();
    expect(PrefsLocalCopy(prefs).outbox(), isEmpty);
  });
}
