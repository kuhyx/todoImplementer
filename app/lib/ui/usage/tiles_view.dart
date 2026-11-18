/// Headline tiles, server banners and lists (textgate: glyph + number; a
/// banner shows its server text only when tapped).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';
import 'package:todo_implementer/ui/usage/glyphs.dart';

/// Height of one tile row.
const tileHeight = 64.0;

/// Tiles per row at [width].
int tilesPerRow(double width) => (width / 128).floor().clamp(2, 6);

/// Height [TilesBlock] needs at [width].
double tilesHeight(TilesBlock b, double width) {
  final rows = (b.tiles.length / tilesPerRow(width)).ceil();
  return rows * tileHeight + (rows - 1) * AppSpacing.xs;
}

/// A grid of [UsageTile]s, laid out to [tilesHeight].
class TilesView extends StatelessWidget {
  /// Creates the view.
  const new(this.block, {super.key});

  /// The tiles.
  final TilesBlock block;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final per = tilesPerRow(box.maxWidth);
      final w = (box.maxWidth - (per - 1) * AppSpacing.xs) / per;
      return Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: [
          for (final t in block.tiles)
            SizedBox(width: w, height: tileHeight, child: _Tile(t)),
        ],
      );
    },
  );
}

class _Tile extends StatelessWidget {
  const new(this.tile);

  final UsageTile tile;

  @override
  Widget build(BuildContext context) {
    final level = tile.level;
    final mark = level == null ? null : levelGlyph(level);
    final way = tile.higherIsBetter;
    return Semantics(
      label: [
        tile.label,
        tile.value,
        ?mark?.$3,
        if (tile.target case final t?) 'target $t',
      ].join(', '),
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppPalette.inkRaised1,
          borderRadius: BorderRadius.circular(AppRadius.md),
          border: mark == null ? null : Border.all(color: mark.$2),
        ),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(tile.icon, size: 16, color: AppPalette.mutedOnDark),
                  const Spacer(),
                  if (mark != null) Icon(mark.$1, size: 16, color: mark.$2),
                ],
              ),
              Row(
                children: [
                  Flexible(
                    child: Text(
                      tile.value,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: AppTextSize.body,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  if (tile.target case final t?) ...[
                    const SizedBox(width: AppSpacing.xs),
                    Icon(
                      way == null
                          ? Icons.flag_outlined
                          : (way ? Icons.north : Icons.south),
                      size: 12,
                      color: AppPalette.mutedOnDark,
                    ),
                    Text(
                      t,
                      style: const TextStyle(
                        fontSize: AppTextSize.caption,
                        color: AppPalette.mutedOnDark,
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Height of a banner.
const bannerHeight = 40.0;

/// A level glyph; tapping it shows the server's text in a sheet.
class BannerView extends StatelessWidget {
  /// Creates the view.
  const new(this.block, {super.key});

  /// The banner.
  final BannerBlock block;

  @override
  Widget build(BuildContext context) {
    final (icon, color, word) = levelGlyph(block.level);
    return SizedBox(
      height: bannerHeight,
      child: Material(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          onTap: block.text.isEmpty
              ? null
              : () => showModalBottomSheet<void>(
                  context: context,
                  showDragHandle: true,
                  builder: (_) => Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: SelectableText(block.text),
                  ),
                ),
          child: Semantics(
            label: '$word: ${block.text}',
            excludeSemantics: true,
            child: Row(
              children: [
                const SizedBox(width: AppSpacing.sm),
                Icon(icon, color: color),
                const Spacer(),
                if (block.text.isNotEmpty)
                  const Icon(Icons.expand_more, color: AppPalette.mutedOnDark),
                const SizedBox(width: AppSpacing.sm),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Height of one list entry or table row.
const rowHeight = 52.0;

/// One page of a [ListBlock]: entries that open a route are tappable.
class ListPage extends StatelessWidget {
  /// Creates the page for [entries] of [block].
  const new(this.block, this.entries, {required this.open, super.key});

  /// The list.
  final ListBlock block;

  /// This page's slice.
  final List<(String, UsageRoute?)> entries;

  /// Opens a route.
  final ValueChanged<UsageRoute> open;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final (text, route) in entries)
        SizedBox(
          height: rowHeight,
          child: ListTile(
            dense: true,
            leading: Icon(block.icon, size: 18),
            title: Text(text, maxLines: 2, overflow: TextOverflow.ellipsis),
            trailing: route == null ? null : const Icon(Icons.chevron_right),
            onTap: route == null ? null : () => open(route),
          ),
        ),
    ],
  );
}

/// A context file's content; the only block that scrolls (a text viewer,
/// R7's exemption).
class ContentView extends StatelessWidget {
  /// Creates the view.
  const new(this.block, {super.key});

  /// The content.
  final ContentBlock block;

  @override
  Widget build(BuildContext context) {
    final text = block.text;
    if (text == null) {
      return const Center(
        child: Icon(
          Icons.visibility_off_outlined,
          semanticLabel: 'Not readable',
        ),
      );
    }
    return SingleChildScrollView(
      child: SelectableText(
        text,
        style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
      ),
    );
  }
}
