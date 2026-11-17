import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';

import '../support/fakes.dart';

const _db = 'https://db.example';

void main() {
  late Map<String, Object?> tree;
  late List<(String, String)> calls;
  late Map<String, StreamController<Object?>> watches;
  late StreamController<int> moves;
  var putFails = false;

  RtdbBoardRelay relay() => RtdbBoardRelay(
    client: RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: _db,
      idToken: () async => 'tok',
      httpClient: MockClient((req) async {
        final path = req.url.path.replaceAll('.json', '').substring(1);
        calls.add((req.method, path));
        if (req.method == 'PUT') {
          if (putFails) return http.Response('nope', 500);
          tree[path] = jsonDecode(req.body);
          return http.Response(req.body, 200);
        }
        return http.Response(jsonEncode(tree[path]), 200);
      }),
    ),
    dev: 'dev1',
    watch: (rid) => (watches[rid] = StreamController<Object?>()).stream,
    moves: () => moves.stream,
    clock: () => DateTime.fromMillisecondsSinceEpoch(1000),
  );

  setUp(() {
    tree = {};
    calls = [];
    watches = {};
    moves = StreamController<int>();
    putFails = false;
  });

  test('send writes a sealed-path req and returns the result', () async {
    final r = relay();
    final out = r.send('task_ship', {'card': 'c'});
    await pumpEventQueue();
    final rid = watches.keys.single;
    final req = tree[fullPath('requests/$rid/req')]! as Map<String, dynamic>;
    expect(req['kind'], 'task_ship');
    expect(req['dev'], 'dev1');
    expect(req['sent_at'], 1000);
    expect(req['created'], {'.sv': 'timestamp'});
    expect(req['body'], {'card': 'c'});
    watches[rid]!
      ..add(null)
      ..add({'claim': <String, dynamic>{}})
      ..add({
        'result': {
          'ok': true,
          'at': 1,
          'for': 'task_ship',
          'data': {'x': 1},
        },
      })
      ..add({
        'result': {'ok': false},
      });
    final ok = await out as RelayOk;
    expect(ok.data, {'x': 1});
  });

  test('a failed PUT is an offline outcome, never a hang', () async {
    putFails = true;
    final out = await relay().send('task_go', const {}) as RelayFailed;
    expect((out.code, out.retry), ('offline', true));
  });

  test('boards: refresh request, first snapshot, then each move', () async {
    tree[fullPath('snap/board')] = boardJson([card('a')]);
    final r = relay();
    final seen = <String>[];
    final sub = r.boards().listen((b) => seen.add(b.tasks.single.id));
    await pumpEventQueue();
    expect(calls.where((c) => c.$1 == 'PUT').single.$2, contains('requests'));
    expect(seen, ['a']);
    tree[fullPath('snap/board')] = boardJson([card('b')]);
    moves.add(1);
    await pumpEventQueue();
    tree.remove(fullPath('snap/board'));
    moves.add(2);
    await pumpEventQueue();
    expect(seen, ['a', 'b']);
    unawaited(sub.cancel());
  });

  test('no first snapshot: waits for the first move', () async {
    final r = relay();
    final seen = <String>[];
    final sub = r.boards().listen((b) => seen.add(b.build));
    await pumpEventQueue();
    expect(seen, isEmpty);
    unawaited(sub.cancel());
  });

  test('live wiring builds hub and rev watcher on one stream', () {
    final client = RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: _db,
      idToken: () async => 'tok',
      httpClient: MockClient((_) async => http.Response('null', 200)),
    );
    final r = RtdbBoardRelay.live(
      client: client,
      stream: RtdbStream(client),
      dev: 'd',
    );
    expect(r.dev, 'd');
    expect(r.watch('x'), isA<Stream<Object?>>());
    expect(r.moves(), isA<Stream<int>>());
  });

  test('outcomeOf maps ok and refusals', () {
    expect(outcomeOf({'ok': true}), isA<RelayOk>());
    final f = outcomeOf({
      'ok': false,
      'code': 'disabled',
      'error': 'e',
      'retry': true,
    }) as RelayFailed;
    expect((f.code, f.error, f.retry), ('disabled', 'e', true));
    final bare = outcomeOf(const {}) as RelayFailed;
    expect((bare.code, bare.retry), ('internal', false));
  });

  test('ulid: 26 Crockford chars, time-ordered', () {
    final a = ulid(
      now: DateTime.fromMillisecondsSinceEpoch(1),
      random: Random(1),
    );
    final b = ulid(now: DateTime.fromMillisecondsSinceEpoch(2));
    expect(a, hasLength(26));
    expect(a.compareTo(b), lessThan(0));
    expect(ulid(), matches(RegExp(r'^[0-9A-HJKMNP-TV-Z]{26}$')));
  });
}
