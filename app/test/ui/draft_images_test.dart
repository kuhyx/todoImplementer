// T2493: the add-task draft's images live as files (phone, PC) or in the
// preferences (web), apart from the text a keystroke saves.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/ui/board/draft_images.dart';

Uint8List _b(List<int> bytes) => Uint8List.fromList(bytes);

void main() {
  test(
    '[T2493] files keep the images in order and drop the extra ones',
    () async {
      final root = Directory.systemTemp.createTempSync('draft-images');
      addTearDown(() => root.deleteSync(recursive: true));
      final store = FileDraftImages(root: () async => root);
      expect(await store.load(), isEmpty); // no directory yet
      final images = [
        for (var i = 0; i < 11; i++) _b([i, i]),
      ];
      await store.save(images);
      expect(await store.load(), images); // 10 sorts after 2 by number
      final dir = Directory('${root.path}/newtask-draft');
      File('${dir.path}/notes.txt').writeAsStringSync('stray');
      expect(await store.load(), hasLength(11));
      await store.save([
        _b([9]),
      ]);
      expect(await store.load(), [
        _b([9]),
      ]);
      expect(dir.listSync().map((f) => f.uri.pathSegments.last), ['0.img']);
      await store.save(const []);
      expect(dir.listSync(), isEmpty);
    },
  );

  test('[T2493] no support directory reads as no images', () async {
    expect(platformDraftImages(), isA<FileDraftImages>());
    expect(await FileDraftImages().load(), isEmpty);
    final broken = FileDraftImages(
      root: () => Future.error(const FileSystemException('none')),
    );
    expect(await broken.load(), isEmpty);
    await broken.save([
      _b([1]),
    ]);
  });

  test('[T2493] the web form keeps them in the preferences', () async {
    SharedPreferences.setMockInitialValues({});
    final store = PrefsDraftImages();
    expect(await store.load(), isEmpty);
    await store.save([
      _b([1, 2]),
    ]);
    expect(await store.load(), [
      _b([1, 2]),
    ]);
    await store.save(const []);
    expect((await SharedPreferences.getInstance()).getKeys(), isEmpty);
    SharedPreferences.setMockInitialValues({'newtask.draft.images': '["%%"]'});
    expect(await PrefsDraftImages().load(), isEmpty);
    final broken = PrefsDraftImages(
      prefs: () => Future.error(StateError('no prefs')),
    );
    await broken.save([
      _b([1]),
    ]);
  });
}
