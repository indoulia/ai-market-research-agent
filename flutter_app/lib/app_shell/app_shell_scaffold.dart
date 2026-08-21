import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design_system/tokens/mra_spacing.dart';
import 'app_destination.dart';

/// EPIC-M1.134 — the responsive app shell. Chooses bottom navigation,
/// navigation rail or an extended rail purely from available window width
/// (via [MraBreakpoints]), never from platform/device detection. Wraps a
/// go_router [StatefulShellRoute] branch so each destination keeps its own
/// navigation stack and scroll position when switching tabs.
class AppShellScaffold extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const AppShellScaffold({super.key, required this.navigationShell});

  void _onDestinationSelected(int index) {
    navigationShell.goBranch(
      index,
      initialLocation: index == navigationShell.currentIndex,
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 600;
        final isExtended = constraints.maxWidth >= 1024;

        if (isCompact) {
          return Scaffold(
            appBar: const _ShellAppBar(),
            body: navigationShell,
            bottomNavigationBar: NavigationBar(
              selectedIndex: navigationShell.currentIndex,
              onDestinationSelected: _onDestinationSelected,
              destinations: kAppDestinations
                  .map(
                    (d) => NavigationDestination(
                      icon: Icon(d.icon),
                      selectedIcon: Icon(d.selectedIcon),
                      label: d.label,
                    ),
                  )
                  .toList(),
            ),
          );
        }

        return Scaffold(
          appBar: const _ShellAppBar(),
          body: Row(
            children: [
              NavigationRail(
                extended: isExtended,
                minExtendedWidth: 220,
                selectedIndex: navigationShell.currentIndex,
                onDestinationSelected: _onDestinationSelected,
                labelType: isExtended ? null : NavigationRailLabelType.all,
                destinations: kAppDestinations
                    .map(
                      (d) => NavigationRailDestination(
                        icon: Icon(d.icon),
                        selectedIcon: Icon(d.selectedIcon),
                        label: Text(d.label),
                      ),
                    )
                    .toList(),
              ),
              const VerticalDivider(width: 1),
              Expanded(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1200),
                    child: navigationShell,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ShellAppBar extends StatelessWidget implements PreferredSizeWidget {
  const _ShellAppBar();

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: const Text('MRA'),
      actions: [
        IconButton(
          tooltip: 'Search',
          icon: const Icon(Icons.search),
          onPressed: () {},
        ),
        IconButton(
          tooltip: 'Account',
          icon: const Icon(Icons.account_circle_outlined),
          onPressed: () {},
        ),
        const SizedBox(width: MraSpacing.sm),
      ],
    );
  }
}
