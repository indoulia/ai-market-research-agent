import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import '../news_events/news_events_screen.dart';
import 'market_overview_screen.dart';

/// EPIC-M1.140 — Market destination: "Overview" and "News & Events" as
/// tabs of one screen, since EPIC-M1.134's approved shell has a fixed
/// six-destination navigation and doesn't add a seventh "News" tab.
class MarketScreen extends StatefulWidget {
  const MarketScreen({super.key});

  @override
  State<MarketScreen> createState() => _MarketScreenState();
}

class _MarketScreenState extends State<MarketScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        MraTabBar(
          labels: const ['Overview', 'News & Events'],
          controller: _controller,
        ),
        Expanded(
          child: TabBarView(
            controller: _controller,
            children: const [MarketOverviewScreen(), NewsEventsScreen()],
          ),
        ),
      ],
    );
  }
}
