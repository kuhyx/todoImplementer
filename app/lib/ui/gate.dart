/// Not configured -> Google sign-in -> crdt-sync key -> the shell.
///
/// Nothing syncs before the key is open: the client refuses to send under
/// the e2e root while locked, and this gate shows only the lock button.
library;

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show E2ePassphraseButton;
import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:rtdb_relay/rtdb_relay.dart' show SignInOutcome;
import 'package:todo_implementer/shell/shell.dart';
import 'package:todo_implementer/sync/services.dart';
import 'package:todo_implementer/ui/board/board_page.dart';
import 'package:todo_implementer/ui/sessions/sessions_page.dart';
import 'package:todo_implementer/ui/usage/usage_page.dart';

/// The gate in front of the shell.
class AppGate extends StatefulWidget {
  /// Creates the gate.
  const new({required this.services, super.key});

  /// Session, key gate and relay.
  final AppServices services;

  @override
  State<AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<AppGate> {
  late Future<bool> _session = widget.services.auth.hasSession();
  late Future<bool> _open = widget.services.gate.unlock();
  Object? _signInError;
  bool _busy = false;

  Future<void> _signIn() async {
    setState(() {
      _busy = true;
      _signInError = null;
    });
    Object? error;
    try {
      final outcome = await widget.services.auth.signInWithGoogle();
      if (outcome != SignInOutcome.signedIn) error = outcome;
    } on Object catch (e) {
      // `on Object`: the wrong-account guard and plugin Errors both show.
      error = e;
    }
    final session = widget.services.auth.hasSession()..ignore();
    setState(() {
      _busy = false;
      _signInError = error;
      _session = session;
    });
  }

  void _retryKey() {
    // The FutureBuilder subscribes on the next frame; mark the error handled
    // now so a failed unlock is drawn, not reported as uncaught.
    final next = widget.services.gate.unlock()..ignore();
    setState(() {
      _open = next;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.services.config.isComplete) {
      // Built without tool/write_firebase_config.dart values.
      return const Scaffold(
        body: Center(
          child: Icon(
            Icons.settings_suggest_outlined,
            key: Key('not-configured'),
            size: AppSpacing.xxl,
            color: AppPalette.danger,
          ),
        ),
      );
    }
    return FutureBuilder<bool>(
      future: _session,
      builder: (context, session) {
        if (session.connectionState != ConnectionState.done) {
          return const _Loading();
        }
        if (!(session.data ?? false)) return _signInView();
        return FutureBuilder<bool>(
          future: _open,
          builder: (context, open) {
            if (open.connectionState != ConnectionState.done) {
              return const _Loading();
            }
            if (open.data ?? false) {
              final s = widget.services;
              final sessions = s.sessions;
              final usage = s.usage;
              return Shell(
                board: BoardPage(relay: s.relay, usage: usage?.usage()),
                sessions: sessions == null
                    ? null
                    : SessionsPage(feed: sessions, relay: s.relay),
                usage: usage == null ? null : UsagePage(relay: usage),
              );
            }
            return _lockView('${open.error ?? widget.services.gate.reason}');
          },
        );
      },
    );
  }

  Widget _signInView() => Scaffold(
    body: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton.filled(
            key: const Key('sign-in'),
            iconSize: AppSpacing.xl,
            onPressed: _busy ? null : _signIn,
            icon: const Icon(Icons.login),
          ),
          if (_signInError case final e?)
            Icon(
              Icons.error_outline,
              key: const Key('sign-in-error'),
              color: AppPalette.danger,
              semanticLabel: '$e',
            ),
        ],
      ),
    ),
  );

  Widget _lockView(String why) => Scaffold(
    body: Center(
      child: Semantics(
        label: why,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            E2ePassphraseButton(locked: true, onSaved: _retryKey),
            const SizedBox(width: AppSpacing.md),
            IconButton(
              key: const Key('unlock-retry'),
              icon: const Icon(Icons.refresh),
              onPressed: _retryKey,
            ),
          ],
        ),
      ),
    ),
  );
}

class _Loading extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
