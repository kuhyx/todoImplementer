// T2353: every open of a card's logs started from nothing (a spinner, then
// the whole feed again); the last feed now shows at once, also after an app
// restart (the newest kFeedKeep events are saved on close).
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/feed_cache.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';

void main() {
  late StreamController<RtdbEvent> events;

  RtdbBoardRelay relay(FeedCache feeds) => RtdbBoardRelay(
    client: RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: 'https://db.example',
      idToken: () async => 'tok',
      httpClient: MockClient((_) async => http.Response('null', 200)),
    ),
    dev: 'dev1',
    watch: (_) => const Stream.empty(),
    moves: () => const Stream.empty(),
    listen: (_) => events.stream,
    feeds: feeds,
  );

  Json line(int n) => {'type': 'activity', 'text': 'l$n', 'seq': n};

  Future<List<List<Json>>> openFeed(
    RtdbBoardRelay r, {
    List<Json>? push,
  }) async {
    events = StreamController<RtdbEvent>();
    final got = <List<Json>>[];
    final sub = r.liveFeed('c1').listen(got.add);
    await pumpEventQueue();
    if (push != null) {
      events.add(
        RtdbPut('/', {
          for (final e in push) 's${'${e['seq']}'.padLeft(9, '0')}': e,
        }),
      );
      await pumpEventQueue();
    }
    await sub.cancel();
    await pumpEventQueue();
    return got;
  }

  test(
    '[T2353] a reopened feed shows the last lines before any read',
    () async {
      final r = relay(MemoryFeedCache());
      await openFeed(r, push: [line(1), line(2)]);
      final again = await openFeed(r);
      expect(again.single.map((e) => e['text']), ['l1', 'l2']);
    },
  );

  test('[T2353] the newest lines survive an app restart', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await openFeed(
      relay(PrefsFeedCache(prefs)),
      push: [for (var n = 1; n <= kFeedKeep + 10; n++) line(n)],
    );
    final fresh = PrefsFeedCache(await SharedPreferences.getInstance());
    final shown = (await openFeed(relay(fresh))).single;
    expect(shown.length, kFeedKeep);
    expect(shown.last['text'], 'l${kFeedKeep + 10}');
    expect(PrefsFeedCache(prefs).read('other'), isNull);
  });
}
