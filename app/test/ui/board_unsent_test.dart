// T2604: a new task written offline shows on the board at once, marked with
// the unsent glyph until the next sync sends it.
import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/board/board_page.dart';

import '../support/fakes.dart';

void main() {
  testWidgets('[T2604] an unsent card carries the unsent glyph', (
    tester,
  ) async {
    pixel6a(tester);
    final relay = FakeRelay();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildDarkTheme(),
        home: Scaffold(
          body: SafeArea(child: BoardPage(relay: relay)),
        ),
      ),
    );
    relay.push(
      boardJson([
        card('queued-0', status: 'unsent', title: 'buy milk'),
        card('c1'),
      ]),
    );
    await tester.pump();
    expect(find.byKey(const Key('card-unsent')), findsOneWidget);
  });
}
