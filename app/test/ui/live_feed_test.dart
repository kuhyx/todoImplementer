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

  Future<FakeRelay> feedOn(WidgetTester tester) async {
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
    return relay;
  }

  final spinner = find.byType(CircularProgressIndicator);
  final empty = find.byKey(const Key('feed-empty'));

  testWidgets('[T2310] a feed that never answers stops spinning after 5 s', (
    tester,
  ) async {
    final relay = await feedOn(tester);
    expect(spinner, findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    expect(spinner, findsNothing);
    expect(empty, findsOneWidget);
    relay.feeds['c1']!.add([
      {'type': 'activity', 'kind': 'text', 'text': 'late'},
    ]);
    await tester.pump();
    expect(find.text('late'), findsOneWidget);
    expect(empty, findsNothing);
  });

  testWidgets('[T2310] an empty first read shows the empty state at once', (
    tester,
  ) async {
    final relay = await feedOn(tester);
    relay.feeds['c1']!.add(const []);
    await tester.pump();
    expect(spinner, findsNothing);
    expect(empty, findsOneWidget);
    relay.feeds['c1']!.add([
      {'type': 'stage', 'stage': 'needs_you'},
    ]);
    await tester.pump();
    expect(find.byKey(const Key('feed-stage')), findsOneWidget);
    expect(empty, findsOneWidget);
  });
}
