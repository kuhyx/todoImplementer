import 'package:flutter_test/flutter_test.dart';
import 'package:todo_implementer/ui/usage/usage_page.dart';
import 'package:todo_implementer/model/usage/route.dart';

void main() {
  test('every usage view has its own one-word tooltip', () {
    final tips = UsageView.values.map(tabTooltip).toList();
    expect(tips.toSet().length, UsageView.values.length);
    expect(tips.every((t) => t.isNotEmpty && !t.contains(' ')), isTrue);
  });
}
