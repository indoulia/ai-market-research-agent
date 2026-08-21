import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'general_settings_screen.dart';
import 'quick_preferences_screen.dart';

/// EPIC-M1.142 — Settings destination: "Preferences" and "Settings" as
/// tabs of one screen (same nesting pattern EPIC-M1.140 used for Market's
/// "Overview"/"News & Events"). Uses [DefaultTabController] rather than a
/// manually-owned [TabController] so [GeneralSettingsScreen] can jump back
/// to the Preferences tab for its "manage notifications" shortcut without
/// the tabs needing to be threaded through as a constructor parameter.
class PreferencesSettingsScreen extends StatelessWidget {
  const PreferencesSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          _PreferencesTabBar(),
          const Expanded(
            child: TabBarView(
              children: [QuickPreferencesScreen(), GeneralSettingsScreen()],
            ),
          ),
        ],
      ),
    );
  }
}

class _PreferencesTabBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MraTabBar(
      labels: const ['Preferences', 'Settings'],
      controller: DefaultTabController.of(context),
    );
  }
}
