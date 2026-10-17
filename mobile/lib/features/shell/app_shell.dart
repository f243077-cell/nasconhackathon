import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';

/// Tab bar: Fixtures · Standings · Store · Club · Account.
/// tab-bars.md: tabs navigate (never act), always visible, single-word labels, filled symbols.
class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const AppShell({super.key, required this.navigationShell});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: p.separator, width: 0.5))),
        child: NavigationBar(
          selectedIndex: navigationShell.currentIndex,
          // Re-tapping the current tab pops it back to its root, like iOS.
          onDestinationSelected: (i) => navigationShell.goBranch(i, initialLocation: i == navigationShell.currentIndex),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.calendar_month_rounded), label: 'Fixtures'),
            NavigationDestination(icon: Icon(Icons.format_list_numbered_rounded), label: 'Standings'),
            NavigationDestination(icon: Icon(Icons.shopping_bag_rounded), label: 'Store'),
            NavigationDestination(icon: Icon(Icons.shield_rounded), label: 'Club'),
            NavigationDestination(icon: Icon(Icons.account_circle_rounded), label: 'Account'),
          ],
        ),
      ),
    );
  }
}
