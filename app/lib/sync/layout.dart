/// todoImplementer's sealed RTDB tree (DOCS-native-app-relay.md, "Layout"
/// and "Sealing"). The PC worker builds the same rules in Python; a path
/// missing here throws `E2eLayoutError` on write instead of leaking clear.
library;

import 'package:rtdb_relay/rtdb_relay.dart';

/// The base the e2e root derives from: data lives at `todoimpl/v1-e2e`.
const String kBase = 'todoimpl/v1';

/// The tree rules: clear `meta`, `e2e`, `rev` and claims; every other node
/// is a sealed unit keeping only its server timestamps clear.
final RelayLayout kTodoImplLayout = RelayLayout(
  kBase,
  clear: const [...kRelayClear, 'meta', 'e2e', 'rev'],
  units: const {
    ...kRelayUnits,
    'snap/*': {},
    'presence/clients/*': {'seen'},
    'watch/*': {},
    'live/*/*': {},
  },
);

/// Full path of [rel] under the e2e root.
String fullPath(String rel) => '${kTodoImplLayout.root}/$rel';
