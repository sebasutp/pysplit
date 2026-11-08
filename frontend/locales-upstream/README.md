# Vendored upstream Spliit messages

This directory is a snapshot of the upstream Spliit locale catalogues. It is
the default `--source` for `frontend/scripts/sync-locales.mjs`, so the sync
check works offline and without a local `spliit/` checkout.

- `en-US.json` is the upstream source catalogue used for the source-string
  guard.
- The other 37 files are the upstream translations. Locales that this app does
  not ship (currently `br`, `gl`, `ml`) are kept so a future locale can be added
  without re-fetching upstream.

## Updating the snapshot

When upstream translations change, refresh every file at once, then verify that
the app catalogues are still in sync:

```bash
cp /path/to/spliit/messages/*.json frontend/locales-upstream/
node frontend/scripts/sync-locales.mjs --check
```

The default sync mode (`--prefer-app`) only copies an upstream value into a
locale when the app value is still the English placeholder (or missing) and the
source-string and placeholder/markup signatures still match. Reviewed app
translations are never overwritten. Use `--prefer-upstream` only for a
deliberate refresh of app translations from upstream.

Review the `--check` diff before committing the refreshed snapshot. Do not run
the sync with `--prefer-upstream` unless replacing reviewed translations is the
intent.
