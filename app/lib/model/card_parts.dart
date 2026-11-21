/// A card's offered actions and its Needs-you record
/// (`common.schema.json#/$defs/action` and `#/$defs/needs`).
library;

import 'package:flutter/foundation.dart';
import 'package:todo_implementer/model/json.dart';

/// A button the card offers (`common.schema.json#/$defs/action`).
@immutable
class CardAction {
  /// Creates an action.
  const new({
    required this.id,
    required this.label,
    required this.enabled,
    this.reason,
    this.confirm = false,
    this.value,
    this.option,
    this.choices = const [],
  });

  /// Parses one action.
  factory fromJson(Json j) {
    final o = objOr(j, 'option');
    return CardAction(
      id: str(j, 'id'),
      label: str(j, 'label'),
      enabled: flag(j, 'enabled'),
      reason: strOr(j, 'reason'),
      confirm: flag(j, 'confirm'),
      value: strOr(j, 'value'),
      option: o == null ? null : CardAction.fromJson(o),
      choices: [
        for (final c in objs(j, 'choices'))
          (
            id: str(c, 'id'),
            label: str(c, 'label'),
            isDefault: strOr(c, 'note') == 'default',
          ),
      ],
    );
  }

  /// Action id (`start`, `ship`, `copy-resume`, ...).
  final String id;

  /// The server's label: spoken only (textgate), never painted.
  final String label;

  /// False: drawn disabled with [reason].
  final bool enabled;

  /// Why it is disabled.
  final String? reason;

  /// Ask "sure?" first (ship, cancel).
  final bool confirm;

  /// copy-resume / copy-fix: the text to copy; model: the id of the model
  /// the card runs on (the pin, else the latest turn's, else the default).
  final String? value;

  /// model only: the picker's rows (the id a tap sends, a short name, and
  /// whether it is the model the roles run unpinned).
  final List<({String id, String label, bool isDefault})> choices;

  /// start only: the auto_ship checkbox.
  final CardAction? option;

  /// Screen-reader text: the label, plus the reason when disabled.
  String get spoken => [label, if (!enabled) ?reason].join(': ');

  /// True for actions done on the device (clipboard), not on the PC.
  bool get local => id == 'copy-resume' || id == 'copy-fix';
}

/// Why a card is in Needs you.
@immutable
class Needs {
  /// Creates the record.
  const new({
    required this.kind,
    required this.text,
    required this.category,
    required this.effort,
    this.command,
    this.links = const [],
  });

  /// Parses it.
  factory fromJson(Json j) => Needs(
    kind: str(j, 'kind'),
    text: str(j, 'text'),
    category: str(j, 'category'),
    effort: intOr(j, 'effort') ?? 1,
    command: strOr(j, 'command'),
    links: strs(j, 'links'),
  );

  /// `spec_questions`, `run_failed`, ...
  final String kind;

  /// What exactly is needed (spoken; shown in the card sheet as content).
  final String text;

  /// `questions`, `criteria`, `action`, `auto`, `phone`, `permission`.
  final String category;

  /// Answers or clicks still needed.
  final int effort;

  /// permission: the one-line grant command.
  final String? command;

  /// Absolute http(s) pages the ask names; empty when it names none.
  final List<String> links;
}
