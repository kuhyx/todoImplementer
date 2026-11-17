/// Where the usage page is: a view, maybe an argument (a session key, a
/// context file path, a generic panel name), and the global filters that
/// travel with every `tokens` request (`web/src/usage/route.ts`, `api.ts`).
library;

import 'package:flutter/foundation.dart';

/// The usage views; the last three take an argument and have no tab.
enum UsageView {
  /// Spend over time.
  overview,

  /// Every session.
  sessions,

  /// Cost per todo item, repo and stage.
  items,

  /// Spend per finished session, commit, estimate, note.
  efficiency,

  /// Work that ran without kuhy (`snap/usage`).
  autonomy,

  /// Optimisation levers and their metrics.
  levers,

  /// Always-loaded context files.
  context,

  /// Spike days, expensive sessions, loops.
  anomalies,

  /// Sonnet against Opus.
  ab,

  /// Panels without a dedicated view.
  more,

  /// One session (`arg` = its key).
  session,

  /// One context file (`arg` = its path).
  file,

  /// One generic panel (`arg` = its name).
  panel,
}

/// The views that get a tab, in the web page's order.
const tabViews = <UsageView>[
  UsageView.overview,
  UsageView.sessions,
  UsageView.items,
  UsageView.efficiency,
  UsageView.autonomy,
  UsageView.levers,
  UsageView.context,
  UsageView.anomalies,
  UsageView.ab,
  UsageView.more,
];

/// One place on the usage page.
@immutable
class UsageRoute {
  /// Creates the route.
  const new(this.view, [this.arg = '']);

  /// The view.
  final UsageView view;

  /// Its argument, or empty.
  final String arg;

  /// The tab that lights up for this route.
  UsageView get tab => switch (view) {
    UsageView.session => UsageView.sessions,
    UsageView.file => UsageView.context,
    UsageView.panel => UsageView.more,
    _ => view,
  };

  @override
  bool operator ==(Object other) =>
      other is UsageRoute && other.view == view && other.arg == arg;

  @override
  int get hashCode => Object.hash(view, arg);
}

/// Session scope filter values.
const scopes = ['all', 'main', 'sub'];

/// The global filters, in the order the API documents them.
@immutable
class UsageFilters {
  /// Creates the filters; empty means "not set".
  const new({
    this.cwd = '',
    this.from = '',
    this.model = '',
    this.scope = 'all',
    this.to = '',
    this.window = '',
  });

  /// Working directory.
  final String cwd;

  /// First day, `YYYY-MM-DD`.
  final String from;

  /// Model name.
  final String model;

  /// `all`, `main` or `sub`.
  final String scope;

  /// Last day, `YYYY-MM-DD`.
  final String to;

  /// A snapshot window.
  final String window;

  /// Whether any filter narrows the data.
  bool get active => query().isNotEmpty;

  /// A copy with one field set by its API name.
  UsageFilters withField(String key, String value) => UsageFilters(
    cwd: key == 'cwd' ? value : cwd,
    from: key == 'from' ? value : from,
    model: key == 'model' ? value : model,
    scope: key == 'scope' ? value : scope,
    to: key == 'to' ? value : to,
    window: key == 'window' ? value : window,
  );

  /// The filters as API query pairs (unset ones and scope `all` dropped).
  Map<String, String> query() => {
    if (cwd.isNotEmpty) 'cwd': cwd,
    if (from.isNotEmpty) 'from': from,
    if (model.isNotEmpty) 'model': model,
    if (scope.isNotEmpty && scope != 'all') 'scope': scope,
    if (to.isNotEmpty) 'to': to,
    if (window.isNotEmpty) 'window': window,
  };

  /// The query string for a panel, asking every one of [tables] in full
  /// (`t.<table>.limit=0`): sort and filter run in the app.
  String panelQuery([List<String> tables = const []]) => Uri(
    queryParameters: {...query(), for (final t in tables) 't.$t.limit': '0'},
  ).query;

  @override
  bool operator ==(Object other) =>
      other is UsageFilters && other.panelQuery() == panelQuery();

  @override
  int get hashCode => panelQuery().hashCode;
}
