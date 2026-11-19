/// The pages a Needs-you ask names (`needs.links`, T2135): one link glyph
/// each, the URL as its tooltip. The app has no browser hand-off (a new
/// dependency is ask-first), so a tap copies the URL; only http(s) shows.
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

/// The link glyphs of one need.
class NeedsLinks extends StatelessWidget {
  /// Creates the row for [links].
  const new({required this.links, super.key});

  /// Absolute URLs from the server.
  final List<String> links;

  /// True for a URL the row may show.
  static bool isWeb(String url) {
    final uri = Uri.tryParse(url);
    return uri != null &&
        uri.hasAuthority &&
        (uri.scheme == 'http' || uri.scheme == 'https');
  }

  @override
  Widget build(BuildContext context) {
    final shown = links.where(isWeb).toList();
    if (shown.isEmpty) return const SizedBox.shrink();
    return Wrap(
      children: [
        for (final url in shown)
          IconButton(
            key: ValueKey('needs-link-$url'),
            tooltip: url,
            icon: const Icon(Icons.link),
            onPressed: () =>
                unawaited(Clipboard.setData(ClipboardData(text: url))),
          ),
      ],
    );
  }
}
