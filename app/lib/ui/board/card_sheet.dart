/// The card sheet: the card's content, its offered actions, and the inputs
/// some actions need (a message and images for `send`, answers for
/// `spec-answers`, the auto-ship option for `start`). Results come back over
/// the relay; a refusal shows as its code glyph in red.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/action_bar.dart';
import 'package:todo_implementer/ui/board/detail_page.dart'
    show kDetailPatience;
import 'package:todo_implementer/ui/board/glyphs.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';
import 'package:todo_implementer/ui/board/model_picker.dart';
import 'package:todo_implementer/ui/board/needs_line.dart';
import 'package:todo_implementer/ui/board/spec_answers.dart';

/// Relay kind of a card action id (`spec-ok` -> `task_spec_ok`).
String kindOf(String actionId) => 'task_${actionId.replaceAll('-', '_')}';

/// The sheet body for [card].
class CardSheet extends StatefulWidget {
  /// Creates the sheet.
  const new({
    required this.card,
    required this.relay,
    required this.onError,
    this.onDetail,
    super.key,
  });

  /// Opens the card's full drawer page.
  final VoidCallback? onDetail;

  /// The card.
  final TaskCard card;

  /// Where actions go.
  final BoardRelay relay;

  /// Records a failure for the copy-errors action.
  final void Function(RelayFailed failure) onError;

  @override
  State<CardSheet> createState() => _CardSheetState();
}

class _CardSheetState extends State<CardSheet> {
  final _message = TextEditingController();
  late final _images = ImageAttach(_message);
  bool _autoShip = false;
  List<SpecQuestion>? _questions;
  RelayFailed? _failure;

  @override
  void dispose() {
    _images.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<RelayOutcome> _send(String kind, Json args) =>
      widget.relay.send(kind, {'card': widget.card.id, 'args': args});

  Future<void> _settle(RelayOutcome out) async {
    if (out is RelayFailed) {
      widget.onError(out);
      if (mounted) setState(() => _failure = out);
      return;
    }
    if (mounted) await Navigator.of(context).maybePop();
  }

  Future<void> _run(CardAction a) async {
    setState(() => _failure = null);
    switch (a.id) {
      case 'copy-resume' || 'copy-fix':
        await Clipboard.setData(ClipboardData(text: a.value ?? ''));
        await HapticFeedback.selectionClick();
      case 'spec-answers':
        // Same patience as the detail page (T2314): a dead worker ends in
        // the failure glyph and a re-enabled action, which is the retry.
        final out = await widget.relay.send('task_detail', {
          'card': widget.card.id,
        }, timeout: kDetailPatience);
        if (out is RelayOk) {
          setState(() => _questions = openQuestions(out.data));
        } else {
          await _settle(out);
        }
      case 'send':
        final text = _message.text.trim();
        if (text.isEmpty) return await HapticFeedback.heavyImpact();
        final (images, failed) = await _images.upload(
          (kind, body) => widget.relay.send(kind, body),
        );
        if (failed != null) return await _settle(failed);
        await _settle(
          await _send(kindOf(a.id), {
            'text': text,
            if (images.isNotEmpty) 'images': images,
          }),
        );
      case 'start':
        final args = a.option?.enabled ?? false
            ? <String, dynamic>{'auto_ship': _autoShip}
            : <String, dynamic>{};
        await _settle(await _send(kindOf(a.id), args));
      default:
        await _settle(await _send(kindOf(a.id), const {}));
    }
  }

  Widget _autoShipChip(CardAction opt) => Semantics(
    label: opt.spoken,
    excludeSemantics: true,
    child: Align(
      alignment: Alignment.centerLeft,
      child: FilterChip(
        key: const Key('auto-ship'),
        avatar: const Icon(Icons.rocket_launch_outlined),
        label: const SizedBox.shrink(),
        selected: _autoShip,
        onSelected: opt.enabled ? (v) => setState(() => _autoShip = v) : null,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    final needs = card.needs;
    final specOk = inlineSpecOk(card);
    final offers = {for (final a in card.actions) a.id: a};
    final questions = _questions;
    final failure = _failure;
    const muted = TextStyle(color: AppPalette.mutedOnDark);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    card.title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (widget.onDetail case final open?)
                  IconButton(
                    key: const Key('open-detail'),
                    icon: const Icon(Icons.open_in_full, semanticLabel: 'Open'),
                    onPressed: open,
                  ),
              ],
            ),
            if (card.repo case final repo?) Text(repo, style: muted),
            if (card.model case final model?)
              Text(model, key: const Key('card-model'), style: muted),
            if (card.current.isNotEmpty) Text(card.current),
            if (needs != null)
              Row(
                children: [
                  Icon(needsIcon(needs.category), color: AppPalette.warning),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: specOk == null
                        ? SelectableText(needs.command ?? needs.text)
                        : specOkButton(specOk, _run),
                  ),
                ],
              ),
            const SizedBox(height: AppSpacing.md),
            if (offers.containsKey('send')) ...[
              ImageStrip(
                attach: _images,
                prefix: 'sheet',
                field: TextField(
                  key: const Key('send-text'),
                  controller: _message,
                  contentInsertionConfiguration: _images.paste,
                  minLines: 1,
                  maxLines: 5,
                ),
              ),
            ],
            if (offers['start']?.option case final opt?) _autoShipChip(opt),
            const SizedBox(height: AppSpacing.sm),
            ActionBar(
              actions: [
                for (final a in card.actions)
                  if (a.id != 'model' && a != specOk) a,
              ],
              onRun: _run,
            ),
            if (offers['model'] case final pick?)
              ModelPicker(
                action: pick,
                onPick: (id) async =>
                    await _settle(await _send('task_model', {'model': id})),
              ),
            if (questions != null) ...[
              const SizedBox(height: AppSpacing.md),
              SpecAnswers(
                questions: questions,
                onSend: (answers) async => await _settle(
                  await _send('task_spec_answers', {'answers': answers}),
                ),
              ),
            ],
            if (failure != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.md),
                child: Icon(
                  codeIcon(failure.code),
                  key: const Key('sheet-failure'),
                  color: AppPalette.danger,
                  semanticLabel: failure.error,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
