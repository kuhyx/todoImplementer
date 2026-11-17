/// Everything the app talks to, built once per start.
library;

import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/config/firebase_config.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/google_sign_in_backend.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';
import 'package:uuid/uuid.dart';

const _devKey = 'todoimpl.device_id';

/// This install's device id: a uuid made on first start, never a fixed
/// `phone` or `pc` (two installs must never share one).
Future<String> deviceId() async {
  final prefs = await SharedPreferences.getInstance();
  final known = prefs.getString(_devKey);
  if (known != null) return known;
  final made = const Uuid().v4();
  await prefs.setString(_devKey, made);
  return made;
}

/// The session, the sealed client, the key gate and the board relay.
class AppServices {
  /// Creates the bundle (tests pass fakes).
  const new({
    required this.config,
    required this.auth,
    required this.gate,
    required this.relay,
  });

  /// Builds the production bundle for [config].
  static Future<AppServices> open(FirebaseConfig config) async {
    final dev = await deviceId();
    final auth = RelayAuth(
      config: config,
      googleToken: googleIdToken,
      store: secureCredentialStore('todoimpl.firebase.credentials'),
    );
    final client = RtdbClient(
      layout: kTodoImplLayout,
      databaseUrl: config.databaseUrl,
      idToken: auth.idToken,
      sealRequired: true,
    );
    return AppServices(
      config: config,
      auth: auth,
      gate: E2eGate(client: client),
      relay: RtdbBoardRelay.live(
        client: client,
        stream: RtdbStream(client),
        dev: dev,
      ),
    );
  }

  /// Build-time identifiers.
  final FirebaseConfig config;

  /// The Firebase session.
  final RelayAuth auth;

  /// Opens the e2e key from the keystore passphrase.
  final E2eGate gate;

  /// The board's link to the PC.
  final BoardRelay relay;
}
