import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/shell/app.dart';
import 'package:todo_implementer/shell/night_lock.dart';

Widget _app(DateTime at) => MaterialApp(
  home: NightLock(now: () => at, child: const Text('board')),
);

void main() {
  test('the night runs 22:55 to 05:55 and wraps midnight', () {
    bool at(int h, int m) => isNight(DateTime(2026, 11, 21, h, m));
    expect(at(22, 54), isFalse);
    expect(at(22, 55), isTrue);
    expect(at(0, 0), isTrue);
    expect(at(5, 54), isTrue);
    expect(at(5, 55), isFalse);
    expect(at(12, 0), isFalse);
  });

  testWidgets('at night the board is hidden behind a moon', (tester) async {
    await tester.pumpWidget(_app(DateTime(2026, 11, 21, 23)));
    expect(find.text('board'), findsNothing);
    expect(find.byIcon(Icons.bedtime), findsOneWidget);
  });

  testWidgets('by day the board shows', (tester) async {
    await tester.pumpWidget(_app(DateTime(2026, 11, 21, 12)));
    expect(find.text('board'), findsOneWidget);
    expect(find.byIcon(Icons.bedtime), findsNothing);
  });

  testWidgets('the lock lifts by itself in the morning', (tester) async {
    var at = DateTime(2026, 11, 21, 5, 54);
    await tester.pumpWidget(
      MaterialApp(
        home: NightLock(now: () => at, child: const Text('board')),
      ),
    );
    expect(find.text('board'), findsNothing);
    at = DateTime(2026, 11, 21, 5, 55);
    await tester.pump(const Duration(minutes: 1));
    expect(find.text('board'), findsOneWidget);
  });

  testWidgets('the whole app sits behind the lock', (tester) async {
    final day = nightClock;
    nightClock = () => DateTime(2026, 11, 21, 23);
    addTearDown(() => nightClock = day);
    await tester.pumpWidget(const TodoImplementerApp());
    expect(find.byIcon(Icons.bedtime), findsOneWidget);
  });
}
