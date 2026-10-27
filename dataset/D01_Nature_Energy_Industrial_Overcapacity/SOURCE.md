# D01 Nature_Energy_Industrial_Overcapacity

Official catalog entry: https://zenodo.org/records/19600477

Original v1 supplementary data archive. No pickle data is deserialized and no downloaded code is executed.

Original downloaded files are stored in this directory. ZIP files are retained and safely extracted under `extracted/<archive stem>/`. Per-file provenance and hashes are in `_provenance/*.manifest.json`; authoritative source metadata is copied to `_provenance/official_*`. The current acquisition manifest is `../_provenance/manifest_scientific.json`. A file is complete only when its manifest status is `downloaded` or `downloaded_and_extracted`; `.part` files and `.segments` directories are incomplete transfer state.

Windows compatibility repair on 2026-10-27: the extracted research view recovers 60 Chinese GIS component filenames from unflagged UTF-8 ZIP names and retains the two earlier colon-to-underscore mappings. 301 macOS metadata files are omitted from the extracted view only; their original members and hashes remain recorded and recoverable from data.zip. All 252 research files preserve their original bytes. See ENCODING_REPAIR.md, _provenance/data.zip.filename_mapping.json and _provenance/windows_repair_20261027/verification.json. Prior manifests and scripts are backed up under that repair directory.
