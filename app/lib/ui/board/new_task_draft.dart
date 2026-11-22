/// The add-task page's draft (T2493): a refused send ("bad token"), a
/// closed page or a killed app must not lose a task being written. The text
/// and the repo picks are saved on every change, the images whenever the list
/// changes (apart, so a keystroke never rewrites megabytes). Only a task that
/// went out clears it; an empty box with no images is no draft. A store that
/// fails only means no draft: the page never fails over it.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/repo_chooser.dart';

/// What the page held.
class NewTaskDraft {
  /// A draft.
  const new({
    required this.text,
    required this.picked,
    this.scope,
    this.open = false,
    this.images = const [],
  });

  /// The box (its `[Image #N]` tags included).
  final String text;

  /// None, all or some repos; null when nothing was chosen.
  final RepoScope? scope;

  /// The repos still to send to.
  final List<String> picked;

  /// True when the chooser was open.
  final bool open;

  /// The images, item N being `[Image #N]`.
  final List<Uint8List> images;
}

/// Where the draft is kept.
abstract interface class NewTaskDrafts {
  /// The draft, or null when there is none.
  Future<NewTaskDraft?> load();

  /// Keeps the text and the picks of [draft] (not its images).
  Future<void> saveState(NewTaskDraft draft);

  /// Keeps [images].
  Future<void> saveImages(List<Uint8List> images);

  /// No draft any more.
  Future<void> clear();
}

/// A draft of this run only (tests).
class MemoryNewTaskDrafts implements NewTaskDrafts {
  NewTaskDraft? _state;
  List<Uint8List> _images = const [];

  @override
  Future<NewTaskDraft?> load() async => switch (_state) {
    final s? => NewTaskDraft(
      text: s.text,
      scope: s.scope,
      picked: s.picked,
      open: s.open,
      images: _images,
    ),
    null => null,
  };

  @override
  Future<void> saveState(NewTaskDraft draft) async => _state = draft;

  @override
  Future<void> saveImages(List<Uint8List> images) async => _images = images;

  @override
  Future<void> clear() async {
    _state = null;
    _images = const [];
  }
}

/// The draft in the app's preferences: one key for the text and the picks,
/// one for the images (base64).
class PrefsNewTaskDrafts implements NewTaskDrafts {
  /// The store; [prefs] opens the preferences (tests pass a failing one).
  new({Future<SharedPreferences> Function()? prefs})
    : _prefs = prefs ?? SharedPreferences.getInstance;

  final Future<SharedPreferences> Function() _prefs;
  static const _state = 'newtask.draft';
  static const _images = 'newtask.draft.images';

  static List<Uint8List> _decode(String? raw) {
    try {
      return [
        for (final b in jsonDecode(raw ?? '[]') as List<Object?>)
          base64Decode(b! as String),
      ];
    } on Object {
      return const [];
    }
  }

  @override
  Future<NewTaskDraft?> load() async {
    try {
      final prefs = await _prefs();
      final raw = jsonDecode(prefs.getString(_state) ?? 'null');
      if (raw is! Map || raw['text'] is! String) return null;
      final scope = raw['scope'];
      final picked = raw['picked'];
      return NewTaskDraft(
        text: raw['text'] as String,
        scope: RepoScope.values.where((s) => s.name == scope).firstOrNull,
        picked: [
          if (picked is List)
            for (final p in picked)
              if (p is String) p,
        ],
        open: raw['open'] == true,
        images: _decode(prefs.getString(_images)),
      );
    } on Object {
      return null;
    }
  }

  Future<void> _write(Future<void> Function(SharedPreferences p) act) async {
    try {
      await act(await _prefs());
    } on Object {
      // Blocked or full (a web build's ~5 MB): the draft lives in the page.
    }
  }

  @override
  Future<void> saveState(NewTaskDraft draft) => _write(
    (p) => p.setString(
      _state,
      jsonEncode({
        'text': draft.text,
        'scope': draft.scope?.name,
        'picked': draft.picked,
        'open': draft.open,
      }),
    ),
  );

  @override
  Future<void> saveImages(List<Uint8List> images) => _write(
    (p) => p.setString(_images, jsonEncode(images.map(base64Encode).toList())),
  );

  @override
  Future<void> clear() => _write((p) async {
    await p.remove(_state);
    await p.remove(_images);
  });
}

/// The store the page uses (tests swap in a [MemoryNewTaskDrafts]).
NewTaskDrafts newTaskDrafts = PrefsNewTaskDrafts();

/// Ties the page's box and images to the store: [state] is the page now.
class DraftKeeper {
  /// A keeper for [text] and [images].
  new(this.text, this.images, this.state) : store = newTaskDrafts;

  /// The store.
  final NewTaskDrafts store;

  /// The box.
  final TextEditingController text;

  /// The box's images.
  final ImageAttach images;

  /// The page as a draft (text and picks).
  final NewTaskDraft Function() state;
  bool _ready = false;
  bool _done = false;
  List<Uint8List> _saved = const [];

  /// Reads the draft, then saves every change; the draft is handed to
  /// [apply] only while the box and the images are still empty.
  Future<void> start(void Function(NewTaskDraft draft) apply) async {
    text.addListener(keep);
    images.addListener(_keepImages);
    final found = await store.load();
    _ready = true;
    _saved = found?.images ?? const [];
    if (found != null && text.text.isEmpty && images.images.isEmpty) {
      images.restore(found.images);
      apply(found);
    }
    keep();
    _keepImages();
  }

  /// Saves the text and the picks (an empty page clears the draft).
  void keep() {
    if (!_ready || _done) return;
    final now = state();
    unawaited(
      now.text.trim().isEmpty && images.images.isEmpty
          ? store.clear()
          : store.saveState(now),
    );
  }

  void _keepImages() {
    final now = images.images;
    final same =
        now.length == _saved.length &&
        [for (var i = 0; i < now.length; i++) identical(now[i], _saved[i])]
            .every((b) => b);
    if (!_ready || _done || same) return;
    _saved = now;
    unawaited(store.saveImages(now));
    keep();
  }

  /// The task went out: no draft, nothing saved after this.
  Future<void> finish() async {
    _done = true;
    await store.clear();
  }

  /// Stops listening.
  void dispose() {
    text.removeListener(keep);
    images.removeListener(_keepImages);
  }
}
