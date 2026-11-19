/// `[Image #N]` tags for Send to Claude and New task, the page's rules
/// (web/src/lib/image-tags.ts) in Dart: where a tag goes, how removing an
/// image renumbers the rest, and which bytes count as an image
/// (`requests.schema.json#/$defs/image_ref`: png, jpeg, webp or gif).
library;

import 'package:flutter/services.dart';

final _tag = RegExp(r'\[Image #(\d+)\]( ?)');
final _space = RegExp(r'\s');

bool _blank(String text, int at) =>
    at >= 0 && at < text.length && _space.hasMatch(text[at]);

/// [value] with `[Image #n]` at the caret (replacing a selection), a space
/// on each side unless one is there; the caret ends after the tag. With no
/// caret yet the tag goes at the end.
TextEditingValue insertTag(TextEditingValue value, int n) {
  final text = value.text;
  final sel = value.selection;
  final start = sel.isValid ? sel.start : text.length;
  final end = sel.isValid ? sel.end : text.length;
  final lead = start == 0 || _blank(text, start - 1) ? '' : ' ';
  final trail = _blank(text, end) ? '' : ' ';
  final tag = '$lead[Image #$n]$trail';
  return TextEditingValue(
    text: text.replaceRange(start, end, tag),
    selection: TextSelection.collapsed(offset: start + tag.length),
  );
}

/// [text] without image [n]'s tag (and the space after it); later tags
/// move down by one.
String dropTag(String text, int n) => text.replaceAllMapped(_tag, (m) {
  final at = int.parse(m[1]!);
  if (at == n) return '';
  return '[Image #${at > n ? at - 1 : at}]${m[2]}';
});

bool _starts(Uint8List b, List<int> head, [int from = 0]) {
  if (b.length < from + head.length) return false;
  for (var i = 0; i < head.length; i++) {
    if (b[from + i] != head[i]) return false;
  }
  return true;
}

/// The type the server reads from [bytes] (png, jpeg, webp, gif), or null;
/// the same first bytes as `newtask/noteimages.py`.
String? imageType(Uint8List bytes) {
  if (_starts(bytes, const [0x89, 0x50, 0x4E, 0x47, 13, 10, 26, 10])) {
    return 'png';
  }
  if (_starts(bytes, const [0xFF, 0xD8, 0xFF])) return 'jpeg';
  if (_starts(bytes, 'GIF87a'.codeUnits) ||
      _starts(bytes, 'GIF89a'.codeUnits)) {
    return 'gif';
  }
  if (_starts(bytes, 'RIFF'.codeUnits) && _starts(bytes, 'WEBP'.codeUnits, 8)) {
    return 'webp';
  }
  return null;
}
