import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/card_parts.dart';
import 'package:todo_implementer/ui/board/needs_links.dart';

import 'support/detail_harness.dart';
import 'support/fakes.dart';

const _lab = 'https://kuhy.duckdns.org/logo-lab';

Map<String, dynamic> _detail(List<String> links) => {
  ...richDetail(),
  'card': card(
    'c1',
    needs: {
      'kind': 'claude_action',
      'text': 'Pick one.',
      'category': 'action',
      'effort': 3,
      'links': links,
    },
  ),
};

void main() {
  test('[T2135] needs parses its links, none when absent', () {
    final row = {
      'kind': 'claude_action',
      'text': 't',
      'category': 'action',
      'effort': 3,
    };
    final withLinks = {
      ...row,
      'links': [_lab],
    };
    expect(Needs.fromJson(withLinks).links, [_lab]);
    expect(Needs.fromJson(row).links, isEmpty);
  });

  test('[T2135] only absolute http and https pages show', () {
    expect(NeedsLinks.isWeb(_lab), isTrue);
    expect(NeedsLinks.isWeb('http://127.0.0.1:4321/x'), isTrue);
    expect(NeedsLinks.isWeb('javascript:alert(1)'), isFalse);
    expect(NeedsLinks.isWeb('file:///etc/passwd'), isFalse);
    expect(NeedsLinks.isWeb('/logo-lab'), isFalse);
  });

  testWidgets('[T2135] the overview shows a link glyph that copies the URL', (
    tester,
  ) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String;
        }
        return null;
      },
    );
    await pumpDetail(tester, detail: _detail([_lab, 'javascript:alert(1)']));
    await settle(tester);
    expect(find.byKey(const ValueKey('needs-link-$_lab')), findsOneWidget);
    expect(find.byIcon(Icons.link), findsOneWidget);
    await hit(tester, find.byKey(const ValueKey('needs-link-$_lab')));
    expect(copied, _lab);
  });

  testWidgets('[T2135] no links draws nothing', (tester) async {
    await pumpDetail(tester, detail: _detail([]));
    await settle(tester);
    expect(find.byIcon(Icons.link), findsNothing);
  });
}
