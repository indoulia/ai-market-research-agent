import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../tracking/tracked_prediction.dart';
import '../tracking/tracking_repository.dart';
import '../tracking/tracking_summary.dart';
import 'dashboard_repository.dart';
import 'dashboard_snapshot.dart';
import 'recommendation.dart';
import 'recommendations_repository.dart';

enum _LoadState { loading, error, loaded }

const _bucketOptions = [
  MraFilterOption('ALL', 'All sizes'),
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

const _marketOptions = [
  MraFilterOption('ALL', 'All markets'),
  MraFilterOption('NSE', 'NSE'),
];

/// One row of the opportunities grid, unified so it can come from either
/// the initial `/dashboard/snapshot` request or a follow-on
/// `/recommendations` page (see [_DashboardScreenState._loadMore]).
class _OpportunityRow {
  final int id;
  final RecommendationCardData card;
  const _OpportunityRow(this.id, this.card);
}

/// EPIC-M3.2 — the Home destination: a compact "what is the market doing,
/// what are the best positive opportunities, what changed" first screen.
/// Consumes EPIC-M3.2's `GET /api/v1/dashboard/snapshot` for all core
/// content in one request (AC), falling back to EPIC-M1.135's
/// `/recommendations` only for scrolling past the snapshot's own top-N
/// opportunities.
class DashboardScreen extends StatefulWidget {
  final DashboardRepository? dashboardRepository;
  final RecommendationsRepository? repository;
  final TrackingRepository? trackingRepository;

  const DashboardScreen({
    super.key,
    this.dashboardRepository,
    this.repository,
    this.trackingRepository,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final DashboardRepository _dashboardRepository;
  late final RecommendationsRepository _repository;
  late final TrackingRepository _trackingRepository;
  final TextEditingController _sectorController = TextEditingController();

  static const int _limit = 12;

  _LoadState _state = _LoadState.loading;
  DashboardSnapshot? _snapshot;
  List<_OpportunityRow> _extraRows = const [];
  String? _nextCursor;
  bool _bootstrappedCursor = false;
  bool _loadingMore = false;
  ApiException? _error;

  // EPIC-173 Performance card — fetched independently of the snapshot so a
  // tracking-service hiccup never blocks the rest of the dashboard; null
  // means "not available yet", not "zero".
  TrackingSummary? _trackingSummary;
  List<TrackedPrediction> _closedCalls = const [];

  int? _selectedHorizon;
  String _market = 'ALL';
  String _sizeBucket = 'ALL';
  String? _sector;

  @override
  void initState() {
    super.initState();
    _dashboardRepository = widget.dashboardRepository ?? DashboardRepository();
    _repository = widget.repository ?? RecommendationsRepository();
    _trackingRepository = widget.trackingRepository ?? TrackingRepository();
    _load();
    _loadPerformance();
  }

  /// EPIC-173 — best-effort; the Performance card degrades to trust-only
  /// (already carried by [_snapshot]) if either fetch fails, rather than
  /// surfacing a second full-screen error state for a secondary widget.
  Future<void> _loadPerformance() async {
    try {
      final summary = await _trackingRepository.fetchSummary(range: '30d');
      if (mounted) setState(() => _trackingSummary = summary);
    } catch (_) {
      // Left null -- _PerformanceCard renders trust-only.
    }
    try {
      final page = await _trackingRepository.fetchPredictions(
        status: 'closed',
        pageSize: 5,
      );
      if (mounted) setState(() => _closedCalls = page.items);
    } catch (_) {
      // Left empty -- the Activity card's "Closed calls" tab shows its
      // own empty state rather than fabricating rows.
    }
  }

  @override
  void dispose() {
    _sectorController.dispose();
    super.dispose();
  }

  bool get _canLoadMore => !_bootstrappedCursor || _nextCursor != null;

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final snapshot = await _dashboardRepository.fetchSnapshot(
        market: _market == 'ALL' ? null : _market,
        horizonDays: _selectedHorizon,
        sector: _sector,
        marketCapBucket: _sizeBucket == 'ALL' ? null : _sizeBucket,
        limit: _limit,
      );
      setState(() {
        _snapshot = snapshot;
        _extraRows = const [];
        _nextCursor = null;
        _bootstrappedCursor = false;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _snapshot == null) return;
    setState(() => _loadingMore = true);
    try {
      if (!_bootstrappedCursor) {
        // The snapshot's `topOpportunities` has no cursor of its own -- one
        // "bootstrap" call to the identically-sorted/filtered
        // `/recommendations` page 1 recovers the pagination cursor.
        // Duplicate rows (guaranteed, since it's the exact same query) are
        // filtered out; if that leaves nothing new, fall straight through
        // to the real next page so this doesn't cost the user an empty tap.
        final page = await _repository.fetchPage(
          horizonDays: _selectedHorizon,
          market: _market == 'ALL' ? null : _market,
          sector: _sector,
          marketCapBucket: _sizeBucket == 'ALL' ? null : _sizeBucket,
          sort: RecommendationSort.score,
          pageSize: _limit,
        );
        _bootstrappedCursor = true;
        _nextCursor = page.nextCursor;
        final seenIds = {
          ..._snapshot!.topOpportunities.map((o) => o.id),
          ..._extraRows.map((r) => r.id),
        };
        final fresh = page.items.where((r) => !seenIds.contains(r.id));
        if (fresh.isNotEmpty) {
          setState(() {
            _extraRows = [..._extraRows, ...fresh.map(_rowFromRecommendation)];
            _loadingMore = false;
          });
          return;
        }
      }
      if (_nextCursor == null) {
        setState(() => _loadingMore = false);
        return;
      }
      final page = await _repository.fetchPage(
        horizonDays: _selectedHorizon,
        market: _market == 'ALL' ? null : _market,
        sector: _sector,
        marketCapBucket: _sizeBucket == 'ALL' ? null : _sizeBucket,
        sort: RecommendationSort.score,
        pageSize: _limit,
        cursor: _nextCursor,
      );
      setState(() {
        _extraRows = [..._extraRows, ...page.items.map(_rowFromRecommendation)];
        _nextCursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      // A load-more failure keeps what's already loaded visible; the user
      // can retry by scrolling again. Only the initial load surfaces a
      // full-screen error state.
      setState(() => _loadingMore = false);
    }
  }

  void _onFiltersChanged() => _load();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final windowClass = MraBreakpoints.classify(constraints.maxWidth);
        // EPIC-173 — the "watch" rail sits beside the grid at the same
        // width AppShellScaffold extends its own NavigationRail, and folds
        // below the grid otherwise.
        final showSideRail =
            windowClass == MraWindowClass.expanded ||
            windowClass == MraWindowClass.large;

        final mainColumn = RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(child: _buildHeader(context, windowClass)),
              ..._buildBody(context, windowClass),
              if (!showSideRail)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(
                      MraSpacing.lg,
                      0,
                      MraSpacing.lg,
                      MraSpacing.lg,
                    ),
                    child: _buildSideRail(context),
                  ),
                ),
            ],
          ),
        );

        if (!showSideRail) return mainColumn;

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: mainColumn),
            SizedBox(
              width: 320,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  0,
                  MraSpacing.lg,
                  MraSpacing.lg,
                  MraSpacing.lg,
                ),
                child: SingleChildScrollView(child: _buildSideRail(context)),
              ),
            ),
          ],
        );
      },
    );
  }

  /// EPIC-173 — Performance / Activity / Important events / Coming soon,
  /// in that order. Renders nothing until the snapshot has loaded once
  /// (matches the rest of the screen's honest-empty-state convention
  /// rather than showing rail skeletons for secondary content).
  Widget _buildSideRail(BuildContext context) {
    final snapshot = _snapshot;
    if (snapshot == null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _PerformanceCard(
          trustSummary: snapshot.trustSummary,
          tracking: _trackingSummary,
        ),
        const SizedBox(height: MraSpacing.md),
        _ActivityCard(
          recentChanges: snapshot.recentChanges,
          closedCalls: _closedCalls,
        ),
        if (snapshot.importantEvents.isNotEmpty) ...[
          const SizedBox(height: MraSpacing.md),
          _ImportantEventsCard(events: snapshot.importantEvents),
        ],
        const SizedBox(height: MraSpacing.md),
        const _ComingSoonCard(),
      ],
    );
  }

  bool _howItWorksDismissed = false;

  Widget _buildHeader(BuildContext context, MraWindowClass windowClass) {
    final theme = Theme.of(context);
    final snapshot = _snapshot;

    return Padding(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                flex: 3,
                child: Text(
                  'Dashboard',
                  style: theme.textTheme.headlineSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (snapshot != null)
                Flexible(
                  child: Text(
                    'Updated ${_relativeLabel(snapshot.marketAsOf)}',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.end,
                  ),
                ),
              IconButton(
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh),
                onPressed: _load,
              ),
            ],
          ),
          if (snapshot != null) ...[
            const SizedBox(height: MraSpacing.md),
            _MarketStatusRow(snapshot: snapshot),
          ],
          if (!_howItWorksDismissed) ...[
            const SizedBox(height: MraSpacing.md),
            _HowMarksyWorksStrip(
              onDismiss: () => setState(() => _howItWorksDismissed = true),
            ),
          ],
          const SizedBox(height: MraSpacing.lg),
          _buildToolbar(context),
        ],
      ),
    );
  }

  /// EPIC-173 — the horizon/market/size filters and sector search collapse
  /// into one wrapped toolbar (was four separate full-width rows). Same
  /// widgets and state as before, layout only.
  Widget _buildToolbar(BuildContext context) {
    return MraCard(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.md,
        vertical: MraSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: MraSpacing.md,
            runSpacing: MraSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              HorizonSelector(
                horizonsDays: const [1, 3, 5, 7],
                selectedDays: _selectedHorizon ?? 3,
                onChanged: (days) {
                  setState(() => _selectedHorizon = days);
                  _onFiltersChanged();
                },
              ),
              MraFilterBar(
                options: _marketOptions,
                selectedIds: {_market},
                onToggle: (id) {
                  setState(() => _market = id);
                  _onFiltersChanged();
                },
              ),
              MraFilterBar(
                options: _bucketOptions,
                selectedIds: {_sizeBucket},
                onToggle: (id) {
                  setState(() => _sizeBucket = id);
                  _onFiltersChanged();
                },
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          MraSearchField(
            hintText: 'Filter by sector',
            prefixIcon: Icons.filter_alt_outlined,
            controller: _sectorController,
            onClear: _sector == null
                ? null
                : () {
                    _sectorController.clear();
                    setState(() => _sector = null);
                    _onFiltersChanged();
                  },
            onSubmitted: (value) {
              setState(
                () => _sector = value.trim().isEmpty ? null : value.trim(),
              );
              _onFiltersChanged();
            },
          ),
        ],
      ),
    );
  }

  List<Widget> _buildBody(BuildContext context, MraWindowClass windowClass) {
    switch (_state) {
      case _LoadState.loading:
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            sliver: SliverList.list(
              children: List.generate(
                3,
                (_) => const Padding(
                  padding: EdgeInsets.only(bottom: MraSpacing.md),
                  child: MraCard(child: SkeletonCard()),
                ),
              ),
            ),
          ),
        ];
      case _LoadState.error:
        return [
          SliverFillRemaining(
            hasScrollBody: false,
            child: MraStateView.error(
              message: _error?.message,
              onAction: _load,
            ),
          ),
        ];
      case _LoadState.loaded:
        final topRows = _snapshot!.topOpportunities
            .map(_rowFromOpportunity)
            .toList();
        final rows = [...topRows, ..._extraRows];
        if (rows.isEmpty) {
          return [
            const SliverFillRemaining(
              hasScrollBody: false,
              child: MraStateView.empty(
                message: 'No positive opportunities match these filters.',
              ),
            ),
          ];
        }
        final columns = switch (windowClass) {
          MraWindowClass.compact => 1,
          MraWindowClass.medium => 2,
          _ => 3,
        };
        // EPIC-173 — compact width renders a dense single-line row instead
        // of the full card (ring/sparkline/score-row), so roughly twice as
        // many opportunities fit per scroll on a phone.
        final opportunitiesSliver = windowClass == MraWindowClass.compact
            ? SliverToBoxAdapter(
                child: MraCard(
                  padding: EdgeInsets.zero,
                  child: Column(
                    children: [
                      for (var i = 0; i < rows.length; i++) ...[
                        if (i > 0) const Divider(height: 1),
                        _CompactOpportunityRow(
                          data: rows[i].card,
                          onTap: () => context.push(
                            '/home/recommendation/${rows[i].id}',
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              )
            : SliverGrid(
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisSpacing: MraSpacing.md,
                  crossAxisSpacing: MraSpacing.md,
                  mainAxisExtent: 340,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _buildCard(context, rows[index]),
                  childCount: rows.length,
                ),
              );
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            sliver: opportunitiesSliver,
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(MraSpacing.lg),
              child: Center(
                child: _loadingMore
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : (_canLoadMore
                          ? OutlinedButton(
                              onPressed: _loadMore,
                              child: const Text('Load more opportunities'),
                            )
                          : Text(
                              'You’re all caught up',
                              style: Theme.of(context).textTheme.labelSmall,
                            )),
              ),
            ),
          ),
        ];
    }
  }

  Widget _buildCard(BuildContext context, _OpportunityRow row) {
    return RecommendationCard(
      data: row.card,
      onTap: () => context.push('/home/recommendation/${row.id}'),
    );
  }

  static _OpportunityRow _rowFromOpportunity(DashboardOpportunity o) {
    return _OpportunityRow(
      o.id,
      RecommendationCardData(
        symbol: o.symbol,
        companyName: o.name,
        currentPrice: o.price,
        // The snapshot's leaner opportunity shape (EPIC-M3.2's own field
        // list) doesn't carry day change-% or evidence freshness -- both
        // are honestly omitted rather than fabricated; the full detail
        // screen (reachable via this card's own tap) still has them.
        changePercent: null,
        horizonDays: o.horizon,
        targetPrice: o.targetPrice,
        stopLossPrice: o.stopLoss,
        upsidePercent: o.upsidePercent,
        score: o.score,
        confidence: o.confidence,
        trust: o.trustScore,
        priceHistory: [o.price ?? 0, o.price ?? 0],
        lastUpdatedLabel: _relativeLabel(o.updatedAt),
        evidenceFreshness: null,
      ),
    );
  }

  static _OpportunityRow _rowFromRecommendation(Recommendation r) {
    return _OpportunityRow(
      r.id,
      RecommendationCardData(
        symbol: r.symbol,
        companyName: r.companyName,
        currentPrice: r.price,
        changePercent: r.changePct,
        horizonDays: r.horizonDays,
        targetPrice: r.targetPrice,
        stopLossPrice: r.stopLoss,
        upsidePercent: r.upsidePct,
        score: r.score,
        confidence: r.confidence,
        trust: r.trustScore,
        priceHistory: [r.price ?? 0, r.price ?? 0],
        lastUpdatedLabel: _relativeLabel(r.updatedAt),
        evidenceFreshness: r.evidenceFreshness,
      ),
    );
  }

  static String _relativeLabel(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}

/// Compact market-status header: regime + freshness. `marketStatus`
/// "UNKNOWN" is a real, honest gap (no market-calendar module exists yet,
/// M1.139) -- rendered as a neutral chip, never guessed from wall-clock
/// time.
class _MarketStatusRow extends StatelessWidget {
  final DashboardSnapshot snapshot;
  const _MarketStatusRow({required this.snapshot});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: MraSpacing.sm,
      runSpacing: MraSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        MraChip(
          label: snapshot.marketStatus == 'UNKNOWN'
              ? 'Market status unavailable'
              : snapshot.marketStatus,
          tone: MraChipTone.neutral,
          icon: Icons.storefront_outlined,
        ),
        if (snapshot.marketRegime != null)
          MraChip(
            label: snapshot.marketRegime!,
            tone: MraChipTone.info,
            icon: Icons.show_chart,
          ),
      ],
    );
  }
}

/// EPIC-173 — dismissible "how Marksy works" strip: score → target/SL →
/// tracked outcome. Dismissal is session-only for Phase 1 (a preferences
/// flag to persist it is a documented fast-follow, not a data source this
/// screen invents on its own).
class _HowMarksyWorksStrip extends StatelessWidget {
  final VoidCallback onDismiss;
  const _HowMarksyWorksStrip({required this.onDismiss});

  static const _steps = [
    (
      icon: Icons.query_stats,
      title: 'Score every stock',
      subtitle: 'Evidence-based, not tips',
    ),
    (
      icon: Icons.flag_outlined,
      title: 'Get target & stop-loss',
      subtitle: 'Every call is a clear plan',
    ),
    (
      icon: Icons.fact_check_outlined,
      title: 'Track the outcome',
      subtitle: 'Trust% reflects real closed calls',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    return MraCard(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.md,
        vertical: MraSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Wrap(
              spacing: MraSpacing.lg,
              runSpacing: MraSpacing.sm,
              children: [
                for (final step in _steps)
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 220),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(step.icon, size: 18, color: scheme.info),
                        const SizedBox(width: MraSpacing.xs),
                        Flexible(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                step.title,
                                style: theme.textTheme.labelMedium,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              Text(
                                step.subtitle,
                                style: theme.textTheme.labelSmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Dismiss',
            icon: const Icon(Icons.close, size: 18),
            onPressed: onDismiss,
          ),
        ],
      ),
    );
  }
}

/// EPIC-173 — merges the snapshot's `trustSummary` with the tracking
/// service's hit-rate. [tracking] is null until its own fetch resolves (or
/// forever, if it fails) -- the card degrades to trust-only rather than
/// blocking on or fabricating a hit-rate.
class _PerformanceCard extends StatelessWidget {
  final DashboardTrustSummary trustSummary;
  final TrackingSummary? tracking;

  const _PerformanceCard({required this.trustSummary, required this.tracking});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final trust = trustSummary.trustScore;
    final delta = trustSummary.trustDelta;
    final hitRate = tracking?.targetHitRate;

    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(
                Icons.verified_outlined,
                size: 16,
                color: theme.colorScheme.onSurfaceVariant,
              ),
              const SizedBox(width: MraSpacing.xs),
              Text('Performance', style: theme.textTheme.labelMedium),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            trust == null ? '—' : '${(trust * 100).round()}%',
            style: MraTypography.numeric(
              theme.textTheme.headlineSmall!,
              weight: FontWeight.w700,
            ),
          ),
          Text(
            trust == null
                ? 'Trust score · not enough evaluated history yet'
                : 'Trust score'
                      '${delta == null ? '' : (delta >= 0 ? ' · +${(delta * 100).toStringAsFixed(1)}' : ' · ${(delta * 100).toStringAsFixed(1)}')} vs last 30 days',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (trustSummary.smallSample) ...[
            const SizedBox(height: MraSpacing.xs),
            const MraChip(label: 'Small sample', tone: MraChipTone.warning),
          ],
          if (hitRate != null) ...[
            const SizedBox(height: MraSpacing.md),
            Text(
              '${(hitRate * 100).round()}% hit target · '
              'last 30 closed calls',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: MraSpacing.xs),
            ClipRRect(
              borderRadius: BorderRadius.circular(MraRadii.sm),
              child: LinearProgressIndicator(
                value: hitRate.clamp(0, 1).toDouble(),
                minHeight: 6,
                backgroundColor: theme.colorScheme.surfaceContainerHigh,
                valueColor: AlwaysStoppedAnimation<Color>(scheme.positive),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// EPIC-173 — "Recently changed" (open recommendations, from the snapshot)
/// and "Closed calls" (past outcomes, from `TrackingRepository`) share one
/// card via [MraTabBar] instead of two stacked cards.
class _ActivityCard extends StatefulWidget {
  final List<DashboardOpportunity> recentChanges;
  final List<TrackedPrediction> closedCalls;

  const _ActivityCard({required this.recentChanges, required this.closedCalls});

  @override
  State<_ActivityCard> createState() => _ActivityCardState();
}

class _ActivityCardState extends State<_ActivityCard>
    with SingleTickerProviderStateMixin {
  late final TabController _controller = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      padding: const EdgeInsets.symmetric(vertical: MraSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          MraTabBar(
            labels: const ['Recently changed', 'Closed calls'],
            controller: _controller,
          ),
          SizedBox(
            height: 168,
            child: TabBarView(
              controller: _controller,
              children: [_recentChangesList(theme), _closedCallsList(theme)],
            ),
          ),
        ],
      ),
    );
  }

  Widget _recentChangesList(ThemeData theme) {
    if (widget.recentChanges.isEmpty) {
      return Center(
        child: Text(
          'No recent changes',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      );
    }
    final shown = widget.recentChanges.take(5).toList();
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
      itemCount: shown.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final item = shown[index];
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: MraSpacing.xs),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  '${item.symbol} · ${item.status}',
                  style: theme.textTheme.bodySmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                _DashboardScreenState._relativeLabel(item.updatedAt),
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _closedCallsList(ThemeData theme) {
    if (widget.closedCalls.isEmpty) {
      return Center(
        child: Text(
          'No closed calls in this window',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
      itemCount: widget.closedCalls.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final call = widget.closedCalls[index];
        final outcome = call.outcome;
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: MraSpacing.xs),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  call.symbol,
                  style: theme.textTheme.bodySmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (outcome != null)
                MraChip(
                  label: outcome,
                  tone: outcome.toUpperCase().contains('TARGET')
                      ? MraChipTone.positive
                      : MraChipTone.neutral,
                ),
            ],
          ),
        );
      },
    );
  }
}

/// Important events/news -- reflowed as a vertical list for the watch
/// rail (was a horizontal scroller in the old single-column header).
class _ImportantEventsCard extends StatelessWidget {
  final List<DashboardEvent> events;
  const _ImportantEventsCard({required this.events});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final shown = events.take(4).toList();
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Important events', style: theme.textTheme.labelMedium),
          const SizedBox(height: MraSpacing.sm),
          for (final event in shown)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: MraSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '${event.symbol} · ${event.title}',
                    style: theme.textTheme.bodySmall,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    event.source,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// EPIC-173 — IPO and NFO share one "coming soon" card via tabs. No IPO/NFO
/// data source exists anywhere in this codebase; this is a static, honest
/// placeholder (same posture as `AppDestination.ownerEpic`'s unbuilt-screen
/// pattern), not a preview of real data.
class _ComingSoonCard extends StatefulWidget {
  const _ComingSoonCard();

  @override
  State<_ComingSoonCard> createState() => _ComingSoonCardState();
}

class _ComingSoonCardState extends State<_ComingSoonCard>
    with SingleTickerProviderStateMixin {
  late final TabController _controller = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      padding: const EdgeInsets.symmetric(vertical: MraSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            child: Row(
              children: [
                const MraChip(label: 'Coming soon', tone: MraChipTone.info),
                const Spacer(),
              ],
            ),
          ),
          MraTabBar(labels: const ['IPO', 'NFO'], controller: _controller),
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: MraSpacing.lg,
              vertical: MraSpacing.sm,
            ),
            child: SizedBox(
              height: 64,
              child: TabBarView(
                controller: _controller,
                children: [
                  Text(
                    'Open/upcoming mainboard & SME IPOs, GMP trend and '
                    'subscription status.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  Text(
                    'New Fund Offer launch window, category and AMC, framed '
                    'with the same Trust context as a stock call.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// EPIC-173 — dense single-line opportunity row for `MraWindowClass.compact`
/// screens: shrunk score ring, no sparkline, target/SL collapsed to one
/// line, so roughly twice as many opportunities are visible per scroll.
class _CompactOpportunityRow extends StatelessWidget {
  final RecommendationCardData data;
  final VoidCallback onTap;

  const _CompactOpportunityRow({required this.data, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final changePercent = data.changePercent;
    final isUp = (changePercent ?? 0) >= 0;
    final changeColor = isUp ? scheme.marketUp : scheme.marketDown;

    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: MraSpacing.md,
          vertical: MraSpacing.sm,
        ),
        child: Row(
          children: [
            SizedBox(
              width: 30,
              height: 30,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox.expand(
                    child: CircularProgressIndicator(
                      value: data.score.clamp(0, 100).toDouble() / 100,
                      strokeWidth: 3,
                      backgroundColor: theme.colorScheme.surfaceContainerHigh,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        data.score >= 70 ? scheme.positive : scheme.warning,
                      ),
                    ),
                  ),
                  Text(
                    data.score.round().toString(),
                    style: theme.textTheme.labelSmall,
                  ),
                ],
              ),
            ),
            const SizedBox(width: MraSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          data.symbol,
                          style: theme.textTheme.labelLarge,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (data.companyName != null) ...[
                        const SizedBox(width: MraSpacing.xs),
                        Expanded(
                          child: Text(
                            data.companyName!,
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ],
                  ),
                  Text(
                    '${data.horizonDays}D · Target ${data.targetPrice.toStringAsFixed(2)}'
                    ' · SL ${data.stopLossPrice.toStringAsFixed(2)}',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: MraSpacing.sm),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    data.currentPrice?.toStringAsFixed(2) ?? '—',
                    style: MraTypography.numeric(theme.textTheme.labelLarge!),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (changePercent != null)
                    Text(
                      '${isUp ? '▲' : '▼'}${changePercent.abs().toStringAsFixed(2)}%',
                      style: MraTypography.numeric(
                        theme.textTheme.labelSmall!.copyWith(
                          color: changeColor,
                        ),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
