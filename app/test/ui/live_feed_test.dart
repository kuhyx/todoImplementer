import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/ui/board/live_feed.dart';

import '../support/fakes.dart';

void main() {
  testWidgets('[T2099] the live feed lists the newest activity first', (
    tester,
  ) async {
    pixel6a(tester);
    final relay = FakeRelay();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildDarkTheme(),
        home: Scaffold(
          body: LiveFeed(relay: relay, card: 'c1'),
        ),
      ),
    );
    relay.feeds['c1']!.add([
      for (final t in ['one', 'two', 'three'])
        {'type': 'activity', 'kind': 'result', 'text': t},
    ]);
    await tester.pump();
    double top(String t) => tester.getTopLeft(find.text(t)).dy;
    expect(top('three'), lessThan(top('two')));
    expect(top('two'), lessThan(top('one')));
  });
}
