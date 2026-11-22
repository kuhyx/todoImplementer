/// The sessions page (web `sessions/app.ts`): the live `snap/sessions`
/// node as a grid that never scrolls vertically (overflow pages sideways,
/// R7), the toolbar, and the bulk bar while sessions are selected. Every
/// request goes through the relay's session kinds; a success asks the
/// worker to republish so the change shows at once.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/model/sessions_view.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';
import 'package:todo_implementer/ui/sessions/bulk_bar.dart';
import 'package:todo_implementer/ui/sessions/session_glyphs.dart';
import 'package:todo_implementer/ui/sessions/session_sheet.dart';
import 'package:todo_implementer/ui/sessions/session_tile.dart';
import 'package:todo_implementer/ui/sessions/sessions_toolbar.dart';

/// Sessions page fed by [feed]; requests go through [relay].
class SessionsPage extends StatefulWidget {
  /// Creates the page; [clock] is for tests.
  const new({
    required this.feed,
    required this.relay,
    this.clock = DateTime.now,
    super.key,
  });

  /// The `snap/sessions` stream.
  final SessionsFeed feed;

  /// Sends the session kinds.
  final BoardRelay relay;

  /// The time idle ages are measured against.
  final DateTime Function() clock;

  @override
  State<SessionsPage> createState() => _SessionsPageState();
}

class _SessionsPageState extends State<SessionsPage> {
  late final Stream<SessionList> _lists = widget.feed();
  SessionQuery _query = const SessionQuery();
  Set<String> _selected = {};
  bool _busy = false;
  SessionOutcome? _bulk;
  final List<SessionOutcome> _errors = [];

  Future<SessionOutcome> _perform(
    SessionVerb verb,
    List<String> ids, {
    bool unmark = false,
  }) async {
    final out = sessionOutcome(
      await widget.relay.send(
        verb.kind,
        sessionBody(verb, ids, unmark: unmark),
      ),
    );
    if (!mounted) return out;
    setState(() {
      if (out.kind != OutcomeKind.ok) _errors.add(out);
    });
    if (out.kind == OutcomeKind.ok && verb != SessionVerb.resume) {
      unawaited(widget.relay.send('snapshot_refresh', const {}));
    }
    return out;
  }

  Future<void> _runBulk(
    SessionVerb verb,
    List<String> ids, {
    bool unmark = false,
  }) async {
    setState(() {
      _busy = true;
      _bulk = null;
    });
    final out = await _perform(verb, ids, unmark: unmark);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _bulk = out;
      if (out.kind == OutcomeKind.ok && verb != SessionVerb.resume) {
        _selected = {};
      }
    });
  }

  void _toggle(String id) => setState(() {
    _selected = _selected.contains(id)
        ? ({..._selected}..remove(id))
        : {..._selected, id};
  });

  void _open(Session s) => showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => SessionSheet(session: s, perform: _perform),
  );

  @override
  Widget build(BuildContext context) => StreamBuilder<SessionList>(
    stream: _lists,
    builder: (context, snap) {
      final list = snap.data;
      if (list == null) {
        return Center(
          child: CircularProgressIndicator(semanticsLabel: spoken['wait']),
        );
      }
      final now = widget.clock();
      final items = visibleSessions(list.sessions, _query, now);
      final listed = {for (final s in list.sessions) s.id};
      final ids = [
        for (final s in items)
          if (_selected.contains(s.id) && listed.contains(s.id)) s.id,
      ];
      final showBulk = ids.isNotEmpty || _bulk != null;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        child: Column(
          children: [
            SessionsToolbar(
              all: list.sessions,
              query: _query,
              shown: items.length,
              onChanged: (q) => setState(() => _query = q),
            ),
            if (_errors.isNotEmpty) _errorRow(),
            if (showBulk)
              BulkBar(
                ids: ids,
                commands: [
                  for (final s in items)
                    if (ids.contains(s.id)) s.resumeCommand,
                ].join('\n'),
                busy: _busy,
                moveBlock: _moveBlock(items, ids),
                outcome: _bulk,
                onRun: (verb, {unmark = false}) =>
                    unawaited(_runBulk(verb, ids, unmark: unmark)),
                onSelectAll: () => setState(() {
                  final all = {for (final s in items) s.id};
                  _selected = _selected.containsAll(all) ? {} : all;
                }),
                onClear: () => setState(() {
                  _selected = {};
                  _bulk = null;
                }),
              ),
            const SizedBox(height: AppSpacing.xs),
            Expanded(
              child: items.isEmpty
                  ? const Center(
                      child: Icon(
                        Icons.terminal,
                        key: Key('sessions-empty'),
                        size: AppSpacing.xxl * 2,
                        color: AppPalette.lineDark,
                      ),
                    )
                  : FitGrid(
                      key: const Key('sessions-grid'),
                      itemCount: items.length,
                      columns: MediaQuery.sizeOf(context).width < 600 ? 2 : 4,
                      minSquare: 0.55,
                      itemBuilder: (_, i) => SessionTile(
                        key: ValueKey('session-${items[i].id}'),
                        session: items[i],
                        age: ageLabel(items[i], now),
                        selected: _selected.contains(items[i].id),
                        onOpen: () => _open(items[i]),
                        onSelect: () => _toggle(items[i].id),
                      ),
                    ),
            ),
          ],
        ),
      );
    },
  );

  /// The server's reason the first selected session cannot move, if any.
  String? _moveBlock(List<Session> items, List<String> ids) {
    for (final s in items) {
      if (ids.contains(s.id) && !s.movable) return s.moveReason;
    }
    return null;
  }

  Widget _errorRow() {
    final last = _errors.last;
    return Row(
      children: [
        outcomeGlyph(last, key: const Key('sessions-failure')),
        Semantics(
          label: spoken['errors'],
          button: true,
          excludeSemantics: true,
          child: IconButton(
            key: const Key('sessions-copy-errors'),
            tooltip: 'errors',
            onPressed: () => Clipboard.setData(
              ClipboardData(text: _errors.map((e) => e.summary).join('\n')),
            ),
            icon: Badge.count(
              count: _errors.length,
              child: const Icon(Icons.copy_all),
            ),
          ),
        ),
      ],
    );
  }
}
