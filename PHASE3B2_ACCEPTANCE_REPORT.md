# Phase 3B.2 Acceptance Report

Generated after the successful corrected all-15 acceptance run. The candidate bundle remains inactive and outside the Git repository.

## 1. Destination Baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- Local HEAD and `origin/main`: `446a432c3bcf07eb20f5b99e84db155809cd9c12`
- Starting committed baseline remained unchanged.

## 2. Official Source Identity

- Repository: `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- Pinned commit: `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- Checkout: detached, clean; no working-tree or cached diff.
- Push URL: `DISABLED_DO_NOT_PUSH`.

## 3. Phase 3B.1 Trust Anchor

- Selection file SHA-256: `7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97`
- Git blob: `60fe633c8e2860a56cb46248cd4b937c1a231833`
- Formal run: `FORECASTPH_FORMAL_20260911_01`; cutoff `2026-09-11`; experiment SHA `8359270bffcd43dd41830a01bb2f4e2d4c527b56`.
- Selection catalog validation: 15/15 canonical companies, no missing/unknown symbols.

## 4. Canonical Company Universe

`ALI, APX, BPI, GLO, ICT, JFC, MBT, MEG, MER, NIKL, PGOLD, SCC, SECB, SHLPH, SMPH` — all 15 resolved and processed.

## 5. Historical Data Preflight

15/15 companies; 1,649 rows each; 24,735 total rows; ordered unique dates from 2020-01-02 through 2026-10-01. Zero post-cutoff rows were included (0 later canonical rows observed).

## 6. Official Historical Parity

All 15 pinned official CSVs were verified. Row-level date/OHLCV comparison found 0 mismatches and 0 duplicate canonical symbol/date pairs. Total verified source CSV count: 15.

## 7. Bundle Version

`2026.10.01-authoritative-v1`.

## 8. External Bundle Location Policy

Final candidate: `~/pse-pulse-production-artifacts/2026.10.01-authoritative-v1/`. The acceptance evidence is stored separately at `~/pse-pulse-production-artifacts/bundle_validation.json`. Generated binaries remain outside Git.

## 9. Atomic Build Contract and Run History

- Attempt 1 stopped at ALI/LSTM persistence because the caller expected four values from the accepted three-value persistence API. Atomic cleanup succeeded; no final bundle or staging directory survived.
- Attempt 2 stopped during preflight because `/tmp/pse-pulse-official-source` was absent. No model training started and no artifacts were produced.
- Corrected run: pinned source restored, preflight passed, and all 45 artifacts trained and verified before atomic finalization. The recorded build window was approximately 40 seconds (first source verification log at 19:30:47 PHT; manifest created at 19:31:21 PHT). No retry or fallback was used within this run.

## 10. Authoritative LIR Refit

All companies used their selected alpha, all 47 causal candidate features, production-history PACF with `ywmle`, 20 return-lag candidates, zero raw-price lags, `StandardScaler` plus `Lasso`, next-session Close-delta targets, and additive Close reconstruction. Per-company fitted feature counts and PACF-selected return lags are shown below.

## 11. Authoritative ARIMA Refit

Each company used exactly its selected order and trend with statsmodels ARIMA, stationarity/invertibility constraints disabled as configured, and confirmed convergence required. All 15 passed without alternate specifications.

## 12. Authoritative LSTM Refit

All 15 used their catalog specifications, CPU training, seed 42, chronological batches without shuffling, the Phase 3B.1 univariate Close-delta architecture, fresh Stage A epoch selection, and fresh Stage B full-history refit.

## 13. Formal-vs-Production LSTM Epoch Counts

The table lists every company's formal evaluation epoch count separately from its freshly selected production epoch count. No formal count was reused as the production count.

## 14. Joblib Authoritative Binding

LIR alpha, ARIMA order/trend, authoritative regime, model/schema/implementation identity, history boundary, source lineage, and exact selection provenance were checked before safe joblib loading. The existing SHA-before-deserialization loader remained in use.

## 15. LSTM Artifact Security Regression

The established `pytorch_state_dict` format and safe loader remain unchanged. The CPU `map_location`, `weights_only=True`, SHA-before-`torch.load`, authoritative-selection binding, and separate safe-reload path passed the Torch-enabled artifact tests and the independent bundle verifier.

## 16. Bundle Manifest Contract

Schema `pse-pulse.production-bundle` version 1; exactly 15 symbols and 45 entries ordered by symbol then LAG_REGRESSION, ARIMA, LSTM. Manifest includes official methodology/data provenance, selection CSV SHA/blob and formal run, build environment, history limits, per-entry selection evidence, artifact/metadata paths, hashes, sizes, and training boundaries. JSON was finalized with sorted keys, two-space indentation, `allow_nan=False`, and one terminal newline.

## 17. Bundle Fingerprint

- Manifest SHA-256: `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`
- Manifest size: 106,439 bytes
- Bundle version: `2026.10.01-authoritative-v1`

## 18. 15-Company Artifact Inventory and Checksums

Each cell in the artifact and metadata groups follows the family order LIR, ARIMA, LSTM. All values below were independently read from the finalized manifest; the verifier recomputed these digests from disk.

| Symbol | LIR alpha | LIR features; PACF lags | ARIMA selection | LSTM selection (lookback, hidden, lr, batch) | Formal → production epochs |
|---|---:|---|---|---|---:|
| ALI | 0.3 | 28; PACF=1 | ARIMA(0, 1, 0), trend=n | L=20, H=16, lr=0.001, batch=32 | 41 → 34 |
| APX | 0.01 | 29; PACF=2, 6 | ARIMA(1, 1, 1), trend=n | L=5, H=16, lr=0.001, batch=32 | 1 → 7 |
| BPI | 0.1 | 31; PACF=1, 2, 14, 17 | ARIMA(1, 1, 1), trend=n | L=5, H=16, lr=0.003, batch=32 | 9 → 3 |
| GLO | 10.0 | 32; PACF=2, 5, 9, 10, 14 | ARIMA(0, 1, 0), trend=n | L=5, H=16, lr=0.003, batch=32 | 2 → 2 |
| ICT | 0.1 | 31; PACF=1, 2, 4, 5 | ARIMA(1, 1, 1), trend=t | L=5, H=32, lr=0.001, batch=32 | 16 → 15 |
| JFC | 3.0 | 30; PACF=9, 11, 16 | ARIMA(0, 1, 0), trend=n | L=5, H=16, lr=0.003, batch=32 | 8 → 1 |
| MBT | 0.1 | 31; PACF=1, 2, 6, 8 | ARIMA(2, 1, 0), trend=n | L=5, H=16, lr=0.001, batch=32 | 20 → 18 |
| MEG | 0.03 | 28; PACF=3 | ARIMA(1, 0, 0), trend=n | L=10, H=32, lr=0.003, batch=32 | 1 → 24 |
| MER | 0.3 | 32; PACF=1, 2, 8, 9, 11 | ARIMA(1, 1, 1), trend=n | L=20, H=32, lr=0.001, batch=32 | 28 → 1 |
| NIKL | 0.03 | 29; PACF=13, 19 | ARIMA(0, 1, 0), trend=n | L=5, H=32, lr=0.001, batch=32 | 1 → 3 |
| PGOLD | 0.3 | 32; PACF=1, 5, 6, 7, 12 | ARIMA(1, 1, 0), trend=n | L=10, H=32, lr=0.003, batch=32 | 10 → 20 |
| SCC | 0.01 | 29; PACF=1, 13 | ARIMA(0, 1, 0), trend=n | L=20, H=32, lr=0.001, batch=32 | 1 → 1 |
| SECB | 1.0 | 30; PACF=3, 8, 14 | ARIMA(0, 1, 0), trend=n | L=5, H=32, lr=0.003, batch=32 | 17 → 3 |
| SHLPH | 0.3 | 31; PACF=1, 3, 10, 17 | ARIMA(0, 1, 0), trend=n | L=20, H=16, lr=0.001, batch=32 | 16 → 1 |
| SMPH | 0.03 | 29; PACF=1, 2 | ARIMA(1, 1, 1), trend=t | L=20, H=16, lr=0.003, batch=32 | 5 → 14 |

| Symbol | LIR artifact SHA-256 | ARIMA artifact SHA-256 | LSTM artifact SHA-256 | LIR metadata SHA-256 | ARIMA metadata SHA-256 | LSTM metadata SHA-256 |
|---|---|---|---|---|---|---|
| ALI | `767d8797ee8a2953470d513e03683da420224e19f63b3a515513ef11e98eb772` | `e6eef821559116c67f6bc69a6d1ee0214344fefa1d6e2a17dd75a9034e7d8ea3` | `24f5a284416e259775516df7401d2edb075a053b41574dc63b861c67951f8372` | `bee8dce6df5fb85d1c3b50c5e613ad84aeffe5646efdf41b28c68f5ddddb24fa` | `7d8f2a2495a9d34d06e07f262af96ff114627fe0c530aa572ed3de8ca1886367` | `d7e6c40a6542ee7cbad5023433497c0c41dc46f1746bf2431de57177fb708dc1` |
| APX | `58fa15a16d31ff4539a09fb8e249994ec326476955ea315f86c07f8484f22145` | `53133667a97e07f9988cb0970ea4e0535efe5d0635c60398a2dc18bebdd95e5e` | `8cdf20b2d6b303d40a713d1b319493f12bc59120d96c4322a88ed65b6731aed4` | `4374c2de096ca730074f90b57e114106797814436eee5cd3d89260ac19a20f5b` | `6efa07b92f39439c587dc8fd61479f5ebdd48110e4444240e00e1f579daf2dae` | `96576aa90b78b4f4b187afd36f6dca7098e88b6a0192bbfde0cc1b6e81a1d149` |
| BPI | `959a89cf4f183aba49446f81b4d27eef2c74b4aaf10763d92d660f4e465f1d57` | `984bd9231382a3176439fe7c3ad168063953b6f624aa487d2a8dc006786c4842` | `2858c8cf8afe366a03a704aa7c8267cf319b8ad445307a02618f6f5fae6e13fa` | `07519b98f681e8e6d962ef1b5b70bc53ff1d0b0678c920045ad86b1919648903` | `149b462b65f5073adb0fc87039777b8561f091e0918b3b4834201b565d7362a1` | `cd879bcb085ff1f2d59aceca19fbff8433513959cd4084bf3d37ab7c11bddeaf` |
| GLO | `58771a2a0838b97f2d76a26518717453d31448c32fbc6d7b7be5e0b9fa6d3fcc` | `ca982b9f63c9a25c9dd986f43b35d97db29bc0df4ea24f0df64e0daf47e56459` | `e27425ae172a7df812dc9cfe91c7109a34245aec6c71acc8c34136462ab7efb7` | `08844269952e01e442c294f30ece234df21291711aff8fc385f6f959d67b22aa` | `59abc15989898e8b52e11ec43ddcb170123e92e239ca2a76672022ee8ac81006` | `31dba3929edb440b36a286556d7796cea9aabd38251566d57aaf514ce9edf5da` |
| ICT | `1e56a8cea28e63810a22224b2246f4aabdeb30eba1900ee3bea0836cebade185` | `e5c54f559767e3144ffe121a8a01669a724ab5b006d450e7f63f393777fd0364` | `8305e7e05213031166516eadc5782008ca2cedcf55278896be7e4fbed83ff1ac` | `6daef4341f5e0d2cadb2ab2b53fbfb89d564ae3a512949681b398787cdf8be35` | `03b0bcece9feea8bb8353ef3af0c047588d0c667f62eaf517951ee0aeb9e7fea` | `6aa9d6a7bff9951c4de8c458425ba92d9750220914927e53ec3deedbb32740cf` |
| JFC | `3ad16da36dadf6f54e6cf70910abb10d5f5469a44abe18c9cb0c3de7d4ff0067` | `d0347c4c3c047f1d9a9bfbed1e4ed95bf2ec666ebc50d2a5883105950b2172a0` | `50861042d8bf1944d2d2ee29f982239a89fd86d3e793fecfbd5fac80725a8763` | `e9bc7166811c392ff77fc3221c293ef5e55b4de81b0ec7dd5e1cb992f4806c6e` | `3b1aa55e917e1dcabb8920df1ddc8bc0528a44162cb43aa8ce18bc1acbb9b9b6` | `bd373f7b59a1b45dfdd7fd9c3a25e1616a4d47968f512d13a3baf014979f770f` |
| MBT | `d0cf4fd61496d1b9fd48ebb51d3d44d1a20752fe65811e35b36119de4bf20edb` | `2b2db99d2d20ea69981ecf6b72289d0e05830e98ede24d808cd624ac4b31f246` | `2c49048d6f984142da57045254dabf0a04b87cdf7a55ed0b856bae644bad01d6` | `098975849ac0f607ab1468b81ce0c1777897a163cf9d825971fc740d9c5a5bc1` | `335b6e196a68d67f09a38152a12814c836c1b18529755d3f374827c116145ad1` | `056fe82b49b2fe5b2d513b6e5c19ecd54ae196fe2c8667b27b67a0a96bcdc413` |
| MEG | `c11642121f9899807ae52ddbd6989431f92860a988da70392034d6d053d03df1` | `ab3c6e96beaa8c8d7ba0956bbd7e33204f6db37373729b38196465ff997e2a7f` | `740dec22826225a50cb07a765047b0f51279420eeb5f27f6c371f8e751f0470b` | `542728ba8f23dfa0b59e0ab62d8140fdd6bf12f6827b8cf892a7988314ba1123` | `0b349734788eee072e026d1b811f73ed424c029ac86487effb4ca9e95e2b3d5c` | `6d6570973fbe5353558043c4de7d738e1112c5cdc45ea6eb1ad0fb1158a83bc1` |
| MER | `0247921380cc4020eda988b0c5323707c60e45503a2e9651deaa30ddf12bb94d` | `57d73c395d129ecf9e59740e1b83834c8350a1e342da5a74a7f629da56f78063` | `b055d4a05a7cbb325ccc49fec9ec55c19c7bc824f9761a18b13714ddc5d0ec7a` | `7b589edbf6e35c3c057b2a9f2d749ab968512df5a3119a5252017cfed8f9fe2d` | `781483a4d0bc5bcd5ab60b3192b8706b45922a6b482e32314112bd9742c7eb99` | `17e646bf424816b760467547817edfa7a9cd69913211ed54be17509af0a0beb4` |
| NIKL | `d4188e908b2a7193e479650b55d48da5c2bde123196d5b26aa41c43b17ae4e96` | `ca2b1d52e6d3b53fc337e87127535794e6b688f22958d051bd396af423dd24cb` | `d64099ddae54cce6caffa10a1bcd1fca3937803d4a70c2ffbd9b18de60e714c8` | `a7b5ff6a4620b4a3e7a281caae0d7d9666862085a270e5b5e0e6d6eecdb3de50` | `16bad92cf5bf6172dcf9ca78938e2612823521f89a580fe207f81a42de711be0` | `f9de8068f83f2e0a5e46111034ed06de2c8366934c61e946e81ea5129ea0659b` |
| PGOLD | `e7c545163cd0861eadaadc5100d793b54709928de48d88312354bb27ce4cc3ae` | `ef8f1891250825acec128e1bd1edfc917d579b71a7fdd72cc32f59fdfa0dadc5` | `8ca96e4e0b1eed82d612a7d36c26daab458b177910cf772d77e3efe422d4d32f` | `26432eab8cf1bf787a62f52c783ec393f9fab4cb127464df62c4ec54a19fda2a` | `567dbb1f19f722a9bb71404f33cf67d08d20510c5ce57deaecd34ec7748a2e99` | `fcca3b2d992b113f92d2480cbd4062cfe807214406b7eacb9805cd0b72078183` |
| SCC | `c5ee7b0d4c6bb7ba1247ba7a6cd880ed910dba916ad7e055eef5e1b3aedabace` | `3c64d1e61ba4fdb20ed59bb1e441c1d911bc392e3693b30a67a4cb7806b9d412` | `9eb68feabf9a257fad11a87057e4f2b7fff334e2dfe41f88088e867b615b33c5` | `32d110902a3143050c5834895d14e9cfe71fb0e9d868533494044b485d0eaad9` | `658438ce5c1cf8fe3ffef9da97daf40b4ea947275b5ccb1d29f3b26c5ce97195` | `46b57fe8013e590dfa7d44de4d4786355faff259847e4708df9818192b92f3eb` |
| SECB | `cc9143a982d865ba0825b5f16c132e9d9f19bff5542802999bf76b0f49302337` | `9912b24543d60cd98297dc080dcbda68155b94e60e9160326fceff971118411f` | `b009f5c4ce115b00ec6f68f65404f92eb02e39e386da2e9297557506f74e4ecf` | `752b19c4d166bdc2a4ec23c664b5fbe1d85c9d6b21abf870c4370074ac804005` | `f0a004ec915fc7d0e3fc8503acd67771853876f84dbda7dc606e23d8ba834d96` | `fd4af065e03b24ef38e7612d24ba4f9069b27ab6d1b12400f8e4e7cf58d9b380` |
| SHLPH | `977594646da20bb3c300638f1d1dc23c05b734dfe1288a7363f3e25198cae4da` | `f449552cdf581808b46e25fc102bd044651a1653fc45d079ac88431828388661` | `49249b10e61070f8db7daf23463693b78fb2ecb2610b052ba89cb42feee3ec95` | `40ef28a2aa9469584852ada187a68cae4466ecf3ec770dc6c8f6836139bd69f1` | `4bfa32908e5cd1968e8472f6984a72bd0c5b8904be6efc51d4c7e00d9d6f6fa1` | `71b22d1da66fcb55cc2dd66dc3bc01fc2b3c85a80754e5c4d69e45f4fc303871` |
| SMPH | `d5f2c5394aa48ea4dacacc9fbe329026a8a20835db7473529e85dbda8026d892` | `dcf8f9b3330c91c4d51b0e08758e149a0d904e894008c3f77ceae5190b76c4db` | `97ae901db3deb52d0cb710a589e88816b9a8856d05fbdb46cf17c1e7e21a4a63` | `8acd7f29c89dfb1b9ae24985f872d0742fd322f4db56025e18dcaca57e6443c5` | `5acab08e069d5981b222e83772dc359cce98f27af43545b21cb13a2864649ea5` | `3d03824a5890a4aeb2888be40315f17dadb8944769770807e0645809c83b9a6d` |

Counts: 15 LIR binaries, 15 ARIMA binaries, 15 LSTM binaries; 45 metadata JSON files; one manifest. Core bundle file count: 91. There are 15 symbol directories and no extra files.

## 19. 45-Artifact Safe Reload

Fresh-process standalone verification passed: 45/45 artifact hashes, 45/45 metadata hashes, 45/45 authoritative selection checks, history-boundary checks, and safe reloads. Result: `BUNDLE VERIFICATION PASSED 45/45`.

## 20. 45-Artifact One-Step Inference

All 45 predictions were generated after reloading the artifacts from disk, from origin 2026-10-01 to PSE next-session target 2026-10-02. Every delta is finite; every reconstructed close is finite and positive. Evidence is in `~/pse-pulse-production-artifacts/bundle_validation.json`; no prediction was persisted to the database.

## 21. All-15 Acceptance Table

| Symbol | Model | Origin | Target | Predicted delta | Predicted close | Result |
|---|---|---|---|---:|---:|---|
| ALI | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.0167801857585 | 15.0832198142 | PASS |
| ALI | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 15.1 | PASS |
| ALI | LSTM | 2026-10-01 | 2026-10-02 | -0.0318911714466 | 15.0681088286 | PASS |
| APX | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.00234877242005 | 16.9223487724 | PASS |
| APX | ARIMA | 2026-10-01 | 2026-10-02 | 0.0174522024115 | 16.9374522024 | PASS |
| APX | LSTM | 2026-10-01 | 2026-10-02 | 0.0121514114743 | 16.9321514115 | PASS |
| BPI | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.199035860517 | 94.3009641395 | PASS |
| BPI | ARIMA | 2026-10-01 | 2026-10-02 | -0.0552935258054 | 94.4447064742 | PASS |
| BPI | LSTM | 2026-10-01 | 2026-10-02 | -0.169668318256 | 94.3303316817 | PASS |
| GLO | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.237770897833 | 1534.7622291 | PASS |
| GLO | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 1535 | PASS |
| GLO | LSTM | 2026-10-01 | 2026-10-02 | -1.21331571462 | 1533.78668429 | PASS |
| ICT | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.139256658473 | 866.860743342 | PASS |
| ICT | ARIMA | 2026-10-01 | 2026-10-02 | 6.84597983584 | 873.845979836 | PASS |
| ICT | LSTM | 2026-10-01 | 2026-10-02 | 8.07034363851 | 875.070343639 | PASS |
| JFC | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.0278637770898 | 138.972136223 | PASS |
| JFC | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 139 | PASS |
| JFC | LSTM | 2026-10-01 | 2026-10-02 | -0.145582105156 | 138.854417895 | PASS |
| MBT | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.0500462365526 | 61.0000462366 | PASS |
| MBT | ARIMA | 2026-10-01 | 2026-10-02 | 0.0807943242099 | 61.0307943242 | PASS |
| MBT | LSTM | 2026-10-01 | 2026-10-02 | 0.0883266992601 | 61.0383266993 | PASS |
| MEG | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.0011826625387 | 2.11881733746 | PASS |
| MEG | ARIMA | 2026-10-01 | 2026-10-02 | -0.00153719453508 | 2.11846280546 | PASS |
| MEG | LSTM | 2026-10-01 | 2026-10-02 | 0.0024844340519 | 2.12248443405 | PASS |
| MER | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 1.44180527828 | 418.641805278 | PASS |
| MER | ARIMA | 2026-10-01 | 2026-10-02 | 0.272048119036 | 417.472048119 | PASS |
| MER | LSTM | 2026-10-01 | 2026-10-02 | 0.641169145248 | 417.841169145 | PASS |
| NIKL | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.000848297213622 | 3.94084829721 | PASS |
| NIKL | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 3.94 | PASS |
| NIKL | LSTM | 2026-10-01 | 2026-10-02 | 0.000649974675998 | 3.94064997468 | PASS |
| PGOLD | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.000866873065015 | 39.7008668731 | PASS |
| PGOLD | ARIMA | 2026-10-01 | 2026-10-02 | -0.0372836406015 | 39.6627163594 | PASS |
| PGOLD | LSTM | 2026-10-01 | 2026-10-02 | -0.0204239491199 | 39.6795760509 | PASS |
| SCC | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.017181167368 | 14.1171811674 | PASS |
| SCC | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 14.1 | PASS |
| SCC | LSTM | 2026-10-01 | 2026-10-02 | -0.00997755296745 | 14.090022447 | PASS |
| SECB | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.0671207430341 | 62.432879257 | PASS |
| SECB | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 62.5 | PASS |
| SECB | LSTM | 2026-10-01 | 2026-10-02 | -0.0088438143189 | 62.4911561857 | PASS |
| SHLPH | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | -0.0130959752322 | 7.98690402477 | PASS |
| SHLPH | ARIMA | 2026-10-01 | 2026-10-02 | 0 | 8 | PASS |
| SHLPH | LSTM | 2026-10-01 | 2026-10-02 | -0.013904819791 | 7.98609518021 | PASS |
| SMPH | LAG_REGRESSION | 2026-10-01 | 2026-10-02 | 0.0555468801278 | 15.8555468801 | PASS |
| SMPH | ARIMA | 2026-10-01 | 2026-10-02 | -0.00467560309495 | 15.7953243969 | PASS |
| SMPH | LSTM | 2026-10-01 | 2026-10-02 | 0.00118764804691 | 15.801187648 | PASS |

## 22. Lightweight Backend Results

Post-build focused Phase 3B.2 suite: 17 passed. Full Torch-free backend suite: 180 passed, 2 skipped, 0 failures. `pip check`: no broken requirements found. Compileall passed for application, pipeline, Alembic, tests, and Phase 3B.2 scripts.

## 23. Torch-Enabled Backend Results

Full suite: 228 passed, 0 skipped, 0 failures. `pip check`: no broken requirements found.

## 24. Frontend Regression

Post-build `npm run lint`, `npx tsc --noEmit`, and `npm run build` passed. Next.js generated 26/26 static pages. `npm audit --omit=dev` found 0 vulnerabilities.

## 25. Migration/API Regression

A fresh SQLite database upgraded through `0005_add_model_artifacts_and_forecast_lineage` (head). Post-build API regression passed 18/18 tests covering health, company listing, latest forecasts, models, pipeline status, and system behavior. `REAL_MODELS_ENABLED` default remains `false`; acceptance predictions are not in the public API.

## 26. Repository Hygiene

All generated `.joblib`, `.pt`, manifest, validation JSON, and bundle directory content is external under `~/pse-pulse-production-artifacts/`. No generated model artifacts or ZIP files were found as repository changes. The pre-existing `backend/pse_pulse_dev.db` was not used as an artifact destination and database forecast/model-artifact row deltas were zero.

## 27. Official Source Integrity

Pinned source commit is correct, detached and clean, with both diffs empty and push disabled.

OFFICIAL SOURCE REPOSITORY WAS NOT MODIFIED.

## 28. Pre-Commit Destination Git Status (Acceptance Snapshot)

This records the state at the pre-commit acceptance checkpoint. Branch `main`; HEAD remains `446a432c3bcf07eb20f5b99e84db155809cd9c12`. Phase 3B.2 implementation and this report remain uncommitted and unstaged. `git diff --check` passed. No commit or push was made.

## 29. Deferred Phase 3B.3 Work

Phase 3B.3 evaluation and any activation gate remain deferred. No forecast activation, real forecast persistence, Azure upload, Azure resource creation, or Azure deployment occurred.

### Acceptance summary

- 15/15 companies; LIR 15/15; ARIMA 15/15; LSTM 15/15.
- 45/45 artifacts; 45/45 metadata files; 45/45 safe reloads; 45/45 accepted inferences.
- Persisted real Forecast rows: 0. New active ModelArtifact rows: 0.
- `REAL_MODELS_ENABLED=false`; generated binaries outside Git; Phase 3B.3 not started.

### Post-review orchestration hardening

The successful acceptance bundle was generated before this final orchestration-hardening correction. This correction does not change model training, artifact bytes, manifest contents, or inference. It only guarantees cleanup if a future failure occurs after staging verification but before the builder returns.

Post-correction checks, recorded separately from the accepted training-run results: focused Phase 3B.2 tests 22 passed; Torch-free backend 185 passed, 2 skipped; Torch-enabled backend 233 passed; frontend lint/typecheck/build passed with 26/26 static pages and npm audit reported 0 vulnerabilities; migration reached 0005 and API regression passed 18/18. Both environment `pip check` runs reported no broken requirements. The standalone verifier again passed 45/45 and the accepted manifest SHA-256 remained unchanged.
