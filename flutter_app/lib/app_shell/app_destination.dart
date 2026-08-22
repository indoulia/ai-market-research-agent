import 'package:flutter/material.dart';

/// EPIC-M1.134 — the six primary app destinations. A single source of truth
/// so mobile bottom nav, medium/large nav rail and route config never drift.
class AppDestination {
  final String path;
  final String label;
  final IconData icon;
  final IconData selectedIcon;

  /// The EPIC that owns this destination's real screen; until that lands,
  /// the destination renders an honest placeholder rather than fake content.
  final String ownerEpic;

  const AppDestination({
    required this.path,
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.ownerEpic,
  });
}

const List<AppDestination> kAppDestinations = [
  AppDestination(
    path: '/home',
    label: 'Home',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
    ownerEpic: 'EPIC-M1.136 Recommendation Dashboard UI',
  ),
  AppDestination(
    path: '/discover',
    label: 'Discover',
    icon: Icons.explore_outlined,
    selectedIcon: Icons.explore,
    ownerEpic: 'EPIC-M1.140 Discovery/Market/News UI',
  ),
  AppDestination(
    path: '/tracking',
    label: 'Tracking',
    icon: Icons.timeline_outlined,
    selectedIcon: Icons.timeline,
    ownerEpic: 'EPIC-M1.148 Longitudinal Tracking Dashboard UI',
  ),
  AppDestination(
    path: '/market',
    label: 'Market',
    icon: Icons.public_outlined,
    selectedIcon: Icons.public,
    ownerEpic: 'EPIC-M1.140 Discovery/Market/News UI',
  ),
  AppDestination(
    path: '/opportunities',
    label: 'Opportunities',
    icon: Icons.grid_view_outlined,
    selectedIcon: Icons.grid_view,
    ownerEpic: 'EPIC-M3.3 Opportunity Explorer',
  ),
  AppDestination(
    path: '/history',
    label: 'History',
    icon: Icons.history_outlined,
    selectedIcon: Icons.history,
    ownerEpic: 'EPIC-M3.17 Recommendation History UI',
  ),
  AppDestination(
    path: '/settings',
    label: 'Settings',
    icon: Icons.settings_outlined,
    selectedIcon: Icons.settings,
    ownerEpic: 'EPIC-M1.142 Feedback/Preferences UI',
  ),
];
