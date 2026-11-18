import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';

import '../support/session_fakes.dart';

void main() {
  test('the feed reads snap/sessions now and on every rev move', () async {
    final tree = <String, Object?>{};
    final moves = StreamController<int>.broadcast();
    final client = RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: 'https://db.example',
      idToken: () async => 'tok',
      httpClient: MockClient(
        (req) async => http.Response(
          jsonEncode(tree[req.url.path.replaceAll('.json', '').substring(1)]),
          200,
        ),
      ),
    );
    final path = fullPath('snap/sessions');
    tree[path] = listJson([sessionJson(title: 'one')]);
    final got = <String>[];
    final sub = rtdbSessionsFeed(
      client: client,
      moves: moves.stream,
    )().listen((l) => got.add(l.sessions.map((s) => s.title).join()));
    await pumpEventQueue();
    tree[path] = null; // a gap: nothing published yet reads as no list
    moves.add(1);
    await pumpEventQueue();
    tree[path] = listJson([sessionJson(title: 'two')]);
    moves.add(2);
    await pumpEventQueue();
    expect(got, ['one', 'two']);
    unawaited(sub.cancel());

    tree[path] = null;
    final empty = await rtdbSessionsFeed(
      client: client,
      moves: const Stream<int>.empty(),
    )().toList();
    expect(empty, isEmpty);
  });

  test('bodies: one id or many, mark done or null, kinds', () {
    expect(sessionBody(SessionVerb.resume, ['a']), {
      'args': {'id': 'a'},
    });
    expect(sessionBody(SessionVerb.mark, ['a', 'b']), {
      'args': {
        'ids': ['a', 'b'],
        'mark': 'done',
      },
    });
    expect(sessionBody(SessionVerb.mark, ['a'], unmark: true), {
      'args': {'id': 'a', 'mark': null},
    });
    expect(SessionVerb.delete.kind, 'session_delete');
    expect(SessionVerb.handoff.kind, 'session_handoff');
    expect(sessionBody(SessionVerb.handoff, ['a', 'b']), {
      'args': {
        'ids': ['a', 'b'],
      },
    });
  });

  test('outcomes: ok, refused, failed and a relay failure', () {
    expect(sessionOutcome(const RelayOk({'ok': true, 'summary': 'marked 1'})), (
      kind: OutcomeKind.ok,
      summary: 'marked 1',
    ));
    expect(
      sessionOutcome(
        const RelayOk({'ok': false, 'refused': true, 'summary': 'too new'}),
      ),
      (kind: OutcomeKind.refused, summary: 'too new'),
    );
    expect(
      sessionOutcome(
        const RelayOk({'ok': false, 'summary': 'x', 'stderr': 'boom'}),
      ),
      (kind: OutcomeKind.failed, summary: 'x\nboom'),
    );
    expect(sessionOutcome(const RelayFailed(code: 'offline', error: 'net')), (
      kind: OutcomeKind.failed,
      summary: 'offline: net',
    ));
  });
}
