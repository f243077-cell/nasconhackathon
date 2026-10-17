import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/session.dart';
import 'core/theme.dart';
import 'data/models.dart';
import 'features/auth/login_screen.dart';
import 'features/club/club_screen.dart';
import 'features/fixtures/fixtures_screen.dart';
import 'features/match/match_screen.dart';
import 'features/more/more_screen.dart';
import 'features/roster/roster_screen.dart';
import 'features/scoring/scoring_screen.dart';
import 'features/settings/settings_screen.dart';
import 'features/shell/app_shell.dart';
import 'features/standings/standings_screen.dart';
import 'features/store/cart_screen.dart';
import 'features/store/product_screen.dart';
import 'features/store/receipt_screen.dart';
import 'features/store/store_screen.dart';
import 'features/sync/sync_screen.dart';
import 'widgets/sync_status_bar.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/fixtures',
    refreshListenable: refresh,
    redirect: (context, state) {
      final signedIn = ref.read(sessionProvider) != null;
      final loc = state.matchedLocation;
      final public = loc == '/login' || loc == '/settings';
      if (!signedIn && !public) return '/login';
      if (signedIn && loc == '/login') return '/fixtures';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => AppShell(navigationShell: shell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/fixtures', builder: (_, _) => const FixturesScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/standings', builder: (_, _) => const StandingsScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/store', builder: (_, _) => const StoreScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/club', builder: (_, _) => const ClubTab())]),
          StatefulShellBranch(routes: [GoRoute(path: '/more', builder: (_, _) => const MoreScreen())]),
        ],
      ),
      // Detail screens are pushed on top of the shell, so Back always returns to where you were.
      GoRoute(path: '/match/:id', builder: (_, s) => MatchScreen(matchId: s.pathParameters['id']!)),
      GoRoute(path: '/club/:id', builder: (_, s) => ClubScreen(clubId: s.pathParameters['id']!)),
      GoRoute(path: '/product/:id', builder: (_, s) => ProductScreen(productId: s.pathParameters['id']!)),
      GoRoute(path: '/cart', builder: (_, _) => const CartScreen()),
      GoRoute(path: '/receipt', builder: (_, s) => ReceiptScreen(order: s.extra! as Order)),
      GoRoute(path: '/roster', builder: (_, _) => const RosterScreen()),
      GoRoute(path: '/scoring', builder: (_, s) => ScoringScreen(initialMatchId: s.uri.queryParameters['match'])),
      GoRoute(path: '/sync', builder: (_, _) => const SyncScreen()),
    ],
  );
});

class NasconApp extends ConsumerWidget {
  const NasconApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final tenant = ref.watch(sessionProvider)?.tenant;
    return MaterialApp.router(
      title: 'NaSCon Sports',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(parseHexColor(tenant?.primaryColor)),
      routerConfig: router,
      // SyncStatusBar sits above every screen (including Login and dialogs' parent routes).
      builder: (context, child) => Column(children: [
        SafeArea(bottom: false, child: SyncStatusBar(onTap: () => router.push('/sync'))),
        Expanded(child: MediaQuery.removePadding(context: context, removeTop: true, child: child!)),
      ]),
    );
  }
}
