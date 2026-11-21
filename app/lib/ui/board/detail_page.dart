/// The card drawer as a full page: `task_detail` loaded over the relay and
/// split into icon tabs (overview with needs, asks, lesson and umbrella;
/// live feed; plan; diff; checks; live check; issues for an umbrella).
/// An ask answer reloads the detail so the server's new state shows.
/// Send to Claude sits under the asks whenever the card offers it (T2276).
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/detail.dart';
import 'package:todo_implementer/sync/board_relay.dart';
import 'package:todo_implementer/ui/board/asks_view.dart';
import 'package:todo_implementer/ui/board/detail_tabs.dart';
import 'package:todo_implementer/ui/board/glyphs.dart';
import 'package:todo_implementer/ui/board/image_attach.dart';
import 'package:todo_implementer/ui/board/live_feed.dart';
import 'package:todo_implementer/ui/board/needs_line.dart';
import 'package:todo_implementer/ui/board/needs_links.dart';
import 'package:todo_implementer/ui/board/note_box.dart';
import 'package:todo_implementer/ui/board/umbrella_view.dart';

/// How long the page waits for the PC worker's `task_detail` answer.
const kDetailPatience = Duration(seconds: 15);

/// The first load's wait: a spinner around the PC glyph, named for what it
/// waits on (the PC worker's answer to `task_detail`).
class _Waiting extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) => const Center(
    child: Stack(
      alignment: Alignment.center,
      children: [
        CircularProgressIndicator(
          semanticsLabel: 'Waiting for the PC: card detail',
        ),
        Icon(
          Icons.computer,
          key: Key('detail-waits-on'),
          size: AppSpacing.md,
          color: AppPalette.mutedOnDark,
        ),
      ],
    ),
  );
}

/// The drawer page of [card].
class DetailPage extends StatefulWidget {
  /// Creates the page.
  const new({
    required this.card,
    required this.relay,
    required this.onError,
    super.key,
  });

  /// Card id.
  final String card;

  /// The link to the PC.
  final BoardRelay relay;

  /// Records a refusal for the copy-errors action.
  final void Function(RelayFailed failure) onError;

  @override
  State<DetailPage> createState() => _DetailPageState();
}

class _DetailPageState extends State<DetailPage> {
  TaskDetail? _detail;
  RelayFailed? _failure;
  late final ShotLoad _shots = shotLoader(widget.relay, widget.card);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    if (_detail == null && _failure != null) setState(() => _failure = null);
    final out = await widget.relay.send('task_detail', {
      'card': widget.card,
    }, timeout: kDetailPatience);
    if (!mounted) return;
    setState(() {
      if (out is RelayOk) {
        _detail = TaskDetail.fromJson(out.data);
      } else if (out is RelayFailed) {
        widget.onError(out);
        _failure = out;
      }
    });
  }

  Future<void> _ask(String kind, Map<String, dynamic> args) async {
    final out = await widget.relay.send(kind, {
      'card': widget.card,
      'args': args,
    });
    if (out is RelayFailed) {
      widget.onError(out);
      if (mounted) setState(() => _failure = out);
      return;
    }
    await _load();
  }

  Future<bool> _note(String text, ImageAttach attach) async {
    final (images, failed) = await attach.upload(widget.relay.send);
    final out =
        failed ??
        await widget.relay.send('task_send', {
          'card': widget.card,
          'args': {'text': text, if (images.isNotEmpty) 'images': images},
        });
    if (out is RelayFailed) {
      widget.onError(out);
      if (mounted) setState(() => _failure = out);
      return false;
    }
    await _load();
    return true;
  }

  Widget _overview(TaskDetail d) {
    final needs = d.card.needs;
    final specOk = inlineSpecOk(d.card);
    final lesson = d.lesson;
    final umbrella = d.umbrella;
    final send = d.card.actions.where((a) => a.id == 'send').firstOrNull;
    // The note box is pinned under the list: never below the fold (T2339).
    final list = ListView(
      key: const Key('overview'),
      padding: const EdgeInsets.all(AppSpacing.sm),
      children: [
        Text(d.card.title, style: Theme.of(context).textTheme.titleMedium),
        if (d.card.repo case final repo?)
          Text(repo, style: const TextStyle(color: AppPalette.mutedOnDark)),
        if (d.card.model case final model?)
          Text(
            model,
            key: const Key('detail-model'),
            style: const TextStyle(color: AppPalette.mutedOnDark),
          ),
        if (d.card.current.isNotEmpty) Text(d.card.current),
        if (needs != null)
          needsTile(needs, specOk, (_) => _ask('task_spec_ok', {})),
        if (needs != null) NeedsLinks(links: needs.links),
        if (d.error case final e? when e != needs?.text)
          ListTile(
            key: const Key('detail-error'),
            leading: const Icon(Icons.error, color: AppPalette.danger),
            title: SelectableText(e),
          ),
        if (d.asks.isNotEmpty)
          AsksView(asks: d.asks, onSend: _ask, loadShot: _shots),
        if (lesson != null)
          ListTile(
            key: const Key('lesson'),
            leading: const Icon(Icons.school_outlined),
            title: Text(lesson.rule),
            subtitle: Text('${lesson.mistake}\n${lesson.evidence}'),
          ),
        if (umbrella != null) UmbrellaView(detail: umbrella),
      ],
    );
    if (send == null) return list;
    return Column(
      children: [
        Expanded(child: list),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: NoteBox(action: send, onSend: _note),
        ),
      ],
    );
  }

  /// The first load failed or timed out: its glyph, and a retry.
  Widget _retry(RelayFailed f) => Center(
    child: IconButton(
      key: const Key('detail-retry'),
      iconSize: AppSpacing.xxl * 2,
      color: AppPalette.danger,
      icon: Icon(codeIcon(f.code), semanticLabel: 'Retry: ${f.error}'),
      onPressed: _load,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    final failure = _failure;
    final tabs = <(IconData, Widget Function(TaskDetail))>[
      (Icons.info_outline, _overview),
      (Icons.stream, (_) => LiveFeed(relay: widget.relay, card: widget.card)),
      (Icons.map_outlined, planTab),
      (Icons.difference_outlined, diffTab),
      (Icons.fact_check_outlined, checksTab),
      (Icons.photo_library_outlined, (d) => liveCheckTab(d, _shots)),
      if (d?.umbrella != null)
        (
          Icons.bug_report_outlined,
          (_) => IssuesTab(relay: widget.relay, card: widget.card),
        ),
    ];
    return DefaultTabController(
      length: tabs.length,
      child: Scaffold(
        appBar: AppBar(
          actions: [
            if (failure != null)
              Icon(
                codeIcon(failure.code),
                key: const Key('detail-failure'),
                color: AppPalette.danger,
                semanticLabel: failure.error,
              ),
            IconButton(
              key: const Key('detail-reload'),
              icon: const Icon(Icons.refresh, semanticLabel: 'Reload'),
              onPressed: _load,
            ),
          ],
          bottom: TabBar(
            isScrollable: true,
            tabs: [for (final (icon, _) in tabs) Tab(icon: Icon(icon))],
          ),
        ),
        body: switch ((d, failure)) {
          (final TaskDetail d, _) => TabBarView(
            children: [for (final (_, build) in tabs) build(d)],
          ),
          (null, final RelayFailed f) => _retry(f),
          (null, null) => const _Waiting(),
        },
      ),
    );
  }
}
