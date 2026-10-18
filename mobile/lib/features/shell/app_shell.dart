import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/session.dart';
import '../../core/theme.dart';

/// Tab roots, in bar order. Detail pages light the tab they belong to (see [DetailShell]).
const tabRoutes = ['/fixtures', '/standings', '/store', '/club', '/more'];

/// Root tabs: floating pill nav over the page; tab bodies cross-fade on switch.
class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  final List<Widget> children;
  const AppShell({super.key, required this.navigationShell, required this.children});

  @override
  Widget build(BuildContext context) {
    final current = navigationShell.currentIndex;
    return Scaffold(
      extendBody: true, // pages scroll under the floating bar
      body: _FadingBranches(index: current, children: children),
      bottomNavigationBar: FloatingNavBar(
        currentIndex: current,
        // Re-tapping the current tab pops it back to its root.
        onTap: (i) => navigationShell.goBranch(i, initialLocation: i == current),
      ),
    );
  }
}

/// Every pushed page (match, club, product, cart, live, co-stream, scan …) keeps the same bar, with the
/// tab it belongs to lit. Signed-out viewers (deep links, QR) get no bar, since the tabs need an account.
class DetailShell extends ConsumerWidget {
  final String location;
  final Widget child;
  const DetailShell({super.key, required this.location, required this.child});

  static int indexFor(String loc) {
    if (loc.startsWith('/standings')) return 1;
    if (loc.startsWith('/product') || loc.startsWith('/cart') || loc.startsWith('/receipt')) return 2;
    if (loc.startsWith('/club/')) return 3;
    if (loc.startsWith('/sync') || loc.startsWith('/settings') || loc.startsWith('/scan') ||
        loc.startsWith('/broadcast') || loc.startsWith('/scoring')) {
      return 4;
    }
    return 0; // match, live, co-stream
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final signedIn = ref.watch(sessionProvider) != null;
    return Scaffold(
      extendBody: true,
      body: child,
      bottomNavigationBar:
          signedIn ? FloatingNavBar(currentIndex: indexFor(location), onTap: (i) => context.go(tabRoutes[i])) : null,
    );
  }
}

/// Keeps every tab alive (state and scroll preserved) and cross-fades with a slight lift between them.
class _FadingBranches extends StatelessWidget {
  final int index;
  final List<Widget> children;
  const _FadingBranches({required this.index, required this.children});

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.of(context).disableAnimations;
    final duration = reduce ? Duration.zero : const Duration(milliseconds: 240);
    return Stack(fit: StackFit.expand, children: [
      for (var i = 0; i < children.length; i++)
        // The fade itself must keep ticking, so TickerMode only pauses the hidden tab's own content.
        IgnorePointer(
          ignoring: i != index,
          child: AnimatedOpacity(
            opacity: i == index ? 1 : 0,
            duration: duration,
            curve: Curves.easeOutCubic,
            child: AnimatedSlide(
              offset: i == index ? Offset.zero : const Offset(0, 0.015),
              duration: duration,
              curve: Curves.easeOutCubic,
              child: TickerMode(
                enabled: i == index,
                child: ExcludeSemantics(excluding: i != index, child: children[i]),
              ),
            ),
          ),
        ),
    ]);
  }
}

/// Floating pill nav: Fixtures · Table · Store · Clubs · Me. The lime capsule slides to the selected tab.
class FloatingNavBar extends StatelessWidget {
  final int currentIndex;
  final ValueChanged<int> onTap;
  const FloatingNavBar({super.key, required this.currentIndex, required this.onTap});

  static const _tabs = [
    (Icons.calendar_month_outlined, 'Fixtures'),
    (Icons.sort_rounded, 'Table'),
    (Icons.shopping_bag_outlined, 'Store'),
    (Icons.shield_outlined, 'Clubs'),
    (Icons.person_outline_rounded, 'Me'),
  ];

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final reduce = MediaQuery.of(context).disableAnimations;
    final n = _tabs.length;
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.only(bottom: 14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Semantics(
          container: true,
          label: 'Main',
          child: Container(
            height: 64,
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: p.nav,
              borderRadius: BorderRadius.circular(32),
              border: Border.all(color: p.navEdge),
              boxShadow: const [BoxShadow(color: Color(0x8C000000), blurRadius: 30, offset: Offset(0, 12))],
            ),
            child: Stack(children: [
              // Sliding selection capsule.
              AnimatedAlign(
                alignment: Alignment(-1 + 2 * currentIndex / (n - 1), 0),
                duration: reduce ? Duration.zero : const Duration(milliseconds: 300),
                curve: Curves.easeOutCubic,
                child: FractionallySizedBox(
                  widthFactor: 1 / n,
                  heightFactor: 1,
                  child: DecoratedBox(decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(26))),
                ),
              ),
              Row(children: [
                for (var i = 0; i < n; i++)
                  Expanded(
                    child: _NavItem(icon: _tabs[i].$1, label: _tabs[i].$2, selected: i == currentIndex, onTap: () => onTap(i)),
                  ),
              ]),
            ]),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _NavItem({required this.icon, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final reduce = MediaQuery.of(context).disableAnimations;
    final color = selected ? p.onAccent : const Color(0xFFA3A398);
    final duration = reduce ? Duration.zero : const Duration(milliseconds: 220);
    return Semantics(
      button: true,
      selected: selected,
      label: '$label tab',
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: AnimatedScale(
          scale: selected ? 1.0 : 0.94,
          duration: duration,
          curve: Curves.easeOut,
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            TweenAnimationBuilder<Color?>(
              tween: ColorTween(end: color),
              duration: duration,
              builder: (_, c, _) => Icon(icon, size: 22, color: c),
            ),
            const SizedBox(height: 2),
            AnimatedDefaultTextStyle(
              duration: duration,
              style: TextStyle(fontFamily: bodyFont, fontSize: 11, fontWeight: FontWeight.w600, color: color),
              child: Text(label, maxLines: 1),
            ),
          ]),
        ),
      ),
    );
  }
}
