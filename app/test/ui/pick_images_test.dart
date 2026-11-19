// T2338: the real platform picker `pickImages` (image_picker over its method
// channel) has to ask for a 1600 px, quality 80 re-encode and hand back the
// picked files' bytes; every other test swaps the picker for a fake.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/ui/board/image_strip.dart';

const MethodChannel _channel = MethodChannel('plugins.flutter.io/image_picker');

/// Answers the channel with [paths] and records each call.
List<MethodCall> _answer(List<String> paths) {
  final calls = <MethodCall>[];
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(_channel, (call) async {
        calls.add(call);
        return call.method == 'pickMultiImage'
            ? paths
            : (paths.isEmpty ? null : paths.first);
      });
  addTearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null),
  );
  return calls;
}

List<String> _files(List<List<int>> contents) {
  final dir = Directory.systemTemp.createTempSync('pick_images_test');
  addTearDown(() => dir.deleteSync(recursive: true));
  return [
    for (var i = 0; i < contents.length; i++)
      (File('${dir.path}/$i.jpg')..writeAsBytesSync(contents[i])).path,
  ];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('[T2338] gallery with room for many uses the multi picker', () async {
    final calls = _answer(
      _files([
        [1, 2],
        [3],
      ]),
    );
    final out = await pickImages(PickFrom.gallery, 5);
    expect(out, [
      Uint8List.fromList([1, 2]),
      Uint8List.fromList([3]),
    ]);
    expect(calls.single.method, 'pickMultiImage');
    final args = calls.single.arguments as Map<Object?, Object?>;
    expect(args['maxWidth'], 1600);
    expect(args['maxHeight'], 1600);
    expect(args['imageQuality'], 80);
    expect(args['limit'], 5);
  });

  test('[T2338] gallery with room for one picks a single image', () async {
    final calls = _answer(
      _files([
        [9],
      ]),
    );
    final out = await pickImages(PickFrom.gallery, 1);
    expect(out, [
      Uint8List.fromList([9]),
    ]);
    final args = calls.single.arguments as Map<Object?, Object?>;
    expect(calls.single.method, 'pickImage');
    expect(args['source'], 1);
    expect(args['imageQuality'], 80);
  });

  test('[T2338] camera takes one photo from the camera source', () async {
    final calls = _answer(
      _files([
        [4, 5],
      ]),
    );
    final out = await pickImages(PickFrom.camera, 8);
    expect(out, [
      Uint8List.fromList([4, 5]),
    ]);
    expect((calls.single.arguments as Map<Object?, Object?>)['source'], 0);
  });

  test('[T2338] a cancelled pick gives no images', () async {
    _answer(const []);
    expect(await pickImages(PickFrom.camera, 8), isEmpty);
    expect(await pickImages(PickFrom.gallery, 1), isEmpty);
  });
}
