/// T2535: a note's images show as thumbnails in the card sheet and the
/// detail page, fetched over the relay (`image_get`); a tap opens full size.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/board.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/board/note_images.dart';

import '../support/detail_harness.dart';
import '../support/fakes.dart';

const _pic = {'folder': '3d6cd2ea-de63', 'file': '1.jpg'};

Json _withPics(Json c) => {
  ...c,
  'images': [_pic],
};

Future<FakeRelay> _sheet(WidgetTester tester, {RelayOutcome? image}) async {
  pixel6a(tester);
  final relay = FakeRelay()
    ..outcomes['image_get'] =
        image ?? const RelayOk({'data_b64': tinyPng, 'type': 'image/png'});
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: BoardPage(relay: relay)),
    ),
  );
  relay.push(boardJson([_withPics(card('c1'))]));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('card-c1')));
  await tester.pumpAndSettle();
  return relay;
}

void main() {
  setUp(clearNoteImages);

  test('[T2535] a card reads its images, none when absent', () {
    final c = TaskCard.fromJson(_withPics(card('c1')));
    expect(c.images.single.folder, '3d6cd2ea-de63');
    expect(c.images.single.file, '1.jpg');
    expect(TaskCard.fromJson(card('c2')).images, isEmpty);
  });

  testWidgets('[T2535] the sheet shows the thumbnail; a tap opens it full', (
    tester,
  ) async {
    final relay = await _sheet(tester);
    expect(relay.sent.where((s) => s.$1 == 'image_get').single.$2, _pic);
    final thumb = find.byKey(const ValueKey('note-image-3d6cd2ea-de63/1.jpg'));
    expect(thumb, findsOneWidget);
    await tester.tap(thumb);
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsOneWidget);
    await tester.tap(find.byType(InteractiveViewer));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsNothing);
  });

  test(
    '[T2535] the cache keeps the newest images and refetches the oldest',
    () async {
      final relay = FakeRelay()
        ..outcomes['image_get'] = const RelayOk({'png_b64': tinyPng});
      for (var i = 0; i <= kImageCacheSize; i++) {
        expect(await loadNoteImage(relay, NoteImage('f', '$i.png')), isNotNull);
      }
      await loadNoteImage(relay, NoteImage('f', '$kImageCacheSize.png'));
      expect(relay.sent.length, kImageCacheSize + 1);
      await loadNoteImage(relay, const NoteImage('f', '0.png'));
      expect(relay.sent.length, kImageCacheSize + 2);
    },
  );

  testWidgets('[T2535] an image the PC cannot send shows a broken glyph', (
    tester,
  ) async {
    await _sheet(
      tester,
      image: const RelayFailed(code: 'not_found', error: 'gone', retry: false),
    );
    expect(find.byIcon(Icons.broken_image_outlined), findsOneWidget);
  });

  testWidgets('[T2535] the detail page shows the note images too', (
    tester,
  ) async {
    final detail = richDetail();
    final relay = await pumpDetail(
      tester,
      detail: {...detail, 'card': _withPics(detail['card'] as Json)},
    );
    await settle(tester);
    expect(relay.sent.where((s) => s.$1 == 'image_get').single.$2, _pic);
    expect(
      find.byKey(const ValueKey('note-image-3d6cd2ea-de63/1.jpg')),
      findsOneWidget,
    );
  });
}
