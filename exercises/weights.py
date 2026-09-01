"""Parsing and validation helpers for a user's kettlebell inventory."""

from decimal import Decimal, InvalidOperation

MIN_WEIGHT_KG = Decimal('0.1')
MAX_WEIGHT_KG = Decimal('200')


def _tokens(raw):
    if raw is None:
        return []
    value = str(raw)
    if not value.strip():
        return []
    return [chunk.strip() for chunk in value.split(',')]


def _parse_token(token):
    if not token:
        return None
    try:
        value = Decimal(token)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or not MIN_WEIGHT_KG <= value <= MAX_WEIGHT_KG:
        return None
    return value.normalize()


def invalid_weight_tokens(raw):
    """Return malformed or unsafe tokens, preserving their input order."""
    return [token for token in _tokens(raw) if _parse_token(token) is None]


def parse_available_weights(raw):
    """Return finite, safe, unique weights sorted from lightest to heaviest.

    Existing profiles are allowed to contain free-form legacy text. Invalid
    values are therefore ignored here; new form submissions use
    :func:`normalize_available_weights` after validating every token.
    """
    values = {_parse_token(token) for token in _tokens(raw)}
    values.discard(None)
    return [float(value) for value in sorted(values)]


def format_weight(value):
    """Format a validated weight without redundant zeroes."""
    text = format(value.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def normalize_available_weights(raw):
    """Return the canonical comma-separated representation of safe weights."""
    values = {_parse_token(token) for token in _tokens(raw)}
    values.discard(None)
    return ', '.join(format_weight(value) for value in sorted(values))
