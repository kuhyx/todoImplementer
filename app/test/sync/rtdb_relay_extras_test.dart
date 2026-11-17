import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';

import '../support/fakes.dart';

void main() {
  late Map<String, Object?> tree;
  late Map<String, StreamController<Object?>> watches;
  late StreamController<int> revs;
  late StreamController<RtdbEvent> events;
  late List<String> listened;

  RtdbBoardRelay relay({bool seams = true}) => RtdbBoardRelay(
    client: RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: 'https://db.example',
      idToken: () async => 'tok',
      httpClient: MockClient((req) async {
        final path = req.url.path.replaceAll('.json', '').substring(1);
        if (req.method == 'PUT') {
          tree[path] = jsonDecode(req.body);
          return http.Response(req.body, 200);
        }
        return http.Response(jsonEncode(tree[path]), 200);
      }),
    ),
    dev: 'dev1',
    watch: (rid) => (watches[rid] = StreamController<Object?>()).stream,
    moves: () => const Stream.empty(),
    revOf: seams
        ? (key) => key == 'merges' ? revs.stream : const Stream.empty()
        : null,
    listen: seams
        ? (path) {
            listened.add(path);
            return events.stream;
          }
        : null,
  );

  List<String> sentKinds() => [
    for (final e in tree.entries)
      if (e.key.endsWith('/req')) (e.value! as Map)['kind'] as String,
  ];

  setUp(() {
    tree = {};
    watches = {};
    revs = StreamController<int>();
    events = StreamController<RtdbEvent>();
    listened = [];
  });

  test('merges: first snapshot, then each rev move', () async {
    tree[fullPath('snap/merges')] = {
      'suggestions': [mergeJson('aaaaaaaaaaaa')],
    };
    final seen = <int>[];
    final sub = relay().merges().listen((m) => seen.add(m.length));
    await pumpEventQueue();
    tree.remove(fullPath('snap/merges'));
    revs.add(1);
    await pumpEventQueue();
    expect(seen, [1, 0]);
    unawaited(sub.cancel());
  });

  test('default seams: merges once, live feed silent', () async {
    final r = relay(seams: false);
    expect(await r.merges().toList(), [isEmpty]);
    final feed = <List<Object?>>[];
    final sub = r.liveFeed('c1').listen(feed.add);
    await pumpEventQueue();
    expect(feed, isEmpty);
    await sub.cancel();
  });

  test('liveFeed watches, applies puts and patches, releases', () async {
    final r = relay();
    final feeds = <List<Map<String, dynamic>>>[];
    final sub = r.liveFeed('c1').listen(feeds.add);
    await pumpEventQueue();
    expect(listened, [fullPath('live/c1')]);
    events
      ..add(
        const RtdbPut('/', {
          's000000002': {'type': 'activity', 'text': 'b'},
          's000000001': {'type': 'activity', 'text': 'a'},
        }),
      )
      ..add(const RtdbConnected())
      ..add(
        const RtdbPatch('/', {
          's000000003': {'type': 'stage', 'stage': 'implement'},
        }),
      );
    await pumpEventQueue();
    expect(feeds.length, 2);
    expect(feeds.last.map((e) => e['text'] ?? e['stage']), [
      'a',
      'b',
      'implement',
    ]);
    await sub.cancel();
    await pumpEventQueue();
    expect(sentKinds(), ['live_watch', 'live_watch']);
  });

  test('feedOf ignores non-maps and non-object children', () {
    expect(feedOf(null), isEmpty);
    expect(
      feedOf({
        's1': 3,
        's0': {'type': 'x'},
      }),
      [
        {'type': 'x'},
      ],
    );
  });
}
