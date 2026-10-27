# D08 HydroATLAS

Official catalog entry: https://www.hydrosheds.org/hydroatlas

Complete global BasinATLAS, RiverATLAS and LakeATLAS v1.0 shapefile datasets, plus technical documentation and attribute catalogs. Duplicate geodatabase representations are omitted.

Original downloaded files are stored in this directory. ZIP files are retained and safely extracted under `extracted/<archive stem>/`. Per-file provenance and hashes are in `_provenance/*.manifest.json`; authoritative source metadata is copied to `_provenance/official_*`. The current acquisition manifest is `../_provenance/manifest_scientific.json`. A file is complete only when its manifest status is `downloaded` or `downloaded_and_extracted`; `.part` files and `.segments` directories are incomplete transfer state.
