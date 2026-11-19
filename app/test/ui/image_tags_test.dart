// T2330: `[Image #N]` tags in the app follow the page's rules
// (web/src/lib/image-tags.ts): a tag lands at the caret with a space on each
// side unless one is there, removing image N drops its tag and renumbers the
// later ones, and only png, jpeg, webp and gif bytes count as images.
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/ui/board/image_tags.dart';

TextEditingValue _at(String text, int caret, [int? end]) => TextEditingValue(
  text: text,
  selection: TextSelection(baseOffset: caret, extentOffset: end ?? caret),
);

Uint8List _bytes(List<int> head) => Uint8List.fromList([...head, 0, 0, 0, 0]);

void main() {
  test('[T2330] a tag goes in at the caret with spaces around it', () {
    final mid = insertTag(_at('see this one', 4), 1);
    expect(mid.text, 'see [Image #1] this one');
    expect(mid.selection.baseOffset, 'see [Image #1] '.length);
    expect(insertTag(_at('', 0), 2).text, '[Image #2] ');
    expect(insertTag(_at('look', 4), 1).text, 'look [Image #1] ');
    expect(insertTag(_at('ab', 1), 1).text, 'a [Image #1] b');
    expect(insertTag(_at('a XX b', 2, 4), 3).text, 'a [Image #3] b');
  });

  test('[T2330] no caret yet: the tag goes at the end', () {
    const none = TextEditingValue(text: 'note');
    final out = insertTag(none, 1);
    expect(out.text, 'note [Image #1] ');
    expect(out.selection.baseOffset, out.text.length);
  });

  test('[T2330] removing image N drops its tag and renumbers the rest', () {
    const text = '[Image #1] a [Image #2] b [Image #3] c';
    expect(dropTag(text, 2), '[Image #1] a b [Image #2] c');
    expect(dropTag(text, 1), 'a [Image #1] b [Image #2] c');
    expect(dropTag('x [Image #1]', 1), 'x ');
  });

  test('[T2330] only png, jpeg, webp and gif bytes are images', () {
    expect(imageType(_bytes([0x89, 0x50, 0x4E, 0x47, 13, 10, 26, 10])), 'png');
    expect(imageType(_bytes([0x89, 0x50, 0x4E, 0x47])), isNull);
    expect(imageType(_bytes([0xFF, 0xD8, 0xFF])), 'jpeg');
    expect(imageType(_bytes('GIF89a'.codeUnits)), 'gif');
    expect(imageType(_bytes('GIF87a'.codeUnits)), 'gif');
    expect(imageType(_bytes('GIF8'.codeUnits)), isNull);
    expect(
      imageType(_bytes([...'RIFF'.codeUnits, 1, 2, 3, 4, ...'WEBP'.codeUnits])),
      'webp',
    );
    expect(imageType(_bytes([0, 0, 0, 0x18, ...'ftypheic'.codeUnits])), isNull);
    expect(imageType(Uint8List(2)), isNull);
  });
}
