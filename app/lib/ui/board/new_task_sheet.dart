/// The new-task sheet: kuhy's own task for a repo (repo, title, details),
/// sent as `new_task`. The fields are icon-labelled (textgate); the send
/// button is enabled only when the server would accept the request.
/// Pictures are not offered yet (they need a JPEG encoder dependency).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

final _repoPattern = RegExp(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$');

/// True when [repo] and [title] pass `requests.schema.json#/$defs/new_task`.
bool newTaskValid(String repo, String title) =>
    _repoPattern.hasMatch(repo.trim()) &&
    title.trim().isNotEmpty &&
    title.trim().length <= 200 &&
    !title.contains('\n');

/// The sheet body.
class NewTaskSheet extends StatefulWidget {
  /// Creates the sheet.
  const new({
    required this.repos,
    required this.relay,
    required this.onError,
    this.repo,
    super.key,
  });

  /// Repo suggestions (the board's repos).
  final List<String> repos;

  /// Where the request goes.
  final BoardRelay relay;

  /// Records a refusal.
  final void Function(RelayFailed failure) onError;

  /// Preselected repo (the repo filter), if any.
  final String? repo;

  @override
  State<NewTaskSheet> createState() => _NewTaskSheetState();
}

class _NewTaskSheetState extends State<NewTaskSheet> {
  TextEditingController? _repo;
  final _title = TextEditingController();
  final _body = TextEditingController();
  bool _busy = false;
  RelayFailed? _failure;

  String get _repoText => _repo?.text ?? widget.repo ?? '';

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _failure = null;
    });
    final out = await widget.relay.send('new_task', {
      'args': {
        'repo': _repoText.trim(),
        'title': _title.text.trim(),
        if (_body.text.trim().isNotEmpty) 'body': _body.text,
      },
    });
    if (!mounted) return;
    if (out is RelayFailed) {
      widget.onError(out);
      setState(() {
        _busy = false;
        _failure = out;
      });
      return;
    }
    await Navigator.of(context).maybePop();
  }

  InputDecoration _icon(IconData icon, String spoken) => InputDecoration(
    prefixIcon: Icon(icon, semanticLabel: spoken),
    isDense: true,
  );

  @override
  Widget build(BuildContext context) {
    final ok = newTaskValid(_repoText, _title.text) && !_busy;
    final failure = _failure;
    void changed(String _) => setState(() {});
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Autocomplete<String>(
            initialValue: TextEditingValue(text: widget.repo ?? ''),
            optionsBuilder: (v) => widget.repos.where(
              (r) => r.toLowerCase().contains(v.text.toLowerCase()),
            ),
            onSelected: changed,
            fieldViewBuilder: (_, controller, focus, _) {
              _repo = controller;
              return TextField(
                key: const Key('nt-repo'),
                controller: controller,
                focusNode: focus,
                onChanged: changed,
                decoration: _icon(Icons.folder_outlined, 'Repo'),
              );
            },
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            key: const Key('nt-title'),
            controller: _title,
            onChanged: changed,
            decoration: _icon(Icons.title, 'Title'),
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            key: const Key('nt-body'),
            controller: _body,
            minLines: 4,
            maxLines: 4,
            decoration: _icon(Icons.notes, 'Details'),
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (failure != null)
                Icon(
                  codeIcon(failure.code),
                  key: const Key('nt-failure'),
                  color: AppPalette.danger,
                  semanticLabel: failure.error,
                ),
              IconButton.filled(
                key: const Key('nt-send'),
                onPressed: ok ? _submit : null,
                icon: _busy
                    ? const SizedBox.square(
                        dimension: AppSpacing.md,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add_task, semanticLabel: 'Add'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
