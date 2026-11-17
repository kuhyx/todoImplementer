/// An umbrella card's children (`umbrella.schema.json#/$defs/detail`):
/// round and width as badges, one row per child with its status colour and
/// the manager's verdict glyph.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

/// Glyph of a manager verdict.
IconData verdictIcon(String? verdict) => switch (verdict) {
  'clean' => Icons.check_circle_outline,
  'coached' => Icons.record_voice_over_outlined,
  'fixed' => Icons.build_circle_outlined,
  'escalate' => Icons.arrow_circle_up,
  _ => Icons.hourglass_empty,
};

/// The umbrella block.
class UmbrellaView extends StatelessWidget {
  /// Creates the block.
  const new({required this.detail, super.key});

  /// The `umbrella` detail object.
  final Json detail;

  @override
  Widget build(BuildContext context) {
    final rows = objs(detail, 'rows');
    return Column(
      key: const Key('umbrella'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Badge.count(
              count: intOr(detail, 'round') ?? 0,
              child: const Icon(Icons.loop, semanticLabel: 'round'),
            ),
            const SizedBox(width: AppSpacing.md),
            Badge.count(
              count: intOr(detail, 'width') ?? 1,
              child: const Icon(
                Icons.view_week_outlined,
                semanticLabel: 'width',
              ),
            ),
          ],
        ),
        for (final r in rows)
          ListTile(
            key: ValueKey('child-${str(r, 'id')}'),
            dense: true,
            leading: Icon(
              Icons.circle,
              size: AppSpacing.md,
              color: statusColor(str(r, 'status')),
            ),
            title: Text(
              str(r, 'title', str(r, 'id')),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: strOr(r, 'repo') == null ? null : Text(str(r, 'repo')),
            trailing: Icon(verdictIcon(strOr(r, 'verdict'))),
          ),
      ],
    );
  }
}
