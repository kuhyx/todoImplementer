/// The images of one text box (Send to Claude or New task details): each
/// is checked, shrunk to fit and tagged `[Image #N]` at the caret. Before the
/// send each image goes up alone as an `image_upload` request and the send
/// names the staged ids `{upload}` (DOCS-native-app-relay.md, "Images").
///
/// No count cap (kuhy, 2026-11-21, T2426): the relay seals a request into one
/// RTDB string (10 MB at most; base64 twice makes it about 16/9 of the
/// bytes), so each image alone fits [kMaxImageBytes].
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/image_tags.dart';

/// One image, so its sealed `image_upload` request stays under RTDB's 10 MB
/// string limit.
const int kMaxImageBytes = 9 * 512 * 1024;

/// Sends one relay request (the board relay's `send`).
typedef SendKind = Future<RelayOutcome> Function(String kind, Json body);

/// The MIME types a keyboard paste may hand in.
const List<String> kImageMimes = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
];

/// Why an image was not added; the strip draws each as a glyph.
enum ImageProblem {
  /// Not png, jpeg, webp or gif.
  type,

  /// Still over [kMaxImageBytes] after shrinking.
  size,

  /// The picker, camera or paste gave nothing readable.
  unavailable,
}

/// Fits [bytes] into [maxBytes]; null when it cannot.
typedef Shrink = Future<Uint8List?> Function(Uint8List bytes, int maxBytes);

/// [bytes] as they are when they fit, else re-encoded as a PNG at 3/4 of the
/// size per step (at most 8 steps); null when nothing fits or it does not
/// decode.
Future<Uint8List?> shrinkToFit(Uint8List bytes, int maxBytes) async {
  if (bytes.length <= maxBytes) return bytes;
  final ui.Image full;
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    full = (await codec.getNextFrame()).image;
  } on Exception {
    return null;
  }
  var scale = 1.0;
  for (var step = 0; step < 8; step++) {
    scale *= 0.75;
    final w = math.max(1, (full.width * scale).round());
    final h = math.max(1, (full.height * scale).round());
    final rec = ui.PictureRecorder();
    ui.Canvas(rec).drawImageRect(
      full,
      ui.Rect.fromLTWH(0, 0, full.width.toDouble(), full.height.toDouble()),
      ui.Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()),
      ui.Paint()..filterQuality = ui.FilterQuality.medium,
    );
    final small = await rec.endRecording().toImage(w, h);
    final data = await small.toByteData(format: ui.ImageByteFormat.png);
    small.dispose();
    final out = data!.buffer.asUint8List();
    if (out.length <= maxBytes) return out;
  }
  return null;
}

/// The images of [text]'s box.
class ImageAttach extends ChangeNotifier {
  /// Images for [text]; [shrink] fits each one (tests pass a fake).
  new(this.text, {Shrink? shrink}) : _shrink = shrink ?? shrinkToFit;

  /// The box the tags go into.
  final TextEditingController text;
  final Shrink _shrink;
  final List<Uint8List> _images = [];
  final List<String?> _ids = []; // the staged upload of each image, once sent
  ImageProblem? _problem;
  int _pending = 0;

  /// True while an image is being checked or shrunk (a paste included).
  bool get busy => _pending > 0;

  /// The images, item N being `[Image #N]`.
  List<Uint8List> get images => List.unmodifiable(_images);

  /// Why the last image was refused; null after a success.
  ImageProblem? get problem => _problem;

  /// Sends each image not sent yet as `image_upload`; returns the `images`
  /// argument (`{upload: id}` in order), or the first refusal. A retry after
  /// a refusal sends only the images that did not go up.
  Future<(List<Json>, RelayFailed?)> upload(SendKind send) async {
    for (var i = 0; i < _images.length; i++) {
      if (_ids[i] != null) continue;
      final out = await send('image_upload', {
        'data_b64': base64Encode(_images[i]),
      });
      if (out is RelayFailed) return (const <Json>[], out);
      final staged = (out as RelayOk).data['upload'];
      final id = staged is Map ? staged['id'] : null;
      if (id is! String) {
        const why = 'image_upload answered no upload id';
        return (
          const <Json>[],
          const RelayFailed(code: 'internal', error: why),
        );
      }
      _ids[i] = id;
    }
    return (
      [
        for (final id in _ids) {'upload': id},
      ],
      null,
    );
  }

  /// Accepts images a keyboard pastes into the box (Gboard's clipboard).
  ContentInsertionConfiguration get paste => ContentInsertionConfiguration(
    allowedMimeTypes: kImageMimes,
    onContentInserted: (content) {
      final data = content.data;
      if (data == null) return refuse(ImageProblem.unavailable);
      unawaited(add(data));
    },
  );

  /// Names [why] as the reason nothing was added.
  void refuse(ImageProblem why) {
    _problem = why;
    notifyListeners();
  }

  /// Adds [bytes] as the next image, or names why not.
  Future<void> add(Uint8List bytes) async {
    _pending++;
    notifyListeners();
    try {
      await _add(bytes);
    } finally {
      _pending--;
      notifyListeners();
    }
  }

  Future<void> _add(Uint8List bytes) async {
    if (imageType(bytes) == null) return refuse(ImageProblem.type);
    final fit = await _shrink(bytes, kMaxImageBytes);
    if (fit == null || fit.length > kMaxImageBytes) {
      return refuse(ImageProblem.size);
    }
    _images.add(fit);
    _ids.add(null);
    _problem = null;
    text.value = insertTag(text.value, _images.length);
    notifyListeners();
  }

  /// Drops image [index] (0-based) and its tag; later tags renumber.
  void remove(int index) {
    _images.removeAt(index);
    _ids.removeAt(index);
    text.text = dropTag(text.text, index + 1);
    notifyListeners();
  }

  /// Puts back a draft's [saved] images (T2493); their tags are in the text.
  void restore(List<Uint8List> saved) {
    _images.addAll(saved);
    _ids.addAll(List.filled(saved.length, null));
    notifyListeners();
  }

  /// No images, no reason shown (after a send went out).
  void clear() {
    _images.clear();
    _ids.clear();
    _problem = null;
    notifyListeners();
  }
}
