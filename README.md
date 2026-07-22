# ColorGPX

> 将 GPX 轨迹按速度、高程或坡度渲染为渐变色图层的 QGIS 插件

**ColorGPX** 从 GPX 文件的 track_points 图层中提取速度（speed）、高程（elevation）信息，并自动计算坡度（slope），生成点、线或渐变线图层，并按对应属性进行色彩渲染，让轨迹数据一目了然。

## 效果预览

| 速度渲染 (Speed) | 高程渲染 (Elevation) | 坡度渲染 (Slope) |
| :---: | :---: | :---: |
| ![速度](screenshots/speed.png) | ![高程](screenshots/elevation.png) | ![坡度](screenshots/slope.png) |


## 功能特性

- **点渲染 / 线渲染 / 渐变线渲染** — 三种模式自由切换：点模式逐点着色，线模式逐段着色，渐变线模式沿轨迹真实渐变（需 QGIS 3.40+）
- **速度 / 高程 / 坡度渲染** — 按速度、高程或坡度值自动分级，点/线模式支持 Jenks 自然断点分类，渐变线模式按字段真实最值线性映射
- **坡度计算** — 基于 Haversine 公式计算两点间水平距离与高差，使用 `atan(高差/水平距离)` 输出角度（°）。正值为上坡，负值为下坡，采用双向 EMA 平滑过渡，自动过滤 GPS 高程噪声（高差 < 0.5m 视为平地）
- **GPX Extensions 兼容** — 支持从 `<extensions>` 中读取速度和高程，兼容 Guru Maps、OsmAnd 等非标准 GPX 应用
- **色带选择** — 使用 QGIS 内置色带，带实时预览缩略图，支持滚动选择
- **反转色带** — 一键反转渐变方向
- **渐变线属性** — 自动设置内插线符号层的最小值/最大值（取 `_S`/`_E` 字段最值）、标注精度（1位）、标签单位后缀（速度→m/s，高程→m，坡度→°）
- **输出控制** — 创建临时图层或保存为 GeoJSON / GPKG / Shapefile


## 使用方法

1. 加载一个 GPX 文件，QGIS 会自动创建 track_points 图层
2. 点击工具栏的 **GPX → ColorGPX** 按钮
3. 在弹出面板中：
   - 选择输入图层（GPX 的 track_points）
   - 选择渲染模式（点 / 线 / 渐变线）
   - 选择渲染字段（速度 / 高程 / 坡度）
   - 选择色带并可选反转
4. 点击 **确认运行**
5. 渲染完成后图层自动添加到地图


## 兼容性

| 项目 | 要求 |
|------|------|
| QGIS | 3.1+（点/线模式）· 3.40+（渐变线模式）|
| Python | 3.x |
| 依赖 | 仅使用 QGIS / PyQt 内置模块，无需额外安装 |

## 许可证

GPL-2.0-or-later

## 作者

**OpenQGIS** · [GitHub](https://github.com/OpenQGIS) · OpenQGIS@outlook.com

---

# English Version

> A QGIS plugin to render GPX tracks as gradient-colored layers by speed, elevation or slope

**ColorGPX** extracts speed and elevation information from GPX track_points layers, automatically calculates slope, generates point, line, or gradient line layers, and renders them with colors based on the corresponding attributes, making track data clear at a glance.

## Screenshots

| Speed | Elevation | Slope |
| :---: | :---: | :---: |
| ![Speed](screenshots/speed.png) | ![Elevation](screenshots/elevation.png) | ![Slope](screenshots/slope.png) |


## Features

- **Point / Line / Gradient Line Rendering** — Three modes: point mode colors each point, line mode colors each segment, gradient line mode renders true interpolated gradients along the track (requires QGIS 3.40+)
- **Speed / Elevation / Slope Rendering** — Automatically classifies by speed, elevation or slope; point/line modes support Jenks natural breaks, gradient line mode maps linearly from field min/max
- **Slope Calculation** — Uses Haversine formula to compute horizontal distance and elevation difference between points, outputs angle in degrees (°) via `atan(Δele / distance)`. Positive = uphill, negative = downhill, smoothed with bidirectional EMA, GPS noise filtered automatically (Δele < 0.5m treated as flat)
- **GPX Extensions Support** — Reads speed and elevation from `<extensions>` blocks, compatible with Guru Maps, OsmAnd, and other non-standard GPX apps
- **Color Ramp Selection** — Uses QGIS built-in color ramps with real-time preview thumbnails and scrollable selection
- **Reverse Color Ramp** — One-click reversal of gradient direction
- **Gradient Line Properties** — Automatically sets the interpolated line symbol layer's min/max values (from `_S`/`_E` field extremes), label precision (1 decimal), and unit suffix (speed→m/s, elevation→m, slope→°)
- **Output Control** — Create temporary layers or save as GeoJSON / GPKG / Shapefile


## Usage

1. Load a GPX file — QGIS will automatically create a track_points layer
2. Click the **GPX → ColorGPX** button on the toolbar
3. In the popup panel:
   - Select input layer (GPX's track_points)
   - Select rendering mode (Point / Line / Gradient Line)
   - Select rendering field (Speed / Elevation / Slope)
   - Choose a color ramp with optional reversal
4. Click **Run**
5. The rendered layer will be automatically added to the map


## Compatibility

| Item | Requirement |
|------|-------------|
| QGIS | 3.1+ (Point/Line) · 3.40+ (Gradient Line) |
| Python | 3.x |
| Dependencies | Uses only QGIS / PyQt built-in modules, no additional installation required |

## License

GPL-2.0-or-later

## Author

**OpenQGIS** · [GitHub](https://github.com/OpenQGIS) · OpenQGIS@outlook.com
