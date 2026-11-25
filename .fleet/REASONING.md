# Rename to Living Library

## Approach

Made `living_library` the primary Python package and kept `akashic_codex` as
deprecation-warning compatibility shims for the package and its modules.
Registered `living-library` as the MCP server name and kept the old console
entry point and module imports available as aliases.

The default database location is now `~/.living-library/living-library.db`.
When that directory is absent and `~/.akashic/` exists, the code falls back to
`~/.akashic/akashic.db`, emits a migration hint, and does not move or copy the
database automatically. `LIVING_LIBRARY_DB_PATH` remains the explicit override.

Updated package metadata, CLI commands, README, design notes, MCP instructions,
test fixtures, dependency bounds, and package data. Added the `living-library`
console script beside the deprecated `akashic-codex` script.

## Alternatives rejected

Replaced the old package rather than keeping it would break existing imports
and client configurations immediately. Renaming directories or moving the live
database automatically was also rejected because it could lose or duplicate
user data outside this repository.

## Risks

Existing MCP client configurations should migrate from `akashic-codex` to
`living-library`; the server implementation remains executable through both
entry-point names during the transition. Legacy database fallback is temporary
and should be removed after the old data location is no longer used.

## Not done

The GitHub repository itself was not renamed. That is a hosted-repository
operation and is intentionally left as the human-supervised final step.
