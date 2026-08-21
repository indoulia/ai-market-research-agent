import 'package:flutter/material.dart';

import '../../core/auth/auth_controller.dart';
import '../../design_system/design_system.dart';
import '../feedback/feedback_history_screen.dart';
import 'general_settings_screen.dart';
import 'quick_preferences_screen.dart';

/// EPIC-M1.142 — Settings destination: "Preferences" and "Settings" as
/// tabs of one screen (same nesting pattern EPIC-M1.140 used for Market's
/// "Overview"/"News & Events"). Uses [DefaultTabController] rather than a
/// manually-owned [TabController] so [GeneralSettingsScreen] can jump back
/// to the Preferences tab for its "manage notifications" shortcut without
/// the tabs needing to be threaded through as a constructor parameter.
///
/// EPIC-M3.10 adds a third "History" tab for
/// [FeedbackHistoryScreen] — the genuine gap left after EPIC-M1.141/
/// M1.142 already covered preferences and feedback submission (see that
/// EPIC's Completion Report).
class PreferencesSettingsScreen extends StatelessWidget {
  /// EPIC-M1.146 — threaded through only so [GeneralSettingsScreen] can
  /// show a "Sign out" action; null in every context (tests, the QA
  /// gallery) that doesn't wire up real auth.
  final AuthController? authController;

  const PreferencesSettingsScreen({super.key, this.authController});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          _PreferencesTabBar(),
          Expanded(
            child: TabBarView(
              children: [
                const QuickPreferencesScreen(),
                GeneralSettingsScreen(authController: authController),
                const FeedbackHistoryScreen(),
              ],
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
      labels: const ['Preferences', 'Settings', 'History'],
      controller: DefaultTabController.of(context),
    );
  }
}
