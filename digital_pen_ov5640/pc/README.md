# Digital Pen PC Reference Pipeline

该 Python 包承载黑白 Anoto 点阵笔的 PC 参考算法。当前已完成从灰度图检测点阵、恢复网格与方向、通过多窗口一致性解出 Anoto 坐标的静态流水线。

## 隔离环境

项目使用根目录下的 `.venv`，缓存和临时文件分别位于 `.cache`、`.tmp`，不向系统 Python 或用户级 site-packages 安装包。

`microdots` 当前从外部参考项目安装到项目 `.venv`，外部源码保持只读：

```powershell
.venv\Scripts\python.exe -m pip install `
  -e "D:\ZZGG_Innovation_Project\点阵笔\大创\py-microdots-develop\py-microdots-develop"
```

## 离线坐标解码

使用 profile A 对应的 manifest、section 和尺寸限制：

```powershell
.venv\Scripts\python.exe pc/apps/decode_image.py `
  --image artifacts/task6/ov5640-aligned-000001.pgm `
  --pattern pc/configs/pattern.yaml `
  --annotated artifacts/task7/decoded.png
```

命令输出页面 ID、当前视野左上网格点的 section 内坐标、支持窗口数、置信度、旋转和相机镜像状态。`--pattern` 也可直接接收具体的 manifest JSON；使用尚未关联 manifest 的 B/C profile 时，必须同时提供 `--section-u` 和 `--section-v`。
