/// The Firebase identifiers this build talks to.
///
/// The literal values live in the gitignored `firebase_local.dart`, written
/// by `tool/write_firebase_config.dart`. The repo is public, so the uid and
/// API key never appear in source (DOCS-native-app.md).
library;

import 'package:rtdb_relay/rtdb_relay.dart' show RelayFirebaseConfig;
import 'package:todo_implementer/config/firebase_local.dart' as local;

/// The four identifiers the sync layer needs.
class FirebaseConfig extends RelayFirebaseConfig {
  /// Creates a config; tests pass fakes.
  const new({
    required super.apiKey,
    required super.databaseUrl,
    required super.syncUid,
    required super.serverClientId,
  });

  /// The values compiled into this build.
  static const FirebaseConfig compiled = FirebaseConfig(
    apiKey: local.kFirebaseApiKey,
    databaseUrl: local.kFirebaseDatabaseUrl,
    syncUid: local.kFirebaseSyncUid,
    serverClientId: local.kGoogleServerClientId,
  );

  /// Whether the app can sign in and reach the database at all.
  bool get isComplete =>
      apiKey.isNotEmpty && databaseUrl.isNotEmpty && syncUid.isNotEmpty;
}
