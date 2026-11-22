/// Send to Claude on the drawer page: a note box beside the asks, so a note
/// never waits for the questions to be answered (T2276). It is drawn only
/// when the card offers `send`; a disabled send keeps the box and speaks
/// its reason. The text and its images (T2332) stay when the PC refuses it.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';

/// Sends one note; [images] uploads its images first (T2426). True when the
/// PC took it.
typedef NoteSend = Future<bool> Function(String text, ImageAttach images);

/// The note box for [action] (the card's `send`).
class NoteBox extends StatefulWidget {
  /// Creates the box.
  const new({required this.action, required this.onSend, super.key});

  /// The card's `send` action.
  final CardAction action;

  /// Posts the note.
  final NoteSend onSend;

  @override
  State<NoteBox> createState() => _NoteBoxState();
}

class _NoteBoxState extends State<NoteBox> {
  final _text = TextEditingController();
  late final _images = ImageAttach(_text);
  bool _busy = false;

  @override
  void dispose() {
    _images.dispose();
    _text.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _text.text.trim();
    if (text.isEmpty) return;
    setState(() => _busy = true);
    final taken = await widget.onSend(text, _images);
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (taken) {
        _text.clear();
        _images.clear();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final action = widget.action;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: ImageStrip(
        attach: _images,
        prefix: 'detail',
        field: TextField(
          key: const Key('detail-send-text'),
          controller: _text,
          contentInsertionConfiguration: _images.paste,
          minLines: 1,
          maxLines: 5,
        ),
        trailing: IconButton(
          key: const Key('detail-send'),
          tooltip: 'send',
          icon: _busy
              ? const SizedBox.square(
                  dimension: AppSpacing.md,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Icon(Icons.send, semanticLabel: action.spoken),
          onPressed: action.enabled && !_busy ? _send : null,
        ),
      ),
    );
  }
}
