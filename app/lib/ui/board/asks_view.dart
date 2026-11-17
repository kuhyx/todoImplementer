/// The note's `ask` block as buttons, the web drawer's ask cards: a choice
/// shows its options (recommended starred), a command runs or copies, a
/// screenshot loads and is approved or rejected. Risky asks fire on a long
/// press only; an auto-adopted choice offers undo.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:todo_implementer/model/detail.dart';
import 'package:todo_implementer/ui/board/shot_image.dart';

export 'package:todo_implementer/ui/board/shot_image.dart';

/// Sends one ask request (`ask_*` kind and its args).
typedef AskSend = Future<void> Function(String kind, Map<String, dynamic> args);

/// Every ask of a card.
class AsksView extends StatelessWidget {
  /// Creates the view.
  const new({
    required this.asks,
    required this.onSend,
    required this.loadShot,
    super.key,
  });

  /// The asks.
  final List<AskItem> asks;

  /// Sends a request.
  final AskSend onSend;

  /// Loads a screenshot.
  final ShotLoad loadShot;

  @override
  Widget build(BuildContext context) {
    final anyRecommended = asks.any(
      (a) => a.open && a.type == 'choice' && a.recommended != null,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (anyRecommended)
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              key: const Key('ask-take-recommended'),
              icon: const Icon(
                Icons.auto_awesome,
                semanticLabel: 'Recommended',
              ),
              onPressed: () => onSend('ask_take_recommended', const {}),
            ),
          ),
        for (final a in asks)
          Card(
            key: ValueKey('ask-${a.id}'),
            color: AppPalette.inkRaised1,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(a.title),
                  const SizedBox(height: AppSpacing.xs),
                  switch (a.type) {
                    'command' => _Command(ask: a, onSend: onSend),
                    'screenshot' => _Shot(
                      ask: a,
                      onSend: onSend,
                      load: loadShot,
                    ),
                    _ => _Choice(ask: a, onSend: onSend),
                  },
                ],
              ),
            ),
          ),
      ],
    );
  }
}

/// Wraps [child] so it fires [onFire] on a tap, or a long press when risky.
Widget _fire({
  required bool risky,
  required VoidCallback? onFire,
  required Widget child,
}) => GestureDetector(
  onTap: risky ? null : onFire,
  onLongPress: risky ? onFire : null,
  child: AbsorbPointer(child: child),
);

class _Choice extends StatelessWidget {
  const new({required this.ask, required this.onSend});

  final AskItem ask;

  final AskSend onSend;

  @override
  Widget build(BuildContext context) {
    if (!ask.open) {
      return Row(
        children: [
          Icon(
            ask.state == 'auto' ? Icons.schedule : Icons.check_circle,
            color: AppPalette.success,
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(child: Text(ask.answer ?? '')),
          if (ask.state == 'auto')
            IconButton(
              key: ValueKey('ask-undo-${ask.id}'),
              icon: const Icon(Icons.undo, semanticLabel: 'Undo'),
              onPressed: () => onSend('ask_undo', {'ask': ask.id}),
            ),
        ],
      );
    }
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: [
        for (final o in ask.options)
          _fire(
            risky: ask.risky,
            onFire: () {
              final (kind, args) = answerRequest(ask, o);
              unawaited(onSend(kind, args));
            },
            child: Chip(
              key: ValueKey('ask-opt-${ask.id}-$o'),
              avatar: o == ask.recommended
                  ? const Icon(Icons.star, color: AppPalette.accent)
                  : null,
              label: Text(o),
            ),
          ),
      ],
    );
  }
}

class _Command extends StatelessWidget {
  const new({required this.ask, required this.onSend});

  final AskItem ask;

  final AskSend onSend;

  @override
  Widget build(BuildContext context) {
    final command = ask.command ?? '';
    final exit = ask.exit;
    final (kind, args) = runRequest(ask);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectableText(
          command,
          style: const TextStyle(fontFamily: 'monospace'),
        ),
        Row(
          children: [
            IconButton(
              key: ValueKey('ask-copy-${ask.id}'),
              icon: const Icon(Icons.content_copy, semanticLabel: 'Copy'),
              onPressed: () => Clipboard.setData(ClipboardData(text: command)),
            ),
            if (ask.open && ask.mode != 'terminal')
              _fire(
                risky: ask.risky,
                onFire: () => onSend(kind, args),
                child: Padding(
                  key: ValueKey('ask-run-${ask.id}'),
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  child: Icon(
                    ask.mode == 'add_run'
                        ? Icons.playlist_add
                        : Icons.play_arrow,
                    semanticLabel: 'Run',
                  ),
                ),
              ),
            if (exit != null)
              Icon(
                exit == 0 ? Icons.check_circle : Icons.error,
                color: exit == 0 ? AppPalette.success : AppPalette.danger,
                semanticLabel: 'exit $exit',
              ),
          ],
        ),
        if (ask.tail case final tail? when tail.isNotEmpty)
          SelectableText(tail, style: const TextStyle(fontFamily: 'monospace')),
      ],
    );
  }
}

class _Shot extends StatelessWidget {
  const new({required this.ask, required this.onSend, required this.load});

  final AskItem ask;

  final AskSend onSend;

  final ShotLoad load;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (ask.shot case final shot?) ShotImage(name: shot, load: load),
      if (ask.open)
        Row(
          children: [
            IconButton(
              key: ValueKey('ask-approve-${ask.id}'),
              icon: const Icon(
                Icons.thumb_up_alt_outlined,
                semanticLabel: 'Approve',
              ),
              onPressed: () => onSend('ask_approve', {'ask': ask.id}),
            ),
            IconButton(
              key: ValueKey('ask-reject-${ask.id}'),
              icon: const Icon(
                Icons.thumb_down_alt_outlined,
                semanticLabel: 'Reject',
              ),
              onPressed: () => onSend('ask_reject', {'ask': ask.id}),
            ),
          ],
        )
      else
        Icon(
          ask.state == 'approved' ? Icons.thumb_up_alt : Icons.thumb_down_alt,
          color: ask.state == 'approved'
              ? AppPalette.success
              : AppPalette.danger,
        ),
    ],
  );
}
