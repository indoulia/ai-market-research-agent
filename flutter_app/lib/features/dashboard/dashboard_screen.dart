import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'recommendation.dart';
import 'recommendations_repository.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M1.136 — the primary MRA screen. Consumes EPIC-M1.135's
/// `GET /api/v1/recommendations` only — no client-side ranking/business
/// logic beyond display formatting (M1.135 AC: "Flutter consumes this
/// exact contract; no UI-side business ranking").
class DashboardScreen extends StatefulWidget {
  final RecommendationsRepository? repository;

  const DashboardScreen({super.key, this.repository});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final RecommendationsRepository _repository;
  final ScrollController _scrollController = ScrollController();

  _LoadState _state = _LoadState.loading;
  List<Recommendation> _items = const [];
  String? _nextCursor;
  bool _loadingMore = false;
  DateTime? _lastUpdated;
  ApiException? _error;
  int? _selectedHorizon;
  RecommendationSort _sort = RecommendationSort.score;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? RecommendationsRepository();
    _scrollController.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_nextCursor == null || _loadingMore || _state != _LoadState.loaded) {
      return;
    }
    final threshold = _scrollController.position.maxScrollExtent - 400;
    if (_scrollController.position.pixels >= threshold) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _repository.fetchPage(
        horizonDays: _selectedHorizon,
        sort: _sort,
      );
      setState(() {
        _items = page.items;
        _nextCursor = page.nextCursor;
        _lastUpdated = page.asOfServerTime;
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
    setState(() => _loadingMore = true);
    try {
      final page = await _repository.fetchPage(
        horizonDays: _selectedHorizon,
        sort: _sort,
        cursor: _nextCursor,
      );
      setState(() {
        _items = [..._items, ...page.items];
        _nextCursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      // A load-more failure keeps the already-loaded page visible; the user
      // can retry by scrolling again. Only the initial load surfaces a
      // full-screen error state.
      setState(() => _loadingMore = false);
    }
  }

  void _onHorizonChanged(int days) {
    setState(() => _selectedHorizon = days);
    _load();
  }

  void _onSortChanged(RecommendationSort sort) {
    setState(() => _sort = sort);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final windowClass = MraBreakpoints.classify(constraints.maxWidth);
        return RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            controller: _scrollController,
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
    final avgTrust = _averageOf(_items.map((r) => r.trustScore));
    final avgConfidence = _averageOf(_items.map((r) => r.confidence));

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
                  'Recommendations',
                  style: theme.textTheme.headlineSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              // EPIC-M1.143: also flexible (not just the title) — at
              // extreme text-scale/narrow-width combinations this label's
              // own intrinsic width could overflow the row on its own.
              if (_lastUpdated != null)
                Flexible(
                  child: Text(
                    'Updated ${_relativeLabel(_lastUpdated!)}',
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
          const SizedBox(height: MraSpacing.md),
          Row(
            children: [
              Expanded(
                child: KpiStatCard(
                  label: 'Opportunities',
                  value: _items.length.toString(),
                  icon: Icons.trending_up,
                ),
              ),
              const SizedBox(width: MraSpacing.sm),
              Expanded(
                child: KpiStatCard(
                  label: 'Avg Trust',
                  value: avgTrust == null ? '—' : avgTrust.round().toString(),
                  icon: Icons.verified_outlined,
                ),
              ),
              const SizedBox(width: MraSpacing.sm),
              Expanded(
                child: KpiStatCard(
                  label: 'Avg Confidence',
                  value: avgConfidence == null
                      ? '—'
                      : avgConfidence.round().toString(),
                  icon: Icons.insights_outlined,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.lg),
          HorizonSelector(
            horizonsDays: const [1, 3, 5, 7],
            selectedDays: _selectedHorizon ?? 3,
            onChanged: _onHorizonChanged,
          ),
          const SizedBox(height: MraSpacing.md),
          MraFilterBar(
            options: const [
              MraFilterOption('score', 'Score'),
              MraFilterOption('trust', 'Trust'),
              MraFilterOption('upside', 'Upside'),
            ],
            selectedIds: {_sort.name},
            onToggle: (id) => _onSortChanged(
              RecommendationSort.values.firstWhere((s) => s.name == id),
            ),
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
        if (_items.isEmpty) {
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
                    itemCount: _items.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: MraSpacing.md),
                    itemBuilder: (context, index) =>
                        _buildCard(context, _items[index]),
                  )
                : SliverGrid(
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: columns,
                      mainAxisSpacing: MraSpacing.md,
                      crossAxisSpacing: MraSpacing.md,
                      mainAxisExtent: 340,
                    ),
                    delegate: SliverChildBuilderDelegate(
                      (context, index) => _buildCard(context, _items[index]),
                      childCount: _items.length,
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
                    : (_nextCursor == null
                          ? Text(
                              'You’re all caught up',
                              style: Theme.of(context).textTheme.labelSmall,
                            )
                          : const SizedBox.shrink()),
              ),
            ),
          ),
        ];
    }
  }

  Widget _buildCard(BuildContext context, Recommendation r) {
    return RecommendationCard(
      data: RecommendationCardData(
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
        // M1.135 doesn't return historical prices for the card sparkline —
        // flat line is an honest "no trend data" rendering, not fabricated
        // history.
        priceHistory: [r.price ?? 0, r.price ?? 0],
        lastUpdatedLabel: _relativeLabel(r.updatedAt),
      ),
      onTap: () => context.push('/home/recommendation/${r.id}'),
    );
  }

  static double? _averageOf(Iterable<double?> values) {
    final nonNull = values.whereType<double>().toList();
    if (nonNull.isEmpty) return null;
    return nonNull.reduce((a, b) => a + b) / nonNull.length;
  }

  static String _relativeLabel(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
