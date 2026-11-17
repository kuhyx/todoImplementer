/// The merge strip: Haiku-suggested groups of similar open notes from
/// `snap/merges`, paged sideways above the grid. Merge fires on a long
/// press (it closes the members); dismiss on a tap. Nothing shows when
/// there is no suggestion.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/action_bar.dart';

/// Strip height in logical px.
const double mergeStripHeight = 64;

/// The strip, fed by [relay].
class MergeStrip extends StatefulWidget {
  /// Creates the strip.
  const new({required this.relay, required this.onError, super.key});

  /// Source of `snap/merges` and target of the actions.
  final BoardRelay relay;

  /// Records a refusal for the copy-errors action.
  final void Function(RelayFailed failure) onError;

  @override
  State<MergeStrip> createState() => _MergeStripState();
}

class _MergeStripState extends State<MergeStrip> {
  late final Stream<List<MergeSuggestion>> _merges = widget.relay.merges();

  @override
  Widget build(BuildContext context) => StreamBuilder<List<MergeSuggestion>>(
    stream: _merges,
    builder: (context, snap) {
      final all = snap.data ?? const <MergeSuggestion>[];
      if (all.isEmpty) return const SizedBox.shrink();
      return SizedBox(
        key: const Key('merge-strip'),
        height: mergeStripHeight,
        child: PageView.builder(
          itemCount: all.length,
          controller: PageController(viewportFraction: 0.92),
          itemBuilder: (_, i) => _Suggestion(
            key: ValueKey('merge-${all[i].id}'),
            suggestion: all[i],
            onRun: (a) async {
              final out = await widget.relay.send(mergeKind(a.id), {
                'group': all[i].id,
                'args': const <String, dynamic>{},
              });
              if (out is RelayFailed) widget.onError(out);
            },
          ),
        ),
      );
    },
  );
}

class _Suggestion extends StatelessWidget {
  const new({required this.suggestion, required this.onRun, super.key});

  final MergeSuggestion suggestion;

  final ActionTap onRun;

  @override
  Widget build(BuildContext context) => Card(
    color: AppPalette.inkRaised1,
    margin: const EdgeInsets.symmetric(
      horizontal: AppSpacing.xs,
      vertical: AppSpacing.xs,
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      child: Row(
        children: [
          const Icon(Icons.merge, color: AppPalette.accent),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Semantics(
              label: suggestion.reason,
              child: Text(
                suggestion.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
          Badge.count(
            count: suggestion.members.length,
            child: const Icon(Icons.description_outlined),
          ),
          const SizedBox(width: AppSpacing.sm),
          ActionBar(actions: suggestion.actions, onRun: onRun),
        ],
      ),
    ),
  );
}
