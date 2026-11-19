/// The card's live activity feed (`live/{card}` while watched): one row per
/// event, a glyph per kind, newest at the top, the stage as a chip.
///
/// A wait never hangs: with no first read after [kFeedPatience], or an
/// empty one, the tab shows the dimmed feed glyph; a later read still lands.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/detail_tabs.dart';

/// How long the spinner waits for the first read of `live/{card}`.
const kFeedPatience = Duration(seconds: 5);

/// Glyph of a live activity kind.
IconData feedIcon(String kind) => switch (kind) {
  'text' => Icons.chat_bubble_outline,
  'tool' => Icons.build_outlined,
  'result' => Icons.flag_outlined,
  'error' => Icons.error_outline,
  'user' => Icons.person_outline,
  _ => Icons.settings_outlined,
};

/// The feed of [card].
class LiveFeed extends StatefulWidget {
  /// Creates the feed.
  const new({required this.relay, required this.card, super.key});

  /// Source of `live/{card}`.
  final BoardRelay relay;

  /// Card id.
  final String card;

  @override
  State<LiveFeed> createState() => _LiveFeedState();
}

class _LiveFeedState extends State<LiveFeed> {
  late final Stream<List<Json>> _feed = widget.relay.liveFeed(widget.card);
  late final Timer _patience;
  var _waited = false;

  static Widget _empty() => notYet(Icons.stream, const Key('feed-empty'));

  @override
  void initState() {
    super.initState();
    _patience = Timer(kFeedPatience, () => setState(() => _waited = true));
  }

  @override
  void dispose() {
    _patience.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => StreamBuilder<List<Json>>(
    stream: _feed,
    builder: (context, snap) {
      final events = snap.data;
      if (events == null) {
        return _waited
            ? _empty()
            : const Center(
                child: CircularProgressIndicator(semanticsLabel: 'feed'),
              );
      }
      final activity = events.where((e) => e['type'] == 'activity').toList();
      final stage = events.lastWhere(
        (e) => e['type'] == 'stage',
        orElse: () => const {},
      );
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (strOr(stage, 'stage') case final s?)
            Align(
              alignment: Alignment.centerLeft,
              child: Chip(key: const Key('feed-stage'), label: Text(s)),
            ),
          Expanded(
            child: activity.isEmpty
                ? _empty()
                : ListView.builder(
                    key: const Key('feed-list'),
                    itemCount: activity.length,
                    itemBuilder: (_, i) {
                      final e = activity[activity.length - 1 - i];
                      final kind = str(e, 'kind');
                      final tool = strOr(e, 'tool');
                      return ListTile(
                        dense: true,
                        leading: Icon(
                          feedIcon(kind),
                          color: kind == 'error' ? AppPalette.danger : null,
                        ),
                        title: Text(
                          [?tool, str(e, 'text')].join(' '),
                          maxLines: 6,
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    },
                  ),
          ),
        ],
      );
    },
  );
}
