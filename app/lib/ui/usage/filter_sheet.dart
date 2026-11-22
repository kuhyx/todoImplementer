/// The global filters (`web/src/usage/filter-bar.ts`) as a sheet: scope as
/// glyph segments, directory/model/window pickers of the server's options
/// (data), two date pickers. Check applies, the crossed funnel clears.
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:todo_implementer/model/json.dart';
import 'package:todo_implementer/model/usage/route.dart';

const _scopeGlyphs = <String, (IconData, String)>{
  'all': (Icons.all_inclusive, 'All sessions'),
  'main': (Icons.person_outline, 'Main sessions'),
  'sub': (Icons.smart_toy_outlined, 'Subagents'),
};

/// The sheet; pops the new [UsageFilters] (or null when dismissed).
class FilterSheet extends StatefulWidget {
  /// Creates the sheet from the current [filters] and the tokens [index].
  const new({required this.filters, required this.index, super.key});

  /// The filters now.
  final UsageFilters filters;

  /// `GET /api/tokens` (options and snapshot windows).
  final Json index;

  @override
  State<FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<FilterSheet> {
  late UsageFilters _draft = widget.filters;

  void _set(String key, String value) =>
      setState(() => _draft = _draft.withField(key, value));

  Widget _pick(String key, IconData icon, String label, List<String> values) {
    final now = switch (key) {
      'cwd' => _draft.cwd,
      'model' => _draft.model,
      _ => _draft.window,
    };
    final known = {'', ...values, now}.toList();
    return Row(
      children: [
        Icon(icon, semanticLabel: label),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: DropdownButton<String>(
            key: ValueKey('pick-$key'),
            isExpanded: true,
            value: now,
            items: [
              for (final v in known)
                DropdownMenuItem(
                  value: v,
                  child: v.isEmpty
                      ? const Icon(
                          Icons.all_inclusive,
                          size: 18,
                          semanticLabel: 'Any',
                        )
                      : Text(v, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (v) => _set(key, v ?? ''),
          ),
        ),
      ],
    );
  }

  Widget _date(String key, IconData icon, String label) {
    final now = key == 'from' ? _draft.from : _draft.to;
    return Row(
      children: [
        Icon(icon, semanticLabel: label),
        const SizedBox(width: AppSpacing.sm),
        TextButton(
          key: ValueKey('date-$key'),
          onPressed: () async {
            final picked = await showDatePicker(
              context: context,
              firstDate: DateTime(2024),
              lastDate: DateTime.now().add(const Duration(days: 1)),
              initialDate: DateTime.tryParse(now) ?? DateTime.now(),
            );
            if (picked != null) {
              _set(key, picked.toIso8601String().substring(0, 10));
            }
          },
          child: now.isEmpty
              ? const Icon(Icons.event, semanticLabel: 'Pick a day')
              : Text(now),
        ),
        if (now.isNotEmpty)
          IconButton(
            key: ValueKey('clear-$key'),
            tooltip: 'clear',
            icon: const Icon(Icons.close, semanticLabel: 'Clear'),
            onPressed: () => _set(key, ''),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final options = objOr(widget.index, 'options') ?? const {};
    final coverage = objOr(widget.index, 'coverage') ?? const {};
    return SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          SegmentedButton<String>(
            key: const ValueKey('scope'),
            showSelectedIcon: false,
            segments: [
              for (final s in scopes)
                ButtonSegment(
                  value: s,
                  icon: Icon(
                    _scopeGlyphs[s]!.$1,
                    semanticLabel: _scopeGlyphs[s]!.$2,
                  ),
                ),
            ],
            selected: {_draft.scope},
            onSelectionChanged: (s) => _set('scope', s.first),
          ),
          _pick(
            'cwd',
            Icons.folder_outlined,
            'Directory',
            strs(options, 'cwds'),
          ),
          _pick('model', Icons.memory, 'Model', strs(options, 'models')),
          _pick(
            'window',
            Icons.history,
            'Snapshot window',
            strs(coverage, 'snapshots'),
          ),
          _date('from', Icons.first_page, 'From'),
          _date('to', Icons.last_page, 'To'),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                key: const ValueKey('filters-clear'),
                tooltip: 'clear',
                icon: const Icon(
                  Icons.filter_alt_off_outlined,
                  semanticLabel: 'Clear filters',
                ),
                onPressed: () => Navigator.pop(context, const UsageFilters()),
              ),
              IconButton.filled(
                key: const ValueKey('filters-apply'),
                tooltip: 'apply',
                icon: const Icon(Icons.check, semanticLabel: 'Apply'),
                onPressed: () => Navigator.pop(context, _draft),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
