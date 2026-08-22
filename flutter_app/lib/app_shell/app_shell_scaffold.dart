import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../design_system/components/marksy_logo.dart';
import '../design_system/tokens/mra_colors.dart';
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

  Map<ShortcutActivator, VoidCallback> _shortcuts() {
    return {
      for (var i = 0; i < kAppDestinations.length; i++)
        SingleActivator(_digitKey(i + 1), alt: true): () =>
            _onDestinationSelected(i),
    };
  }

  LogicalKeyboardKey _digitKey(int oneBased) {
    const digits = [
      LogicalKeyboardKey.digit1,
      LogicalKeyboardKey.digit2,
      LogicalKeyboardKey.digit3,
      LogicalKeyboardKey.digit4,
      LogicalKeyboardKey.digit5,
      LogicalKeyboardKey.digit6,
      LogicalKeyboardKey.digit7,
    ];
    return digits[oneBased - 1];
  }

  @override
  Widget build(BuildContext context) {
    // Web/desktop keyboard shortcut: Alt+1..7 jumps to a destination, per
    // EPIC-M1.134's "keyboard shortcuts ... on web" shell requirement.
    return CallbackShortcuts(
      bindings: _shortcuts(),
      child: Focus(autofocus: true, child: _buildResponsiveShell(context)),
    );
  }

  Widget _buildResponsiveShell(BuildContext context) {
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
      // EPIC-173 — the one piece of brand chrome that stays deep-navy on
      // every screen/theme, matching the approved dashboard reference
      // (https://claude.ai/code/artifact/dc85a4ea-4aa3-4520-84db-4b657c6a38bd)
      // rather than following the app's own light/dark ThemeData.
      backgroundColor: MraColors.brandDeepNavy,
      foregroundColor: MraColors.neutral0,
      title: const MarksyLogo(iconSize: 24, fontSize: 18, light: true),
      actions: [
        IconButton(
          tooltip: 'Search',
          icon: const Icon(Icons.search),
          // No standalone global-search screen exists yet — Discover's
          // search field is the real "search symbol or company" surface,
          // so route there rather than leaving this a dead no-op button.
          onPressed: () => context.go('/discover'),
        ),
        IconButton(
          tooltip: 'Account',
          icon: const Icon(Icons.account_circle_outlined),
          onPressed: () => context.go('/settings'),
        ),
        const SizedBox(width: MraSpacing.sm),
      ],
    );
  }
}
