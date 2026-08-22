import 'package:flutter/material.dart';

import '../design_system/design_system.dart';

/// EPIC-M1.133 acceptance criterion: a component gallery/demo exists for QA,
/// demonstrating every shared design-system component in one place.
class GalleryScreen extends StatefulWidget {
  const GalleryScreen({super.key});

  @override
  State<GalleryScreen> createState() => _GalleryScreenState();
}

class _GalleryScreenState extends State<GalleryScreen> {
  int _selectedHorizon = 3;
  final Set<String> _selectedFilters = {'top'};
  bool _showSkeletons = false;

  static const _sampleHistory = [10.2, 10.6, 10.4, 10.9, 11.3, 11.1, 11.8];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('MRA Design System Gallery'),
        actions: [
          IconButton(
            tooltip: 'Toggle skeleton demo',
            icon: Icon(
              _showSkeletons ? Icons.visibility_off : Icons.visibility,
            ),
            onPressed: () => setState(() => _showSkeletons = !_showSkeletons),
          ),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final windowClass = MraBreakpoints.classify(constraints.maxWidth);
          final columns = switch (windowClass) {
            MraWindowClass.compact => 1,
            MraWindowClass.medium => 2,
            _ => 3,
          };

          return SingleChildScrollView(
            padding: const EdgeInsets.all(MraSpacing.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1200),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SectionTitle('KPI stat cards'),
                  GridView.count(
                    crossAxisCount: columns,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: MraSpacing.md,
                    crossAxisSpacing: MraSpacing.md,
                    childAspectRatio: 2.6,
                    children: const [
                      KpiStatCard(
                        label: 'Opportunities',
                        value: '18',
                        icon: Icons.trending_up,
                        delta: '+3',
                      ),
                      KpiStatCard(
                        label: 'Avg Trust',
                        value: '76',
                        icon: Icons.verified_outlined,
                      ),
                      KpiStatCard(
                        label: 'Avg Confidence',
                        value: '68',
                        icon: Icons.insights_outlined,
                        delta: '-2',
                        deltaPositive: false,
                      ),
                    ],
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Recommendation card'),
                  if (_showSkeletons)
                    const MraCard(child: SkeletonCard())
                  else
                    RecommendationCard(
                      data: RecommendationCardData(
                        symbol: 'TATASTEEL',
                        companyName: 'Tata Steel Ltd.',
                        currentPrice: 168.35,
                        changePercent: 1.42,
                        horizonDays: _selectedHorizon,
                        targetPrice: 176.5,
                        stopLossPrice: 163.0,
                        upsidePercent: 4.8,
                        score: 82,
                        confidence: 71,
                        trust: 65,
                        priceHistory: _sampleHistory,
                        lastUpdatedLabel: 'Updated 4m ago',
                      ),
                      onTap: () =>
                          showMraToast(context, 'Opened TATASTEEL detail'),
                    ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Horizon selector'),
                  HorizonSelector(
                    horizonsDays: const [1, 3, 5, 7],
                    selectedDays: _selectedHorizon,
                    onChanged: (v) => setState(() => _selectedHorizon = v),
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Filter bar'),
                  MraFilterBar(
                    options: const [
                      MraFilterOption('top', 'Top picks'),
                      MraFilterOption('new', 'New today'),
                      MraFilterOption('high_trust', 'High trust'),
                    ],
                    selectedIds: _selectedFilters,
                    onToggle: (id) => setState(() {
                      if (_selectedFilters.contains(id)) {
                        _selectedFilters.remove(id);
                      } else {
                        _selectedFilters.add(id);
                      }
                    }),
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Search'),
                  const MraSearchField(hintText: 'Search symbol or company'),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Chips'),
                  const Wrap(
                    spacing: MraSpacing.sm,
                    children: [
                      MraChip(label: 'Neutral', tone: MraChipTone.neutral),
                      MraChip(
                        label: 'Positive',
                        tone: MraChipTone.positive,
                        icon: Icons.check_circle,
                      ),
                      MraChip(
                        label: 'Warning',
                        tone: MraChipTone.warning,
                        icon: Icons.warning_amber,
                      ),
                      MraChip(
                        label: 'Error',
                        tone: MraChipTone.error,
                        icon: Icons.error,
                      ),
                      MraChip(
                        label: 'Info',
                        tone: MraChipTone.info,
                        icon: Icons.info,
                      ),
                      MraChip(
                        label: 'Market up',
                        tone: MraChipTone.marketUp,
                        icon: Icons.trending_up,
                      ),
                      MraChip(
                        label: 'Market down',
                        tone: MraChipTone.marketDown,
                        icon: Icons.trending_down,
                      ),
                    ],
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Dense data table'),
                  MraDenseTable(
                    columns: const [
                      MraColumn('Symbol'),
                      MraColumn('Price', alignment: Alignment.centerRight),
                      MraColumn('Score', alignment: Alignment.centerRight),
                    ],
                    rows: [
                      [
                        const Text('TATASTEEL'),
                        const Text('168.35'),
                        const Text('82'),
                      ],
                      [
                        const Text('INFY'),
                        const Text('1512.10'),
                        const Text('74'),
                      ],
                    ],
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('News card'),
                  NewsCard(
                    headline: 'RBI holds repo rate steady amid inflation watch',
                    source: 'Market Wire',
                    publishedLabel: '2h ago',
                    tag: 'Macro',
                    onTap: () {},
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Timeline'),
                  const Column(
                    children: [
                      TimelineEventRow(
                        title: 'Recommendation generated',
                        timestampLabel: 'Aug 21, 09:15',
                        tone: MraTimelineTone.positive,
                      ),
                      TimelineEventRow(
                        title: 'Target revised',
                        subtitle: 'Target raised to 176.50',
                        timestampLabel: 'Aug 21, 14:02',
                        tone: MraTimelineTone.neutral,
                        isLast: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  _SectionTitle('Empty / error / offline states'),
                  Row(
                    children: [
                      Expanded(
                        child: SizedBox(
                          height: 220,
                          child: MraStateView.empty(),
                        ),
                      ),
                      Expanded(
                        child: SizedBox(
                          height: 220,
                          child: MraStateView.error(onAction: () {}),
                        ),
                      ),
                      Expanded(
                        child: SizedBox(
                          height: 220,
                          child: MraStateView.offline(onAction: () {}),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: MraSpacing.xxl),
                  FilledButton(
                    onPressed: () => showMraBottomSheet(
                      context: context,
                      title: 'Sheet example',
                      builder: (_) => const Text('Bottom sheet content.'),
                    ),
                    child: const Text('Show bottom sheet'),
                  ),
                  const SizedBox(height: MraSpacing.xxxl),
                  Text(
                    'Window class: ${windowClass.name} (${constraints.maxWidth.toStringAsFixed(0)}px)',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: MraSpacing.md),
      child: Text(text, style: Theme.of(context).textTheme.titleLarge),
    );
  }
}
