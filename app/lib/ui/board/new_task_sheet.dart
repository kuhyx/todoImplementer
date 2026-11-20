/// The add-task page (full screen, T2349): where it goes ([RepoChooser]:
/// none, all or some repos, folded once picked, T2351), one text box whose
/// first line is the title (no title field, T2350), and one row with the
/// image buttons, the attached images and the send button (T2352). Sent as
/// `new_task`: one per repo, or one with no repo for none. The box takes
/// images (T2334): `[Image #N]` tags in the text, the bytes in `images`.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';
import 'package:todo_implementer/ui/board/repo_chooser.dart';

/// The schema's title cap.
const kMaxTitle = 200;

/// (title, body): the first non-blank line, cut to [kMaxTitle], and the
/// lines after it; a cut line keeps the whole text as the body.
(String, String) splitNote(String text) {
  final lines = text.trim().split('\n');
  final first = lines.first.trim();
  if (first.length > kMaxTitle) {
    return (first.substring(0, kMaxTitle).trim(), text.trim());
  }
  return (first, lines.skip(1).join('\n').trim());
}

/// True when [text] gives a title `new_task` accepts.
bool newTaskValid(String text) => splitNote(text).$1.isNotEmpty;

/// The page body.
class NewTaskSheet extends StatefulWidget {
  /// Creates the page.
  const new({
    required this.repos,
    required this.relay,
    required this.onError,
    this.repo,
    super.key,
  });

  /// The board's repos (the chooser's chips and "all").
  final List<String> repos;

  /// Where the requests go.
  final BoardRelay relay;

  /// Records a refusal.
  final void Function(RelayFailed failure) onError;

  /// Preselected repo (the board's repo filter): counts as picked.
  final String? repo;

  @override
  State<NewTaskSheet> createState() => _NewTaskSheetState();
}

class _NewTaskSheetState extends State<NewTaskSheet> {
  final _body = TextEditingController();
  late final _images = ImageAttach(_body);
  late RepoScope? _scope = widget.repo == null ? null : RepoScope.some;
  late final Set<String> _picked = {?widget.repo};
  late bool _open = widget.repo == null;
  bool _busy = false;
  RelayFailed? _failure;

  @override
  void dispose() {
    _images.dispose();
    _body.dispose();
    super.dispose();
  }

  // The repos still to send to; [null] means one repo-less note.
  List<String?> _targets() => switch (_scope) {
    RepoScope.none => const [null],
    RepoScope.all => [...widget.repos],
    RepoScope.some => [..._picked],
    null => const [],
  };

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _failure = null;
    });
    final (title, body) = splitNote(_body.text);
    final images = _images.refs;
    for (final repo in _targets()) {
      final out = await widget.relay.send('new_task', {
        'args': {
          'repo': ?repo,
          'title': title,
          if (body.isNotEmpty) 'body': body,
          if (images.isNotEmpty) 'images': images,
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
      // Sent: a retry after a later refusal must not send it twice.
      if (repo != null) {
        setState(() {
          if (_scope == RepoScope.all) _picked.addAll(widget.repos);
          _scope = RepoScope.some;
          _picked.remove(repo);
        });
      }
    }
    await Navigator.of(context).maybePop();
  }

  Widget _send(bool ok) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      if (_failure case final failure?)
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
  );

  @override
  Widget build(BuildContext context) {
    final ok = newTaskValid(_body.text) && _targets().isNotEmpty && !_busy;
    return Scaffold(
      appBar: AppBar(
        leading: const CloseButton(),
        toolbarHeight: AppSpacing.xl + AppSpacing.md,
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          0,
          AppSpacing.md,
          AppSpacing.sm,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            RepoChooser(
              repos: widget.repos,
              open: _open,
              scope: _scope,
              picked: _picked,
              onScope: (s) => setState(() {
                _scope = s;
                _open = false;
              }),
              onToggle: (r) => setState(() {
                if (_scope != RepoScope.some) _picked.clear();
                _scope = RepoScope.some;
                if (!_picked.remove(r)) _picked.add(r);
              }),
              onFold: () => setState(() => _open = false),
              onOpen: () => setState(() => _open = true),
            ),
            const SizedBox(height: AppSpacing.sm),
            Expanded(
              child: TextField(
                key: const Key('nt-body'),
                controller: _body,
                contentInsertionConfiguration: _images.paste,
                onChanged: (_) => setState(() {}),
                onTap: () {
                  if (_open && _targets().isNotEmpty) {
                    setState(() => _open = false);
                  }
                },
                expands: true,
                maxLines: null,
                textAlignVertical: TextAlignVertical.top,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.notes, semanticLabel: 'Task'),
                ),
              ),
            ),
            ImageStrip(attach: _images, prefix: 'nt', trailing: _send(ok)),
          ],
        ),
      ),
    );
  }
}
