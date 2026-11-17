# todo_implementer (Flutter app)

Native client of the todoImplementer board: Android (`com.kuhy.todo_implementer`) and, later, the PC as a
Flutter web build in a Chrome `--app` window. It talks to the board over the Firebase RTDB relay, never over
HTTP. Spec, done criteria and parts: `../DOCS-native-app.md`; relay kinds and guards:
`../DOCS-native-app-relay.md`.

Status: scaffold (part P3). The shell has three icon-only pages (board, sessions, usage) with no content yet;
sign-in, unlock and the relay plug in next.

## Commands (run from `app/`, Flutter pinned in `.fvmrc`)

- test: `CAP_MEM=4G ~/.claude/scripts/capped.sh fvm flutter test --coverage` (100 % line coverage)
- lint: `fvm dart analyze lib test` and `fvm dart format --set-exit-if-changed lib test`
- install on the Pixel (from the main checkout, never a worktree):
  `~/.claude/scripts/phone_deploy.sh ~/src/todoImplementer/app --release --stage prep`, then `dart`, `kotlin`,
  `assemble`, `install` (one call each)
- Firebase registration of (package, release SHA-1) in kuhy-syncs: `../scripts/register_firebase_android.sh`
  (`--check` verifies)
- icon: shared family, key `todo_implementer` in `~/src/testsAndMisc/python_pkg/app_icons`

CI (`../.github/workflows/app.yml`) analyses, tests and publishes a release-signed APK on every push to main
that touches `app/`. versionCode is that workflow file's run number: never rename the file.
