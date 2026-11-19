// T2331: the app's image list for Send to Claude and New task: at most 8,
// png/jpeg/webp/gif only, each shrunk to fit 6 MB and the relay's total
// budget, the refusal named by its glyph, inline `{data_b64}` refs in order.
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/image_tags.dart';

import '../support/detail_harness.dart' show tinyPng;

final Uint8List png = base64Decode(tinyPng);
final Uint8List heic = Uint8List.fromList([
  0,
  0,
  0,
  0x18,
  ...'ftypheic'.codeUnits,
]);

/// A [side] x [side] PNG of random pixels drawn with dart:ui (it barely
/// compresses, so its size follows its area).
Future<Uint8List> noisyPng(int side) async {
  final rec = ui.PictureRecorder();
  final canvas = ui.Canvas(rec);
  var seed = 12345;
  for (var i = 0; i < side; i++) {
    for (var j = 0; j < side; j++) {
      seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
      canvas.drawRect(
        ui.Rect.fromLTWH(i.toDouble(), j.toDouble(), 1, 1),
        ui.Paint()..color = ui.Color(0xFF000000 | (seed & 0xFFFFFF)),
      );
    }
  }
  final image = await rec.endRecording().toImage(side, side);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  return data!.buffer.asUint8List();
}

void main() {
  late TextEditingController text;
  late List<int> rooms;
  late ImageAttach attach;

  setUp(() {
    text = TextEditingController();
    rooms = [];
    attach = ImageAttach(
      text,
      shrink: (bytes, room) async {
        rooms.add(room);
        return bytes;
      },
    );
  });

  test('[T2331] eight images, each tagged; the ninth is refused', () async {
    for (var i = 0; i < kMaxImages; i++) {
      await attach.add(png);
    }
    expect(attach.images, hasLength(8));
    expect(attach.problem, isNull);
    expect(text.text, contains('[Image #8]'));
    await attach.add(png);
    expect(attach.images, hasLength(8));
    expect(attach.problem, ImageProblem.count);
    expect(text.text, isNot(contains('[Image #9]')));
  });

  test('[T2331] a HEIC or other non-image is refused untouched', () async {
    await attach.add(heic);
    expect(attach.images, isEmpty);
    expect(attach.problem, ImageProblem.type);
    expect(text.text, isEmpty);
    expect(rooms, isEmpty);
  });

  test('[T2331] each image is shrunk to the room it has left', () async {
    await attach.add(png);
    // The relay's total budget is below the server's 6 MB per image.
    expect(kMaxTotalBytes, lessThan(kMaxImageBytes));
    expect(rooms.single, kMaxTotalBytes);
    final p = png.length;
    final big = Uint8List.fromList([
      ...png,
      ...List.filled(kMaxTotalBytes - 3 * p, 0),
    ]);
    await attach.add(big);
    expect(rooms.last, kMaxTotalBytes - p);
    await attach.add(png);
    expect(rooms.last, p);
    expect(attach.images, hasLength(3));
    await attach.add(png);
    expect(attach.problem, ImageProblem.size);
    expect(attach.images, hasLength(3));
    final refused = ImageAttach(text, shrink: (_, _) async => null);
    await refused.add(png);
    expect(refused.problem, ImageProblem.size);
    expect(refused.images, isEmpty);
  });

  test('[T2331] remove renumbers; refs are inline base64 in order', () async {
    final other = Uint8List.fromList([...png, 1]);
    await attach.add(png);
    await attach.add(other);
    await attach.add(png);
    attach.remove(0);
    expect(text.text, '[Image #1] [Image #2] ');
    expect(attach.refs, [
      {'data_b64': base64Encode(other)},
      {'data_b64': base64Encode(png)},
    ]);
    await attach.add(heic);
    attach.clear();
    expect(attach.images, isEmpty);
    expect(attach.problem, isNull);
  });

  test(
    '[T2331] a pasted image is added; an unreadable paste is named',
    () async {
      final paste = attach.paste;
      expect(paste.allowedMimeTypes, containsAll(['image/png', 'image/gif']));
      paste.onContentInserted!(
        KeyboardInsertedContent(
          mimeType: 'image/png',
          uri: 'content://x',
          data: png,
        ),
      );
      await pumpEventQueue();
      expect(attach.images, hasLength(1));
      paste.onContentInserted!(
        const KeyboardInsertedContent(
          mimeType: 'image/png',
          uri: 'content://y',
        ),
      );
      expect(attach.problem, ImageProblem.unavailable);
    },
  );

  testWidgets('[T2331] shrinkToFit scales a big PNG under the cap', (
    tester,
  ) async {
    await tester.runAsync(() async {
      final big = await noisyPng(200);
      expect(await shrinkToFit(png, 100), same(png));
      final small = await shrinkToFit(big, big.length ~/ 3);
      expect(small, isNotNull);
      expect(small!.length, lessThanOrEqualTo(big.length ~/ 3));
      expect(imageType(small), 'png');
      expect(await shrinkToFit(big, 10), isNull);
      expect(await shrinkToFit(heic, 1), isNull);
    });
  });
}
