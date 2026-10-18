import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';

/// Floating pill nav: Fixtures · Table · Store · Clubs · Me.
/// Tabs navigate (never act), always visible, single-word labels; the current tab is an accent capsule.
class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const AppShell({super.key, required this.navigationShell});

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
    final current = navigationShell.currentIndex;
    return Scaffold(
      extendBody: true, // pages scroll under the floating bar
      body: navigationShell,
      bottomNavigationBar: SafeArea(
        top: false,
        minimum: const EdgeInsets.only(bottom: 14),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Semantics(
            container: true,
            label: 'Main',
            child: Container(
              height: 64,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              decoration: BoxDecoration(
                color: p.nav,
                borderRadius: BorderRadius.circular(32),
                border: Border.all(color: p.navEdge),
                boxShadow: const [BoxShadow(color: Color(0x8C000000), blurRadius: 30, offset: Offset(0, 12))],
              ),
              child: Row(children: [
                for (var i = 0; i < _tabs.length; i++)
                  Expanded(
                    child: _NavItem(
                      icon: _tabs[i].$1,
                      label: _tabs[i].$2,
                      selected: i == current,
                      // Re-tapping the current tab pops it back to its root.
                      onTap: () => navigationShell.goBranch(i, initialLocation: i == current),
                    ),
                  ),
              ]),
            ),
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
    final color = selected ? p.onAccent : const Color(0xFFA3A398);
    return Semantics(
      button: true,
      selected: selected,
      label: '$label tab',
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: AnimatedContainer(
          duration: MediaQuery.of(context).disableAnimations ? Duration.zero : const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          height: 52,
          decoration: BoxDecoration(color: selected ? p.accent : Colors.transparent, borderRadius: BorderRadius.circular(26)),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon, size: 22, color: color),
            const SizedBox(height: 2),
            Text(label, maxLines: 1, style: TextStyle(fontFamily: bodyFont, fontSize: 11, fontWeight: FontWeight.w600, color: color)),
          ]),
        ),
      ),
    );
  }
}
