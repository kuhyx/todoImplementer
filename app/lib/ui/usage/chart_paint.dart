/// Painters of the usage charts (dataviz marks: thin bars with a 2 px gap,
/// 2 px lines, recessive grid, one y axis from zero).
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';

/// Left gutter for the y labels.
const yGutter = 44.0;

/// Index of the label under x = [dx] in a plot of [width].
int indexAt(double dx, double width, int count) {
  if (count == 0) return -1;
  final x = (dx - yGutter).clamp(0, width - yGutter - 1);
  return (x / ((width - yGutter) / count)).floor().clamp(0, count - 1);
}

/// Bars, lines and intervals of a [ChartBlock]; [selected] is highlighted.
class ChartPainter extends CustomPainter {
  /// Creates the painter.
  const new(this.block, this.selected);

  /// The chart.
  final ChartBlock block;

  /// The tapped label, or -1.
  final int selected;

  static final _grid = Paint()
    ..color = AppPalette.lineDark
    ..strokeWidth = 1;

  void _label(Canvas c, String text, Offset at, {bool right = false}) {
    final p = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(color: AppPalette.mutedOnDark, fontSize: 10),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: yGutter - 4);
    p.paint(c, at - Offset(right ? p.width : 0, p.height / 2));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final values = [
      for (final s in block.series) ...s.values.whereType<num>(),
      ...block.low,
      ...block.high,
    ];
    final top = values.fold<num>(0, math.max).toDouble();
    final bottom = values.fold<num>(0, math.min).toDouble();
    final span = top - bottom == 0 ? 1.0 : top - bottom;
    double y(num v) => size.height * (1 - (v - bottom) / span);
    for (final v in {top, bottom, 0.0}) {
      canvas.drawLine(Offset(yGutter, y(v)), Offset(size.width, y(v)), _grid);
      _label(canvas, block.fmt(v), Offset(yGutter - 4, y(v)), right: true);
    }
    final n = block.labels.length;
    if (n == 0) return;
    final slot = (size.width - yGutter) / n;
    double cx(int i) => yGutter + slot * (i + 0.5);
    if (selected >= 0) {
      canvas.drawRect(
        Rect.fromLTWH(yGutter + slot * selected, 0, slot, size.height),
        Paint()..color = AppPalette.inkRaised2,
      );
    }
    switch (block.kind) {
      case ChartKind.bar:
      case ChartKind.rank:
        _bars(canvas, slot, cx, y);
      case ChartKind.line:
        _lines(canvas, cx, y);
      case ChartKind.interval:
        _intervals(canvas, cx, y);
    }
  }

  void _bars(
    Canvas c,
    double slot,
    double Function(int) cx,
    double Function(num) y,
  ) {
    final k = block.series.length;
    final w = math.max(1, (slot - 2) / k - (k > 1 ? 2 : 0)).toDouble();
    for (final (j, s) in block.series.indexed) {
      final paint = Paint()..color = seriesColor(s.color);
      for (final (i, v) in s.values.indexed) {
        if (v == null) continue;
        final left = cx(i) - slot / 2 + 1 + j * (w + 2);
        final r = Rect.fromLTRB(
          left,
          math.min(y(v), y(0)),
          left + w,
          math.max(y(v), y(0)),
        );
        c.drawRRect(
          RRect.fromRectAndCorners(
            r,
            topLeft: Radius.circular(math.min(4, w / 2)),
            topRight: Radius.circular(math.min(4, w / 2)),
          ),
          paint,
        );
      }
    }
  }

  void _lines(Canvas c, double Function(int) cx, double Function(num) y) {
    for (final s in block.series) {
      final paint = Paint()
        ..color = seriesColor(s.color)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke;
      final path = Path();
      var pen = false;
      for (final (i, v) in s.values.indexed) {
        if (v == null) {
          pen = false;
          continue;
        }
        final p = Offset(cx(i), y(v));
        pen ? path.lineTo(p.dx, p.dy) : path.moveTo(p.dx, p.dy);
        pen = true;
      }
      c.drawPath(path, paint);
      if (selected >= 0 && selected < s.values.length) {
        final v = s.values[selected];
        if (v != null) {
          c.drawCircle(
            Offset(cx(selected), y(v)),
            4,
            Paint()..color = seriesColor(s.color),
          );
        }
      }
    }
  }

  void _intervals(Canvas c, double Function(int) cx, double Function(num) y) {
    final s = block.series.first;
    final paint = Paint()
      ..color = seriesColor(s.color)
      ..strokeWidth = 2;
    for (final (i, v) in s.values.indexed) {
      if (i < block.low.length && i < block.high.length) {
        c.drawLine(
          Offset(cx(i), y(block.low[i])),
          Offset(cx(i), y(block.high[i])),
          paint,
        );
      }
      if (v != null) c.drawCircle(Offset(cx(i), y(v)), 4, paint);
    }
  }

  @override
  bool shouldRepaint(ChartPainter old) =>
      old.block != block || old.selected != selected;
}
