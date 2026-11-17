import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/shell/app.dart';
import 'package:todo_implementer/shell/shell.dart';

/// Pixel 6a geometry in physical px (build-mobile-app R7).
void _pixel6a(WidgetTester tester, {double keyboard = 0}) {
  tester.view
    ..physicalSize = const Size(1080, 2400)
    ..devicePixelRatio = 2.625
    ..padding = const FakeViewPadding(top: 132, bottom: 63)
    ..viewInsets = FakeViewPadding(bottom: keyboard);
  addTearDown(tester.view.reset);
}

void _expectNoVerticalScroll(WidgetTester tester) {
  for (final state in tester.stateList<ScrollableState>(
    find.byType(Scrollable),
  )) {
    if (state.position.axis == Axis.vertical) {
      expect(state.position.maxScrollExtent, 0);
    }
  }
}

void main() {
  for (final keyboard in [0.0, 300.0]) {
    testWidgets('fits one Pixel 6a screen (keyboard $keyboard)', (
      tester,
    ) async {
      _pixel6a(tester, keyboard: keyboard);
      await tester.pumpWidget(const TodoImplementerApp());
      _expectNoVerticalScroll(tester);
      final screen = tester.view.physicalSize / tester.view.devicePixelRatio;
      final bottomInset = 63 / 2.625;
      for (final p in shellPages) {
        final rect = tester.getRect(find.byKey(ValueKey('nav-${p.key}')));
        expect(rect.bottom, lessThanOrEqualTo(screen.height - bottomInset));
        expect(rect.top, greaterThan(132 / 2.625));
      }
    });
  }

  testWidgets('each nav icon shows its page and no visible text', (
    tester,
  ) async {
    _pixel6a(tester);
    await tester.pumpWidget(const TodoImplementerApp());
    for (final p in shellPages) {
      await tester.tap(find.byKey(ValueKey('nav-${p.key}')));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey(p.key)), findsOneWidget);
      // textgate: no text outside the bar, and the bar hides its labels.
      expect(
        find.descendant(
          of: find.byKey(ValueKey(p.key)),
          matching: find.byType(Text),
        ),
        findsNothing,
      );
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).labelBehavior,
        NavigationDestinationLabelBehavior.alwaysHide,
      );
    }
  });
}
