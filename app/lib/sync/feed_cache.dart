/// The last live feed per card (T2353), so a reopened log tab shows its
/// lines at once instead of a spinner and the whole feed again. The memory
/// copy serves this run; [PrefsFeedCache] also saves the newest [kFeedKeep]
/// events on close, so the lines are there after an app restart.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/model/json.dart';

/// Events saved per card across restarts.
const kFeedKeep = 50;

/// Where feeds are kept between opens.
abstract interface class FeedCache {
  /// The last feed of [card], or null when none was seen.
  List<Json>? read(String card);

  /// Keeps [feed] as [card]'s newest.
  void write(String card, List<Json> feed);

  /// Makes [card]'s feed last (the feed was closed).
  Future<void> save(String card);
}

/// The feeds of this run only.
class MemoryFeedCache implements FeedCache {
  final _feeds = <String, List<Json>>{};

  @override
  List<Json>? read(String card) => _feeds[card];

  @override
  void write(String card, List<Json> feed) => _feeds[card] = feed;

  @override
  Future<void> save(String card) async {}
}

/// Memory plus the newest [kFeedKeep] events per card in [prefs].
class PrefsFeedCache extends MemoryFeedCache {
  /// Creates the cache.
  new(this.prefs);

  /// The app's preferences.
  final SharedPreferences prefs;

  static String _key(String card) => 'feed.$card';

  @override
  List<Json>? read(String card) {
    final seen = super.read(card);
    if (seen != null) return seen;
    final raw = prefs.getString(_key(card));
    if (raw == null) return null;
    final saved = [
      for (final e in jsonDecode(raw) as List<Object?>)
        if (e is Json) e,
    ];
    super.write(card, saved);
    return saved;
  }

  @override
  Future<void> save(String card) async {
    final feed = super.read(card);
    if (feed == null) return;
    final tail = feed.length > kFeedKeep
        ? feed.sublist(feed.length - kFeedKeep)
        : feed;
    await prefs.setString(_key(card), jsonEncode(tail));
  }
}
