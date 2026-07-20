# -*- coding: utf-8 -*-
"""
渐变线渲染 - Interpolated Gradient Line Renderer
=====================================
适用于 QGIS 3.40+ 的沿线 _S 到 _E 真实渐变渲染（使用 InterpolatedLineSymbolLayer）。

已根据 QGIS 3.40 API 完整适配。
"""

from qgis.core import (
    QgsSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsLineSymbol,
    QgsInterpolatedLineSymbolLayer,
    QgsInterpolatedLineColor,
    QgsInterpolatedLineWidth,
    QgsStyle,
    QgsColorRampShader,
    QgsColorRampLegendNodeSettings,
    Qgis,
    QgsProperty
)


def apply_gradient_renderer(layer, field_name, color_ramp_name=None, reverse=False, render_type="speed"):
    """对线图层应用沿线渐变渲染（内插线样式）"""

    # ---- 1. 加载色带 ---- #
    style = QgsStyle().defaultStyle()
    ramp_name = color_ramp_name or "RdYlGn"
    print(f"  色带名称传入: [{ramp_name}]", flush=True)
    ramp = style.colorRamp(ramp_name)
    if not ramp:
        fallback = style.colorRampNames()
        if fallback:
            ramp = style.colorRamp(fallback[0])
            print(f"  色带 [{ramp_name}] 未找到, 回退为 [{fallback[0]}]", flush=True)

    if reverse and ramp:
        ramp = ramp.clone()
        ramp.invert()

    # ---- 2. 计算全局最小/最大值 ---- #
    fields_to_check = [field_name + "_S", field_name + "_E"]
    min_val = float("inf")
    max_val = float("-inf")

    for fname in fields_to_check:
        idx = layer.fields().indexFromName(fname)
        if idx >= 0:
            minv = layer.minimumValue(idx)
            maxv = layer.maximumValue(idx)
            if minv is not None:
                min_val = min(min_val, float(minv))
            if maxv is not None:
                max_val = max(max_val, float(maxv))

    if min_val == float("inf"):
        min_val, max_val = 0.0, 100.0
    if min_val == 0.0:
        min_val = -0.0001
    if max_val <= min_val:
        max_val = min_val + 1.0

    # ---- 3. 构建 QgsColorRampShader ---- #
    shader = QgsColorRampShader(min_val, max_val)
    shader.setMinimumValue(min_val)
    shader.setMaximumValue(max_val)
    shader.setLabelPrecision(1)
    shader.setSourceColorRamp(ramp)
    shader.setColorRampType(Qgis.ShaderInterpolationMethod.Linear)
    shader.classifyColorRamp(255)

    # 标签单位后缀：速度→m/s，高程→m，坡度→°
    if render_type == "speed":
        suffix = "m/s"
    elif render_type == "elevation":
        suffix = "m"
    else:
        suffix = "°"
    legend_settings = QgsColorRampLegendNodeSettings()
    legend_settings.setSuffix(suffix)
    shader.setLegendSettings(legend_settings)

    # ---- 4. 创建 Interpolated Line Symbol Layer ---- #
    symbol_layer = QgsInterpolatedLineSymbolLayer.create({})

    # 固定宽度 0.5
    width_settings = QgsInterpolatedLineWidth()
    width_settings.setIsVariableWidth(False)
    width_settings.setFixedStrokeWidth(0.5)
    symbol_layer.setInterpolatedWidth(width_settings)
    symbol_layer.setWidthUnit(Qgis.RenderUnit.Millimeters)

    # 颜色渐变：先写回 shader，再设置着色方法
    color_settings = QgsInterpolatedLineColor()
    color_settings.setColor(shader)
    color_settings.setColoringMethod(QgsInterpolatedLineColor.ColorRamp)
    symbol_layer.setInterpolatedColor(color_settings)

    # 设置 _S 和 _E 字段（使用 Data Defined Properties）
    start_field = field_name + "_S"
    end_field = field_name + "_E"

    if layer.fields().indexFromName(start_field) >= 0:
        symbol_layer.setDataDefinedProperty(
            QgsSymbolLayer.PropertyLineStartColorValue,
            QgsProperty.fromField(start_field)
        )
    if layer.fields().indexFromName(end_field) >= 0:
        symbol_layer.setDataDefinedProperty(
            QgsSymbolLayer.PropertyLineEndColorValue,
            QgsProperty.fromField(end_field)
        )

    # ---- 5. 创建符号和渲染器 ---- #
    symbol = QgsLineSymbol()
    symbol.changeSymbolLayer(0, symbol_layer)   # 替换默认 symbol layer

    renderer = QgsSingleSymbolRenderer(symbol)

    # ---- 6. 应用渲染器 ---- #
    layer.setRenderer(renderer)
    layer.triggerRepaint()

    print(f"✅ 渐变线渲染已应用 → {field_name}_S → {field_name}_E | 色带: {ramp_name} | 反转: {reverse} | 精度: 1 | 后缀: {suffix}")
