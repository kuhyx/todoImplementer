// T2603: the on-device copy behind OfflineRelay: a byte budget (the web
// build's localStorage holds about 5 MB) and corrupt saved data.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/sync/local_copy.dart';

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  test('[T2603] the details stay under the storage budget', () async {
    final copy = PrefsLocalCopy(prefs, budget: 100);
    await copy.saveDetail('old', {'t': 'a' * 40}, stamp: 1);
    await copy.saveDetail('mid', {'t': 'b' * 40}, stamp: 1);
    await copy.saveDetail('new', {'t': 'c' * 40}, stamp: 1);
    await copy.saveDetail('huge', {'t': 'd' * 400}, stamp: 1);
    final fresh = PrefsLocalCopy(prefs, budget: 100);
    expect(fresh.detail('old'), isNull);
    expect(fresh.detail('huge'), isNull);
    expect(fresh.detail('mid'), isNotNull);
    expect(fresh.detail('new'), isNotNull);
    expect(fresh.stamp('new'), 1);
  });

  test('[T2603] a corrupt saved copy reads as nothing', () async {
    SharedPreferences.setMockInitialValues({
      'local.board': '{oops',
      'local.detail.c1': '[1]',
      'local.details': '{"c1": "x"}',
    });
    final copy = PrefsLocalCopy(await SharedPreferences.getInstance());
    expect(copy.board(), isNull);
    expect(copy.detail('c1'), isNull);
    expect(copy.stamp('c1'), isNull);
  });
}
