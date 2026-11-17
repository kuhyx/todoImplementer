/// A chart block: title glyph, legend glyphs (2+ series), the plot, and a
/// tap readout of one label's values (the phone's hover layer).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/usage/format.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/chart_paint.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';

/// Height a chart takes on a page.
const chartHeight = 200.0;

/// Rows a ranking shows.
const rankRows = 6;

const _small = TextStyle(fontSize: 11, color: AppPalette.mutedOnDark);

/// One chart.
class ChartView extends StatefulWidget {
  /// Creates the view.
  const new(this.block, {super.key});

  /// The chart.
  final ChartBlock block;

  @override
  State<ChartView> createState() => _ChartViewState();
}

class _ChartViewState extends State<ChartView> {
  int _selected = -1;

  ChartBlock get b => widget.block;

  Widget _header() {
    final i = _selected;
    return SizedBox(
      height: 24,
      child: Row(
        children: [
          Icon(b.icon, size: 16, semanticLabel: b.semantics),
          if (b.series.length > 1)
            for (final s in b.series) ...[
              const SizedBox(width: AppSpacing.sm),
              Icon(
                s.icon,
                size: 14,
                color: seriesColor(s.color),
                semanticLabel: s.name,
              ),
            ],
          const Spacer(),
          if (i >= 0 && i < b.labels.length) ...[
            Text(b.labels[i], style: _small),
            for (final s in b.series) ...[
              const SizedBox(width: AppSpacing.sm),
              Icon(Icons.circle, size: 8, color: seriesColor(s.color)),
              const SizedBox(width: 2),
              Text(
                i < s.values.length && s.values[i] != null
                    ? b.fmt(s.values[i]!)
                    : dash,
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => SizedBox(
    height: chartHeight,
    child: Column(
      children: [
        _header(),
        Expanded(
          child: b.kind == ChartKind.rank
              ? _Rank(b)
              : LayoutBuilder(
                  builder: (context, box) => GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTapDown: (d) => setState(
                      () => _selected = indexAt(
                        d.localPosition.dx,
                        box.maxWidth,
                        b.labels.length,
                      ),
                    ),
                    child: CustomPaint(
                      size: Size(box.maxWidth, box.maxHeight),
                      painter: ChartPainter(b, _selected),
                    ),
                  ),
                ),
        ),
        if (b.kind != ChartKind.rank && b.labels.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(left: yGutter),
            child: Row(
              children: [
                Text(b.labels.first, style: _small),
                const Spacer(),
                Text(b.labels.last, style: _small),
              ],
            ),
          ),
      ],
    ),
  );
}

/// A ranking: one bar per label (data), largest first, top [rankRows].
class _Rank extends StatelessWidget {
  const new(this.b);

  final ChartBlock b;

  @override
  Widget build(BuildContext context) {
    final s = b.series.first;
    final top = s.values.whereType<num>().fold<num>(0, (a, v) => v > a ? v : a);
    final n = b.labels.length < rankRows ? b.labels.length : rankRows;
    return Column(
      children: [
        for (var i = 0; i < n; i++)
          Expanded(
            child: Row(
              children: [
                SizedBox(
                  width: 120,
                  child: Text(
                    b.labels[i],
                    style: _small,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Expanded(
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    heightFactor: 0.6,
                    widthFactor: top <= 0
                        ? 0
                        : ((s.values[i] ?? 0) / top).clamp(0, 1).toDouble(),
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: seriesColor(s.color),
                        borderRadius: const BorderRadius.horizontal(
                          right: Radius.circular(4),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  s.values[i] == null ? dash : b.fmt(s.values[i]!),
                  style: const TextStyle(fontSize: 12),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
