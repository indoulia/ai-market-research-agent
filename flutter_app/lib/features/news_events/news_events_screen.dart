import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../dashboard/recommendations_repository.dart';
import '../shared/recommendation_lookup.dart';
import 'news_event_row.dart';
import 'news_events_repository.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M1.140 — News & Events tab: a chronological, materiality-badged
/// stream (UX rule: "do not create a giant news feed; prioritize material
/// events" — handled by only showing what M1.139 already returns, which is
/// keyed off recorded materiality rather than every ingested row).
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

  _LoadState _state = _LoadState.loading;
  List<FeedEntry> _entries = const [];
  ApiException? _error;
  final TextEditingController _symbolController = TextEditingController();
  String? _symbolFilter;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? NewsEventsRepository();
    _recommendationsRepository =
        widget.recommendationsRepository ?? RecommendationsRepository();
    _load();
  }

  @override
  void dispose() {
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final entries = await _repository.fetchFeed(symbol: _symbolFilter);
      setState(() {
        _entries = entries;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
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
          padding: const EdgeInsets.all(MraSpacing.lg),
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
        if (_entries.isEmpty) {
          return const MraStateView.empty(
            message: 'No material news or events recorded yet.',
          );
        }
        return RefreshIndicator(
          onRefresh: _load,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
            itemCount: _entries.length,
            separatorBuilder: (_, _) => const SizedBox(height: MraSpacing.sm),
            itemBuilder: (context, index) => NewsEventRowCard(
              entry: _entries[index],
              onTap: () => _onEntryTap(_entries[index]),
            ),
          ),
        );
    }
  }
}
