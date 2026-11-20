/// A "click Spec OK" need carries the thumb-up button it asks for, so the
/// need line itself is the tap (kuhy, 2026-11-20: "the spec ok itself should
/// be clickable everywhere"); the sheet and the detail page both use it.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/ui/board/action_bar.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';

/// The Spec OK action [card]'s need asks for, else null.
CardAction? inlineSpecOk(TaskCard card) => card.needs?.kind == 'spec_ok'
    ? card.actions.where((a) => a.id == 'spec-ok').firstOrNull
    : null;

/// The thumb-up of [action] in the need line, drawn like the action bar.
Widget specOkButton(CardAction action, ActionTap onRun) => Align(
  alignment: AlignmentDirectional.centerStart,
  child: ActionBar(
    key: const Key('needs-spec-ok'),
    actions: [action],
    onRun: onRun,
  ),
);

/// The detail page's need: glyph, text (or [specOk]'s thumb-up) and the
/// one-line command of a permission need.
Widget needsTile(Needs needs, CardAction? specOk, ActionTap onRun) => ListTile(
  leading: Icon(needsIcon(needs.category), color: AppPalette.warning),
  title: specOk == null
      ? SelectableText(needs.text)
      : specOkButton(specOk, onRun),
  subtitle: needs.command == null
      ? null
      : SelectableText(
          needs.command!,
          style: const TextStyle(fontFamily: 'monospace'),
        ),
);
