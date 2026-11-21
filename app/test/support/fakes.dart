import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';

/// One action JSON.
Json action(
  String id, {
  bool enabled = true,
  bool confirm = false,
  String? value,
  Json? option,
}) => {
  'id': id,
  'label': id,
  'enabled': enabled,
  'reason': enabled ? null : 'why $id',
  'confirm': confirm,
  'value': ?value,
  'option': ?option,
};

/// One card JSON.
Json card(
  String id, {
  String column = 'backlog',
  String status = 'backlog',
  String? repo = 'kuhyx/demo',
  String priority = 'normal',
  List<Json> actions = const [],
  Json? needs,
  double cost = 0,
  int? updated,
  String? route,
  String title = '',
  bool tiers = false,
}) => {
  'id': id,
  'title': title.isEmpty ? 'Title $id' : title,
  'repo': repo,
  'priority': priority,
  'assignee': 'claude',
  'stage': null,
  'status': status,
  'column': column,
  'current': 'doing $id',
  'needs': needs,
  'partial': null,
  'cost_usd': cost,
  'route': route,
  'tier': {'cheap': tiers, 'free': tiers, 'escalated': tiers},
  'resumes_at': null,
  'updated': updated,
  'actions': actions,
  'auto_start': null,
  'auto': null,
};

/// A board JSON around [tasks].
Json boardJson(List<Json> tasks, {Json extra = const {}}) => {
  'build': 'b1',
  'generated_at': 1,
  'slots': {'used': 2},
  'limit': {
    'active': false,
    'until': null,
    'credits': {'enabled': false, 'state': 'off', 'text': 'off'},
  },
  'auto_close': false,
  'columns': [
    for (final c in columnIds)
      {
        'id': c,
        'label': c,
        'count': tasks.where((t) => t['column'] == c).length,
      },
  ],
  'repos': ['kuhyx/demo', 'kuhyx/other'],
  'tasks': tasks,
  ...extra,
};

/// A relay the test drives: push boards, script outcomes, read requests.
class FakeRelay implements BoardRelay {
  /// The board stream.
  final boardsOut = StreamController<Board>.broadcast();

  /// Requests sent, in order.
  final List<(String, Json)> sent = [];

  /// Outcome per kind (default ok with empty data).
  final Map<String, RelayOutcome> outcomes = {};

  /// When set, sends wait for it.
  Completer<void>? gate;

  @override
  Stream<Board> boards() => boardsOut.stream;

  /// Publishes [json] as the next board.
  void push(Json json) => boardsOut.add(Board.fromJson(json));

  @override
  Future<RelayOutcome> send(String kind, Json body, {Duration? timeout}) async {
    sent.add((kind, body));
    final wait = gate?.future;
    if (wait != null && timeout != null) {
      try {
        await wait.timeout(timeout);
      } on TimeoutException {
        return RelayFailed(code: 'timeout', error: 'no $kind', retry: true);
      }
    }
    await wait;
    if (kind == 'image_upload' && !outcomes.containsKey(kind)) {
      return RelayOk({
        'upload': {'id': 'up-${body['data_b64']}'},
      });
    }
    return outcomes[kind] ?? const RelayOk({});
  }

  /// The merges stream.
  final mergesOut = StreamController<List<MergeSuggestion>>.broadcast();

  @override
  Stream<List<MergeSuggestion>> merges() => mergesOut.stream;

  /// Live feeds handed out, per card.
  final Map<String, StreamController<List<Json>>> feeds = {};

  @override
  Stream<List<Json>> liveFeed(String card) =>
      (feeds[card] = StreamController<List<Json>>.broadcast()).stream;
}

/// One merge suggestion JSON.
Json mergeJson(String id, {bool mergeEnabled = true}) => {
  'id': id,
  'title': 'Combined $id',
  'reason': 'alike',
  'members': [
    {'id': 'a1', 'title': 'One', 'repo': 'kuhyx/demo'},
    {'id': 'b2', 'title': 'Two', 'repo': 'kuhyx/demo'},
  ],
  'actions': [
    {
      'id': 'merge',
      'label': 'Merge',
      'enabled': mergeEnabled,
      'reason': mergeEnabled ? null : 'a member runs',
    },
    {'id': 'dismiss', 'label': 'Dismiss', 'enabled': true, 'reason': null},
  ],
};

/// Pixel 6a geometry in physical px (build-mobile-app R7).
void pixel6a(WidgetTester tester, {double keyboard = 0}) {
  tester.view
    ..physicalSize = const Size(1080, 2400)
    ..devicePixelRatio = 2.625
    ..padding = const FakeViewPadding(top: 132, bottom: 63)
    ..viewInsets = FakeViewPadding(bottom: keyboard);
  addTearDown(tester.view.reset);
}

/// Asserts no vertical scrollable can scroll.
void expectNoVerticalScroll(WidgetTester tester) {
  for (final state in tester.stateList<ScrollableState>(
    find.byType(Scrollable),
  )) {
    if (state.position.axis == Axis.vertical) {
      expect(state.position.maxScrollExtent, 0);
    }
  }
}
