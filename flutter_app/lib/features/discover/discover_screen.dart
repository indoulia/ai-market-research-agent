import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../dashboard/recommendations_repository.dart';
import '../shared/recommendation_lookup.dart';
import 'discoveries_repository.dart';
import 'discovery_card.dart';
import 'discovery_item.dart';
import 'discovery_pipeline_panel.dart';

enum _LoadState { loading, error, loaded }

const _bucketOptions = [
  MraFilterOption('ALL', 'All sizes'),
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

// EPIC-M3.6 "discovery basis" filter -- the fixed, small vocabulary of
// `app.discovery.SOURCE_*` values, same treatment as `_bucketOptions`.
const _basisOptions = [
  MraFilterOption('ALL', 'Any basis'),
  MraFilterOption('DAILY_UNIVERSE_SCAN', 'Universe scan'),
  MraFilterOption('CHATGPT', 'AI research'),
  MraFilterOption('WATCHLIST', 'Watchlist'),
];

/// EPIC-M1.140 / EPIC-M3.6 — Discover screen: search + filter bar +
/// discovery-pipeline summary over `GET /api/v1/discovery/candidates`.
class DiscoverScreen extends StatefulWidget {
  final DiscoveriesRepository? repository;
  final RecommendationsRepository? recommendationsRepository;

  const DiscoverScreen({
    super.key,
    this.repository,
    this.recommendationsRepository,
  });

  @override
  State<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends State<DiscoverScreen> {
  late final DiscoveriesRepository _repository;
  late final RecommendationsRepository _recommendationsRepository;
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();

  _LoadState _state = _LoadState.loading;
  List<DiscoveryItem> _items = const [];
  String? _nextCursor;
  bool _loadingMore = false;
  ApiException? _error;
  String _bucket = 'ALL';
  String _basis = 'ALL';
  String _query = '';

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? DiscoveriesRepository();
    _recommendationsRepository =
        widget.recommendationsRepository ?? RecommendationsRepository();
    _scrollController.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_nextCursor == null || _loadingMore || _state != _LoadState.loaded) {
      return;
    }
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 400) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _repository.fetchPage(
        marketCapBucket: _bucket == 'ALL' ? null : _bucket,
        discoveryBasis: _basis == 'ALL' ? null : _basis,
      );
      setState(() {
        _items = page.items;
        _nextCursor = page.nextCursor;
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
        marketCapBucket: _bucket == 'ALL' ? null : _bucket,
        discoveryBasis: _basis == 'ALL' ? null : _basis,
        cursor: _nextCursor,
      );
      setState(() {
        _items = [..._items, ...page.items];
        _nextCursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      setState(() => _loadingMore = false);
    }
  }

  void _onBucketChanged(String id) {
    setState(() => _bucket = id);
    _load();
  }

  void _onBasisChanged(String id) {
    setState(() => _basis = id);
    _load();
  }

  List<DiscoveryItem> get _filteredItems {
    if (_query.isEmpty) return _items;
    final q = _query.toLowerCase();
    return _items
        .where(
          (i) =>
              i.symbol.toLowerCase().contains(q) ||
              (i.companyName?.toLowerCase().contains(q) ?? false),
        )
        .toList();
  }

  Future<void> _onCardTap(DiscoveryItem item) async {
    // EPIC-M3.6: a PUBLISHED candidate already carries its recommendation
    // id -- no extra lookup request needed for that (the common) case.
    final id =
        item.publishedRecommendationId ??
        await findRecommendationIdBySymbol(
          _recommendationsRepository,
          item.symbol,
        );
    if (!mounted) return;
    if (id != null) {
      context.push('/discover/recommendation/$id');
    } else {
      showMraToast(context, 'No active recommendation for ${item.symbol} yet.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final windowClass = MraBreakpoints.classify(constraints.maxWidth);
        final columns = switch (windowClass) {
          MraWindowClass.compact => 1,
          MraWindowClass.medium => 2,
          _ => 3,
        };

        return RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            controller: _scrollController,
            slivers: [
              SliverToBoxAdapter(child: _buildHeader(context)),
              SliverToBoxAdapter(
                child: DiscoveryPipelinePanel(repository: _repository),
              ),
              ..._buildBody(context, columns),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Discover', style: theme.textTheme.headlineSmall),
          const SizedBox(height: MraSpacing.md),
          MraSearchField(
            hintText: 'Search symbol or company',
            controller: _searchController,
            onChanged: (v) => setState(() => _query = v),
            onClear: _query.isEmpty
                ? null
                : () {
                    _searchController.clear();
                    setState(() => _query = '');
                  },
          ),
          const SizedBox(height: MraSpacing.md),
          MraFilterBar(
            options: _bucketOptions,
            selectedIds: {_bucket},
            onToggle: _onBucketChanged,
          ),
          const SizedBox(height: MraSpacing.sm),
          MraFilterBar(
            options: _basisOptions,
            selectedIds: {_basis},
            onToggle: _onBasisChanged,
          ),
        ],
      ),
    );
  }

  List<Widget> _buildBody(BuildContext context, int columns) {
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
        final filtered = _filteredItems;
        if (filtered.isEmpty) {
          return [
            const SliverFillRemaining(
              hasScrollBody: false,
              child: MraStateView.empty(
                message: 'No discovered candidates match these filters.',
              ),
            ),
          ];
        }
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            sliver: columns == 1
                ? SliverList.separated(
                    itemCount: filtered.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: MraSpacing.md),
                    itemBuilder: (context, index) => DiscoveryCard(
                      item: filtered[index],
                      onTap: () => _onCardTap(filtered[index]),
                    ),
                  )
                : SliverGrid(
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: columns,
                      mainAxisSpacing: MraSpacing.md,
                      crossAxisSpacing: MraSpacing.md,
                      mainAxisExtent: 300,
                    ),
                    delegate: SliverChildBuilderDelegate(
                      (context, index) => DiscoveryCard(
                        item: filtered[index],
                        onTap: () => _onCardTap(filtered[index]),
                      ),
                      childCount: filtered.length,
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
                    : const SizedBox.shrink(),
              ),
            ),
          ),
        ];
    }
  }
}
