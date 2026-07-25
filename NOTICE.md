# Data notice

Redra does not bundle a settlement dataset. Its local dataset command downloads
the public SettleSignal settlement catalog.

Dataset: US Class-Action & Refund Settlements (Verified)

Creator: SettleSignal — verified settlement intelligence

Source dataset:
https://huggingface.co/datasets/katana957/us-settlement-catalog

Live feed:
https://settlesignal.com/data/settlements.json

License: Creative Commons Attribution 4.0 International (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/

SettleSignal's official website identifies the Hugging Face dataset above as an
official profile. The dataset card licenses its public fields under CC BY 4.0
and requests attribution with a link to SettleSignal.

Redra returns this attribution with SettleSignal-derived data:

> Data adapted from SettleSignal — verified settlement intelligence
> (https://settlesignal.com/). Source dataset:
> https://huggingface.co/datasets/katana957/us-settlement-catalog. Licensed under
> CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

Changes made by Redra: source fields are normalized and Redra adds derived
lifecycle, claimability, source-kind, and quality metadata. Redra does not alter
the original SettleSignal dataset in place and does not bundle it in this
repository.

Redra is an independent project and is not affiliated with SettleSignal, any
court, settlement administrator, defendant, or law firm.
