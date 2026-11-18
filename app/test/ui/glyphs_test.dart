import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/board_view.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

void main() {
  test('every server id has its own glyph, unknown ids a fallback', () {
    const actions = [
      'start',
      'spec-answers',
      'spec-ok',
      'send',
      'ship',
      'close',
      'cancel',
      'lesson-approve',
      'copy-resume',
      'go',
      'copy-fix',
      'rerun',
    ];
    expect(actions.map(actionIcon).toSet(), hasLength(actions.length));
    expect(actionIcon('x'), Icons.help_outline);
    expect(columnIds.map(columnIcon).toSet(), hasLength(5));
    expect(columnIcon('x'), Icons.view_column_outlined);
    expect(BoardSort.values.map(sortIcon).toSet(), hasLength(5));
    const needs = ['questions', 'criteria', 'action', 'auto', 'phone'];
    expect([...needs, 'permission', 'x'].map(needsIcon).toSet(), hasLength(7));
    const codes = [
      'disabled',
      'offline',
      'upstream_unavailable',
      'rate_limited',
      'expired',
      'gave_up',
      'unsealed',
      'forbidden',
      'not_found',
      'conflict',
      'internal',
    ];
    expect(codes.map(codeIcon).toSet(), hasLength(8));
    const statuses = [
      'needs_you',
      'working',
      'ready_to_ship',
      'paused_limit',
      'backlog',
    ];
    expect(statuses.map(statusColor).toSet(), hasLength(5));
  });
}
