import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/config/firebase_config.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';
import 'package:todo_implementer/sync/services.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('device id: made once per install, then reused', () async {
    SharedPreferences.setMockInitialValues({});
    final first = await deviceId();
    expect(first, matches(RegExp(r'^[0-9a-f-]{36}$')));
    expect(await deviceId(), first);
  });

  test('open wires auth, a sealed client gate and the relay', () async {
    SharedPreferences.setMockInitialValues({'todoimpl.device_id': 'd1'});
    const config = FirebaseConfig(
      apiKey: 'k',
      databaseUrl: 'https://db.example',
      syncUid: 'u',
      serverClientId: 'w',
    );
    final s = await AppServices.open(config);
    expect(s.config.isComplete, isTrue);
    expect(s.gate.locked, isTrue);
    expect((s.relay as RtdbBoardRelay).dev, 'd1');
    expect(s.auth.config, config);
    expect(s.sessions, isNotNull);
    expect((s.relay as RtdbBoardRelay).moves(), isA<Stream<int>>());
    expect(FirebaseConfig.compiled, isA<FirebaseConfig>());
  });
}
