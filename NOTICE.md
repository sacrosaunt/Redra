# Data notice

Redra does not bundle a settlement dataset in this source repository. During the
technical beta, the local dataset command defaults to the public SettleSignal
feed:

https://settlesignal.com/data/settlements.json

- Dataset: US Class-Action & Refund Settlements (Verified)
- Creator: SettleSignal — verified settlement intelligence
- Source: https://huggingface.co/datasets/katana957/us-settlement-catalog
- License stated by the dataset card: CC BY 4.0

Redra preserves that attribution and adds normalized lifecycle, claimability,
source-kind, and quality metadata. Redra is not affiliated with SettleSignal.

## Independent Redra publication format

The software can also import a separately configured Redra publication manifest.
That independent publication remains in a gated shadow beta and is not the
fresh-install default until its launch checks pass.

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

The independent publication license does not alter any rights that may exist in
third-party source material or websites. Source names and links are retained for
provenance and verification.
