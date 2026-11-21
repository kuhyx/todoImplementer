import 'dart:async';

import 'package:material_ui/material_ui.dart';

/// kuhy's night, local time (kuhy, 2026-11-21): the board works on its own
/// and the phone is kept out of it. The server refuses the phone too
/// (DOCS-phone.md "Night"); this screen just says so without words.
const ({int hour, int minute}) nightStart = (hour: 22, minute: 55);

/// When the night ends and the board opens again.
const ({int hour, int minute}) nightEnd = (hour: 5, minute: 55);

/// Whether [at] falls in the night (the window wraps midnight).
bool isNight(DateTime at) {
  final minute = at.hour * 60 + at.minute;
  final start = nightStart.hour * 60 + nightStart.minute;
  final end = nightEnd.hour * 60 + nightEnd.minute;
  return minute >= start || minute < end;
}

/// The clock every [NightLock] reads unless given its own; the test config
/// pins it to noon so no app test depends on the hour it runs at.
DateTime Function() nightClock = DateTime.now;

/// Shows [child] by day and a moon at night; checks the clock every minute.
class NightLock extends StatefulWidget {
  /// Creates the lock; [now] is the clock (tests pass a fixed one).
  const new({required this.child, this.now, super.key});

  /// The app behind the lock.
  final Widget child;

  /// The clock read on build and every minute.
  final DateTime Function()? now;

  @override
  State<NightLock> createState() => _NightLockState();
}

class _NightLockState extends State<NightLock> {
  late final Timer _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(minutes: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _tick.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!isNight((widget.now ?? nightClock)())) return widget.child;
    return const Scaffold(body: Center(child: Icon(Icons.bedtime, size: 96)));
  }
}
