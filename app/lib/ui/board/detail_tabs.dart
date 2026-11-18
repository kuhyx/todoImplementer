/// The drawer's reading tabs: plan, diff, checks, live check (with its
/// screenshots) and the umbrella's free-model issues. Each is text-shaped
/// content, so each scrolls (R7 exempts logs and text). A stage that has
/// not happened yet shows its column glyph dimmed instead of a sentence.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/detail.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/asks_view.dart';

const _mono = TextStyle(fontFamily: 'monospace', fontSize: AppTextSize.caption);

/// The "not yet" placeholder of a tab.
Widget notYet(IconData icon, Key key) => Center(
  child: Icon(
    icon,
    key: key,
    size: AppSpacing.xxl * 2,
    color: AppPalette.lineDark,
  ),
);

/// Colour of one diff line.
Color diffColor(String line) {
  if (line.startsWith('@@')) return AppPalette.accent;
  if (RegExp(r'^(diff|index|---|\+\+\+)').hasMatch(line)) {
    return AppPalette.mutedOnDark;
  }
  if (line.startsWith('+')) return AppPalette.success;
  if (line.startsWith('-')) return AppPalette.danger;
  return AppPalette.textOnDark;
}

/// The plan.
Widget planTab(TaskDetail d) => switch (d.planMd) {
  final md? => SingleChildScrollView(
    padding: const EdgeInsets.all(AppSpacing.sm),
    child: SelectableText(md, key: const Key('plan')),
  ),
  null => notYet(Icons.map_outlined, const Key('plan-none')),
};

/// The diff: changed files with counts, then the coloured patch.
Widget diffTab(TaskDetail d) {
  final diff = d.diff;
  if (diff == null) {
    return notYet(Icons.difference_outlined, const Key('diff-none'));
  }
  final lines = diff.patch.split('\n');
  return ListView.builder(
    key: const Key('diff'),
    padding: const EdgeInsets.all(AppSpacing.sm),
    itemCount: diff.files.length + lines.length + (diff.truncated ? 1 : 0),
    itemBuilder: (_, i) {
      if (i < diff.files.length) {
        final f = diff.files[i];
        return Text.rich(
          TextSpan(
            children: [
              TextSpan(text: f.path, style: _mono),
              TextSpan(
                text: ' +${f.added}',
                style: _mono.copyWith(color: AppPalette.success),
              ),
              TextSpan(
                text: ' -${f.removed}',
                style: _mono.copyWith(color: AppPalette.danger),
              ),
            ],
          ),
        );
      }
      final at = i - diff.files.length;
      if (at == lines.length) {
        return const Icon(Icons.more_horiz, key: Key('diff-cut'));
      }
      final line = lines[at];
      return Text(line, style: _mono.copyWith(color: diffColor(line)));
    },
  );
}

/// The check commands and their output tails.
Widget checksTab(TaskDetail d) {
  final checks = d.checks;
  if (checks == null) {
    return notYet(Icons.fact_check_outlined, const Key('checks-none'));
  }
  return ListView(
    key: const Key('checks'),
    padding: const EdgeInsets.all(AppSpacing.sm),
    children: [
      Icon(
        checks.passed ? Icons.check_circle : Icons.error,
        color: checks.passed ? AppPalette.success : AppPalette.danger,
      ),
      for (final r in checks.results) ...[
        Row(
          children: [
            Icon(
              r.exit == 0 ? Icons.check : Icons.close,
              color: r.exit == 0 ? AppPalette.success : AppPalette.danger,
              semanticLabel: 'exit ${r.exit}',
            ),
            Expanded(child: SelectableText(r.command, style: _mono)),
          ],
        ),
        SelectableText(r.tail, style: _mono),
      ],
    ],
  );
}

/// The live-check report and its screenshots.
Widget liveCheckTab(TaskDetail d, ShotLoad load) {
  final live = d.liveCheck;
  if (live == null) {
    return notYet(Icons.photo_library_outlined, const Key('live-none'));
  }
  return ListView(
    key: const Key('live-check'),
    padding: const EdgeInsets.all(AppSpacing.sm),
    children: [
      SelectableText(live.reportMd),
      for (final s in live.shots)
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.sm),
          child: ShotImage(name: s, load: load),
        ),
    ],
  );
}

/// The umbrella's free-model issues (`task_issues`: the raw jsonl).
class IssuesTab extends StatefulWidget {
  /// Creates the tab.
  const new({required this.relay, required this.card, super.key});

  /// Where `task_issues` goes.
  final BoardRelay relay;

  /// Card id.
  final String card;

  @override
  State<IssuesTab> createState() => _IssuesTabState();
}

class _IssuesTabState extends State<IssuesTab> {
  late final Future<RelayOutcome> _issues = widget.relay.send('task_issues', {
    'card': widget.card,
  });

  @override
  Widget build(BuildContext context) => FutureBuilder<RelayOutcome>(
    future: _issues,
    builder: (_, snap) {
      final out = snap.data;
      if (out == null) {
        return const Center(
          child: CircularProgressIndicator(semanticsLabel: 'issues'),
        );
      }
      final text = out is RelayOk ? out.data['text'] : null;
      if (text is! String || text.trim().isEmpty) {
        return notYet(Icons.bug_report_outlined, const Key('issues-none'));
      }
      final lines = text.trim().split('\n');
      return ListView.builder(
        key: const Key('issues'),
        padding: const EdgeInsets.all(AppSpacing.sm),
        itemCount: lines.length,
        itemBuilder: (_, i) => SelectableText(lines[i], style: _mono),
      );
    },
  );
}
