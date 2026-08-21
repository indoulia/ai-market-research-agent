import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../dashboard/recommendation.dart';
import 'opportunities_repository.dart';

enum _LoadState { loading, error, loaded }

const _horizonOptions = [
  MraFilterOption('ALL', 'All horizons'),
  MraFilterOption('1', '1D'),
  MraFilterOption('3', '3D'),
  MraFilterOption('5', '5D'),
  MraFilterOption('7', '7D'),
];

const _marketOptions = [
  MraFilterOption('ALL', 'All markets'),
  MraFilterOption('NSE', 'NSE'),
  MraFilterOption('BSE', 'BSE'),
];

const _marketCapOptions = [
  MraFilterOption('ALL', 'All sizes'),
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

const _liquidityOptions = [
  MraFilterOption('ALL', 'Any liquidity'),
  MraFilterOption('HIGH', 'High'),
  MraFilterOption('NORMAL', 'Normal'),
  MraFilterOption('LOW', 'Low'),
];

const _minTrustOptions = [
  MraFilterOption('ALL', 'Any trust'),
  MraFilterOption('0.5', '50%+'),
  MraFilterOption('0.7', '70%+'),
  MraFilterOption('0.9', '90%+'),
];

const _sortOptions = [
  MraFilterOption('ranking', 'Ranking'),
  MraFilterOption('score', 'Score'),
  MraFilterOption('trust', 'Trust'),
  MraFilterOption('upside', 'Upside'),
  MraFilterOption('probability', 'Probability'),
  MraFilterOption('freshness', 'Freshness'),
];

/// EPIC-M3.3 — Opportunity Explorer: search/filter/sort/paginate the full
/// positive-opportunity universe via `GET /api/v1/opportunities`, separate
/// from the home dashboard's curated "top opportunities" feed (M3.2) so
/// that screen stays uncluttered (this epic's own Objective).
class OpportunityExplorerScreen extends StatefulWidget {
  final OpportunitiesRepository? repository;

  const OpportunityExplorerScreen({super.key, this.repository});

  @override
  State<OpportunityExplorerScreen> createState() =>
      _OpportunityExplorerScreenState();
}

class _OpportunityExplorerScreenState extends State<OpportunityExplorerScreen> {
  late final OpportunitiesRepository _repository;
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _sectorController = TextEditingController();
  final TextEditingController _industryController = TextEditingController();
  Timer? _debounce;

  _LoadState _state = _LoadState.loading;
  List<Recommendation> _items = const [];
  int _page = 1;
  int _total = 0;
  DateTime? _asOf;
  bool _loadingMore = false;
  ApiException? _error;

  // Filter/sort state -- kept as plain fields on this State object so it
  // survives switching to another tab and back (EPIC-M1.134's
  // StatefulShellBranch keeps each branch's widget subtree, and this
  // screen's own State with it, alive via IndexedStack), satisfying "saved
  // filter state within session" without needing any extra persistence.
  String _market = 'ALL';
  String _horizon = 'ALL';
  String _marketCap = 'ALL';
  String _liquidity = 'ALL';
  String _minTrust = 'ALL';
  String _search = '';
  OpportunitySort _sort = OpportunitySort.ranking;
  bool _descending = true;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? OpportunitiesRepository();
    _scrollController.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _searchController.dispose();
    _sectorController.dispose();
    _industryController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_loadingMore || _state != _LoadState.loaded) return;
    if (_items.length >= _total) return;
    final threshold = _scrollController.position.maxScrollExtent - 400;
    if (_scrollController.position.pixels >= threshold) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _fetch(1);
      setState(() {
        _items = page.items;
        _page = page.page;
        _total = page.total;
        _asOf = page.asOf;
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
      final page = await _fetch(_page + 1);
      setState(() {
        _items = [..._items, ...page.items];
        _page = page.page;
        _total = page.total;
        _loadingMore = false;
      });
    } catch (_) {
      // A load-more failure keeps the already-loaded page visible, matching
      // dashboard/discover's existing convention.
      setState(() => _loadingMore = false);
    }
  }

  Future<OpportunitiesPage> _fetch(int page) {
    return _repository.fetchPage(
      market: _market == 'ALL' ? null : _market,
      horizon: _horizon == 'ALL' ? null : int.parse(_horizon),
      sector: _sectorController.text.trim().isEmpty
          ? null
          : _sectorController.text.trim(),
      industry: _industryController.text.trim().isEmpty
          ? null
          : _industryController.text.trim(),
      marketCap: _marketCap == 'ALL' ? null : _marketCap,
      liquidityBucket: _liquidity == 'ALL' ? null : _liquidity,
      minTrust: _minTrust == 'ALL' ? null : double.parse(_minTrust),
      search: _search.isEmpty ? null : _search,
      sort: _sort,
      descending: _descending,
      page: page,
    );
  }

  void _onFilterChanged() => _load();

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      setState(() => _search = value);
      _load();
    });
  }

  void _onSortToggled(String id) {
    final sort = OpportunitySort.values.firstWhere((s) => s.wireName == id);
    setState(() {
      if (_sort == sort) {
        _descending = !_descending;
      } else {
        _sort = sort;
        _descending = true;
      }
    });
    _load();
  }

  void _onCardTap(Recommendation r) {
    context.push('/opportunities/recommendation/${r.id}');
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final windowClass = MraBreakpoints.classify(constraints.maxWidth);
        final dense = windowClass != MraWindowClass.compact;
        return RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            controller: _scrollController,
            slivers: [
              SliverToBoxAdapter(child: _buildHeader(context)),
              ..._buildBody(context, dense),
            ],
          ),
        );
      },
    );
  }

  int get _activeFilterCount =>
      [
        _market,
        _horizon,
        _marketCap,
        _liquidity,
        _minTrust,
      ].where((v) => v != 'ALL').length +
      (_sectorController.text.trim().isNotEmpty ? 1 : 0) +
      (_industryController.text.trim().isNotEmpty ? 1 : 0);

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);
    // Filters/sort live in bottom sheets (not inline chip rows) so the
    // header stays short regardless of how many filter dimensions this
    // Explorer supports -- with 5 chip rows + 2 text fields inline, the
    // header alone exceeded a typical phone viewport, pushing the
    // empty/error state below the fold (or, worse, squeezing its
    // SliverFillRemaining allocation to zero height and making it
    // unreachable by scrolling at all).
    return Padding(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Opportunity Explorer', style: theme.textTheme.headlineSmall),
          const SizedBox(height: MraSpacing.md),
          MraSearchField(
            hintText: 'Search symbol or company',
            controller: _searchController,
            onChanged: _onSearchChanged,
            onClear: _search.isEmpty && _searchController.text.isEmpty
                ? null
                : () {
                    _debounce?.cancel();
                    _searchController.clear();
                    setState(() => _search = '');
                    _load();
                  },
          ),
          const SizedBox(height: MraSpacing.md),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _openFiltersSheet,
                  icon: const Icon(Icons.filter_list),
                  label: Text(
                    _activeFilterCount == 0
                        ? 'Filters'
                        : 'Filters ($_activeFilterCount)',
                  ),
                ),
              ),
              const SizedBox(width: MraSpacing.sm),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _openSortSheet,
                  icon: Icon(
                    _descending ? Icons.arrow_downward : Icons.arrow_upward,
                  ),
                  label: Text('Sort: ${_sortLabel(_sort)}'),
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.md),
          _buildResultSummary(context),
        ],
      ),
    );
  }

  void _debouncedFilterChange() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), _onFilterChanged);
  }

  static String _sortLabel(OpportunitySort sort) =>
      _sortOptions.firstWhere((o) => o.id == sort.wireName).label;

  void _openFiltersSheet() {
    showMraBottomSheet(
      context: context,
      title: 'Filters',
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          final labelStyle = Theme.of(sheetContext).textTheme.labelMedium;
          void apply(VoidCallback update) {
            setState(update);
            setSheetState(() {});
            _onFilterChanged();
          }

          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Market', style: labelStyle),
                const SizedBox(height: MraSpacing.xs),
                MraFilterBar(
                  key: const Key('opportunityMarketFilter'),
                  options: _marketOptions,
                  selectedIds: {_market},
                  onToggle: (id) => apply(() => _market = id),
                ),
                const SizedBox(height: MraSpacing.md),
                Text('Horizon', style: labelStyle),
                const SizedBox(height: MraSpacing.xs),
                MraFilterBar(
                  key: const Key('opportunityHorizonFilter'),
                  options: _horizonOptions,
                  selectedIds: {_horizon},
                  onToggle: (id) => apply(() => _horizon = id),
                ),
                const SizedBox(height: MraSpacing.md),
                Text('Market cap', style: labelStyle),
                const SizedBox(height: MraSpacing.xs),
                MraFilterBar(
                  key: const Key('opportunityMarketCapFilter'),
                  options: _marketCapOptions,
                  selectedIds: {_marketCap},
                  onToggle: (id) => apply(() => _marketCap = id),
                ),
                const SizedBox(height: MraSpacing.md),
                Text('Liquidity', style: labelStyle),
                const SizedBox(height: MraSpacing.xs),
                MraFilterBar(
                  key: const Key('opportunityLiquidityFilter'),
                  options: _liquidityOptions,
                  selectedIds: {_liquidity},
                  onToggle: (id) => apply(() => _liquidity = id),
                ),
                const SizedBox(height: MraSpacing.md),
                Text('Minimum trust', style: labelStyle),
                const SizedBox(height: MraSpacing.xs),
                MraFilterBar(
                  key: const Key('opportunityMinTrustFilter'),
                  options: _minTrustOptions,
                  selectedIds: {_minTrust},
                  onToggle: (id) => apply(() => _minTrust = id),
                ),
                const SizedBox(height: MraSpacing.md),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _sectorController,
                        decoration: const InputDecoration(
                          labelText: 'Sector',
                          isDense: true,
                        ),
                        onSubmitted: (_) => _onFilterChanged(),
                        onChanged: (_) {
                          setSheetState(() {});
                          _debouncedFilterChange();
                        },
                      ),
                    ),
                    const SizedBox(width: MraSpacing.md),
                    Expanded(
                      child: TextField(
                        controller: _industryController,
                        decoration: const InputDecoration(
                          labelText: 'Industry',
                          isDense: true,
                        ),
                        onSubmitted: (_) => _onFilterChanged(),
                        onChanged: (_) {
                          setSheetState(() {});
                          _debouncedFilterChange();
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  void _openSortSheet() {
    showMraBottomSheet(
      context: context,
      title: 'Sort by',
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              MraFilterBar(
                key: const Key('opportunitySortFilter'),
                options: _sortOptions,
                selectedIds: {_sort.wireName},
                onToggle: (id) {
                  _onSortToggled(id);
                  setSheetState(() {});
                },
              ),
              const SizedBox(height: MraSpacing.md),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Descending'),
                value: _descending,
                onChanged: (value) {
                  setState(() => _descending = value);
                  setSheetState(() {});
                  _load();
                },
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildResultSummary(BuildContext context) {
    final theme = Theme.of(context);
    final countLabel = switch (_state) {
      _LoadState.loading => 'Loading…',
      _LoadState.error => ' ',
      _LoadState.loaded =>
        '$_total opportunit${_total == 1 ? 'y' : 'ies'} found',
    };
    return Row(
      children: [
        Expanded(
          child: Text(
            countLabel,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        if (_asOf != null)
          Flexible(
            child: Text(
              'As of ${_relativeLabel(_asOf!)}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
    );
  }

  List<Widget> _buildBody(BuildContext context, bool dense) {
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
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            sliver: SliverToBoxAdapter(
              child: dense ? _buildDenseTable(context) : _buildCardList(),
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
                    : (_items.length < _total
                          ? const SizedBox.shrink()
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

  Widget _buildCardList() {
    return Column(
      children: [
        for (final item in _items)
          Padding(
            padding: const EdgeInsets.only(bottom: MraSpacing.md),
            child: RecommendationCard(
              data: RecommendationCardData(
                symbol: item.symbol,
                companyName: item.companyName,
                currentPrice: item.price,
                changePercent: item.changePct,
                horizonDays: item.horizonDays,
                targetPrice: item.targetPrice,
                stopLossPrice: item.stopLoss,
                upsidePercent: item.upsidePct,
                score: item.score,
                confidence: item.confidence,
                trust: item.trustScore,
                priceHistory: [item.price ?? 0, item.price ?? 0],
                lastUpdatedLabel: _relativeLabel(item.updatedAt),
                evidenceFreshness: item.evidenceFreshness,
              ),
              onTap: () => _onCardTap(item),
            ),
          ),
      ],
    );
  }

  Widget _buildDenseTable(BuildContext context) {
    return MraDenseTable(
      columns: const [
        MraColumn('Symbol'),
        MraColumn('Price', alignment: Alignment.centerRight),
        MraColumn('Horizon', alignment: Alignment.center),
        MraColumn('Target / SL', alignment: Alignment.centerRight),
        MraColumn('Upside', alignment: Alignment.centerRight),
        MraColumn('Score', alignment: Alignment.center),
        MraColumn('Trust', alignment: Alignment.center),
        MraColumn('Freshness', alignment: Alignment.center),
        MraColumn('Updated', alignment: Alignment.centerRight),
      ],
      onRowTap: (index) => _onCardTap(_items[index]),
      rows: [for (final item in _items) _buildDenseRow(context, item)],
    );
  }

  List<Widget> _buildDenseRow(BuildContext context, Recommendation item) {
    final theme = Theme.of(context);
    return [
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(item.symbol, style: theme.textTheme.bodyMedium),
          if (item.companyName != null)
            Text(
              item.companyName!,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
        ],
      ),
      Text(item.price?.toStringAsFixed(2) ?? '—'),
      Text('${item.horizonDays}D'),
      Text(
        '${item.targetPrice.toStringAsFixed(2)} / ${item.stopLoss.toStringAsFixed(2)}',
      ),
      Text('+${item.upsidePct.toStringAsFixed(1)}%'),
      Text(item.score.toStringAsFixed(0)),
      Text(
        item.trustScore == null ? 'N/A' : item.trustScore!.toStringAsFixed(2),
      ),
      _freshnessChip(item.evidenceFreshness),
      Text(_relativeLabel(item.updatedAt), style: theme.textTheme.labelSmall),
    ];
  }

  Widget _freshnessChip(String freshness) {
    final tone = switch (freshness) {
      'FRESH' => MraChipTone.positive,
      'STALE' => MraChipTone.warning,
      _ => MraChipTone.neutral,
    };
    return MraChip(label: freshness, tone: tone);
  }

  static String _relativeLabel(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
