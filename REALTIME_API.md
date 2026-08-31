# Realtime keyboard analysis

## Connection

Connect to `ws://<host>/api/v1/realtime` (or `wss://` behind TLS) with the same
`X-API-Key` header used by the REST API. The server closes unauthorized handshakes
with WebSocket code `1008`.

## Draft message

Open the WebSocket when the keyboard becomes visible, but do not send every key
event. The keyboard client should read the current composed text from its
`InputConnection` and apply this transmission policy:

- Send the latest draft after 1 second with no input (trailing-edge debounce).
- While typing continues, send the latest draft at least once every 5 seconds
  (maximum wait).
- Do not send when the analysis inputs are unchanged from the previous send.
- Run inexpensive on-device detection immediately; a local risk match may bypass
  the debounce and be sent at once.

For Korean input, send the IME-composed text such as `안녕하세요`, not individual
jamo key events such as `ㅇ`, `ㅏ`, `ㄴ`. A new UUID is still required in
`payload.request_id` for every draft that is actually sent.

Send a new UUID in `payload.request_id` for every sequence.

```json
{
  "type": "draft_changed",
  "session_id": "keyboard-session-uuid",
  "sequence": 12,
  "payload": {
    "request_id": "analysis-request-uuid",
    "device_id": "device-id",
    "app_package": "com.example.chat",
    "conversation_id": "optional-conversation-id",
    "message_id": "optional-message-id",
    "input_text": "current draft",
    "masked_text": "current masked draft",
    "context_messages": [],
    "local_detection": {
      "detected": false,
      "risk_types": [],
      "local_score": 0
    },
    "client_timestamp": "2026-08-29T00:00:00Z",
    "client_version": "0.1.0"
  }
}
```

The sequence must increase within a session. The server sends
`STALE_SEQUENCE` for a duplicate or older sequence.

## Results

The first event is a non-persistent local/rule result that does not wait for AI:

```json
{
  "type": "provisional_result",
  "session_id": "keyboard-session-uuid",
  "sequence": 12,
  "data": {}
}
```

The final event has the same envelope and `type: "final_result"`. Its `data`
matches the existing `POST /api/v1/analyze` response data. A final result is sent
only if its sequence is still the latest accepted draft for that session.

The server keeps at most one waiting draft per WebSocket connection. If input
arrives faster than final analysis, the waiting draft is replaced by the newest
one. The in-flight result is persisted but not sent when it has become stale.

Within a connection and session, equivalent consecutive drafts reuse the most
recent provisional/final result instead of running rule and AI analysis again.
The cache identity excludes `request_id` and `client_timestamp`, uses a SHA-256
digest rather than raw text as its key, and is discarded when the WebSocket closes.

## Deadline

`LLM_RESPONSE_DEADLINE_SECONDS` controls the absolute time allowed for an AI
response and defaults to `1.5`. When it expires, both REST and WebSocket final
analysis return the existing rule/local fallback instead of waiting for the
transport-level `LLM_TIMEOUT_SECONDS`.
