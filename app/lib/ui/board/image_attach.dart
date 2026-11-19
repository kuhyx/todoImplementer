/// The images of one text box (Send to Claude or New task details): each
/// is checked, shrunk to fit and tagged `[Image #N]` at the caret, then sent
/// inline as `{data_b64}` (DOCS-native-app-relay.md, "Images").
///
/// Two caps: the server takes at most 6 MB per image, and the relay seals a
/// whole request into one RTDB string (10 MB at most; base64 twice makes it
/// about 16/9 of the bytes), so all images of one request share
/// [kMaxTotalBytes].
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/ui/board/image_tags.dart';

/// At most this many images per message (`image_refs` maxItems).
const int kMaxImages = 8;

/// The server's cap on one decoded inline image.
const int kMaxImageBytes = 6 * 1024 * 1024;

/// All images of one request together, so the sealed request stays under
/// RTDB's 10 MB string limit.
const int kMaxTotalBytes = 9 * 512 * 1024;

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

  /// Still over the room left after shrinking.
  size,

  /// Already [kMaxImages].
  count,

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
  ImageProblem? _problem;
  int _pending = 0;

  /// True while an image is being checked or shrunk (a paste included).
  bool get busy => _pending > 0;

  /// The images, item N being `[Image #N]`.
  List<Uint8List> get images => List.unmodifiable(_images);

  /// Why the last image was refused; null after a success.
  ImageProblem? get problem => _problem;

  int get _total => _images.fold(0, (sum, b) => sum + b.length);

  /// The `images` argument: inline base64, in order.
  List<Json> get refs => [
    for (final b in _images) {'data_b64': base64Encode(b)},
  ];

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
    if (_images.length >= kMaxImages) return refuse(ImageProblem.count);
    if (imageType(bytes) == null) return refuse(ImageProblem.type);
    final room = math.min(kMaxImageBytes, kMaxTotalBytes - _total);
    final fit = room <= 0 ? null : await _shrink(bytes, room);
    if (fit == null || fit.length > room) return refuse(ImageProblem.size);
    _images.add(fit);
    _problem = null;
    text.value = insertTag(text.value, _images.length);
    notifyListeners();
  }

  /// Drops image [index] (0-based) and its tag; later tags renumber.
  void remove(int index) {
    _images.removeAt(index);
    text.text = dropTag(text.text, index + 1);
    notifyListeners();
  }

  /// No images, no reason shown (after a send went out).
  void clear() {
    _images.clear();
    _problem = null;
    notifyListeners();
  }
}
