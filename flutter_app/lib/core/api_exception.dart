/// EPIC-M1.136 — typed exception mirroring EPIC-M1.132's error envelope
/// (`{ "error": { "code": "MRA_*", "message", "details", "retryable" } }`).
/// UI code branches on [code]/[retryable], never on HTTP status alone.
class ApiException implements Exception {
  final String code;
  final String message;
  final bool retryable;
  final Map<String, dynamic> details;

  const ApiException({
    required this.code,
    required this.message,
    this.retryable = false,
    this.details = const {},
  });

  factory ApiException.fromEnvelope(Map<String, dynamic> json) {
    final error = json['error'] as Map<String, dynamic>?;
    if (error == null) {
      return const ApiException(
        code: 'MRA_INTERNAL',
        message: 'Unexpected response shape.',
      );
    }
    return ApiException(
      code: error['code'] as String? ?? 'MRA_INTERNAL',
      message: error['message'] as String? ?? 'Something went wrong.',
      retryable: error['retryable'] as bool? ?? false,
      details: (error['details'] as Map<String, dynamic>?) ?? const {},
    );
  }

  factory ApiException.network(Object cause) => ApiException(
    code: 'MRA_NETWORK',
    message: 'Could not reach the server.',
    retryable: true,
    details: {'cause': cause.toString()},
  );

  @override
  String toString() => 'ApiException($code: $message)';
}
