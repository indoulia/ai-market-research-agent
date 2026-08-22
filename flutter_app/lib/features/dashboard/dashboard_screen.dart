import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
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

  const DashboardScreen({super.key, this.dashboardRepository, this.repository});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final DashboardRepository _dashboardRepository;
  late final RecommendationsRepository _repository;
  final TextEditingController _sectorController = TextEditingController();

  static const int _limit = 12;

  _LoadState _state = _LoadState.loading;
  DashboardSnapshot? _snapshot;
  List<_OpportunityRow> _extraRows = const [];
  String? _nextCursor;
  bool _bootstrappedCursor = false;
  bool _loadingMore = false;
  ApiException? _error;

  int? _selectedHorizon;
  String _market = 'ALL';
  String _sizeBucket = 'ALL';
  String? _sector;

  @override
  void initState() {
    super.initState();
    _dashboardRepository = widget.dashboardRepository ?? DashboardRepository();
    _repository = widget.repository ?? RecommendationsRepository();
    _load();
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
        return RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(child: _buildHeader(context)),
              ..._buildBody(context, windowClass),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader(BuildContext context) {
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
            const SizedBox(height: MraSpacing.md),
            _TrustSummaryCard(summary: snapshot.trustSummary),
            if (snapshot.importantEvents.isNotEmpty) ...[
              const SizedBox(height: MraSpacing.md),
              _EventsStrip(events: snapshot.importantEvents),
            ],
            if (snapshot.recentChanges.isNotEmpty) ...[
              const SizedBox(height: MraSpacing.md),
              _RecentChangesCard(items: snapshot.recentChanges),
            ],
          ],
          const SizedBox(height: MraSpacing.lg),
          HorizonSelector(
            horizonsDays: const [1, 3, 5, 7],
            selectedDays: _selectedHorizon ?? 3,
            onChanged: (days) {
              setState(() => _selectedHorizon = days);
              _onFiltersChanged();
            },
          ),
          const SizedBox(height: MraSpacing.sm),
          MraFilterBar(
            options: _marketOptions,
            selectedIds: {_market},
            onToggle: (id) {
              setState(() => _market = id);
              _onFiltersChanged();
            },
          ),
          const SizedBox(height: MraSpacing.sm),
          MraFilterBar(
            options: _bucketOptions,
            selectedIds: {_sizeBucket},
            onToggle: (id) {
              setState(() => _sizeBucket = id);
              _onFiltersChanged();
            },
          ),
          const SizedBox(height: MraSpacing.sm),
          TextField(
            controller: _sectorController,
            textInputAction: TextInputAction.search,
            style: theme.textTheme.bodyMedium,
            decoration: InputDecoration(
              hintText: 'Filter by sector',
              prefixIcon: const Icon(Icons.filter_alt_outlined, size: 20),
              suffixIcon: (_sector == null)
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      tooltip: 'Clear sector filter',
                      onPressed: () {
                        _sectorController.clear();
                        setState(() => _sector = null);
                        _onFiltersChanged();
                      },
                    ),
              filled: true,
              fillColor: theme.colorScheme.surfaceContainerHigh,
              contentPadding: const EdgeInsets.symmetric(
                vertical: 0,
                horizontal: MraSpacing.md,
              ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              isDense: true,
            ),
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
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            sliver: columns == 1
                ? SliverList.separated(
                    itemCount: rows.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: MraSpacing.md),
                    itemBuilder: (context, index) =>
                        _buildCard(context, rows[index]),
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
                  ),
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

/// EPIC-M3.2's trust/performance summary widget -- a compact projection of
/// M1.147's tracking summary via the snapshot's `trustSummary`.
class _TrustSummaryCard extends StatelessWidget {
  final DashboardTrustSummary summary;
  const _TrustSummaryCard({required this.summary});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final trust = summary.trustScore;
    final delta = summary.trustDelta;
    return MraCard(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.lg,
        vertical: MraSpacing.md,
      ),
      child: Row(
        children: [
          Icon(
            Icons.verified_outlined,
            size: 18,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: MraSpacing.sm),
          Expanded(
            child: Text(
              trust == null
                  ? 'Trust: not enough evaluated history yet'
                  : 'Trust: ${(trust * 100).round()}%'
                        '${delta == null ? '' : (delta >= 0 ? ' (+${(delta * 100).toStringAsFixed(1)})' : ' (${(delta * 100).toStringAsFixed(1)})')}',
              style: theme.textTheme.bodyMedium,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (summary.smallSample)
            const MraChip(label: 'Small sample', tone: MraChipTone.warning),
        ],
      ),
    );
  }
}

/// Important events/news strip -- a compact horizontal row so it never
/// dominates the screen (AC).
class _EventsStrip extends StatelessWidget {
  final List<DashboardEvent> events;
  const _EventsStrip({required this.events});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      height: 64,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: events.length,
        separatorBuilder: (_, _) => const SizedBox(width: MraSpacing.sm),
        itemBuilder: (context, index) {
          final event = events[index];
          return SizedBox(
            width: 220,
            child: MraCard(
              padding: const EdgeInsets.symmetric(
                horizontal: MraSpacing.md,
                vertical: MraSpacing.sm,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
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
          );
        },
      ),
    );
  }
}

/// Recently-changed-recommendations widget -- the same open, positive-only
/// feed the opportunities grid shows, ordered by recency of update rather
/// than score (see `api/services/dashboard.py`'s own doc comment on why
/// there is no separate lifecycle-history source for this).
class _RecentChangesCard extends StatelessWidget {
  final List<DashboardOpportunity> items;
  const _RecentChangesCard({required this.items});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final shown = items.take(5).toList();
    return MraCard(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.lg,
        vertical: MraSpacing.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Recently changed', style: theme.textTheme.titleMedium),
          const SizedBox(height: MraSpacing.sm),
          for (final item in shown)
            Padding(
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
            ),
        ],
      ),
    );
  }
}
