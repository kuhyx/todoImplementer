/// Everything the app talks to, built once per start.
library;

import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:todo_implementer/config/firebase_config.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/sync/feed_cache.dart';
import 'package:todo_implementer/sync/google_sign_in_backend.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/local_copy.dart';
import 'package:todo_implementer/sync/offline_relay.dart';
import 'package:todo_implementer/sync/rtdb_board_relay.dart';
import 'package:todo_implementer/sync/sessions_feed.dart';
import 'package:todo_implementer/sync/usage_relay.dart';
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
    this.sessions,
    this.usage,
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
    // One listen for every page: board, sessions and usage share the
    // request hub and the `rev` watcher.
    final stream = RtdbStream(client);
    final hub = RequestHub(stream, fullPath('requests'));
    final rev = RevWatcher(stream, fullPath('rev'), yieldTo: hub.inFlight);
    final live = RtdbBoardRelay(
      client: client,
      dev: dev,
      watch: hub.watch,
      moves: () => rev.changesOf('board'),
      // Without these the relay falls back to never-emitting seams: the
      // live feed spun forever and merges never refreshed (T2310).
      revOf: rev.changesOf,
      listen: stream.listen,
      feeds: PrefsFeedCache(await SharedPreferences.getInstance()),
    );
    // Offline-first (T2603): the last board and card details stay on disk.
    final relay = OfflineRelay(
      live,
      PrefsLocalCopy(await SharedPreferences.getInstance()),
    );
    return AppServices(
      config: config,
      auth: auth,
      gate: E2eGate(client: client),
      relay: relay,
      sessions: rtdbSessionsFeed(
        client: client,
        moves: rev.changesOf('sessions'),
      ),
      usage: RtdbUsageRelay(
        send: relay.send,
        read: () => client.get(fullPath('snap/usage')),
        moves: () => rev.changesOf('usage'),
      ),
    );
  }

  /// Build-time identifiers.
  final FirebaseConfig config;

  /// The Firebase session.
  final RelayAuth auth;

  /// Opens the e2e key from the keystore passphrase.
  final E2eGate gate;

  /// The board's link to the PC (and every page's request sender).
  final BoardRelay relay;

  /// The sessions page's `snap/sessions` feed (null: the page glyph).
  final SessionsFeed? sessions;

  /// The usage page's link to the PC (null in tests of the board alone).
  final UsageRelay? usage;
}
