/// Two rings beside the credits switch (T2348): how full the Claude plan
/// is (the fuller of the 5 h and 7 d windows, from `snap/usage`) and how
/// much of this week's free-credit cap is spent. A tap shows the numbers
/// and the resets; the rings themselves carry no words (textgate).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';

/// Plan use from 80 % on is a warning; a full window is red.
const kPlanWarn = 0.8;

/// The plan windows shown, with their glyph.
const List<(String, IconData)> _windows = [
  ('five_hour', Icons.schedule),
  ('seven_day', Icons.date_range),
];

/// Fraction of the fuller plan window, 0 when no usage was read.
double planUsed(Json? usage) {
  var most = 0.0;
  for (final (key, _) in _windows) {
    final w = usage == null ? null : objOr(usage, key);
    final used = w == null ? 0.0 : numOf(w, 'utilization');
    if (used > most) most = used;
  }
  return most;
}

/// Fraction of the credits cap spent this week (1 at or past the cap).
double creditsUsed(Board b) {
  final cap = numOf(b.credits, 'cap_usd');
  if (flag(b.credits, 'over_cap')) return 1;
  if (cap <= 0) return 0;
  return (numOf(b.credits, 'spent_period_usd') / cap).clamp(0, 1).toDouble();
}

Color _planColor(double used) => used >= 1
    ? AppPalette.danger
    : used >= kPlanWarn
    ? AppPalette.warning
    : AppPalette.accent;

String _when(num epoch) {
  final t = DateTime.fromMillisecondsSinceEpoch((epoch * 1000).round());
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.day)}.${two(t.month)} ${two(t.hour)}:${two(t.minute)}';
}

String _usd(double v) => '\$${v.toStringAsFixed(2)}';

/// The plan and credits rings.
class UsageGauges extends StatelessWidget {
  /// Creates the rings.
  const new({required this.board, this.usage, super.key});

  /// The board (credits and plan limit).
  final Board board;

  /// The newest `snap/usage`, if read.
  final Json? usage;

  Widget _ring(
    BuildContext context,
    String key,
    double value,
    Color color,
    IconData icon,
  ) => InkWell(
    key: Key(key),
    customBorder: const CircleBorder(),
    onTap: () => _details(context),
    child: Padding(
      padding: const EdgeInsets.all(AppSpacing.xs),
      child: SizedBox.square(
        dimension: AppSpacing.xl,
        child: Stack(
          alignment: Alignment.center,
          children: [
            SizedBox.expand(
              child: CircularProgressIndicator(
                value: value,
                strokeWidth: 3,
                backgroundColor: AppPalette.inkRaised2,
                valueColor: AlwaysStoppedAnimation(color),
              ),
            ),
            Icon(icon, size: AppSpacing.md),
          ],
        ),
      ),
    ),
  );

  Future<void> _details(BuildContext context) => showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (_) => Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final (key, icon) in _windows)
            if (_window(key) case final w?)
              _row(
                icon,
                '${(numOf(w, 'utilization') * 100).round()}%',
                _when(numOf(w, 'resets_at')),
              ),
          _row(
            Icons.toll_outlined,
            '${_usd(numOf(board.credits, 'spent_period_usd'))} / '
            '${_usd(numOf(board.credits, 'cap_usd'))}',
            null,
          ),
          if (board.limitUntil case final until? when board.limitActive)
            _row(
              Icons.hourglass_bottom,
              _when(until),
              null,
              key: const Key('gauge-limit-until'),
            ),
        ],
      ),
    ),
  );

  Json? _window(String key) {
    final u = usage;
    return u == null ? null : objOr(u, key);
  }

  Widget _row(IconData icon, String main, String? side, {Key? key}) => ListTile(
    key: key,
    dense: true,
    leading: Icon(icon),
    title: Text(main),
    trailing: side == null
        ? null
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.restart_alt, size: AppSpacing.md),
              Text(side),
            ],
          ),
  );

  @override
  Widget build(BuildContext context) {
    final plan = planUsed(usage);
    final hot =
        flag(board.credits, 'over_cap') || board.creditsState == 'exhausted';
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _ring(context, 'gauge-plan', plan, _planColor(plan), Icons.bolt),
        KeyedSubtree(
          key: const Key('gauge-credits'),
          child: Opacity(
            opacity: board.creditsEnabled ? 1 : 0.4,
            child: _ring(
              context,
              'gauge-credits-tap',
              creditsUsed(board),
              hot ? AppPalette.danger : AppPalette.accent,
              Icons.toll_outlined,
            ),
          ),
        ),
      ],
    );
  }
}
