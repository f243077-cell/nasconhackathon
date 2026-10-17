import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nascon_app/app.dart';

void main() {
  testWidgets('starts on the login screen with the sync bar', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: NasconApp()));
    await tester.pumpAndSettle();
    expect(find.text('Sign in'), findsWidgets);
    expect(find.text('Online'), findsOneWidget);
  });
}
