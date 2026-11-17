import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';

/// One page of the shell: its navigation icon and its placeholder glyph.
@immutable
class ShellPage {
  /// Creates a page entry.
  const new({required this.key, required this.icon, required this.semantics});

  /// Stable key of the page body, used by tests.
  final String key;

  /// Icon on the navigation bar and as the empty-page glyph.
  final IconData icon;

  /// Screen-reader label only; textgate keeps the visible UI text-free.
  final String semantics;
}

/// The board, sessions and usage pages, in navigation order.
const shellPages = <ShellPage>[
  ShellPage(key: 'board', icon: Icons.view_kanban_outlined, semantics: 'Board'),
  ShellPage(key: 'sessions', icon: Icons.terminal, semantics: 'Sessions'),
  ShellPage(key: 'usage', icon: Icons.insights_outlined, semantics: 'Usage'),
];

/// Three-page shell: icon-only navigation bar over an empty page body.
///
/// The board page plugs in through [board]; sessions and usage are still
/// their page glyph until P4b/P4c.
class Shell extends StatefulWidget {
  /// Creates the shell; [board] is the board page body (null: its glyph).
  const new({this.board, this.sessions, this.usage, super.key});

  /// The board page, once the relay is ready.
  final Widget? board;

  /// The sessions page, once the relay is ready.
  final Widget? sessions;

  /// The usage page, once the relay is ready.
  final Widget? usage;

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final page = shellPages[_index];
    return Scaffold(
      body: SafeArea(
        child: KeyedSubtree(
          key: ValueKey(page.key),
          child:
              switch (page.key) {
                'board' => widget.board,
                'sessions' => widget.sessions,
                'usage' => widget.usage,
                _ => null,
              } ??
              Center(
                child: Icon(
                  page.icon,
                  size: AppSpacing.xxl * 2,
                  color: AppPalette.mutedOnDark,
                  semanticLabel: page.semantics,
                ),
              ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysHide,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          for (final p in shellPages)
            NavigationDestination(
              key: ValueKey('nav-${p.key}'),
              icon: Icon(p.icon),
              label: p.semantics,
            ),
        ],
      ),
    );
  }
}
