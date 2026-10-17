/// Plain-language error map (AGREED_RULES §5). Raw codes are never shown to the user.
class ApiException implements Exception {
  final String code;
  final String? message;
  final Map<String, dynamic>? details;

  ApiException(this.code, {this.message, this.details});

  @override
  String toString() => 'ApiException($code)';
}

const String offlineMessage = "You're offline. This will sync when you're back online.";
const String genericMessage = 'Something went wrong. Please try again.';

const Map<String, String> _plainMessages = {
  'OUT_OF_STOCK': 'Sorry, this item just sold out.',
  'PAYMENT_DECLINED': 'Your payment was declined. Try another card.',
  'PAYMENT_CAPTURE_FAILED': "Payment couldn't be completed. You were not charged.",
  'TRANSFER_WINDOW_CLOSED': 'The transfer window is closed for that date.',
  'SQUAD_FULL': 'The destination squad is full.',
  'MIN_POSITION_VIOLATION':
      'This move would leave the squad short of required players in that position.',
  'PLAYER_ON_LOAN': "This player is on loan and can't be moved right now.",
  'NOT_IN_SQUAD': 'This player is no longer in that squad.',
  'CROSS_TENANT_TRANSFER': 'Players can only move between clubs of the same organisation.',
  'MATCH_NOT_IN_PROGRESS': "This match isn't live, so scores can't be added.",
  'INVALID_COMPENSATION': "That event was already corrected or can't be corrected.",
  'INVALID_BASE_VERSION': 'Your data was out of date. Refresh and try again.',
  'FORBIDDEN': "You don't have permission to do that.",
  'UNAUTHENTICATED': 'Please sign in again.',
  'RATE_LIMITED': 'Too many requests. Please wait a moment.',
  'INVALID_CREDENTIALS': 'Email or password is incorrect.',
  'INVALID_DISCOUNT_CODE': "That discount code isn't valid.",
  'OFFLINE': offlineMessage,
};

String plainMessageForCode(String? code) => _plainMessages[code] ?? genericMessage;

/// Turns any thrown object into text that is safe to show in the UI.
String friendlyError(Object error) {
  if (error is ApiException) return plainMessageForCode(error.code);
  return genericMessage;
}
