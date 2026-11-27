/// The on-device copy of what the app pulled from the PC (T2603): the last
/// board and the card details, so the app reads them offline and after a
/// restart (offline-first, `~/.claude/rules/offline-first.instructions.md`).
/// Details share a byte [PrefsLocalCopy.budget]: the web build's
/// localStorage holds about 5 MB, so the oldest saved details go first.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/json.dart';

/// Characters of detail JSON kept on disk across all cards.
const kDetailBudget = 2000000;

/// Where pulled data is kept.
abstract interface class LocalCopy {
  /// The last `snap/board` node, or null when none was kept.
  Json? board();

  /// Keeps [node] as the last board.
  Future<void> saveBoard(Json node);

  /// The last `task_detail` data of [card], or null.
  Json? detail(String card);

  /// The card's `updated` stamp when its detail was kept, or null.
  int? stamp(String card);

  /// Keeps [data] as [card]'s detail, taken at [stamp].
  Future<void> saveDetail(String card, Json data, {int? stamp});

  /// The unsent writes, oldest first (`{kind, body}` each).
  List<Json> outbox();

  /// Keeps [items] as the unsent writes.
  Future<void> saveOutbox(List<Json> items);
}

/// [LocalCopy] in the app's preferences.
class PrefsLocalCopy implements LocalCopy {
  /// Creates the copy.
  new(this.prefs, {this.budget = kDetailBudget});

  /// The app's preferences.
  final SharedPreferences prefs;

  /// Characters of detail JSON kept at most.
  final int budget;

  static const _boardKey = 'local.board';

  /// Card id -> `[stamp, size, savedSeq]`, oldest evicted first.
  static const _indexKey = 'local.details';

  static const _outboxKey = 'local.outbox';

  static String _key(String card) => 'local.detail.$card';

  Json? _decode(String? raw) {
    if (raw == null) return null;
    try {
      final node = jsonDecode(raw);
      return node is Json ? node : null;
    } on FormatException {
      return null;
    }
  }

  Map<String, List<int>> _index() => {
    for (final MapEntry(:key, :value)
        in (_decode(prefs.getString(_indexKey)) ?? const <String, dynamic>{})
            .entries)
      if (value is List && value.length == 3 && value.every((v) => v is int))
        key: value.cast<int>(),
  };

  @override
  Json? board() => _decode(prefs.getString(_boardKey));

  @override
  List<Json> outbox() =>
      objs(_decode(prefs.getString(_outboxKey)) ?? const {}, 'items');

  @override
  Future<void> saveOutbox(List<Json> items) =>
      prefs.setString(_outboxKey, jsonEncode({'items': items}));

  @override
  Future<void> saveBoard(Json node) =>
      prefs.setString(_boardKey, jsonEncode(node));

  @override
  Json? detail(String card) =>
      _index().containsKey(card) ? _decode(prefs.getString(_key(card))) : null;

  @override
  int? stamp(String card) {
    final row = _index()[card];
    return row == null || row[0] < 0 ? null : row[0];
  }

  @override
  Future<void> saveDetail(String card, Json data, {int? stamp}) async {
    final raw = jsonEncode(data);
    if (raw.length > budget) return;
    final index = _index()..remove(card);
    final seq = index.values.fold(0, (m, r) => r[2] > m ? r[2] : m) + 1;
    var used = index.values.fold(0, (s, r) => s + r[1]) + raw.length;
    final oldest = index.keys.toList()
      ..sort((a, b) => index[a]![2].compareTo(index[b]![2]));
    for (final gone in oldest) {
      if (used <= budget) break;
      used -= index.remove(gone)![1];
      await prefs.remove(_key(gone));
    }
    index[card] = [stamp ?? -1, raw.length, seq];
    await prefs.setString(_key(card), raw);
    await prefs.setString(_indexKey, jsonEncode(index));
  }
}
