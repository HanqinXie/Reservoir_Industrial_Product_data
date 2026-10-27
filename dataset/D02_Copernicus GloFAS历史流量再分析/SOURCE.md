# D02 来源与实际取得范围

官方数据集：[Copernicus CEMS GloFAS historical](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical)。本地`api_request.txt`记录v4.0、LISFLOOD、consolidated、2015年全部月份/日期的全球范围请求，变量为过去24小时平均河流流量。请求年份与文件时间标签分别记录，不自行解释或移动原时间标签。

实际原始交付是原ZIP及其中的`data_0.nc`。全球文件为365×3000×7200，0.05度网格，变量`avg_dis`、float32、单位m³/s；网格中心纬度范围为59.975°S—89.975°N，经度范围为179.975°W—179.975°E。时间标签为2015-01-02 00:00至2016-01-01 00:00。这里的全球指官方全球请求结果和原生模型网格，不代表覆盖南极或全部历史年份。

原ZIP为2,372,499,291字节，SHA-256：`a96b655a9dbb8e47cac247dc3ef14293e939bff6c187a90f2ab65ff10dec0f3b`。完整流读取核验唯一文件成员CRC通过，内含`data_0.nc`为2,372,137,099字节，其SHA-256与本地文件均为`180eb17eddb594349bed700faa83e1d3a703c2e4c9641d9291c348cbb74d2501`。

`yunnan_bbox_2015_glofas_v4.nc`是从该全球文件按北纬21—29度、东经97—107度筛选的矩形派生子集；网格中心实际范围为21.025—28.975°N、97.025—106.975°E，尺寸365×160×200。未做省界掩膜，不代表完整相关上游流域，未插值、重采样或填补缺失值。其17,113,700字节文件SHA-256为`f152afa1a78a53cd4e2170b5e1ab64e00efacc779c6e03a46816c24f0b312a22`；全部11,680,000个float32值已独立逐位比对。

请求、坐标、时间、文件哈希、ZIP核验及派生关系见[manifest.json](manifest.json)；全值检查见[_provenance/yunnan_bbox_2015_independent_check.json](_provenance/yunnan_bbox_2015_independent_check.json)。许可原文和早期元数据保留在`_provenance/`。本次仅更新取得状态与目录，不改原ZIP、全球NetCDF或矩形子集。
