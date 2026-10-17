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
  testWidgets('starts on the login screen with the sync bar', (tester) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [syncProvider.overrideWith(_FakeSync.new)],
      child: const NasconApp(),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Sign In'), findsWidgets);
    expect(find.text('Online'), findsOneWidget);
  });
}
