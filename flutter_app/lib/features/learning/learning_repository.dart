import '../../core/api_client.dart';
import 'learning_experiment.dart';
import 'learning_history_entry.dart';
import 'learning_summary.dart';

/// EPIC-M3.9 — repository boundary over `GET /learning/{summary,history,
/// experiments}`. Read-only: no method here can mutate production model
/// state (AC: "UI never directly modifies production models").
class LearningRepository {
  final ApiClient _client;

  LearningRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<LearningSummary> fetchSummary() async {
    final response = await _client.get('/learning/summary');
    return LearningSummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<LearningHistoryEntry>> fetchHistory({int limit = 50}) async {
    final response = await _client.get(
      '/learning/history',
      query: {'limit': limit.toString()},
    );
    return (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(LearningHistoryEntry.fromJson)
        .toList();
  }

  Future<List<LearningExperiment>> fetchExperiments() async {
    final response = await _client.get('/learning/experiments');
    return (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(LearningExperiment.fromJson)
        .toList();
  }
}
