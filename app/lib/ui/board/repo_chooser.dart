/// Where a new task goes (T2351): none (a repo-less note triage routes),
/// all of the board's repos, or some. Open it shows glyph chips for none and
/// all and one chip per repo (repo names are kuhy's own words); once a
/// choice is made it folds to one row, and a tap on that row opens it again.
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

/// The chooser, open or folded; the sheet owns the state.
class RepoChooser extends StatelessWidget {
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

  static String _short(String repo) => repo.split('/').last;

  Widget _scopeChip(RepoScope s, IconData icon, String spoken) => ChoiceChip(
    key: Key('nt-repo-${s.name}'),
    selected: scope == s,
    showCheckmark: false,
    label: Icon(icon, semanticLabel: spoken, size: AppSpacing.md),
    onSelected: (_) => onScope(s),
  );

  Widget _folded() => InkWell(
    key: const Key('nt-repos-folded'),
    onTap: onOpen,
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          const Icon(Icons.folder_outlined, semanticLabel: 'Repos'),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: switch (scope) {
              RepoScope.none => const Align(
                alignment: Alignment.centerLeft,
                child: Icon(Icons.block, semanticLabel: 'No repo'),
              ),
              RepoScope.all => const Align(
                alignment: Alignment.centerLeft,
                child: Icon(Icons.select_all, semanticLabel: 'All repos'),
              ),
              _ => Text(
                picked.map(_short).join(', '),
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
    if (!open) return _folded();
    return Row(
      key: const Key('nt-repos'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 200),
            child: SingleChildScrollView(
              child: Wrap(
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xs,
                children: [
                  _scopeChip(RepoScope.none, Icons.block, 'No repo'),
                  _scopeChip(RepoScope.all, Icons.select_all, 'All repos'),
                  for (final r in repos)
                    FilterChip(
                      key: Key('nt-repo-$r'),
                      selected: scope == RepoScope.some && picked.contains(r),
                      label: Text(_short(r)),
                      onSelected: (_) => onToggle(r),
                    ),
                ],
              ),
            ),
          ),
        ),
        IconButton(
          key: const Key('nt-repos-done'),
          icon: const Icon(Icons.check, semanticLabel: 'Done'),
          onPressed: scope == RepoScope.some && picked.isNotEmpty
              ? onFold
              : null,
        ),
      ],
    );
  }
}
