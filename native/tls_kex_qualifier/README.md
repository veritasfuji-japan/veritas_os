# Native TLS key-exchange qualifier (foundation)

This directory is an isolated, opt-in OpenSSL 3 qualification boundary. It is
not imported by VERITAS, does not replace `SandboxHTTPSTransport`, and does not
authorize network effects. The strong path fails closed unless an exact private
library context, non-empty property query, unique implementations, cacheable
dispatch definitions, and separately reviewed static manifests all agree.

Build the runtime probe with `make`, then run `./openssl_kex_probe`. The probe
uses a private `OSSL_LIB_CTX`, explicitly loads only the default provider, and
checks the public provider operation interface. Its output is diagnostic input;
it is not by itself a `PROVEN` claim. Persistent profiles use function IDs and
build identities, never function addresses.
