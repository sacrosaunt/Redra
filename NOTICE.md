# Data notice

Redra does not bundle a settlement dataset in this source repository. By default,
the local dataset command downloads Redra's independently assembled publication
manifest from:

https://data.redra.ai/catalog/v1/manifest.json

Redra collects and normalizes factual settlement metadata from the court,
government, and settlement-administrator sources linked by each record. Redra's
selection, organization, normalization, derived lifecycle fields, and other
original compilation material are licensed under Creative Commons Attribution
4.0 International (CC BY 4.0):

https://creativecommons.org/licenses/by/4.0/

This license does not alter any rights that may exist in third-party source
material or websites. Source names and links are provided for provenance and
verification. Redra is not affiliated with any court, government agency,
settlement administrator, defendant, or law firm.

The publication is divided into independently validated `open` and `upcoming`
feeds. Upcoming records evidence a future claim window but are not currently
claimable, expose no current claim URL, and are excluded from claimable totals.

## Legacy SettleSignal compatibility

Existing installations may explicitly configure the former SettleSignal feed.
When that compatibility path is used, Redra preserves SettleSignal attribution as
described by its public dataset card:

- Dataset: US Class-Action & Refund Settlements (Verified)
- Creator: SettleSignal — verified settlement intelligence
- Source: https://huggingface.co/datasets/katana957/us-settlement-catalog
- License stated by the dataset card: CC BY 4.0

Redra is an independent project and is not affiliated with SettleSignal.
