/// Glyphs and tones of the sessions page (web `sessions/labels.ts`). The
/// words live only in semantics labels: the page shows icons and numbers
/// (textgate).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/sessions.dart';
import 'package:todo_implementer/model/sessions_view.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';

/// Glyph of a status tag.
IconData statusIcon(SessionStatus s) => switch (s) {
  SessionStatus.needsAction => Icons.priority_high,
  SessionStatus.question => Icons.question_mark,
  SessionStatus.untagged => Icons.label_off_outlined,
  SessionStatus.running => Icons.autorenew,
  SessionStatus.done => Icons.check_circle_outline,
  SessionStatus.continuing => Icons.redo,
};

/// Tone: what wants kuhy is danger, unknown is warning, live work is info,
/// finished is muted.
Color statusTone(SessionStatus s) => switch (s) {
  SessionStatus.needsAction || SessionStatus.question => AppPalette.danger,
  SessionStatus.untagged => AppPalette.warning,
  SessionStatus.running => AppPalette.info,
  SessionStatus.done || SessionStatus.continuing => AppPalette.mutedOnDark,
};

/// Screen-reader name of a status tag.
String statusName(SessionStatus s) => switch (s) {
  SessionStatus.needsAction => 'needs action',
  SessionStatus.question => 'question',
  SessionStatus.untagged => 'no status tag',
  SessionStatus.running => 'running',
  SessionStatus.done => 'done',
  SessionStatus.continuing => 'continuing in a new session',
};

/// Glyph of a mark (null: the "all marks" filter).
IconData markIcon(SessionMark? m) => switch (m) {
  SessionMark.manual => Icons.person_outline,
  SessionMark.tag => Icons.sell_outlined,
  SessionMark.open => Icons.radio_button_unchecked,
  null => Icons.select_all,
};

/// Screen-reader name of a mark (null: the "all marks" filter).
String markName(SessionMark? m) => switch (m) {
  SessionMark.manual => 'marked done by hand',
  SessionMark.tag => 'done by its status tag',
  SessionMark.open => 'not done',
  null => 'any mark',
};

/// Screen-reader names of the page's controls (web `label`), never drawn.
const spoken = <String, String>{
  'resume': 'resume in a terminal',
  'resume-max': 'at most 5 terminals at once',
  'copy': 'copy the resume command',
  'handoff': 'move to the board',
  'handoff-max': 'at most 5 sessions at once',
  'copy-all': 'copy the resume commands',
  'mark': 'mark done',
  'unmark': 'remove the done mark',
  'marks': 'done mark',
  'delete': 'hold to move to the trash',
  'clear': 'clear the selection',
  'select-all': 'select all',
  'search': 'search',
  'filters': 'filters',
  'sort': 'sort',
  'show-done': 'show done sessions',
  'reset': 'reset the filters',
  'project': 'project',
  'idle': 'idle for more than this many days',
  'wait': 'waiting for the PC',
  'errors': 'copy the errors',
};

/// One-word tooltip for each session button.
String sessionTooltip(String id) => switch (id) {
  'resume' => 'terminal',
  'copy' => 'copy',
  'handoff' => 'board',
  'copy-all' => 'copyall',
  'mark' => 'done',
  'unmark' => 'undo',
  'delete' => 'delete',
  _ => id,
};

/// Glyph of a sort key.
IconData sortIcon(SessionSort s) => switch (s) {
  SessionSort.group => Icons.circle_outlined,
  SessionSort.age => Icons.schedule,
  SessionSort.project => Icons.folder_outlined,
  SessionSort.title => Icons.sort_by_alpha,
  SessionSort.mark => Icons.check,
};

/// Glyph of an answer.
IconData outcomeIcon(OutcomeKind k) => switch (k) {
  OutcomeKind.ok => Icons.check,
  OutcomeKind.refused => Icons.lock_outline,
  OutcomeKind.failed => Icons.error_outline,
};

/// The answer as a glyph; its own words are the semantics label only.
Widget outcomeGlyph(SessionOutcome o, {Key? key}) => Icon(
  outcomeIcon(o.kind),
  key: key,
  color: o.kind == OutcomeKind.ok ? AppPalette.success : AppPalette.danger,
  semanticLabel: o.summary.isEmpty ? o.kind.name : o.summary,
);
