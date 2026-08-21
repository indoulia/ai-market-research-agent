import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../dashboard/recommendations_repository.dart';
import '../shared/recommendation_lookup.dart';
import 'discoveries_repository.dart';
import 'discovery_card.dart';
import 'discovery_item.dart';

enum _LoadState { loading, error, loaded }

const _bucketOptions = [
  MraFilterOption('ALL', 'All sizes'),
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

/// EPIC-M1.140 — Discover screen: search + filter bar over EPIC-M1.139's
/// `GET /api/v1/discoveries`.
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
    final id = await findRecommendationIdBySymbol(
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
