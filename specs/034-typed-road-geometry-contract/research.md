# Research: Typed Road Geometry

Decision: keep static physical centerlines separate from directed runtime links.

Rationale: opposite directed links share geometry, while route/flow authority
still needs separate link IDs and arrays. Canonical JSON-compatible values feed
a SHA-256 fingerprint; object identity and process hash randomization are not
valid cache keys.
