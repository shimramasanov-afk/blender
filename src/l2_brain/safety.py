"""Capabilities this repository will not implement."""

FORBIDDEN = (
    "anticheat_bypass",
    "input_hiding",
    "client_injection",
    "client_patching",
    "credential_interception",
    "packet_injection",
)

LIVE_CLIENT_BLOCKED_REASON = (
    "Живой клиент закрыт до этапов S1–S3 и явной команды на S4. "
    "См. docs/roadmap.md и ADR-0009."
)
