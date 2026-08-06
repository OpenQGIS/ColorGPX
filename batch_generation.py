# -*- coding: utf-8 -*-
"""Unified single-file and batch generation UI for ColorGPX."""

from dataclasses import dataclass, field
import csv
from datetime import datetime
import os
import re

from qgis.PyQt.QtCore import Qt, QUrl, QSize, QCoreApplication

def tr(text, disambiguation=None):
    return QCoreApplication.translate('ColorGPX', text, disambiguation)
from qgis.PyQt.QtGui import QBrush, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QButtonGroup,
    QScrollArea, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis, QgsMapLayer, QgsProject, QgsStyle, QgsVectorFileWriter,
    QgsVectorLayer,
)
from .ui_style import style_primary_button

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405


MAX_GPX_BYTES = 512 * 1024 * 1024
MAX_FOLDER_FILES = 2000
MAX_TRACK_POINTS = 5000000
GPX_SUFFIX = ".gpx"
MAX_DISPLAY_NAME_CHARS = 30


class CollapsibleSection(QWidget):
    """Compact native Qt disclosure section with a clickable title row."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.toggle = QToolButton(self)
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle.toggled.connect(self._set_expanded)
        outer.addWidget(self.toggle)
        self.content = QGroupBox(self)
        self.content.setTitle("")
        outer.addWidget(self.content)

    def setContentLayout(self, layout):
        self.content.setLayout(layout)

    def _set_expanded(self, expanded):
        self.content.setVisible(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)


def shortened_display_name(name, limit=MAX_DISPLAY_NAME_CHARS):
    """Keep table rows compact while preserving the full name in tooltips."""
    text = str(name or "")
    return text if len(text) <= limit else text[:limit - 1] + "…"


@dataclass
class BatchTask:
    key: str
    name: str
    source_kind: str
    source_path: str
    layer: object = None
    selected: bool = True
    point_count: int = 0
    has_time: bool = False
    has_elevation: bool = False
    has_speed: bool = False
    valid: bool = False
    inspect_error: str = ""
    status: str = "待检查"
    detail: str = ""
    output: str = ""
    result_layer: object = None
    warnings: list = field(default_factory=list)

    @property
    def speed_source(self):
        if self.has_speed:
            return "原始/扩展"
        if self.has_time:
            return "模拟"
        return "缺失"


def canonical_gpx_path(path):
    """Return a normalized local GPX path or an empty string."""
    if not path:
        return ""
    raw = str(path).split("|")[0].split("?type=")[0]
    normalized = os.path.realpath(os.path.abspath(os.path.expanduser(raw)))
    if not normalized.lower().endswith(GPX_SUFFIX):
        return ""
    return normalized


def inspect_gpx(path):
    """Securely stream-inspect a GPX and return its available capabilities."""
    result = {
        "valid": False, "point_count": 0, "has_time": False,
        "has_elevation": False, "has_speed": False, "error": "",
    }
    path = canonical_gpx_path(path)
    if not path or not os.path.isfile(path):
        result["error"] = "GPX 文件不存在或路径无效"
        return result
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        result["error"] = f"无法读取文件信息：{exc}"
        return result
    if size <= 0:
        result["error"] = "GPX 文件为空"
        return result
    if size > MAX_GPX_BYTES:
        result["error"] = "GPX 文件超过 512 MB 安全限制"
        return result

    try:
        with open(path, "rb") as stream:
            trackpoint_depth = 0
            for event, elem in ET.iterparse(stream, events=("start", "end")):  # nosec B314
                tag = elem.tag.rsplit("}", 1)[-1].lower()
                if event == "start" and tag == "trkpt":
                    trackpoint_depth = 1
                    result["point_count"] += 1
                    if result["point_count"] > MAX_TRACK_POINTS:
                        result["error"] = "轨迹点超过 500 万安全限制"
                        return result
                elif event == "start" and trackpoint_depth:
                    trackpoint_depth += 1
                elif event == "end" and trackpoint_depth:
                    if tag in ("ele", "elevation", "altitude", "alt", "height"):
                        result["has_elevation"] = True
                    elif tag == "time":
                        result["has_time"] = True
                    elif tag == "speed":
                        result["has_speed"] = True
                    trackpoint_depth -= 1
                if event == "end":
                    elem.clear()
    except (ET.ParseError, OSError, ValueError) as exc:
        result["error"] = f"GPX 解析失败：{exc}"
        return result
    except Exception as exc:
        result["error"] = f"GPX 检查失败：{exc}"
        return result

    if result["point_count"] < 1:
        result["error"] = "未找到 track_points 轨迹点"
        return result
    result["valid"] = True
    return result


def load_track_points_layer(path, name=None):
    """Load the track_points sublayer from a local GPX file."""
    path = canonical_gpx_path(path)
    if not path:
        return None
    layer_name = name or os.path.splitext(os.path.basename(path))[0]
    for uri in (f"{path}|layername=track_points", f"{path}?type=track_points"):
        layer = QgsVectorLayer(uri, layer_name, "ogr")
        if layer.isValid():
            return layer
    return None


def safe_output_name(template, task, metric, mode, index):
    """Expand approved tokens and remove path/control characters."""
    values = {
        "{source}": task.name,
        "{metric}": metric,
        "{mode}": mode,
        "{index}": str(index),
        "{date}": datetime.now().strftime("%Y%m%d"),
    }
    name = template or "{source}_{metric}_{mode}"
    for token, value in values.items():
        name = name.replace(token, str(value))
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name)
    name = re.sub(r"\s+", "_", name).strip(" ._")
    if name.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                        "LPT1", "LPT2", "LPT3", "LPT4"}:
        name = "ColorGPX_" + name
    return name[:120] or f"ColorGPX_{index}"


class BatchResultDialog(QDialog):
    def __init__(self, tasks, iface=None, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.iface = iface
        self.setWindowTitle(tr("ColorGPX Batch Report"))
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        counts = {}
        for task in tasks:
            counts[task.status] = counts.get(task.status, 0) + 1
        summary = "，".join(f"{key} {value}" for key, value in counts.items())
        layout.addWidget(QLabel(summary or tr("No processing results")))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Source"), tr("Status"), tr("Output"), tr("Field Source"), tr("Description")])
        for task in tasks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            field_source = (
                f"时间:{'有' if task.has_time else '无'} / "
                f"高程:{'有' if task.has_elevation else '无'} / 速度:{task.speed_source}"
            )
            values = [task.name, task.status, task.output, field_source, task.detail]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value or "")))
        self.table.resizeColumnsToContents()
        self.table.cellDoubleClicked.connect(self._locate_result_layer)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        export_btn = QPushButton(tr("Export CSV Report"))
        export_btn.clicked.connect(self._export_csv)
        folder_btn = QPushButton(tr("Open Output Location"))
        folder_btn.clicked.connect(self._open_output_folder)
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.accept)
        style_primary_button(close_btn)
        for button in (export_btn, folder_btn, close_btn):
            button.setFixedHeight(32)
        buttons.addStretch()
        buttons.addWidget(export_btn)
        buttons.addWidget(folder_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export Batch Report"), "ColorGPX_batch_report.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow([tr("Source"), tr("Status"), tr("Output"), tr("Time"), tr("Elevation"), tr("Speed Source"), tr("Description")])
                for task in self.tasks:
                    values = [
                        task.name, task.status, task.output,
                        "有" if task.has_time else "无",
                        "有" if task.has_elevation else "无",
                        task.speed_source, task.detail,
                    ]
                    # Prevent spreadsheet software from interpreting untrusted
                    # filenames or error messages as formulas.
                    writer.writerow([
                        "'" + str(value) if str(value).startswith(("=", "+", "-", "@")) else value
                        for value in values
                    ])
        except OSError as exc:
            QMessageBox.warning(self, "ColorGPX", f"{tr('Report save failed:')} {exc}")

    def _open_output_folder(self):
        paths = [task.output for task in self.tasks if task.output]
        if not paths:
            return
        target = paths[0]
        folder = target if os.path.isdir(target) else os.path.dirname(target)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _locate_result_layer(self, row, _column):
        if not self.iface or not (0 <= row < len(self.tasks)):
            return
        layer = self.tasks[row].result_layer
        if layer and layer.isValid():
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()
        buttons.addWidget(export_btn)
        buttons.addWidget(folder_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export Batch Report"), "ColorGPX_batch_report.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow([tr("Source"), tr("Status"), tr("Output"), tr("Time"), tr("Elevation"), tr("Speed Source"), tr("Description")])
                for task in self.tasks:
                    values = [
                        task.name, task.status, task.output,
                        "有" if task.has_time else "无",
                        "有" if task.has_elevation else "无",
                        task.speed_source, task.detail,
                    ]
                    # Prevent spreadsheet software from interpreting untrusted
                    # filenames or error messages as formulas.
                    writer.writerow([
                        "'" + str(value) if str(value).startswith(("=", "+", "-", "@")) else value
                        for value in values
                    ])
        except OSError as exc:
            QMessageBox.warning(self, "ColorGPX", f"{tr('Report save failed:')} {exc}")

    def _open_output_folder(self):
        paths = [task.output for task in self.tasks if task.output]
        if not paths:
            return
        target = paths[0]
        folder = target if os.path.isdir(target) else os.path.dirname(target)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _locate_result_layer(self, row, _column):
        if not self.iface or not (0 <= row < len(self.tasks)):
            return
        layer = self.tasks[row].result_layer
        if layer and layer.isValid():
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()


class BatchGenerationDialog(QDialog):
    """One queue-based panel for a single input or a batch of inputs."""

    def __init__(self, iface, process_callback, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.process_callback = process_callback
        self.tasks = []
        self.task_keys = set()
        self.cancel_requested = False
        self.result_group = None
        self.setWindowTitle("ColorGPX - 单文件与批量生成")
        self.setMinimumWidth(550)
        self.resize(550, 680)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        for text, handler in (
            ("添加项目图层", self._add_project_layers),
            ("添加 GPX 文件", self._add_gpx_files),
            ("添加文件夹", self._add_folder),
            ("移除", self._remove_selected),
            ("清空", self._clear_tasks),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            source_row.addWidget(button)
        source_row.addStretch()
        layout.addLayout(source_row)

        self.task_table = QTableWidget(0, 9)
        self.task_table.setHorizontalHeaderLabels(
            ["启用", "状态", "名称", "来源", "轨迹点", "时间", "高程", "速度", "说明"]
        )
        self.task_table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.task_table, 1)

        settings_scroll = QScrollArea(self)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        settings_scroll.setMinimumHeight(180)
        settings_scroll.setMaximumHeight(280)
        settings_container = QWidget(settings_scroll)
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(6, 6, 6, 6)
        settings_layout.setSpacing(6)

        settings = CollapsibleSection("全局生成设置")
        grid = QGridLayout()
        self.mode_group = QButtonGroup(self)
        mode_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            ("点", "point"), ("线", "line"), ("渐变线", "gradient_line"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.mode_group.addButton(button, button_id)
            mode_row.addWidget(button)
            if button_id == 0:
                button.setChecked(True)
        mode_row.addStretch()
        self.metric_group = QButtonGroup(self)
        metric_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            ("高程", "elevation"), ("坡度", "slope"), ("速度", "speed"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.metric_group.addButton(button, button_id)
            metric_row.addWidget(button)
            if value == "speed":
                button.setChecked(True)
            button.clicked.connect(self._refresh_task_states)
        metric_row.addStretch()
        self.ramp_preview = QLabel()
        self.ramp_preview.setFixedSize(96, 22)
        self.ramp_display = QLineEdit()
        self.ramp_display.setReadOnly(True)
        ramp_names = QgsStyle().defaultStyle().colorRampNames()
        if ramp_names:
            self.ramp_display.setText(ramp_names[0])
        self.ramp_button = QPushButton("选择…")
        self.ramp_button.clicked.connect(self._pick_color_ramp)
        self.reverse_check = QCheckBox("反转色带")
        self.reverse_check.toggled.connect(self._update_ramp_preview)
        self.elev_unit = QComboBox(); self.elev_unit.addItems(["m", "ft"])
        self.speed_unit = QComboBox(); self.speed_unit.addItems(["m/s", "km/h", "mph"])
        self.slope_unit = QComboBox(); self.slope_unit.addItems(["°", "%"])
        self.elev_field = QLineEdit("ELEV")
        self.speed_field = QLineEdit("speed")
        self.slope_field = QLineEdit("Slope")
        self.batch_policy = QComboBox()
        self.batch_policy.addItem(tr("Continue executable tasks, skip incompatible tasks"), "continue")
        self.batch_policy.addItem(tr("Strict mode: Stop if incompatible tasks exist"), "strict")
        self.batch_policy.addItem(tr("Run tasks with complete fields only"), "complete_only")
        grid.addWidget(QLabel(tr("Render mode")), 0, 0); grid.addLayout(mode_row, 0, 1, 1, 3)
        grid.addWidget(QLabel(tr("Render field")), 1, 0); grid.addLayout(metric_row, 1, 1, 1, 3)
        ramp_row = QHBoxLayout()
        ramp_row.addWidget(self.ramp_preview)
        ramp_row.addWidget(self.ramp_display, 1)
        ramp_row.addWidget(self.ramp_button)
        ramp_row.addWidget(self.reverse_check)
        grid.addWidget(QLabel(tr("Color ramp")), 2, 0); grid.addLayout(ramp_row, 2, 1, 1, 3)
        units_grid = QGridLayout()
        units_grid.setContentsMargins(0, 0, 0, 0)
        units_grid.setHorizontalSpacing(8)
        fields_grid = QGridLayout()
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(8)
        for column, (label, unit_widget, field_widget) in enumerate((
            (tr("Elevation"), self.elev_unit, self.elev_field),
            (tr("Slope"), self.slope_unit, self.slope_field),
            (tr("Speed"), self.speed_unit, self.speed_field),
        )):
            units_grid.addWidget(QLabel(label), 0, column)
            units_grid.addWidget(unit_widget, 1, column)
            fields_grid.addWidget(QLabel(label), 0, column)
            fields_grid.addWidget(field_widget, 1, column)
            units_grid.setColumnStretch(column, 1)
            fields_grid.setColumnStretch(column, 1)
        grid.addWidget(QLabel(tr("Unit")), 3, 0)
        grid.addLayout(units_grid, 3, 1, 1, 3)
        grid.addWidget(QLabel(tr("Field name")), 4, 0)
        grid.addLayout(fields_grid, 4, 1, 1, 3)
        grid.addWidget(QLabel(tr("Exception policy")), 5, 0)
        grid.addWidget(self.batch_policy, 5, 1, 1, 3)
        settings.setContentLayout(grid)
        settings_layout.addWidget(settings)

        output = CollapsibleSection(tr("Output & Naming"))
        output_grid = QGridLayout()
        self.output_mode_group = QButtonGroup(self)
        output_mode_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            (tr("Temporary layer"), "temporary"),
            (tr("Separate files"), "separate"),
            (tr("Single GeoPackage"), "single_gpkg"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.output_mode_group.addButton(button, button_id)
            output_mode_row.addWidget(button)
            if button_id == 0:
                button.setChecked(True)
            button.clicked.connect(self._update_output_ui)
        output_mode_row.addStretch()
        self.output_path = QLineEdit()
        self.output_browse = QPushButton(tr("Browse…"))
        self.output_browse.clicked.connect(self._browse_output)
        self.format_combo = QComboBox()
        self.format_combo.addItem("GeoPackage (*.gpkg)", (".gpkg", "GPKG"))
        self.format_combo.addItem("GeoJSON (*.geojson)", (".geojson", "GeoJSON"))
        self.format_combo.addItem("Shapefile (*.shp)", (".shp", "ESRI Shapefile"))
        self.name_template = QLineEdit("{source}_{metric}_{mode}")
        self.collision_combo = QComboBox()
        self.collision_combo.addItem(tr("Auto-append index"), "suffix")
        self.collision_combo.addItem(tr("Skip existing results"), "skip")
        self.collision_combo.addItem(tr("Overwrite existing results"), "overwrite")
        output_grid.addWidget(QLabel(tr("Output mode")), 0, 0); output_grid.addLayout(output_mode_row, 0, 1, 1, 3)
        output_grid.addWidget(QLabel(tr("Output location")), 1, 0); output_grid.addWidget(self.output_path, 1, 1, 1, 2)
        output_grid.addWidget(self.output_browse, 1, 3)
        output_grid.addWidget(QLabel(tr("File format")), 2, 0); output_grid.addWidget(self.format_combo, 2, 1)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        for text, handler in (
            ("添加项目图层", self._add_project_layers),
            ("添加 GPX 文件", self._add_gpx_files),
            ("添加文件夹", self._add_folder),
            ("移除", self._remove_selected),
            ("清空", self._clear_tasks),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            source_row.addWidget(button)
        source_row.addStretch()
        layout.addLayout(source_row)

        self.task_table = QTableWidget(0, 9)
        self.task_table.setHorizontalHeaderLabels(
            ["启用", "状态", "名称", "来源", "轨迹点", "时间", "高程", "速度", "说明"]
        )
        self.task_table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.task_table, 1)

        settings_scroll = QScrollArea(self)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        settings_scroll.setMinimumHeight(180)
        settings_scroll.setMaximumHeight(280)
        settings_container = QWidget(settings_scroll)
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(6, 6, 6, 6)
        settings_layout.setSpacing(6)

        settings = CollapsibleSection("全局生成设置")
        grid = QGridLayout()
        self.mode_group = QButtonGroup(self)
        mode_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            ("点", "point"), ("线", "line"), ("渐变线", "gradient_line"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.mode_group.addButton(button, button_id)
            mode_row.addWidget(button)
            if button_id == 0:
                button.setChecked(True)
        mode_row.addStretch()
        self.metric_group = QButtonGroup(self)
        metric_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            ("高程", "elevation"), ("坡度", "slope"), ("速度", "speed"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.metric_group.addButton(button, button_id)
            metric_row.addWidget(button)
            if value == "speed":
                button.setChecked(True)
            button.clicked.connect(self._refresh_task_states)
        metric_row.addStretch()
        self.ramp_preview = QLabel()
        self.ramp_preview.setFixedSize(96, 22)
        self.ramp_display = QLineEdit()
        self.ramp_display.setReadOnly(True)
        ramp_names = QgsStyle().defaultStyle().colorRampNames()
        if ramp_names:
            self.ramp_display.setText(ramp_names[0])
        self.ramp_button = QPushButton("选择…")
        self.ramp_button.clicked.connect(self._pick_color_ramp)
        self.reverse_check = QCheckBox("反转色带")
        self.reverse_check.toggled.connect(self._update_ramp_preview)
        self.elev_unit = QComboBox(); self.elev_unit.addItems(["m", "ft"])
        self.speed_unit = QComboBox(); self.speed_unit.addItems(["m/s", "km/h", "mph"])
        self.slope_unit = QComboBox(); self.slope_unit.addItems(["°", "%"])
        self.elev_field = QLineEdit("ELEV")
        self.speed_field = QLineEdit("speed")
        self.slope_field = QLineEdit("Slope")
        self.batch_policy = QComboBox()
        self.batch_policy.addItem(tr("Continue executable tasks, skip incompatible tasks"), "continue")
        self.batch_policy.addItem(tr("Strict mode: Stop if incompatible tasks exist"), "strict")
        self.batch_policy.addItem(tr("Run tasks with complete fields only"), "complete_only")
        grid.addWidget(QLabel(tr("Render mode")), 0, 0); grid.addLayout(mode_row, 0, 1, 1, 3)
        grid.addWidget(QLabel(tr("Render field")), 1, 0); grid.addLayout(metric_row, 1, 1, 1, 3)
        ramp_row = QHBoxLayout()
        ramp_row.addWidget(self.ramp_preview)
        ramp_row.addWidget(self.ramp_display, 1)
        ramp_row.addWidget(self.ramp_button)
        ramp_row.addWidget(self.reverse_check)
        grid.addWidget(QLabel(tr("Color ramp")), 2, 0); grid.addLayout(ramp_row, 2, 1, 1, 3)
        units_grid = QGridLayout()
        units_grid.setContentsMargins(0, 0, 0, 0)
        units_grid.setHorizontalSpacing(8)
        fields_grid = QGridLayout()
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(8)
        for column, (label, unit_widget, field_widget) in enumerate((
            (tr("Elevation"), self.elev_unit, self.elev_field),
            (tr("Slope"), self.slope_unit, self.slope_field),
            (tr("Speed"), self.speed_unit, self.speed_field),
        )):
            units_grid.addWidget(QLabel(label), 0, column)
            units_grid.addWidget(unit_widget, 1, column)
            fields_grid.addWidget(QLabel(label), 0, column)
            fields_grid.addWidget(field_widget, 1, column)
            units_grid.setColumnStretch(column, 1)
            fields_grid.setColumnStretch(column, 1)
        grid.addWidget(QLabel(tr("Unit")), 3, 0)
        grid.addLayout(units_grid, 3, 1, 1, 3)
        grid.addWidget(QLabel(tr("Field name")), 4, 0)
        grid.addLayout(fields_grid, 4, 1, 1, 3)
        grid.addWidget(QLabel(tr("Exception policy")), 5, 0)
        grid.addWidget(self.batch_policy, 5, 1, 1, 3)
        settings.setContentLayout(grid)
        settings_layout.addWidget(settings)

        output = CollapsibleSection(tr("Output & Naming"))
        output_grid = QGridLayout()
        self.output_mode_group = QButtonGroup(self)
        output_mode_row = QHBoxLayout()
        for button_id, (label, value) in enumerate((
            (tr("Temporary layer"), "temporary"),
            (tr("Separate files"), "separate"),
            (tr("Single GeoPackage"), "single_gpkg"))):
            button = QRadioButton(label)
            button.setProperty("value", value)
            self.output_mode_group.addButton(button, button_id)
            output_mode_row.addWidget(button)
            if button_id == 0:
                button.setChecked(True)
            button.clicked.connect(self._update_output_ui)
        output_mode_row.addStretch()
        self.output_path = QLineEdit()
        self.output_browse = QPushButton(tr("Browse…"))
        self.output_browse.clicked.connect(self._browse_output)
        self.format_combo = QComboBox()
        self.format_combo.addItem("GeoPackage (*.gpkg)", (".gpkg", "GPKG"))
        self.format_combo.addItem("GeoJSON (*.geojson)", (".geojson", "GeoJSON"))
        self.format_combo.addItem("Shapefile (*.shp)", (".shp", "ESRI Shapefile"))
        self.name_template = QLineEdit("{source}_{metric}_{mode}")
        self.collision_combo = QComboBox()
        self.collision_combo.addItem(tr("Auto-append index"), "suffix")
        self.collision_combo.addItem(tr("Skip existing results"), "skip")
        self.collision_combo.addItem(tr("Overwrite existing results"), "overwrite")
        output_grid.addWidget(QLabel(tr("Output mode")), 0, 0); output_grid.addLayout(output_mode_row, 0, 1, 1, 3)
        output_grid.addWidget(QLabel(tr("Output location")), 1, 0); output_grid.addWidget(self.output_path, 1, 1, 1, 2)
        output_grid.addWidget(self.output_browse, 1, 3)
        output_grid.addWidget(QLabel(tr("File format")), 2, 0); output_grid.addWidget(self.format_combo, 2, 1)
        output_grid.addWidget(QLabel(tr("Naming template")), 2, 2); output_grid.addWidget(self.name_template, 2, 3)
        output_grid.addWidget(QLabel(tr("Collision policy")), 3, 0); output_grid.addWidget(self.collision_combo, 3, 1)
        output.setContentLayout(output_grid)
        settings_layout.addWidget(output)
        settings_layout.addStretch()
        settings_scroll.setWidget(settings_container)
        layout.addWidget(settings_scroll)

        self.summary_label = QLabel(tr("No tasks added yet"))
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.report_btn = QPushButton(tr("View Report"))
        self.report_btn.setEnabled(False)
        self.report_btn.clicked.connect(self._show_report)
        self.run_btn = QPushButton(tr("Start Generation"))
        self.run_btn.clicked.connect(self._run_batch)
        style_primary_button(self.run_btn)
        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self._cancel_or_close)
        self.retry_btn = QPushButton(tr("Retry Failed"))
        self.retry_btn.setEnabled(False)
        self.retry_btn.clicked.connect(self._retry_failed)
        # Keep primary and secondary actions visually aligned. The primary
        # button has additional QSS padding, so relying on sizeHint alone
        # makes it taller than the native secondary buttons.
        for button in (
                self.report_btn, self.retry_btn,
                self.run_btn, self.cancel_btn):
            button.setFixedHeight(32)
        layout.addLayout(actions)
        self._update_ramp_preview()
        self._update_output_ui()

    def _make_task(self, path, source_kind, layer=None):
        path = canonical_gpx_path(path)
        if not path:
            return None
        key = os.path.normcase(path)
        if key in self.task_keys:
            return None
        inspected = inspect_gpx(path)
        if layer is None and inspected["valid"]:
            layer = load_track_points_layer(path)
        display_name = layer.name() if source_kind == "QGIS 图层" and layer else (
            os.path.splitext(os.path.basename(path))[0])
        task = BatchTask(
            key=key, name=display_name,
            source_kind=source_kind, source_path=path, layer=layer,
            point_count=inspected["point_count"], has_time=inspected["has_time"],
            has_elevation=inspected["has_elevation"], has_speed=inspected["has_speed"],
            valid=bool(inspected["valid"] and layer and layer.isValid()),
            inspect_error=inspected["error"] or ("无法加载 track_points 图层" if not layer else ""),
        )
        self.task_keys.add(key)
        return task

    def _add_task(self, task):
        if not task:
            return
        self.tasks.append(task)
        self._refresh_table()

    def _add_gpx_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加 GPX 文件", "", "GPX (*.gpx)")
        for path in paths:
            self._add_task(self._make_task(path, "GPX 文件"))

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 GPX 文件夹")
        if not folder:
            return
        recursive_choice = QMessageBox.question(
            self, "扫描文件夹", "是否同时扫描子文件夹？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No)
        if recursive_choice == QMessageBox.StandardButton.Cancel:
            return
        recursive = recursive_choice == QMessageBox.StandardButton.Yes
        found = []
        try:
            walker = os.walk(folder, followlinks=False) if recursive else [(folder, [], os.listdir(folder))]
        except OSError as exc:
            QMessageBox.warning(self, "ColorGPX", f"{tr('Unable to read folder:')} {exc}")
            return
        for root, _dirs, files in walker:
            for filename in files:
                if filename.lower().endswith(GPX_SUFFIX):
                    candidate = os.path.join(root, filename)
                    if os.path.islink(candidate):
                        continue
                    found.append(candidate)
                    if len(found) >= MAX_FOLDER_FILES:
                        break
            if len(found) >= MAX_FOLDER_FILES:
                break
        for path in sorted(found):
            self._add_task(self._make_task(path, "文件夹"))
        if len(found) >= MAX_FOLDER_FILES:
            QMessageBox.warning(self, "ColorGPX", f"{tr('To avoid exhausting resources, a maximum of')} {MAX_FOLDER_FILES} {tr('files can be added at a time.')}")

    def _add_project_layers(self):
        layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != QgsMapLayer.LayerType.VectorLayer:
                continue
            source_lower = str(layer.source()).lower()
            if "track_points" not in source_lower:
                continue
            path = canonical_gpx_path(layer.source())
            if path:
                layers.append((layer, path))
        if not layers:
            QMessageBox.information(self, "ColorGPX", tr("No available GPX track_points layer found in current project."))
            return
        picker = QDialog(self)
        picker.setWindowTitle(tr("Select Project Layer"))
        picker_layout = QVBoxLayout(picker)
        list_widget = QListWidget()
        for layer, path in layers:
            item = QListWidgetItem(f"{layer.name()} - {path}")
            item.setData(Qt.ItemDataRole.UserRole, layer.id())
            item.setCheckState(Qt.CheckState.Unchecked)
            list_widget.addItem(item)
        picker_layout.addWidget(list_widget)
        row = QHBoxLayout(); ok = QPushButton(tr("Add")); cancel = QPushButton(tr("Cancel"))
        ok.clicked.connect(picker.accept); cancel.clicked.connect(picker.reject)
        row.addStretch(); row.addWidget(ok); row.addWidget(cancel); picker_layout.addLayout(row)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            layer = QgsProject.instance().mapLayer(item.data(Qt.ItemDataRole.UserRole))
            if layer:
                self._add_task(self._make_task(layer.source(), "QGIS 图层", layer))

    def _remove_selected(self):
        rows = sorted({item.row() for item in self.task_table.selectedItems()}, reverse=True)
        for row in rows:
            task = self.tasks.pop(row)
            self.task_keys.discard(task.key)
        self._refresh_table()

    def _clear_tasks(self):
        self.tasks.clear(); self.task_keys.clear(); self._refresh_table()

    def _task_readiness(self, task):
        if not task.valid:
            return "不可运行", task.inspect_error
        metric = self._checked_value(self.metric_group)
        if metric == "speed":
            if task.has_speed:
                return "可运行", "使用原始或扩展速度"
            if task.has_time:
                return "可运行·部分", "缺少速度，将根据时间模拟"
            return "不可运行", "缺少速度和时间，无法生成速度"
        if metric in ("elevation", "slope") and not task.has_elevation:
            return "不可运行", "缺少高程，无法生成高程或坡度"
        optional = []
        if not task.has_time:
            optional.append("缺少时间")
        if not task.has_speed:
            optional.append("缺少原始速度")
        return ("可运行·部分", "；".join(optional)) if optional else ("可运行", "字段完整")

    def _refresh_task_states(self, *_args):
        for task in self.tasks:
            task.status, task.detail = self._task_readiness(task)
        self._refresh_table()

    def _refresh_table(self):
        self.task_table.blockSignals(True)
        self.task_table.setRowCount(0)
        for task in self.tasks:
            if task.status in ("待检查", "可运行", "可运行·部分", "不可运行"):
                task.status, task.detail = self._task_readiness(task)
            row = self.task_table.rowCount(); self.task_table.insertRow(row)
            enabled = QTableWidgetItem()
            enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            enabled.setCheckState(Qt.CheckState.Checked if task.selected else Qt.CheckState.Unchecked)
            values = [enabled, task.status, shortened_display_name(task.name), task.source_kind, task.point_count,
                      "有" if task.has_time else "无", "有" if task.has_elevation else "无",
                      task.speed_source, task.detail]
            for col, value in enumerate(values):
                item = value if isinstance(value, QTableWidgetItem) else QTableWidgetItem(str(value))
                if col != 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(task.name if col == 2 else task.detail)
                if col == 1:
                    if task.status in ("可运行", "完整生成"):
                        item.setForeground(QBrush(QColor("#2e7d32")))
                    elif task.status in ("可运行·部分", "部分生成", "跳过", "取消"):
                        item.setForeground(QBrush(QColor("#b26a00")))
                    elif task.status in ("不可运行", "失败"):
                        item.setForeground(QBrush(QColor("#c62828")))
                self.task_table.setItem(row, col, item)
        self.task_table.blockSignals(False)
        self.task_table.resizeColumnsToContents()
        self.task_table.setColumnWidth(2, 190)
        self._update_summary()

    def _on_item_changed(self, item):
        if item.column() == 0 and 0 <= item.row() < len(self.tasks):
            self.tasks[item.row()].selected = item.checkState() == Qt.CheckState.Checked
            self._update_summary()

    def _update_summary(self):
        selected = [task for task in self.tasks if task.selected]
        ready = sum(task.status.startswith("可运行") for task in selected)
        partial = sum(task.status == "可运行·部分" for task in selected)
        blocked = sum(task.status == "不可运行" for task in selected)
        self.summary_label.setText(
            f"共 {len(selected)} 个选中任务：可运行 {ready-partial}，部分信息 {partial}，不可运行 {blocked}"
        )

    @staticmethod
    def _checked_value(group):
        button = group.checkedButton()
        return button.property("value") if button else None

    def _make_ramp_preview(self, ramp, width=96, height=22, reverse=False):
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for x in range(width):
            ratio = x / float(max(1, width - 1))
            if reverse:
                ratio = 1.0 - ratio
            painter.fillRect(x, 0, 1, height, ramp.color(ratio))
        painter.setPen(QColor("#808080"))
        painter.drawRect(0, 0, width - 1, height - 1)
        painter.end()
        return pixmap

    def _pick_color_ramp(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Select Color Ramp"))
        dialog.resize(360, 360)
        layout = QVBoxLayout(dialog)
        ramp_list = QListWidget(dialog)
        ramp_list.setIconSize(QSize(96, 22))
        for name in QgsStyle().defaultStyle().colorRampNames():
            ramp = QgsStyle().defaultStyle().colorRamp(name)
            icon = QIcon(self._make_ramp_preview(ramp)) if ramp else QIcon()
            ramp_list.addItem(QListWidgetItem(icon, name))
        matches = ramp_list.findItems(
            self.ramp_display.text(), Qt.MatchFlag.MatchExactly)
        if matches:
            ramp_list.setCurrentItem(matches[0])
            ramp_list.scrollToItem(matches[0])
        layout.addWidget(ramp_list)
        buttons = QHBoxLayout()
        ok_button = QPushButton(tr("OK"))
        cancel_button = QPushButton(tr("Cancel"))
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        ramp_list.itemDoubleClicked.connect(dialog.accept)
        buttons.addStretch()
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted and ramp_list.currentItem():
            self.ramp_display.setText(ramp_list.currentItem().text())
            self._update_ramp_preview()

    def _update_ramp_preview(self, *_args):
        ramp = QgsStyle().defaultStyle().colorRamp(self.ramp_display.text())
        if ramp:
            self.ramp_preview.setPixmap(self._make_ramp_preview(
                ramp, reverse=self.reverse_check.isChecked()))
            self.ramp_preview.setToolTip(self.ramp_display.text())

    def _update_output_ui(self, *_args):
        mode = self._checked_value(self.output_mode_group)
        enabled = mode != "temporary"
        self.output_path.setEnabled(enabled); self.output_browse.setEnabled(enabled)
        self.format_combo.setEnabled(mode == "separate")

    def _browse_output(self):
        mode = self._checked_value(self.output_mode_group)
        if mode == "separate":
            path = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        elif mode == "single_gpkg":
            path, _ = QFileDialog.getSaveFileName(self, "选择 GeoPackage", "ColorGPX_batch.gpkg", "GPKG (*.gpkg)")
            if path and not path.lower().endswith(".gpkg"):
                path += ".gpkg"
        else:
            path = ""
        if path:
            self.output_path.setText(path)

    def _cancel_or_close(self):
        if not self.run_btn.isEnabled():
            self.cancel_requested = True
            self.cancel_btn.setText("正在取消…")
        else:
            self.reject()

    def _resolve_separate_path(self, folder, base_name, extension, policy):
        folder = os.path.realpath(folder)
        candidate = os.path.realpath(os.path.join(folder, base_name + extension))
        if os.path.commonpath([folder, candidate]) != folder:
            raise ValueError("输出名称超出目标目录")
        if not os.path.exists(candidate) or policy == "overwrite":
            return candidate
        if policy == "skip":
            return ""
        index = 2
        while True:
            alternate = os.path.join(folder, f"{base_name}_{index}{extension}")
            if not os.path.exists(alternate):
                return alternate
            index += 1

    def _gpkg_layer_exists(self, gpkg_path, layer_name):
        if not os.path.exists(gpkg_path):
            return False
        return QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", "probe", "ogr").isValid()

    def _resolve_gpkg_layer_name(self, gpkg_path, name, policy):
        if not self._gpkg_layer_exists(gpkg_path, name) or policy == "overwrite":
            return name
        if policy == "skip":
            return ""
        index = 2
        while self._gpkg_layer_exists(gpkg_path, f"{name}_{index}"):
            index += 1
        return f"{name}_{index}"

    def _write_layer(self, layer, path, driver, layer_name, overwrite_file=False):
        if not hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
            if driver == "GPKG" and os.path.exists(path) and not overwrite_file:
                raise RuntimeError("当前 QGIS 版本不支持向已有 GeoPackage 追加图层")
            result = QgsVectorFileWriter.writeAsVectorFormat(
                layer, path, "UTF-8", layer.crs(), driver)
            error = result[0] if isinstance(result, (tuple, list)) else result
            if error != QgsVectorFileWriter.WriterError.NoError:
                message = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else str(error)
                raise IOError(message)
            return
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        options.fileEncoding = "UTF-8"
        options.layerName = layer_name
        if driver == "GPKG" and os.path.exists(path) and not overwrite_file:
            options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, path, QgsProject.instance().transformContext(), options)
        error = result[0] if isinstance(result, (tuple, list)) else result
        if error != QgsVectorFileWriter.WriterError.NoError:
            message = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else str(error)
            raise IOError(message)

    def _add_result_to_project(self, layer):
        if self.result_group is None:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.result_group = QgsProject.instance().layerTreeRoot().addGroup(f"ColorGPX {stamp}")
        QgsProject.instance().addMapLayer(layer, False)
        self.result_group.addLayer(layer)

    def _retry_failed(self):
        found = False
        for task in self.tasks:
            if task.status == "失败":
                task.status, task.detail = self._task_readiness(task)
                task.selected = True
                found = True
        if found:
            self._refresh_table()
            self._run_batch()

    def _run_batch(self):
        # A completed task remains selectable for another render pass. Rebuild
        # readiness from the current controls so changing the ramp, mode, field,
        # units, or naming settings can generate the task again.
        for task in self.tasks:
            if task.selected:
                task.status, task.detail = self._task_readiness(task)
        self._refresh_table()
        runnable = [task for task in self.tasks if task.selected and task.status.startswith("可运行")]
        blocked = [task for task in self.tasks if task.selected and task.status == "不可运行"]
        policy_mode = self.batch_policy.currentData()
        if policy_mode == "strict" and blocked:
            QMessageBox.warning(self, "ColorGPX", tr("Incompatible tasks exist in strict mode, please remove or uncheck them first."))
            return
        if policy_mode == "complete_only":
            partial_tasks = [task for task in runnable if task.status == "可运行·部分"]
            for task in partial_tasks:
                task.status = "跳过"
                task.detail = "仅完整任务策略"
            runnable = [task for task in runnable if task.status == "可运行"]
        if not runnable:
            self._refresh_table()
            QMessageBox.information(self, "ColorGPX", tr("No tasks need to be run under current exception policy."))
            return
        if not runnable:
            QMessageBox.warning(self, "ColorGPX", tr("No runnable tasks match current configuration."))
            return
        output_mode = self._checked_value(self.output_mode_group)
        output_path = self.output_path.text().strip()
        if output_mode == "separate" and not os.path.isdir(output_path):
            QMessageBox.warning(self, "ColorGPX", tr("Please select a valid output folder."))
            return
        if output_mode == "single_gpkg":
            output_path = os.path.realpath(output_path)
            if not output_path.lower().endswith(".gpkg") or not os.path.isdir(os.path.dirname(output_path)):
                QMessageBox.warning(self, "ColorGPX", tr("Please select a GeoPackage file in a valid directory."))
                return
        if blocked:
            answer = QMessageBox.question(
                self, "ColorGPX 批处理",
                f"将生成 {len(runnable)} 个任务，跳过 {len(blocked)} 个不兼容任务。是否继续？")
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self.collision_combo.currentData() == "overwrite":
            answer = QMessageBox.warning(
                self, "确认覆盖", "覆盖模式可能替换已有文件或同名图层。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return

        for task in blocked:
            task.status = "跳过"
        self.cancel_requested = False
        self.run_btn.setEnabled(False); self.cancel_btn.setText(tr("Cancel Running"))
        self.progress.setRange(0, len(runnable)); self.progress.setValue(0)
        metric = self._checked_value(self.metric_group)
        mode = self._checked_value(self.mode_group)
        policy = self.collision_combo.currentData()
        extension, driver = self.format_combo.currentData()
        template = self.name_template.text().strip()

        for index, task in enumerate(runnable, 1):
            if self.cancel_requested:
                task.status = "取消"
                continue
            QApplication.processEvents()
            partial_input = task.status == "可运行·部分"
            task.status = "处理中"; self._refresh_table()
            try:
                output_name = safe_output_name(template, task, metric, mode, index)
                simulate_speed = metric == "speed" and not task.has_speed and task.has_time
                out_layer = self.process_callback(
                    task=task, output_name=output_name, render_type=metric,
                    render_mode=mode, color_ramp_name=self.ramp_display.text(),
                    reverse_ramp=self.reverse_check.isChecked(), simulate_speed=simulate_speed,
                    elev_unit=self.elev_unit.currentText(), speed_unit=self.speed_unit.currentText(),
                    slope_unit=self.slope_unit.currentText(), progress_bar=None,
                    elev_name=self.elev_field.text().strip() or "ELEV",
                    speed_name=self.speed_field.text().strip() or "speed",
                    slope_name=self.slope_field.text().strip() or "Slope",
                )
                if out_layer is None or not out_layer.isValid():
                    raise RuntimeError("处理器未返回有效图层")
                project_layer = out_layer
                task.output = "临时图层"
                if output_mode == "separate":
                    target = self._resolve_separate_path(output_path, output_name, extension, policy)
                    if not target:
                        task.status = "跳过"; task.detail = "输出已存在"
                        task.result_layer = None
                        continue
                    self._write_layer(out_layer, target, driver, output_name, overwrite_file=(policy == "overwrite"))
                    task.output = target
                    saved_uri = f"{target}|layername={output_name}" if driver == "GPKG" else target
                    saved_layer = QgsVectorLayer(saved_uri, output_name, "ogr")
                    if saved_layer.isValid():
                        project_layer = saved_layer
                elif output_mode == "single_gpkg":
                    layer_name = self._resolve_gpkg_layer_name(output_path, output_name, policy)
                    if not layer_name:
                        task.status = "跳过"; task.detail = "GeoPackage 同名图层已存在"
                        task.result_layer = None
                        continue
                    self._write_layer(out_layer, output_path, "GPKG", layer_name, overwrite_file=False)
                    task.output = f"{output_path}|layername={layer_name}"
                    saved_layer = QgsVectorLayer(task.output, layer_name, "ogr")
                    if saved_layer.isValid():
                        project_layer = saved_layer
                task.result_layer = project_layer
                self._add_result_to_project(project_layer)
                task.status = "部分生成" if partial_input else "完整生成"
            except Exception as exc:
                task.status = "失败"
                task.detail = str(exc)
                task.result_layer = None
            finally:
                self.progress.setValue(index)
                QApplication.processEvents()

        self.run_btn.setEnabled(True); self.cancel_btn.setText("关闭")
        self.progress.setValue(len(runnable))
        self.report_btn.setEnabled(True); self._refresh_table()
        completed = sum(task.status == "完整生成" for task in self.tasks)
        partial = sum(task.status == "部分生成" for task in self.tasks)
        skipped = sum(task.status in ("跳过", "取消") for task in self.tasks)
        failed = sum(task.status == "失败" for task in self.tasks)
        self.retry_btn.setEnabled(failed > 0)
        message = f"完整 {completed}，部分 {partial}，跳过 {skipped}，失败 {failed}"
        if failed:
            self.iface.messageBar().pushWarning("ColorGPX 批处理完成", message)
        else:
            self.iface.messageBar().pushSuccess("ColorGPX 批处理完成", message)

    def _show_report(self):
        BatchResultDialog(self.tasks, self.iface, self).exec()
