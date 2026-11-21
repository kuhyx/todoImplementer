/// Where a new task goes (T2351): none (a repo-less note triage routes),
/// all of the board's repos, or some. Open it shows glyph chips for none and
/// all and one chip per repo (repo names are kuhy's own words); once a
/// choice is made it folds to one row, and a tap on that row opens it again.
/// A search box filters the chips (the board lists every GitHub repo, T2410);
/// a typed `owner/name` that is not listed gets a chip of its own (T2425).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';

/// The kind of choice.
enum RepoScope {
  /// No repo: one repo-less note.
  none,

  /// Every repo on the board: one task each.
  all,

  /// The picked repos: one task each.
  some,
}

/// The chooser, open or folded; the sheet owns the choice, this the search.
class RepoChooser extends StatefulWidget {
  /// Creates the chooser.
  const new({
    required this.repos,
    required this.open,
    required this.scope,
    required this.picked,
    required this.onScope,
    required this.onToggle,
    required this.onFold,
    required this.onOpen,
    super.key,
  });

  /// The board's repos.
  final List<String> repos;

  /// Whether the chips show.
  final bool open;

  /// The choice so far (null: none made yet).
  final RepoScope? scope;

  /// The picked repos for [RepoScope.some].
  final Set<String> picked;

  /// Picks none or all (folds at once).
  final ValueChanged<RepoScope> onScope;

  /// Adds or removes one repo.
  final ValueChanged<String> onToggle;

  /// Folds after picking repos.
  final VoidCallback onFold;

  /// Opens the folded row again.
  final VoidCallback onOpen;

  @override
  State<RepoChooser> createState() => _RepoChooserState();
}

final RegExp _ownerName = RegExp(r'^[\w.-]+/[\w.-]+$');

/// The repos that match [query] (case-insensitive, any part of the name),
/// picked ones always kept, plus a typed `owner/name` not listed yet.
List<String> matchingRepos(
  List<String> repos,
  Set<String> picked,
  String query,
) {
  final q = query.trim().toLowerCase();
  final shown = [
    for (final r in {...repos, ...picked})
      if (q.isEmpty || r.toLowerCase().contains(q) || picked.contains(r)) r,
  ];
  final typed = query.trim();
  if (_ownerName.hasMatch(typed) && !shown.contains(typed)) shown.add(typed);
  return shown;
}

class _RepoChooserState extends State<RepoChooser> {
  final TextEditingController _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  RepoChooser get w => widget;

  static String _short(String repo) => repo.split('/').last;

  Widget _scopeChip(RepoScope s, IconData icon, String spoken) => ChoiceChip(
    key: Key('nt-repo-${s.name}'),
    selected: w.scope == s,
    showCheckmark: false,
    label: Icon(icon, semanticLabel: spoken, size: AppSpacing.md),
    onSelected: (_) => w.onScope(s),
  );

  Widget _folded() => InkWell(
    key: const Key('nt-repos-folded'),
    onTap: w.onOpen,
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          const Icon(Icons.folder_outlined, semanticLabel: 'Repos'),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: switch (w.scope) {
              RepoScope.none => const Align(
                alignment: Alignment.centerLeft,
                child: Icon(Icons.block, semanticLabel: 'No repo'),
              ),
              RepoScope.all => const Align(
                alignment: Alignment.centerLeft,
                child: Icon(Icons.select_all, semanticLabel: 'All repos'),
              ),
              _ => Text(
                w.picked.map(_short).join(', '),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            },
          ),
          const Icon(Icons.expand_more),
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    if (!w.open) return _folded();
    final picked = w.scope == RepoScope.some ? w.picked : const <String>{};
    final shown = matchingRepos(w.repos, picked, _search.text);
    return Row(
      key: const Key('nt-repos'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                key: const Key('nt-repo-search'),
                controller: _search,
                autocorrect: false,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search, semanticLabel: 'Find repo'),
                  isDense: true,
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: AppSpacing.xs),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 200),
                child: SingleChildScrollView(
                  child: Wrap(
                    spacing: AppSpacing.xs,
                    runSpacing: AppSpacing.xs,
                    children: [
                      _scopeChip(RepoScope.none, Icons.block, 'No repo'),
                      _scopeChip(RepoScope.all, Icons.select_all, 'All repos'),
                      for (final r in shown)
                        FilterChip(
                          key: Key('nt-repo-$r'),
                          selected: picked.contains(r),
                          label: Text(w.repos.contains(r) ? _short(r) : r),
                          onSelected: (_) => w.onToggle(r),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
        IconButton(
          key: const Key('nt-repos-done'),
          icon: const Icon(Icons.check, semanticLabel: 'Done'),
          onPressed: w.scope == RepoScope.some && w.picked.isNotEmpty
              ? w.onFold
              : null,
        ),
      ],
    );
  }
}
