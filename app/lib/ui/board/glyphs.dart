/// One glyph per server id: the board paints icons, never the server's
/// labels (textgate). Labels and reasons stay as screen-reader text.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board_view.dart';

/// Glyph of a card action id.
IconData actionIcon(String id) => switch (id) {
  'start' => Icons.play_arrow,
  'spec-answers' => Icons.question_answer_outlined,
  'spec-ok' => Icons.thumb_up_alt_outlined,
  'send' => Icons.send,
  'ship' => Icons.rocket_launch_outlined,
  'close' => Icons.task_alt,
  'cancel' => Icons.stop_circle_outlined,
  'lesson-approve' => Icons.school_outlined,
  'copy-resume' => Icons.content_copy,
  'go' => Icons.bolt,
  'copy-fix' => Icons.build_outlined,
  'rerun' => Icons.replay,
  'wont' => Icons.do_not_disturb_on_outlined,
  'merge' => Icons.merge,
  'dismiss' => Icons.close,
  _ => Icons.help_outline,
};

/// Glyph of a column id.
IconData columnIcon(String id) => switch (id) {
  'backlog' => Icons.inbox_outlined,
  'running' => Icons.autorenew,
  'needs_you' => Icons.front_hand_outlined,
  'done' => Icons.check_circle_outline,
  _ => Icons.view_column_outlined,
};

/// Glyph of a sort order.
IconData sortIcon(BoardSort s) => switch (s) {
  BoardSort.effort => Icons.low_priority,
  BoardSort.priority => Icons.flag_outlined,
  BoardSort.updated => Icons.schedule,
  BoardSort.cost => Icons.attach_money,
  BoardSort.title => Icons.sort_by_alpha,
};

/// Glyph of a Needs-you category.
IconData needsIcon(String category) => switch (category) {
  'questions' => Icons.question_mark,
  'criteria' => Icons.checklist,
  'action' => Icons.touch_app_outlined,
  'auto' => Icons.healing_outlined,
  'phone' => Icons.smartphone,
  'permission' => Icons.lock_open_outlined,
  _ => Icons.front_hand_outlined,
};

/// Glyph of a relay error code (DOCS-native-app-relay.md, "Results").
IconData codeIcon(String code) => switch (code) {
  'disabled' => Icons.block,
  'offline' || 'upstream_unavailable' => Icons.cloud_off,
  'rate_limited' => Icons.speed,
  'expired' || 'gave_up' => Icons.timer_off_outlined,
  'unsealed' || 'forbidden' => Icons.lock_outline,
  'not_found' => Icons.search_off,
  'conflict' => Icons.sync_problem,
  _ => Icons.error_outline,
};

/// The colour a status is drawn in.
Color statusColor(String status) => switch (status) {
  'needs_you' || 'waiting_phone_update' => AppPalette.warning,
  'working' || 'shipping' || 'queued' => AppPalette.accent,
  'paused_limit' => AppPalette.danger,
  _ => AppPalette.mutedOnDark,
};
