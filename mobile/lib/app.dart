import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/session.dart';
import 'core/theme.dart';
import 'data/models.dart';
import 'features/auth/login_screen.dart';
import 'features/club/club_screen.dart';
import 'features/fixtures/fixtures_screen.dart';
import 'features/live/broadcast_screen.dart';
import 'features/live/costream_screen.dart';
import 'features/live/live_feed.dart';
import 'features/live/match_live_screen.dart';
import 'features/live/qr_scanner_screen.dart';
import 'features/match/match_screen.dart';
import 'features/more/more_screen.dart';
import 'features/scoring/scoring_screen.dart';
import 'features/settings/settings_screen.dart';
import 'features/shell/app_shell.dart';
import 'features/standings/standings_screen.dart';
import 'features/store/cart_screen.dart';
import 'features/store/product_screen.dart';
import 'features/store/receipt_screen.dart';
import 'features/store/store_screen.dart';
import 'features/sync/sync_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/fixtures',
    refreshListenable: refresh,
    redirect: (context, state) {
      // Deep links (§8.4): nascon://entity/{id} and nascon://stream/{id}, however Android hands them
      // over (with or without the host), open Match Live / Co-Stream directly.
      final uri = state.uri;
      final segs = uri.pathSegments.where((x) => x.isNotEmpty).toList();
      final looksLikeLink = uri.scheme == 'nascon' ||
          (segs.length == 2 && (segs.first == 'entity' || segs.first == 'stream')) ||
          (segs.length == 1 && RegExp(r'^(match|cs-session|club|player)-').hasMatch(segs.single));
      if (looksLikeLink) {
        final target = appRouteForUri(uri);
        if (target != null && target != uri.path) return target;
      }
      final signedIn = ref.read(sessionProvider) != null;
      final loc = state.matchedLocation;
      // Live surfaces are read-only for guests, so links and QR scans never stop at login.
      final public = loc == '/login' ||
          loc == '/settings' ||
          loc == '/scan' ||
          loc.startsWith('/live/') ||
          loc.startsWith('/costream/');
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
      // Roster actions now live on the Clubs tab (the "+ Roster action" button); old links land there.
      GoRoute(path: '/roster', redirect: (_, _) => '/club'),
      GoRoute(path: '/scoring', builder: (_, s) => ScoringScreen(initialMatchId: s.uri.queryParameters['match'])),
      GoRoute(path: '/sync', builder: (_, _) => const SyncScreen()),
      GoRoute(path: '/live/:id', builder: (_, s) => MatchLiveScreen(matchId: s.pathParameters['id']!)),
      GoRoute(path: '/costream/:id', builder: (_, s) => CoStreamScreen(sessionId: s.pathParameters['id']!)),
      GoRoute(path: '/scan', builder: (_, _) => const QrScannerScreen()),
      GoRoute(path: '/broadcast', builder: (_, _) => const BroadcastScreen()),
    ],
  );
});

class NasconApp extends ConsumerWidget {
  const NasconApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final tenant = ref.watch(sessionProvider)?.tenant;
    // White-label: the tenant's colour becomes the accent (floodlight lime before sign-in).
    final accent = parseHexColor(tenant?.primaryColor);
    return MaterialApp.router(
      title: 'NaSCon Sports',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(accent),
      themeMode: ThemeMode.dark,
      scrollBehavior: const AppScrollBehavior(),
      routerConfig: router,
      // The Online / Syncing / Offline pill is part of every screen's header (widgets/sync_status_bar.dart).
    );
  }
}
