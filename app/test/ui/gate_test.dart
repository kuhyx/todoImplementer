import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart' show InMemoryCredentialStore;
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show E2ePassphraseButton;
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/rtdb_relay.dart';
import 'package:todo_implementer/config/firebase_config.dart';
import 'package:todo_implementer/shell/app.dart';
import 'package:todo_implementer/shell/shell.dart';
import 'package:todo_implementer/sync/layout.dart';
import 'package:todo_implementer/sync/services.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/sessions/sessions_page.dart';

import '../support/fakes.dart';
import '../support/session_fakes.dart';
import '../support/usage_fakes.dart';

const _config = FirebaseConfig(
  apiKey: 'k',
  databaseUrl: 'https://db.example',
  syncUid: 'u',
  serverClientId: 'w',
);

class _Auth extends RelayAuth {
  new()
    : super(
        config: _config,
        googleToken: ({required serverClientId}) async => null,
        store: InMemoryCredentialStore(),
      );

  bool session = false;
  Object? signIn = SignInOutcome.signedIn;

  @override
  Future<bool> hasSession() async => session;

  @override
  Future<SignInOutcome> signInWithGoogle({
    Future<String?> Function()? tokenFetcher,
  }) async {
    final s = signIn;
    if (s is SignInOutcome) {
      if (s == SignInOutcome.signedIn) session = true;
      return s;
    }
    throw s!;
  }
}

class _Gate extends E2eGate {
  new()
    : super(
        client: RtdbClient(
          layout: kTodoImplLayout,
          databaseUrl: 'https://db.example',
          idToken: () async => 't',
          httpClient: MockClient((_) async => http.Response('null', 200)),
        ),
      );

  final List<Object> answers = [];

  @override
  String get reason => 'locked';

  /// Locked until an unlock answers true.
  bool opened = false;

  @override
  bool get locked => !opened;

  @override
  Future<bool> unlock() async {
    final a = answers.isEmpty ? true : answers.removeAt(0);
    if (a is bool) return opened = a;
    throw a;
  }
}

AppServices _services({
  FirebaseConfig config = _config,
  _Auth? auth,
  _Gate? gate,
  bool sessions = false,
}) => AppServices(
  config: config,
  auth: auth ?? _Auth(),
  gate: gate ?? _Gate(),
  relay: FakeRelay(),
  sessions: sessions ? FakeSessionsFeed().feed : null,
  usage: FakeUsageRelay(),
);

Future<void> _pump(WidgetTester tester, AppServices s) async {
  pixel6a(tester);
  await tester.pumpWidget(TodoImplementerApp(services: Future.value(s)));
  await tester.pumpAndSettle();
}

const _offline = RtdbError('network error: GET /e2e');

void main() {
  _passphraseTests();
  testWidgets('an unconfigured build shows the config cue', (tester) async {
    await _pump(
      tester,
      _services(
        config: const FirebaseConfig(
          apiKey: '',
          databaseUrl: '',
          syncUid: '',
          serverClientId: '',
        ),
      ),
    );
    expect(find.byKey(const Key('not-configured')), findsOneWidget);
  });

  testWidgets('sign in: cancel and errors show, success opens the board', (
    tester,
  ) async {
    final auth = _Auth()..signIn = SignInOutcome.cancelled;
    await _pump(tester, _services(auth: auth));
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sign-in-error')), findsOneWidget);
    auth.signIn = StateError('wrong account');
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sign-in-error')), findsOneWidget);
    auth.signIn = SignInOutcome.signedIn;
    await tester.tap(find.byKey(const Key('sign-in')));
    await _settle(tester);
    expect(find.byType(Shell), findsOneWidget);
    expect(find.byType(BoardPage), findsOneWidget);
  });

  testWidgets('the sessions tab opens the sessions page when wired', (
    tester,
  ) async {
    pixel6a(tester);
    await tester.pumpWidget(
      TodoImplementerApp(
        services: Future.value(
          _services(auth: _Auth()..session = true, sessions: true),
        ),
      ),
    );
    await _settle(tester);
    await tester.tap(find.byKey(const ValueKey('nav-sessions')));
    await _settle(tester);
    expect(find.byType(SessionsPage), findsOneWidget);
  });

  testWidgets('a locked key shows the lock until a retry opens it', (
    tester,
  ) async {
    final gate = _Gate()..answers.addAll([false, StateError('bad key')]);
    await _pump(tester, _services(auth: _Auth()..session = true, gate: gate));
    expect(find.byKey(const Key('unlock-retry')), findsOneWidget);
    await tester.tap(find.byKey(const Key('unlock-retry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('unlock-retry')), findsOneWidget);
    await tester.tap(find.byKey(const Key('unlock-retry')));
    await _settle(tester);
    expect(find.byType(BoardPage), findsOneWidget);
  });

  testWidgets('[T2605] an unreachable key server still opens the board', (
    tester,
  ) async {
    final gate = _Gate()..answers.addAll([_offline, _offline, false]);
    pixel6a(tester);
    final s = _services(auth: _Auth()..session = true, gate: gate);
    await tester.pumpWidget(TodoImplementerApp(services: Future.value(s)));
    await _settle(tester);
    expect(find.byType(BoardPage), findsOneWidget);
    expect(find.byKey(const Key('unlock-retry')), findsNothing);
    await tester.pump(const Duration(seconds: 2));
    await _settle(tester);
    expect(gate.answers, [false]);
    await tester.pump(const Duration(seconds: 5));
    await _settle(tester);
    expect(gate.answers, isEmpty);
    expect(find.byKey(const Key('unlock-retry')), findsOneWidget);
  });

  testWidgets('[T2605] a key server that comes back keeps the board open', (
    tester,
  ) async {
    final gate = _Gate()..answers.addAll([_offline, true]);
    pixel6a(tester);
    final s = _services(auth: _Auth()..session = true, gate: gate);
    await tester.pumpWidget(TodoImplementerApp(services: Future.value(s)));
    await _settle(tester);
    await tester.pump(const Duration(seconds: 2));
    await _settle(tester);
    expect(gate.answers, isEmpty);
    expect(find.byType(BoardPage), findsOneWidget);
    expect(find.byKey(const Key('unlock-retry')), findsNothing);
  });

  testWidgets('loaders while services, session and key resolve', (
    tester,
  ) async {
    pixel6a(tester);
    final services = Completer<AppServices>();
    await tester.pumpWidget(TodoImplementerApp(services: services.future));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    services.complete(_services(auth: _Auth()..session = true));
    await tester.pump();
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsWidgets);
    await _settle(tester);
    expect(find.byType(BoardPage), findsOneWidget);
  });
}

/// Pumps the futures through; the board then spins on its loader forever.
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump();
  }
}

void _passphraseTests() {
  testWidgets(
    '[T2042] the lock opens the passphrase dialog under a pl locale',
    (tester) async {
      tester.platformDispatcher.localesTestValue = const [Locale('pl', 'PL')];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final gate = _Gate()..answers.add(false);
      await _pump(tester, _services(auth: _Auth()..session = true, gate: gate));
      await tester.tap(find.byType(E2ePassphraseButton));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      // The dialog is a material_ui widget; its field is a widgets-layer EditableText.
      expect(find.byType(EditableText), findsOneWidget);
    },
  );
}
