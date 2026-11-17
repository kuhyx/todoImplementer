/// The board page: the live `snap/board` from the relay, drawn as status
/// strip, toolbar, column tabs and a card grid that never scrolls vertically
/// (overflow pages sideways, R7). Tapping a card opens its sheet.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_grid.dart';
import 'package:todo_implementer/ui/board/board_header.dart';
import 'package:todo_implementer/ui/board/card_sheet.dart';
import 'package:todo_implementer/ui/board/detail_page.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';
import 'package:todo_implementer/ui/board/merge_strip.dart';
import 'package:todo_implementer/ui/board/new_task_sheet.dart';

/// Board page fed by [relay].
class BoardPage extends StatefulWidget {
  /// Creates the page.
  const new({required this.relay, super.key});

  /// The link to the PC.
  final BoardRelay relay;

  @override
  State<BoardPage> createState() => _BoardPageState();
}

class _BoardPageState extends State<BoardPage> {
  late final Stream<Board> _boards = widget.relay.boards();
  ViewState _state = const ViewState();
  final List<RelayFailed> _errors = [];
  RelayFailed? _last;

  void _record(RelayFailed f) => setState(() {
    _errors.add(f);
    _last = f;
  });

  Future<void> _global(String kind, Map<String, dynamic> body) async {
    final out = await widget.relay.send(kind, body);
    if (out is RelayFailed) _record(out);
  }

  Future<void> _copyErrors() => Clipboard.setData(
    ClipboardData(text: _errors.map((e) => '${e.code}: ${e.error}').join('\n')),
  );

  void _detail(BuildContext sheet, TaskCard card) {
    Navigator.of(sheet).pop();
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            DetailPage(card: card.id, relay: widget.relay, onError: _record),
      ),
    );
  }

  void _open(TaskCard card) => unawaited(
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheet) => CardSheet(
        card: card,
        relay: widget.relay,
        onError: _record,
        onDetail: () => _detail(sheet, card),
      ),
    ),
  );

  void _newTask(Board board) => unawaited(
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => NewTaskSheet(
        repos: board.repos,
        relay: widget.relay,
        onError: _record,
        repo: _state.repo.isEmpty || _state.repo == yours ? null : _state.repo,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => StreamBuilder<Board>(
    stream: _boards,
    builder: (context, snap) {
      final board = snap.data;
      if (board == null) {
        return const Center(
          child: CircularProgressIndicator(
            semanticsLabel: 'Waiting for the PC',
          ),
        );
      }
      final view = buildView(board, _state);
      final active = activeColumn(view, _state);
      final cards = view.firstWhere((v) => v.column.id == active).cards;
      final last = _last;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        child: Column(
          children: [
            StatusStrip(
              board: board,
              errors: _errors.length,
              onCredits: (on) => _global('credits_fallback', {
                'args': {'enabled': on},
              }),
              onRefresh: () => _global('snapshot_refresh', const {}),
              onCopyErrors: _copyErrors,
            ),
            if (last != null)
              Icon(
                codeIcon(last.code),
                key: const Key('board-failure'),
                color: AppPalette.danger,
                semanticLabel: last.error,
              ),
            MergeStrip(relay: widget.relay, onError: _record),
            Toolbar(
              board: board,
              state: _state,
              onChanged: (s) => setState(() => _state = s),
              onNewTask: () => _newTask(board),
            ),
            ColumnTabs(
              view: view,
              active: active,
              onPick: (c) =>
                  setState(() => _state = _state.copyWith(column: c)),
            ),
            Expanded(
              child: cards.isEmpty
                  ? Center(
                      child: Icon(
                        columnIcon(active),
                        key: const Key('empty-column'),
                        size: AppSpacing.xxl * 2,
                        color: AppPalette.lineDark,
                      ),
                    )
                  : BoardGrid(
                      key: ValueKey('grid-$active'),
                      groups: groupCards(cards, _state.sort),
                      onOpen: _open,
                    ),
            ),
          ],
        ),
      );
    },
  );
}
