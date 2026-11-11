# GGUF result checks

The coordinator checks the reported output hash and counts one result per provider. When three replicas are configured, it requires an output-hash majority. With one replica, the coordinator accepts the matching output hash provisionally. The existing demo-credit ledger uses the replica verdict.

Petals jobs return their generated text and runtime metrics. Provider transport authentication and downloaded artifact integrity checks belong to their respective runtime paths.
