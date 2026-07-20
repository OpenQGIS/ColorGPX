from qgis.core import (
    QgsGraduatedSymbolRenderer, QgsLineSymbol,
    QgsClassificationJenks, QgsRendererRange,
    QgsGradientColorRamp, QgsStyle,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt


def apply_renderer(layer, field_name, color_ramp_name=None, reverse=False):
    """Apply graduated line renderer with selectable color ramp."""

    symbol = QgsLineSymbol.createSimple({"width": "0.5"})
    sl = symbol.symbolLayer(0)
    sl.setPenCapStyle(Qt.PenCapStyle.RoundCap)
    sl.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)

    ramp = _load_ramp(color_ramp_name)

    jenks = QgsClassificationJenks()
    classes = jenks.classes(layer, field_name, 6)

    n = len(classes)
    ranges = []
    for i, c in enumerate(classes):
        ratio = i / (n - 1) if n > 1 else 0.5
        if reverse:
            ratio = 1 - ratio
        color = ramp.color(ratio)
        sym = symbol.clone()
        sym.setColor(color)
        rng = QgsRendererRange(c.lowerBound(), c.upperBound(), sym, c.label())
        ranges.append(rng)

    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def _load_ramp(name):
    """Load a named ramp from QGIS style, falling back to RdYlGn."""
    if name:
        r = QgsStyle().defaultStyle().colorRamp(name)
        if r:
            return r
    r = QgsStyle().defaultStyle().colorRamp("RdYlGn")
    if r:
        return r
    return QgsGradientColorRamp(QColor(0, 0, 255), QColor(255, 0, 0))
