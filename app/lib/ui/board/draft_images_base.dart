/// The draft images' store and its preferences form (the web build's).
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:shared_preferences/shared_preferences.dart';

/// Keeps the draft's images; a store that fails reads as no images.
abstract interface class DraftImages {
  /// The images, item N being `[Image #N]`; [] when none or on failure.
  Future<List<Uint8List>> load();

  /// Keeps [images] in place of the ones kept before.
  Future<void> save(List<Uint8List> images);
}

/// The images as one base64 list in the preferences.
class PrefsDraftImages implements DraftImages {
  /// The store; [prefs] opens the preferences (tests pass a failing one).
  new({Future<SharedPreferences> Function()? prefs})
    : _prefs = prefs ?? SharedPreferences.getInstance;

  final Future<SharedPreferences> Function() _prefs;
  static const _key = 'newtask.draft.images';

  @override
  Future<List<Uint8List>> load() async {
    try {
      final raw = (await _prefs()).getString(_key);
      return [
        for (final b in jsonDecode(raw ?? '[]') as List<Object?>)
          base64Decode(b! as String),
      ];
    } on Object {
      return const [];
    }
  }

  @override
  Future<void> save(List<Uint8List> images) async {
    try {
      final prefs = await _prefs();
      await (images.isEmpty
          ? prefs.remove(_key)
          : prefs.setString(
              _key,
              jsonEncode(images.map(base64Encode).toList()),
            ));
    } on Object {
      // Blocked or full (a web build's ~5 MB): the images live in the page.
    }
  }
}
