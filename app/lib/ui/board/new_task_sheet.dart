/// The add-task page (full screen, T2349): where it goes ([RepoChooser]:
/// none, all or some repos, folded once picked, T2351), one text box whose
/// first line is the title (no title field, T2350), and one row with the
/// image buttons, the attached images and the send button (T2352). Sent as
/// `new_task`: one per picked repo, or one with no repo for none or all.
/// The box takes images (T2334): `[Image #N]` tags in the text, the bytes
/// in `images`.
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

final _imageRef = RegExp(r'\[Image #\d+\]');

/// The line's text with its `[Image #N]` refs out, spaces folded.
String _cleanLine(String line) => _imageRef.hasMatch(line)
    ? line
          .replaceAll(_imageRef, ' ')
          .split(RegExp(r'\s+'))
          .where((w) => w.isNotEmpty)
          .join(' ')
    : line.trim();

/// (title, body), the server's `newtask/titles.py` rule (T2481): the first
/// line of real text with its image refs out, cut to [kMaxTitle]; a note with
/// no text keeps its first line. A skipped or cleaned ref line, or a cut,
/// keeps the whole text as the body, so no ref is lost.
(String, String) splitNote(String text) {
  final all = text.trim();
  final lines = all.split('\n');
  final found = lines.indexWhere((line) => _cleanLine(line).isNotEmpty);
  final at = found < 0 ? 0 : found;
  final title = found < 0 ? lines.first.trim() : _cleanLine(lines[at]);
  final lossy =
      found >= 0 &&
      (title != lines[at].trim() ||
          lines.take(at).any((line) => line.trim().isNotEmpty));
  if (title.length > kMaxTitle) {
    return (title.substring(0, kMaxTitle).trim(), all);
  }
  return (title, lossy ? all : lines.skip(at + 1).join('\n').trim());
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
    // All is one cross-repo change: one note that triage routes as
    // all_repos (an umbrella), not N unrelated cards (kuhy, 2026-11-20).
    RepoScope.none || RepoScope.all => const [null],
    RepoScope.some => [..._picked],
    null => const [],
  };

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _failure = null;
    });
    final (title, body) = splitNote(_body.text);
    final (images, failed) = await _images.upload(
      (kind, b) => widget.relay.send(kind, b),
    );
    for (final repo in failed == null ? _targets() : const <String?>[]) {
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
        setState(() => _picked.remove(repo));
      }
    }
    if (failed != null) {
      if (!mounted) return;
      widget.onError(failed);
      return setState(() {
        _busy = false;
        _failure = failed;
      });
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
