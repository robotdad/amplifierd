# Bundles in amplifierd

Bundles define the behavior, tools, and instructions available to an Amplifier session. amplifierd manages bundles through a registry that maps human-readable names to source URIs.

## How it works

On startup, amplifierd:

1. Creates a `BundleRegistry` backed by `~/.amplifier/` (cache and persisted state).
2. Registers all configured bundles as name → URI mappings.
3. Pre-loads the default bundle so the first session starts quickly.

When a session is created via `POST /sessions`, the daemon resolves the requested bundle by name or URI, downloads it if necessary, prepares it, and hands it to the new session.

## Well-known bundles

amplifierd ships with a set of well-known bundles pre-registered by default:

| Name | URI |
|------|-----|
| `foundation` | `git+https://github.com/microsoft/amplifier-foundation@main` |
| `distro` | `git+https://github.com/microsoft/amplifier-bundle-distro@main` |
| `modes` | `git+https://github.com/microsoft/amplifier-bundle-modes@main` |
| `notify` | `git+https://github.com/microsoft/amplifier-bundle-notify@main` |
| `recipes` | `git+https://github.com/microsoft/amplifier-bundle-recipes@main` |
| `design-intelligence` | `git+https://github.com/microsoft/amplifier-bundle-design-intelligence@main` |
| `exp-delegation` | `git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=experiments/delegation-only` |
| `amplifier-dev` | `git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=bundles/amplifier-dev.yaml` |

These are registered on every startup. Only the default bundle is actually downloaded; the rest are fetched on demand when a session requests them.

## Default bundle

The default bundle is used when a client creates a session without specifying `bundle_name` or `bundle_uri`. Out of the box, the default is `distro`.

```bash
# This creates a session using the distro bundle:
curl -X POST http://127.0.0.1:8410/sessions \
  -H 'Content-Type: application/json' \
  -d '{}'

# Equivalent to:
curl -X POST http://127.0.0.1:8410/sessions \
  -H 'Content-Type: application/json' \
  -d '{"bundle_name": "distro"}'
```

If `default_bundle` is set to `null`, sessions without a bundle specification return HTTP 400.

## Configuration

### Settings file

Bundle configuration lives in `~/.amplifierd/settings.json`:

```json
{
  "bundles": {
    "foundation": "git+https://github.com/microsoft/amplifier-foundation@main",
    "distro": "git+https://github.com/microsoft/amplifier-bundle-distro@main",
    "my-custom": "file:///home/me/my-bundle"
  },
  "default_bundle": "distro"
}
```

Setting `bundles` in the config file **replaces** the well-known defaults entirely. To keep them and add your own, include the well-known entries alongside your additions.

### Environment variables

```bash
# Override the full bundle map (JSON object)
export AMPLIFIERD_BUNDLES='{"distro": "git+https://github.com/microsoft/amplifier-bundle-distro@main", "custom": "file:///tmp/mybundle"}'

# Override just the default bundle
export AMPLIFIERD_DEFAULT_BUNDLE=foundation
```

### CLI flags

The `--bundle` and `--default-bundle` flags override environment and file settings:

```bash
# Add a custom bundle and make it the default
amplifierd serve \
  --bundle custom=file:///home/me/my-bundle \
  --default-bundle custom

# Register multiple bundles
amplifierd serve \
  -b dev=file:///home/me/dev-bundle \
  -b staging=git+https://github.com/myorg/staging-bundle@main
```

CLI `--bundle` entries are merged with (and override) bundles from the environment or settings file.

### Priority

Configuration sources are applied in this order (highest priority first):

1. CLI flags (`--bundle`, `--default-bundle`)
2. Environment variables (`AMPLIFIERD_BUNDLES`, `AMPLIFIERD_DEFAULT_BUNDLE`)
3. Settings file (`~/.amplifierd/settings.json`)
4. Built-in defaults (well-known bundles, `default_bundle: "distro"`)

## Creating a session with a specific bundle

```bash
# By registered name
curl -X POST http://127.0.0.1:8410/sessions \
  -H 'Content-Type: application/json' \
  -d '{"bundle_name": "foundation"}'

# By URI (does not need to be pre-registered)
curl -X POST http://127.0.0.1:8410/sessions \
  -H 'Content-Type: application/json' \
  -d '{"bundle_uri": "git+https://github.com/myorg/my-bundle@main"}'
```

When using `bundle_uri`, the bundle is automatically registered by its name for future lookups.

## Bundle URIs

Bundles are identified by URIs. Supported schemes:

| Scheme | Example | Notes |
|--------|---------|-------|
| `git+https://` | `git+https://github.com/microsoft/amplifier-foundation@main` | Git repository; append `@branch` for a specific ref |
| `git+https://...#subdirectory=` | `git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=bundles/amplifier-dev.yaml` | Nested bundle within a git repo |
| `file://` | `file:///home/me/my-bundle` | Local directory |

## Bundle lifecycle

1. **Register** — Map a name to a URI. No network activity. Happens automatically on startup for configured bundles.
2. **Load** — Resolve the URI, download/clone if needed, cache locally under `~/.amplifier/cache/`. The default bundle is pre-loaded on startup; others are loaded on first use.
3. **Prepare** — Parse the bundle definition, resolve includes, compose behaviors. Produces a `PreparedBundle`.
4. **Create session** — The prepared bundle creates an `AmplifierSession` with the configured tools, instructions, and behaviors.

## Caching

Downloaded bundles are cached in `~/.amplifier/cache/`. The registry tracks loaded bundles in `~/.amplifier/registry.json` so they persist across restarts. If a cached bundle is deleted from disk, the registry detects the stale entry on startup and clears it.

## Resilience

If the `BundleRegistry` fails to initialize (e.g., `amplifier-foundation` is not installed), the daemon starts without it. Bundle-dependent endpoints return HTTP 503 until the issue is resolved. Pre-loading the default bundle is best-effort — a failure is logged but does not prevent startup.
