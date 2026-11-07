# Portable C NaN16 / NANNET interface

The CLOCKED native boundary is deliberately dependency-free C99. It provides:

- architecture/build receipt identity (`x86_64`, `x86`, `aarch64`, `arm`,
  `riscv`, `ppc64`, `wasm`, generic fallback);
- host endianness reporting;
- exact raw NaN16 encode/decode in the canonical byte order
  (far head BE, payload LE, near head LE);
- five-part route bytes and display text;
- NANNET `/v1/bootstrap/oidc` login-body construction;
- Bearer authorization-header construction;
- the 32-lane Boolean evaluation used by NaNLMind.

Network I/O is intentionally left to the caller. This lets the same C code be
linked into an HTTP client, a mobile bridge, or an embedded runner without
pulling in a TLS stack.

Build and run on the host:

```sh
make -C native test
```

Cross-compile examples:

```sh
make -C native CC=aarch64-linux-gnu-gcc build/test_clocked_nan
make -C native CC=arm-linux-gnueabihf-gcc build/test_clocked_nan
make -C native CC=riscv64-linux-gnu-gcc build/test_clocked_nan
```

The GitHub matrix runs native tests on x86_64 and aarch64 and compile checks
for ARMv7 and RISC-V.
