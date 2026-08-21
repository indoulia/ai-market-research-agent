import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../dashboard/recommendations_repository.dart';
import '../shared/recommendation_lookup.dart';
import 'news_event_row.dart';
import 'news_events_repository.dart';

enum _LoadState { loading, error, loaded }

const _typeOptions = [
  MraFilterOption('ALL', 'All'),
  MraFilterOption('NEWS', 'News'),
  MraFilterOption('CORPORATE_ACTION', 'Corporate actions'),
  MraFilterOption('EARNINGS', 'Earnings'),
];

const _materialityOptions = [
  MraFilterOption('ALL', 'All materiality'),
  MraFilterOption('HIGH', 'High'),
  MraFilterOption('LOW', 'Low'),
];

const _dateOptions = [
  MraFilterOption('ALL', 'All time'),
  MraFilterOption('TODAY', 'Today'),
  MraFilterOption('WEEK', 'This week'),
];

/// EPIC-M1.140 — News & Events tab: a chronological, materiality-badged
/// stream (UX rule: "do not create a giant news feed; prioritize material
/// events" — handled by only showing what M1.139 already returns, which is
/// keyed off recorded materiality rather than every ingested row).
/// EPIC-M1.143 added cursor-based infinite scroll — the original version
/// fetched exactly one page per source and never loaded more.
/// EPIC-M3.5 added the type/materiality/date filter row: type selects which
/// of `/news`/`/events` are fetched (an "Earnings" type is a client-side
/// refinement of material news headlines, since neither `NewsEventRecord`
/// nor `CorporateAction` models a dedicated earnings-calendar concept --
/// see the EPIC's Completion Report for why); materiality and date narrow
/// the already-fetched page(s) client-side.
class NewsEventsScreen extends StatefulWidget {
  final NewsEventsRepository? repository;
  final RecommendationsRepository? recommendationsRepository;

  const NewsEventsScreen({
    super.key,
    this.repository,
    this.recommendationsRepository,
  });

  @override
  State<NewsEventsScreen> createState() => _NewsEventsScreenState();
}

class _NewsEventsScreenState extends State<NewsEventsScreen> {
  late final NewsEventsRepository _repository;
  late final RecommendationsRepository _recommendationsRepository;
  final ScrollController _scrollController = ScrollController();

  _LoadState _state = _LoadState.loading;
  List<FeedEntry> _entries = const [];
  String? _newsCursor;
  String? _eventsCursor;
  bool _hasLoadedOnce = false;
  bool _loadingMore = false;
  ApiException? _error;
  final TextEditingController _symbolController = TextEditingController();
  String? _symbolFilter;
  String _typeFilter = 'ALL';
  String _materialityFilter = 'ALL';
  String _dateFilter = 'ALL';

  bool get _fetchNews => _typeFilter != 'CORPORATE_ACTION';
  bool get _fetchEvents =>
      _typeFilter == 'ALL' || _typeFilter == 'CORPORATE_ACTION';

  bool get _hasMore =>
      !_hasLoadedOnce ||
      (_fetchNews && _newsCursor != null) ||
      (_fetchEvents && _eventsCursor != null);

  List<FeedEntry> get _visibleEntries {
    final cutoff = switch (_dateFilter) {
      'TODAY' => DateTime.now().subtract(const Duration(days: 1)),
      'WEEK' => DateTime.now().subtract(const Duration(days: 7)),
      _ => null,
    };
    return _entries.where((entry) {
      if (_materialityFilter != 'ALL' &&
          entry.materiality != _materialityFilter) {
        return false;
      }
      if (_typeFilter == 'EARNINGS' &&
          !entry.headline.toLowerCase().contains('earnings')) {
        return false;
      }
      if (cutoff != null && entry.timestamp.isBefore(cutoff)) {
        return false;
      }
      return true;
    }).toList();
  }

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? NewsEventsRepository();
    _recommendationsRepository =
        widget.recommendationsRepository ?? RecommendationsRepository();
    _scrollController.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_hasMore || _loadingMore || _state != _LoadState.loaded) return;
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 400) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final page = await _repository.fetchPage(
        symbol: _symbolFilter,
        fetchNews: _fetchNews,
        fetchEvents: _fetchEvents,
      );
      final merged = [...page.newEntries]
        ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
      setState(() {
        _entries = merged;
        _newsCursor = page.nextNewsCursor;
        _eventsCursor = page.nextEventsCursor;
        _hasLoadedOnce = true;
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
        symbol: _symbolFilter,
        newsCursor: _newsCursor,
        eventsCursor: _eventsCursor,
        fetchNews: _fetchNews && _newsCursor != null,
        fetchEvents: _fetchEvents && _eventsCursor != null,
      );
      final merged = [..._entries, ...page.newEntries]
        ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
      setState(() {
        _entries = merged;
        _newsCursor = page.nextNewsCursor;
        _eventsCursor = page.nextEventsCursor;
        _loadingMore = false;
      });
    } catch (_) {
      setState(() => _loadingMore = false);
    }
  }

  void _onTypeChanged(String id) {
    if (id == _typeFilter) return;
    setState(() {
      _typeFilter = id;
      _newsCursor = null;
      _eventsCursor = null;
      _hasLoadedOnce = false;
    });
    _load();
  }

  Future<void> _onEntryTap(FeedEntry entry) async {
    final id = await findRecommendationIdBySymbol(
      _recommendationsRepository,
      entry.symbol,
    );
    if (!mounted) return;
    if (id != null) {
      context.push('/market/recommendation/$id');
    } else {
      showMraToast(
        context,
        'No active recommendation for ${entry.symbol} yet.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            MraSpacing.lg,
            MraSpacing.lg,
            MraSpacing.lg,
            0,
          ),
          child: MraSearchField(
            hintText: 'Filter by symbol',
            controller: _symbolController,
            onChanged: (v) {
              setState(
                () => _symbolFilter = v.isEmpty ? null : v.toUpperCase(),
              );
              _load();
            },
            onClear: _symbolFilter == null
                ? null
                : () {
                    _symbolController.clear();
                    setState(() => _symbolFilter = null);
                    _load();
                  },
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: MraSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
                child: MraFilterBar(
                  options: _typeOptions,
                  selectedIds: {_typeFilter},
                  onToggle: _onTypeChanged,
                ),
              ),
              const SizedBox(height: MraSpacing.sm),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
                child: MraFilterBar(
                  options: _materialityOptions,
                  selectedIds: {_materialityFilter},
                  onToggle: (id) => setState(() => _materialityFilter = id),
                ),
              ),
              const SizedBox(height: MraSpacing.sm),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
                child: MraFilterBar(
                  options: _dateOptions,
                  selectedIds: {_dateFilter},
                  onToggle: (id) => setState(() => _dateFilter = id),
                ),
              ),
            ],
          ),
        ),
        Expanded(child: _buildBody(context)),
      ],
    );
  }

  Widget _buildBody(BuildContext context) {
    switch (_state) {
      case _LoadState.loading:
        return const Center(child: CircularProgressIndicator());
      case _LoadState.error:
        return MraStateView.error(message: _error?.message, onAction: _load);
      case _LoadState.loaded:
        final visible = _visibleEntries;
        if (_entries.isEmpty) {
          return const MraStateView.empty(
            message: 'No material news or events recorded yet.',
          );
        }
        if (visible.isEmpty) {
          return const MraStateView.empty(
            message: 'No news or events match the selected filters.',
          );
        }
        return RefreshIndicator(
          onRefresh: _load,
          child: ListView.separated(
            key: const Key('newsEventsList'),
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            itemCount: visible.length + 1,
            separatorBuilder: (_, _) => const SizedBox(height: MraSpacing.sm),
            itemBuilder: (context, index) {
              if (index == visible.length) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: MraSpacing.lg),
                  child: Center(
                    child: _loadingMore
                        ? const SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const SizedBox.shrink(),
                  ),
                );
              }
              return NewsEventRowCard(
                entry: visible[index],
                onTap: () => _onEntryTap(visible[index]),
              );
            },
          ),
        );
    }
  }
}
