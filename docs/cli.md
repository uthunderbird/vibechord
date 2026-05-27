# CLI Reference

Status: `verified`

Commands in the local first implementation:

- `vibechord init`
- `vibechord run "goal"`
- `vibechord status OPERATION_ID`
- `vibechord fleet --once`
- `vibechord watch OPERATION_ID --once`
- `vibechord message OPERATION_ID "text"`
- `vibechord answer OPERATION_ID ATTENTION_ID "text"`
- `vibechord pause OPERATION_ID`
- `vibechord resume OPERATION_ID`
- `vibechord interrupt OPERATION_ID`
- `vibechord cancel OPERATION_ID`
- `vibechord show events OPERATION_ID`
- `vibechord show status OPERATION_ID`
- `vibechord show report OPERATION_ID`
- `vibechord show sessions OPERATION_ID`
- `vibechord agent`
- `vibechord project`
- `vibechord tui --once`
- `vibechord serve`
- `vibechord mcp`
- `vibechord mcp-http`
- `vibechord verify fast|focused|full`

REST production exposure:

- `vibechord serve --production --tls-cert CERT --token TOKEN`

Global options:

- `--root PATH`
- `--json`

Exit code contract:

- `0`: success;
- `1`: command rejected by application rules;
- `2`: invalid CLI usage or invalid local configuration;
- `3`: operation id not found or ambiguous;
- `4`: event store or replay failure;
- `5`: adapter/runtime failure surfaced by the operation loop.
