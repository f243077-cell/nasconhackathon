import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nascon_app/app.dart';
import 'package:nascon_app/data/sync_queue.dart';

/// No SQLite / connectivity plugins in widget tests: start online with an empty queue.
class _FakeSync extends SyncController {
  @override
  SyncState build() => const SyncState();
}

void main() {
  testWidgets('starts on the login screen with the status pill', (tester) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [syncProvider.overrideWith(_FakeSync.new)],
      child: const NasconApp(),
    ));
    await tester.pumpAndSettle();
    expect(find.text('SIGN IN'), findsOneWidget);
    expect(find.text('Online · up to date'), findsOneWidget);
  });
}
