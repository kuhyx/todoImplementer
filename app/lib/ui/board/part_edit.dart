/// Edit a repo part's own title and text from the card sheet before the run
/// reaches it (856c0f0a). The server decides which parts are editable
/// (`parts[].edit`); a locked pencil wears the block badge and speaks its
/// reason. The text comes from `task_detail`, the save goes out as
/// `task_part_edit`, and the new title shows on the tap.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/detail_page.dart'
    show kDetailPatience;
import 'package:todo_implementer/ui/board/glyphs.dart';

/// The parts of [card], each with its pencil, and the one open editor.
class PartEdits extends StatefulWidget {
  /// Creates the list.
  const new({
    required this.card,
    required this.relay,
    required this.onError,
    super.key,
  });

  /// A repo card (its [TaskCard.parts] are drawn).
  final TaskCard card;

  /// Where the detail read and the save go.
  final BoardRelay relay;

  /// Records a failure for the copy-errors action.
  final void Function(RelayFailed failure) onError;

  @override
  State<PartEdits> createState() => _PartEditsState();
}

class _PartEditsState extends State<PartEdits> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  final _shown =
      <String, String>{}; // titles saved here, before the board says so
  String? _open;
  String? _busy;
  RelayFailed? _failure;

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  void _fail(RelayFailed out) {
    widget.onError(out);
    setState(() => _failure = out);
  }

  Future<void> _edit(RepoPart p) async {
    setState(() {
      _busy = p.id;
      _failure = null;
    });
    final out = await widget.relay.send('task_detail', {
      'card': widget.card.id,
    }, timeout: kDetailPatience);
    if (!mounted) return;
    setState(() => _busy = null);
    if (out is RelayFailed) return _fail(out);
    _title.text = _shown[p.id] ?? p.titleSource ?? p.title;
    _body.text = partBodies((out as RelayOk).data)[p.id] ?? '';
    setState(() => _open = p.id);
  }

  Future<void> _save(RepoPart p) async {
    final title = _title.text.trim();
    if (title.isEmpty) return await HapticFeedback.heavyImpact();
    setState(() {
      _busy = p.id;
      _failure = null;
      _shown[p.id] = title;
    });
    final out = await widget.relay.send('task_part_edit', {
      'card': widget.card.id,
      'args': {'part': p.id, 'title': title, 'body': _body.text},
    });
    if (!mounted) return;
    setState(() => _busy = null);
    if (out is RelayFailed) {
      _shown.remove(p.id);
      return _fail(out);
    }
    setState(() => _open = null);
  }

  /// The saved title shows until the board carries it; then the server's
  /// own title, which drops image markdown (T2614, T2619).
  String _label(RepoPart p) {
    final saved = _shown[p.id];
    return saved == null || saved == (p.titleSource ?? p.title)
        ? p.title
        : saved;
  }

  Widget _pencil(RepoPart p) {
    if (_busy == p.id) {
      return const SizedBox.square(
        dimension: AppSpacing.md + AppSpacing.xs,
        child: CircularProgressIndicator(strokeWidth: 2),
      );
    }
    final button = IconButton(
      key: ValueKey('part-edit-${p.id}'),
      tooltip: 'edit',
      icon: const Icon(Icons.edit_outlined),
      onPressed: p.editable && _busy == null ? () => _edit(p) : null,
    );
    return Semantics(
      label: ['Edit ${p.title}', ?p.reason].join(': '),
      button: true,
      enabled: p.editable,
      excludeSemantics: true,
      child: p.editable
          ? button
          : Badge(
              backgroundColor: AppPalette.danger,
              label: const Icon(Icons.block, size: AppSpacing.sm + 2),
              child: button,
            ),
    );
  }

  Widget _editor(RepoPart p) {
    final free = _busy == null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: ValueKey('part-title-${p.id}'),
          controller: _title,
          enabled: free,
          maxLength: 200,
          decoration: const InputDecoration(prefixIcon: Icon(Icons.title)),
        ),
        TextField(
          key: ValueKey('part-body-${p.id}'),
          controller: _body,
          enabled: free,
          minLines: 3,
          maxLines: 10,
          decoration: const InputDecoration(prefixIcon: Icon(Icons.notes)),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            IconButton(
              key: ValueKey('part-cancel-${p.id}'),
              tooltip: 'cancel',
              icon: const Icon(Icons.close, semanticLabel: 'Cancel'),
              onPressed: free ? () => setState(() => _open = null) : null,
            ),
            IconButton.filledTonal(
              key: ValueKey('part-save-${p.id}'),
              tooltip: 'save',
              icon: const Icon(Icons.check, semanticLabel: 'Save'),
              onPressed: free ? () => _save(p) : null,
            ),
          ],
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final failure = _failure;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final p in widget.card.parts) ...[
          Row(
            children: [
              Expanded(
                child: Text(_label(p), key: ValueKey('part-name-${p.id}')),
              ),
              _pencil(p),
            ],
          ),
          if (_open == p.id) _editor(p),
        ],
        if (failure != null)
          Icon(
            codeIcon(failure.code),
            key: const Key('part-failure'),
            color: AppPalette.danger,
            semanticLabel: failure.error,
          ),
      ],
    );
  }
}
