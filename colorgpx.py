from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                                 QLabel, QComboBox, QLineEdit, QPushButton,
                                 QMessageBox, QFileDialog, QTextEdit, QProgressBar, QMenu,
                                 QListWidget, QListWidgetItem, QCheckBox, QSizePolicy, QApplication,
                                 QSlider, QWidget, QGroupBox, QFrame, QLayout)
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor
from qgis.PyQt.QtCore import Qt, QSize, QTimer, QTranslator, QLocale, QCoreApplication, QPoint, QDateTime
from qgis.core import *
from qgis.gui import QgsMapTool, QgsVertexMarker
from qgis.PyQt.QtWidgets import QRadioButton, QButtonGroup
import os
import re

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405



_zh_translations = {
    "1. This GPX does not contain speed information; current speed is simulated speed.": "1. 此 GPX 文件没有内置速度信息，当前速度为根据时间和经纬度计算出的模拟速度。",
    "2. We recommend using [2bulu, Guru Maps, OsmAnd, Organic] to record GPS speed.": "2. 建议使用 [两步路、Guru Maps、OsmAnd、Organic] 等专业软件记录含速度的 GPS 轨迹。",
    "This GPX layer does not contain elevation data (e.g. ele, elevation, altitude, alt, height tags).\nElevation and Slope rendering fields are unavailable.": "此 GPX 图层不包含高程数据（如 ele、elevation、altitude、alt、height 等标签）。\n高程和坡度渲染功能不可用。",
    "This GPX layer does not contain time data (e.g. time tag).\nSpeed rendering field is unavailable.": "此 GPX 图层不包含时间数据（如 time 标签）。\n速度渲染功能不可用。",
    "2. This GPX does not contain elevation data; Elevation and Slope rendering are unavailable.": "2. 此 GPX 文件没有高程数据，高程与坡度渲染不可用。",
    "3. We recommend using [2bulu, Guru Maps, OsmAnd, Organic] to record GPS speed and elevation.": "3. 建议使用 [两步路、Guru Maps、OsmAnd、Organic] 等专业软件记录含速度与高度的 GPS 轨迹。",
    "Elevation and Slope rendering are unavailable (no elevation data).": "高程和坡度渲染不可用（无高程数据）。",
    "Current speed is simulated speed. Elevation and Slope are unavailable.": "当前速度为计算模拟速度。高程与坡度不可用。",
    "This layer has no time data. Speed rendering is unavailable.": "该图层无时间数据。速度渲染不可用。",
    "Current speed is simulated speed. Click for more details.": "当前速度为计算模拟速度。点击查看详情。",
    "Track Info": "轨迹信息",
    "Time": "时间",
    "Elevation": "海拔",
    "Speed": "速度",
    "Slope": "坡度",
    "ColorGPX Hover Settings": "悬浮窗口显示设置",
    "Show Items": "显示内容",
    "Units": "显示单位",
    "Hover Track Info": "悬浮轨迹查看工具",
    "Hover Settings": "悬浮窗口设置",
    "Select Tracking Layer": "选择追踪图层",
    "Available Layers": "可用图层",
    "Start Tracking": "开始追踪",
    "No vector layers found in the project.": "工程中未找到任何向量图层。",
    "💡 Tip:\nLock position info: Left-click.\nUnlock position: Right-click / click blank area.": "💡 提示：\n锁定位置信息：鼠标左键。\n解除位置锁定：鼠标右键 / 点击空白区域。",
}


def tr(text, disambiguation=None):
    """Translate text using QCoreApplication with fallback context."""
    res = QCoreApplication.translate("ColorGPX", text, disambiguation)
    if res == text:
        res = QCoreApplication.translate("ColorGPXDialog", text, disambiguation)
    if res == text:
        locale_name = QgsSettings().value("locale/userLocale", QLocale.system().name())
        if locale_name and str(locale_name).lower().startswith("zh"):
            if text in _zh_translations:
                return _zh_translations[text]
    return res


from .point_processor import process_points
from .point_renderer import apply_renderer as apply_point_renderer
from .line_processor import process_lines
from .line_renderer import apply_renderer as apply_line_renderer
from .gradient_line_renderer import apply_gradient_renderer


class ColorGPXDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ColorGPX - Settings"))
        self.setMinimumWidth(500)

        main_layout = QVBoxLayout(self)

        # ---- left panel ---- #
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel(tr("Input layer (GPX track_points):")))
        self.layer_combo = QComboBox()
        self.refresh_layers()
        left_layout.addWidget(self.layer_combo)

        left_layout.addWidget(QLabel(tr("Render mode:")))
        self.render_mode_group = QButtonGroup()
        self.rb_point = QRadioButton(tr("Point"))
        self.rb_line = QRadioButton(tr("Line"))
        self.rb_gradient = QRadioButton(tr("Gradient Line"))
        self.render_mode_group.addButton(self.rb_point)
        self.render_mode_group.addButton(self.rb_line)
        self.render_mode_group.addButton(self.rb_gradient)
        self.rb_point.setChecked(True)
        self.rb_point.toggled.connect(self._on_mode_changed)
        self.rb_line.toggled.connect(self._on_mode_changed)
        self.rb_gradient.toggled.connect(self._on_mode_changed)

        mode_grid = QGridLayout()
        mode_grid.setSpacing(10)
        mode_grid.setContentsMargins(0, 0, 0, 0)
        mode_grid.setColumnMinimumWidth(0, 90)
        mode_grid.setColumnMinimumWidth(1, 90)
        mode_grid.setColumnMinimumWidth(2, 90)
        mode_grid.setColumnStretch(0, 0)
        mode_grid.setColumnStretch(1, 0)
        mode_grid.setColumnStretch(2, 0)
        mode_grid.setColumnStretch(3, 1)
        mode_grid.addWidget(self.rb_point, 0, 0)
        mode_grid.addWidget(self.rb_line, 0, 1)
        mode_grid.addWidget(self.rb_gradient, 0, 2)
        left_layout.addLayout(mode_grid)

        left_layout.addWidget(QLabel(tr("Render field:")))
        self.render_type_group = QButtonGroup()
        self.rb_speed = QRadioButton(tr("Speed"))
        self.rb_elevation = QRadioButton(tr("Elevation"))
        self.rb_slope = QRadioButton(tr("Slope"))
        self.render_type_group.addButton(self.rb_speed)
        self.render_type_group.addButton(self.rb_elevation)
        self.render_type_group.addButton(self.rb_slope)
        self.rb_speed.setChecked(True)

        type_grid = QGridLayout()
        type_grid.setSpacing(10)
        type_grid.setContentsMargins(0, 0, 0, 0)
        type_grid.setColumnMinimumWidth(0, 90)
        type_grid.setColumnMinimumWidth(1, 90)
        type_grid.setColumnMinimumWidth(2, 90)
        type_grid.setColumnStretch(0, 0)
        type_grid.setColumnStretch(1, 0)
        type_grid.setColumnStretch(2, 0)
        type_grid.setColumnStretch(3, 1)
        type_grid.addWidget(self.rb_elevation, 0, 0)
        type_grid.addWidget(self.rb_slope, 0, 1)

        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)
        speed_layout.addWidget(self.rb_speed)

        self.speed_warn_btn = QPushButton()
        self._icon_warn_yellow = QIcon(os.path.join(os.path.dirname(__file__), "icons_Component", "warning_yellow.svg"))
        self._icon_warn_red = QIcon(os.path.join(os.path.dirname(__file__), "icons_Component", "warning_red.svg"))
        self.speed_warn_btn.setIcon(self._icon_warn_yellow)
        self.speed_warn_btn.setIconSize(QSize(16, 16))
        self.speed_warn_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        self.speed_warn_btn.setToolTip(tr("Current speed is simulated speed. Click for more details."))
        self.speed_warn_btn.setVisible(False)
        self.speed_warn_btn.clicked.connect(self._show_speed_warning)
        speed_layout.addWidget(self.speed_warn_btn)

        speed_widget = QWidget()
        speed_widget.setLayout(speed_layout)
        type_grid.addWidget(speed_widget, 0, 2)

        self.elev_unit_combo = QComboBox()
        self.elev_unit_combo.addItems(["m", "ft"])
        self.elev_unit_combo.setFixedWidth(60)

        self.slope_unit_combo = QComboBox()
        self.slope_unit_combo.addItems(["°", "%"])
        self.slope_unit_combo.setFixedWidth(60)

        self.speed_unit_combo = QComboBox()
        self.speed_unit_combo.addItems(["m/s", "km/h", "mph"])
        self.speed_unit_combo.setFixedWidth(60)

        type_grid.addWidget(self.elev_unit_combo, 1, 0)
        type_grid.addWidget(self.slope_unit_combo, 1, 1)
        type_grid.addWidget(self.speed_unit_combo, 1, 2)

        left_layout.addLayout(type_grid)

        left_layout.addWidget(QLabel(tr("Color ramp:")))
        ramp_row = QHBoxLayout()
        self.ramp_preview = QLabel()
        self.ramp_preview.setFixedSize(74, 22)
        ramp_row.addWidget(self.ramp_preview)
        self.ramp_display = QLineEdit()
        self.ramp_display.setReadOnly(True)
        ramp_row.addWidget(self.ramp_display, stretch=1)
        self.ramp_btn = QPushButton(tr("Select..."))
        self.ramp_btn.clicked.connect(self._pick_color_ramp)
        ramp_row.addWidget(self.ramp_btn)
        left_layout.addLayout(ramp_row)
        # Initialize with first color ramp
        try:
            ramp_names = QgsStyle().defaultStyle().colorRampNames()
            if ramp_names:
                self.ramp_display.setText(ramp_names[0])
                ramp = QgsStyle().defaultStyle().colorRamp(ramp_names[0])
                if ramp:
                    icon = self._make_ramp_preview(ramp)
                    self.ramp_preview.setPixmap(icon.pixmap(74, 22))
        except Exception as e:
            print(f"ColorGPX: Error during default color ramp initialization: {e}")

        # ---- reverse ramp checkbox ---- #
        ramp_rev_row = QHBoxLayout()
        self.reverse_cb = QCheckBox(tr("Reverse ramp"))
        self.processing_callback = None
        self.reverse_cb.toggled.connect(self._update_ramp_preview)
        ramp_rev_row.addWidget(self.reverse_cb)
        ramp_rev_row.addStretch()
        left_layout.addLayout(ramp_rev_row)

        left_layout.addWidget(QLabel(tr("Elevation field name:")))
        self.elev_field = QLineEdit("ELEV")
        left_layout.addWidget(self.elev_field)

        left_layout.addWidget(QLabel(tr("Speed field name:")))
        self.speed_field = QLineEdit("speed")
        left_layout.addWidget(self.speed_field)

        left_layout.addWidget(QLabel(tr("Slope field name:")))
        self.slope_field = QLineEdit("Slope")
        left_layout.addWidget(self.slope_field)

        # ---- output destination ---- #
        left_layout.addWidget(QLabel(tr("Output layer:")))
        dest_layout = QHBoxLayout()
        self.output_name = QLineEdit("ColorGPX")
        dest_layout.addWidget(self.output_name, stretch=1)

        self.output_dest_btn = QPushButton("…")
        self.output_dest_btn.setFixedWidth(35)
        self.output_dest_menu = QMenu(self)
        self.output_dest_menu.addAction(
            tr("Temporary layer")
        ).triggered.connect(self._on_dest_temp)
        self.output_dest_menu.addAction(
            tr("Save to file...")
        ).triggered.connect(self._on_dest_file)
        self.output_dest_btn.setMenu(self.output_dest_menu)
        dest_layout.addWidget(self.output_dest_btn)
        left_layout.addLayout(dest_layout)

        self.output_path = QLineEdit()
        self.output_path.setVisible(False)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(tr("Run"))
        cancel_btn = QPushButton(tr("Cancel"))
        ok_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        # ---- right panel: plugin info ---- #
        self.info_edit = QTextEdit()
        self.info_edit.setReadOnly(True)
        self.info_edit.setFixedWidth(180)
        title = "ColorGPX"
        desc = tr("Render GPX tracks as gradient-colored layers by speed (m/s), elevation (m) or slope (°). Recommended apps: 2bulu, Guru Maps, OsmAnd, Organic.")
        steps_title = tr("How to use")
        step1 = tr("Select a GPX track_points layer")
        step2 = tr("Choose render mode (Point / Line / Gradient Line)")
        step3 = tr("Choose render field (Speed / Elevation / Slope°)")
        step4 = tr("Choose a color ramp")
        step5 = tr("Click \"Run\"")
        save_title = tr("Save")
        save_desc = tr("Optionally save to GeoJSON, GPKG or Shapefile.")
        author = tr("Author: OpenQGIS")

        locale_val = QgsSettings().value("locale/userLocale", "")
        font_family = "Microsoft YaHei,sans-serif" if locale_val.startswith("zh") else "Segoe UI,sans-serif"

        info_html = (
            f'<html><body style="font-family:{font_family};font-size:11px;color:#333;">'
            f'<h3 style="margin:0 0 8px;color:#2c6b32;">{title}</h3>'
            f'<p style="margin:0 0 10px;line-height:1.5;">{desc}</p>'
            f'<hr>'
            f'<h4 style="margin:8px 0 4px;">{steps_title}</h4>'
            f'<ol style="margin:2px 0;padding-left:18px;line-height:1.6;">'
            f'<li>{step1}</li>'
            f'<li>{step2}</li>'
            f'<li>{step3}</li>'
            f'<li>{step4}</li>'
            f'<li>{step5}</li>'
            f'</ol>'
            f'<h4 style="margin:8px 0 4px;">{save_title}</h4>'
            f'<p style="margin:2px 0;line-height:1.5;">{save_desc}</p>'
            f'<p style="margin:8px 0 0;color:#888;font-size:10px;">{author}</p>'
            f'</body></html>'
        )
        self.info_edit.setHtml(info_html)
        top_layout = QHBoxLayout()
        top_layout.addLayout(left_layout, stretch=1)
        top_layout.addWidget(self.info_edit, stretch=0)

        self.progress_bar = QProgressBar()

        main_layout.addLayout(top_layout, stretch=1)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(btn_layout)

        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self._on_layer_changed()

    def _on_mode_changed(self):
        if self.rb_point.isChecked():
            self.output_name.setText("ColorGPX_points")
        elif self.rb_gradient.isChecked():
            self.output_name.setText("ColorGPX_gradient")
        else:
            self.output_name.setText("ColorGPX_line")

    def _on_dest_temp(self):
        self.output_path.setText("")

    def _on_dest_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save layer"),
            "",
            tr("GeoJSON (*.geojson);;GPKG (*.gpkg);;Shapefile (*.shp);;All files (*)")
        )
        if file_path:
            self.output_path.setText(file_path)

    def _pick_color_ramp(self):
        """Open a fixed-height dialog to pick a color ramp."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Select Color Ramp"))
        layout = QVBoxLayout(dialog)

        list_widget = QListWidget()
        list_widget.setIconSize(QSize(74, 22))
        list_widget.setSpacing(0)

        for name in QgsStyle().defaultStyle().colorRampNames():
            ramp = QgsStyle().defaultStyle().colorRamp(name)
            icon = self._make_ramp_preview(ramp) if ramp else QIcon()
            item = QListWidgetItem(icon, name)
            list_widget.addItem(item)

        list_widget.setFixedHeight(12 * 24)

        current = self.ramp_display.text()
        items = list_widget.findItems(current, Qt.MatchFlag.MatchExactly)
        if items:
            list_widget.setCurrentItem(items[0])

        layout.addWidget(list_widget)

        list_widget.itemDoubleClicked.connect(dialog.accept)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(tr("OK"))
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = list_widget.currentItem()
            if selected:
                name = selected.text()
                self.ramp_display.setText(name)
                self._update_ramp_preview()

    def _make_ramp_preview(self, ramp, w=74, h=22, reverse=False):
        """Generate a horizontal gradient icon for a color ramp."""
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for x in range(w):
            ratio = x / (w - 1) if w > 1 else 0.5
            if reverse:
                ratio = 1 - ratio
            c = ramp.color(ratio)
            painter.setPen(c)
            painter.drawLine(x, 0, x, h - 1)
        painter.end()
        return QIcon(pixmap)

    def _update_ramp_preview(self):
        name = self.ramp_display.text()
        if not name:
            return
        try:
            ramp = QgsStyle().defaultStyle().colorRamp(name)
            if ramp:
                icon = self._make_ramp_preview(ramp, reverse=self.reverse_cb.isChecked())
                self.ramp_preview.setPixmap(icon.pixmap(74, 22))
        except Exception as e:
            print(f"ColorGPX: Error updating color ramp preview: {e}")

    def refresh_layers(self):
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.LayerType.VectorLayer:
                self.layer_combo.addItem(layer.name(), layer)

    def get_selected_layer(self):
        return self.layer_combo.currentData()

    def _on_ok(self):
        """Run processing callback if set, otherwise close dialog."""
        if self.processing_callback:
            self.processing_callback()
        else:
            self.accept()

    def _show_speed_warning(self):
        msg = (
            tr("1. This GPX does not contain speed information; current speed is simulated speed.") + "\n" +
            tr("2. We recommend using [2bulu, Guru Maps, OsmAnd, Organic] to record GPS speed.")
        )
        QMessageBox.information(self, tr("Information"), msg)

    def _show_no_elevation_warning(self):
        msg = tr(
            "This GPX layer does not contain elevation data (e.g. ele, elevation, altitude, alt, height tags).\n"
            "Elevation and Slope rendering fields are unavailable."
        )
        QMessageBox.information(self, tr("Information"), msg)

    def _show_no_time_warning(self):
        msg = tr(
            "This GPX layer does not contain time data (e.g. time tag).\n"
            "Speed rendering field is unavailable."
        )
        QMessageBox.information(self, tr("Information"), msg)

    def _show_speed_and_no_elevation_warning(self):
        msg = (
            tr("1. This GPX does not contain speed information; current speed is simulated speed.") + "\n" +
            tr("2. This GPX does not contain elevation data; Elevation and Slope rendering are unavailable.") + "\n" +
            tr("3. We recommend using [2bulu, Guru Maps, OsmAnd, Organic] to record GPS speed and elevation.")
        )
        QMessageBox.information(self, tr("Information"), msg)

    def _on_layer_changed(self):
        layer = self.get_selected_layer()
        if not layer:
            self.has_speed = False
            self.speed_warn_btn.setVisible(False)
            self._set_render_fields_enabled(True)
            return

        has_ele, has_time, has_speed = self._check_gpx_has_data(layer)
        self.has_speed = has_speed

        ele_ok = has_ele
        speed_ok = (has_time or has_speed)

        # Enable/disable radio buttons and their dropdowns selectively
        self.rb_elevation.setEnabled(ele_ok)
        self.elev_unit_combo.setEnabled(ele_ok)
        self.rb_slope.setEnabled(ele_ok)
        self.slope_unit_combo.setEnabled(ele_ok)

        self.rb_speed.setEnabled(speed_ok)
        self.speed_unit_combo.setEnabled(speed_ok)

        # Ensure a valid enabled option is checked
        if self.rb_speed.isChecked() and not speed_ok:
            if ele_ok:
                self.rb_elevation.setChecked(True)
        elif (self.rb_elevation.isChecked() or self.rb_slope.isChecked()) and not ele_ok:
            if speed_ok:
                self.rb_speed.setChecked(True)

        try:
            self.speed_warn_btn.clicked.disconnect()
        except TypeError:
            pass

        # Control warning button based on data cases
        if not ele_ok and not speed_ok:
            self.speed_warn_btn.setIcon(self._icon_warn_red)
            self.speed_warn_btn.setToolTip(
                tr("This layer has no elevation or time data. All render fields are unavailable.")
            )
            self.speed_warn_btn.clicked.connect(self._show_no_data_warning)
            self.speed_warn_btn.setVisible(True)
        elif speed_ok and not ele_ok:
            self.speed_warn_btn.setIcon(self._icon_warn_yellow)
            if has_speed:
                self.speed_warn_btn.setToolTip(
                    tr("Elevation and Slope rendering are unavailable (no elevation data).")
                )
                self.speed_warn_btn.clicked.connect(self._show_no_elevation_warning)
            else:
                self.speed_warn_btn.setToolTip(
                    tr("Current speed is simulated speed. Elevation and Slope are unavailable.")
                )
                self.speed_warn_btn.clicked.connect(self._show_speed_and_no_elevation_warning)
            self.speed_warn_btn.setVisible(True)
        elif not speed_ok and ele_ok:
            self.speed_warn_btn.setIcon(self._icon_warn_yellow)
            self.speed_warn_btn.setToolTip(
                tr("This layer has no time data. Speed rendering is unavailable.")
            )
            self.speed_warn_btn.clicked.connect(self._show_no_time_warning)
            self.speed_warn_btn.setVisible(True)
        else:
            # Both speed_ok and ele_ok are True
            if has_speed:
                self.speed_warn_btn.setVisible(False)
            else:
                self.speed_warn_btn.setIcon(self._icon_warn_yellow)
                self.speed_warn_btn.setToolTip(tr("Current speed is simulated speed. Click for more details."))
                self.speed_warn_btn.clicked.connect(self._show_speed_warning)
                self.speed_warn_btn.setVisible(True)

    def _set_render_fields_enabled(self, enabled: bool):
        """Enable or disable all render-field radio buttons and unit dropdowns."""
        self.rb_speed.setEnabled(enabled)
        self.rb_elevation.setEnabled(enabled)
        self.rb_slope.setEnabled(enabled)
        self.elev_unit_combo.setEnabled(enabled)
        self.slope_unit_combo.setEnabled(enabled)
        self.speed_unit_combo.setEnabled(enabled)

    def _show_no_data_warning(self):
        msg = tr(
            "This layer contains no elevation (ele) or time data (e.g. a plain route/waypoint without GPS recording). "
            "Speed, Elevation and Slope cannot be calculated. "
            "Please use a GPS-recorded track (track_points) layer instead."
        )
        QMessageBox.warning(self, tr("Layer Data Unavailable"), msg)

    def _check_gpx_has_data(self, layer):
        """Return (has_ele, has_time, has_speed) by stream-parsing the source GPX file."""
        if not layer:
            return False, False, False
        source = layer.source()
        if not source:
            return False, False, False
        gpx_file = source.split("|")[0]
        if not os.path.exists(gpx_file):
            return False, False, False
        has_ele = False
        has_time = False
        has_speed = False
        try:
            # Stream parse XML up to 5000 elements to prevent freezing on large files
            with open(gpx_file, 'rb') as f:
                context = ET.iterparse(f, events=('end',))  # nosec B314
                count = 0
                for event, elem in context:
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    tag_lower = tag.lower()
                    if tag_lower in ("ele", "elevation", "altitude", "alt", "height"):
                        has_ele = True
                    elif tag_lower == "time":
                        has_time = True
                    elif tag_lower == "speed":
                        has_speed = True
                    elem.clear()
                    count += 1
                    if count > 5000:
                        break
        except Exception:  # nosec B110
            pass
        return has_ele, has_time, has_speed

    def _check_gpx_has_speed(self, layer):
        """Legacy helper kept for compatibility; use _check_gpx_has_data instead."""
        _, _, has_speed = self._check_gpx_has_data(layer)
        return has_speed


class ColorGPXHoverWidget(QWidget):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        
        self.setStyleSheet("""
            QFrame#cardFrame {
                background-color: rgba(30, 30, 30, 210);
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 6px;
            }
            QLabel {
                color: white;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 11px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        
        self.frame = QFrame()
        self.frame.setObjectName("cardFrame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        
        self.label = QLabel()
        frame_layout.addWidget(self.label)
        layout.addWidget(self.frame)
        
        self.hide()

    def update_info(self, layer, feature, interpolation_ratio=0.0):
        settings = QgsSettings()
        show_time = settings.value("ColorGPX/hover_show_time", True, type=bool)
        show_elev = settings.value("ColorGPX/hover_show_elevation", True, type=bool)
        show_speed = settings.value("ColorGPX/hover_show_speed", True, type=bool)
        show_slope = settings.value("ColorGPX/hover_show_slope", True, type=bool)
        
        unit_elev = settings.value("ColorGPX/hover_unit_elevation", "m", type=str)
        unit_speed = settings.value("ColorGPX/hover_unit_speed", "km/h", type=str)
        unit_slope = settings.value("ColorGPX/hover_unit_slope", "°", type=str)
        
        html = ["<div style='line-height: 1.2;'>"]
        html.append(f"<div style='color: #4CAF50; font-weight: bold;'>{layer.name()}</div>")
        html.append("<div style='border-top: 1px solid rgba(255, 255, 255, 60); margin-top: 3px; margin-bottom: 3px;'></div>")
        html.append("<table style='color: white; font-family: sans-serif; font-size: 11px;'>")
        
        from .hover_utils import detect_field_and_unit, convert_value
        
        # 判断当前被吸附要素的几何类型是否为线类型（如果是线段，我们需要插值）
        is_line = feature.geometry() and QgsWkbTypes.geometryType(feature.geometry().wkbType()) == QgsWkbTypes.GeometryType.LineGeometry
        
        def get_attr(name):
            try:
                val = feature.attribute(name)
                if val == NULL or val is None:
                    return None
                return val
            except KeyError:
                return None

        has_any = False
        if show_time:
            fname, _ = detect_field_and_unit(layer, 'time')
            if fname:
                time_val = get_attr(fname)
                if time_val:
                    if is_line:
                        time_E_val = get_attr("time_E")
                        if isinstance(time_val, QDateTime) and isinstance(time_E_val, QDateTime) and time_val.isValid() and time_E_val.isValid():
                            s_secs = time_val.toSecsSinceEpoch()
                            e_secs = time_E_val.toSecsSinceEpoch()
                            interp_secs = s_secs + interpolation_ratio * (e_secs - s_secs)
                            time_val = QDateTime.fromSecsSinceEpoch(int(interp_secs))
                    
                    if isinstance(time_val, QDateTime):
                        time_str = time_val.toString("yyyy-MM-dd HH:mm:ss")
                    else:
                        time_str = str(time_val)
                    html.append(f"<tr><td>{tr('Time')}:</td><td style='padding-left: 10px;'>{time_str}</td></tr>")
                    has_any = True
                
        if show_elev:
            fname, orig_unit = detect_field_and_unit(layer, 'elevation')
            if fname:
                val = get_attr(fname)
                if val is not None:
                    if is_line:
                        val_S = get_attr(fname + "_S")
                        val_E = get_attr(fname + "_E")
                        if val_S is not None and val_E is not None:
                            val = float(val_S) + interpolation_ratio * (float(val_E) - float(val_S))
                    conv_val = convert_value(val, orig_unit, unit_elev, 'elevation')
                    if conv_val is not None:
                        html.append(f"<tr><td>{tr('Elevation')}:</td><td style='padding-left: 10px;'>{conv_val:.1f} {unit_elev}</td></tr>")
                        has_any = True
                    
        if show_speed:
            fname, orig_unit = detect_field_and_unit(layer, 'speed')
            if fname:
                val = get_attr(fname)
                if val is not None:
                    if is_line:
                        val_S = get_attr(fname + "_S")
                        val_E = get_attr(fname + "_E")
                        if val_S is not None and val_E is not None:
                            val = float(val_S) + interpolation_ratio * (float(val_E) - float(val_S))
                    conv_val = convert_value(val, orig_unit, unit_speed, 'speed')
                    if conv_val is not None:
                        html.append(f"<tr><td>{tr('Speed')}:</td><td style='padding-left: 10px;'>{conv_val:.1f} {unit_speed}</td></tr>")
                        has_any = True
                    
        if show_slope:
            fname, orig_unit = detect_field_and_unit(layer, 'slope')
            if fname:
                val = get_attr(fname)
                if val is not None:
                    if is_line:
                        val_S = get_attr(fname + "_S")
                        val_E = get_attr(fname + "_E")
                        if val_S is not None and val_E is not None:
                            val = float(val_S) + interpolation_ratio * (float(val_E) - float(val_S))
                    conv_val = convert_value(val, orig_unit, unit_slope, 'slope')
                    if conv_val is not None:
                        html.append(f"<tr><td>{tr('Slope')}:</td><td style='padding-left: 10px;'>{conv_val:.1f} {unit_slope}</td></tr>")
                        has_any = True
                    
        html.append("</table></div>")
        
        if not has_any:
            self.hide()
            return
            
        self.label.setText("".join(html))
        self.adjustSize()


class ColorGPXHoverSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ColorGPX Hover Settings"))
        self.setMinimumWidth(500)
        
        main_layout = QVBoxLayout(self)
        
        # Horizontal container layout for settings controls (left) and live preview (right)
        content_layout = QHBoxLayout()
        
        # Left Group Box (Settings)
        group = QGroupBox(tr("Show Items"))
        grid_layout = QGridLayout(group)
        
        self.cb_time = QCheckBox(tr("Time"))
        grid_layout.addWidget(self.cb_time, 0, 0, 1, 2)
        
        self.cb_elev = QCheckBox(tr("Elevation"))
        self.combo_elev = QComboBox()
        self.combo_elev.addItems(["m", "ft"])
        grid_layout.addWidget(self.cb_elev, 1, 0)
        grid_layout.addWidget(self.combo_elev, 1, 1)
        
        self.cb_speed = QCheckBox(tr("Speed"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["km/h", "m/s", "mph"])
        grid_layout.addWidget(self.cb_speed, 2, 0)
        grid_layout.addWidget(self.combo_speed, 2, 1)
        
        self.cb_slope = QCheckBox(tr("Slope"))
        self.combo_slope = QComboBox()
        self.combo_slope.addItems(["°", "%"])
        grid_layout.addWidget(self.cb_slope, 3, 0)
        grid_layout.addWidget(self.combo_slope, 3, 1)
        
        # Connect checkboxes to enable/disable their unit combos
        self.cb_elev.toggled.connect(self.combo_elev.setEnabled)
        self.cb_speed.toggled.connect(self.combo_speed.setEnabled)
        self.cb_slope.toggled.connect(self.combo_slope.setEnabled)
        
        content_layout.addWidget(group)
        
        # Right Group Box (Live Preview)
        preview_group = QGroupBox(tr("Settings Preview"))
        preview_vbox = QVBoxLayout(preview_group)
        
        self.preview_card = QFrame()
        self.preview_card.setObjectName("previewCardFrame")
        self.preview_card.setMinimumWidth(180)
        self.preview_card.setMinimumHeight(100)
        self.preview_card.setStyleSheet("""
            QFrame#previewCardFrame {
                background-color: rgba(30, 30, 30, 210);
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 6px;
            }
            QLabel {
                color: white;
            }
        """)
        
        card_layout = QVBoxLayout(self.preview_card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        card_layout.addWidget(self.preview_label)
        
        preview_vbox.addWidget(self.preview_card)
        preview_vbox.addStretch()
        
        content_layout.addWidget(preview_group)
        main_layout.addLayout(content_layout)
        
        # Load settings
        self.load_settings()
        
        # Connect settings change signals to update_preview slot
        self.cb_time.toggled.connect(self.update_preview)
        self.cb_elev.toggled.connect(self.update_preview)
        self.combo_elev.currentIndexChanged.connect(self.update_preview)
        self.cb_speed.toggled.connect(self.update_preview)
        self.combo_speed.currentIndexChanged.connect(self.update_preview)
        self.cb_slope.toggled.connect(self.update_preview)
        self.combo_slope.currentIndexChanged.connect(self.update_preview)
        
        # Initialize preview values
        self.update_preview()
        
        buttons_layout = QHBoxLayout()
        ok_btn = QPushButton(tr("OK"))
        cancel_btn = QPushButton(tr("Cancel"))
        ok_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addStretch()
        buttons_layout.addWidget(ok_btn)
        buttons_layout.addWidget(cancel_btn)
        main_layout.addLayout(buttons_layout)

        
    def update_preview(self):
        show_time = self.cb_time.isChecked()
        show_elev = self.cb_elev.isChecked()
        show_speed = self.cb_speed.isChecked()
        show_slope = self.cb_slope.isChecked()
        
        unit_elev = self.combo_elev.currentText()
        unit_speed = self.combo_speed.currentText()
        unit_slope = self.combo_slope.currentText()
        
        # Mock values for the preview card based on selected units
        elev_str = "421.6 ft" if unit_elev == "ft" else "128.5 m"
        
        if unit_speed == "m/s":
            speed_str = "7.0 m/s"
        elif unit_speed == "mph":
            speed_str = "15.7 mph"
        else:
            speed_str = "25.3 km/h"
            
        slope_str = "5.2 %" if unit_slope == "%" else "3.0 °"
        
        html = ["<div style='line-height: 1.2;'>"]
        html.append(f"<div style='color: #4CAF50; font-weight: bold;'>ColorGPX Track</div>")
        html.append("<div style='border-top: 1px solid rgba(255, 255, 255, 60); margin-top: 3px; margin-bottom: 3px;'></div>")
        html.append("<table style='color: white; font-family: sans-serif; font-size: 11px;'>")
        
        has_any = False
        if show_time:
            html.append(f"<tr><td>{tr('Time')}:</td><td style='padding-left: 10px;'>2026-07-27 14:15:30</td></tr>")
            has_any = True
        if show_elev:
            html.append(f"<tr><td>{tr('Elevation')}:</td><td style='padding-left: 10px;'>{elev_str}</td></tr>")
            has_any = True
        if show_speed:
            html.append(f"<tr><td>{tr('Speed')}:</td><td style='padding-left: 10px;'>{speed_str}</td></tr>")
            has_any = True
        if show_slope:
            html.append(f"<tr><td>{tr('Slope')}:</td><td style='padding-left: 10px;'>{slope_str}</td></tr>")
            has_any = True
            
        html.append("</table></div>")
        
        if not has_any:
            self.preview_label.setText(f"<div style='color: #888888; font-family: sans-serif; font-size: 11px; padding: 10px;'>{tr('No items selected')}</div>")
        else:
            self.preview_label.setText("".join(html))
        
        self.preview_card.adjustSize()

    def load_settings(self):
        settings = QgsSettings()
        self.cb_time.setChecked(settings.value("ColorGPX/hover_show_time", True, type=bool))
        self.cb_elev.setChecked(settings.value("ColorGPX/hover_show_elevation", True, type=bool))
        self.cb_speed.setChecked(settings.value("ColorGPX/hover_show_speed", True, type=bool))
        self.cb_slope.setChecked(settings.value("ColorGPX/hover_show_slope", True, type=bool))
        
        self.combo_elev.setCurrentText(settings.value("ColorGPX/hover_unit_elevation", "m", type=str))
        self.combo_speed.setCurrentText(settings.value("ColorGPX/hover_unit_speed", "km/h", type=str))
        self.combo_slope.setCurrentText(settings.value("ColorGPX/hover_unit_slope", "°", type=str))
        
    def save_settings(self):
        settings = QgsSettings()
        settings.setValue("ColorGPX/hover_show_time", self.cb_time.isChecked())
        settings.setValue("ColorGPX/hover_show_elevation", self.cb_elev.isChecked())
        settings.setValue("ColorGPX/hover_show_speed", self.cb_speed.isChecked())
        settings.setValue("ColorGPX/hover_show_slope", self.cb_slope.isChecked())
        
        settings.setValue("ColorGPX/hover_unit_elevation", self.combo_elev.currentText())
        settings.setValue("ColorGPX/hover_unit_speed", self.combo_speed.currentText())
        settings.setValue("ColorGPX/hover_unit_slope", self.combo_slope.currentText())
        self.accept()


class ColorGPXHoverLayerDialog(QDialog):
    """启用悬浮追踪工具时弹出，让用户选择固定追踪的向量图层。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Select Tracking Layer"))
        self.setMinimumWidth(320)
        self._selected_layer = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(tr("Available Layers")))
        self.combo = QComboBox()
        layout.addWidget(self.combo)

        # 填充所有向量图层
        self._layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.LayerType.VectorLayer:
                self._layers.append(layer)
                self.combo.addItem(layer.name(), layer)

        if not self._layers:
            layout.addWidget(QLabel(tr("No vector layers found in the project.")))

        # ---- 操作提示 ----
        tip_label = QLabel(tr("💡 Tip:\nLock position info: Left-click.\nUnlock position: Right-click / click blank area."))
        tip_label.setStyleSheet("color: #333333; font-size: 12px; padding: 5px 0;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_start = QPushButton(tr("Start Tracking"))
        self.btn_start.setEnabled(bool(self._layers))
        btn_cancel = QPushButton(tr("Cancel"))
        self.btn_start.clicked.connect(self._on_start)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _on_start(self):
        idx = self.combo.currentIndex()
        if idx >= 0:
            self._selected_layer = self.combo.itemData(idx)
        self.accept()

    def selected_layer(self):
        return self._selected_layer


class ColorGPXHoverMapTool(QgsMapTool):
    def __init__(self, canvas, hover_widget, tracked_layer):
        super().__init__(canvas)
        self.hover_widget = hover_widget
        self.tracked_layer = tracked_layer
        # 记录上一次吸附的 canvas 像素坐标，用于防抖
        self._last_snap_pixel = None
        # 用于在地图上标识吸附点的定位图层/图标
        self.marker = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 固定参数（Pin）相关的状态变量
        self.is_pinned = False
        self.pinned_feat = None
        self.pinned_snap_point = None
        self.pinned_snap_pixel = None
        self.pinned_interpolation_ratio = 0.0
        
        # 用于临时暂存当前 hover 探查到的要素与位置（点击时若在此范围内则固定它）
        self._last_detected_feat = None
        self._last_detected_snap_point = None
        self._last_detected_snap_pixel = None
        self._last_detected_interpolation_ratio = 0.0

    def canvasMoveEvent(self, event):
        layer = self.tracked_layer
        if not layer or not layer.isValid():
            self.hover_widget.hide()
            if self.marker:
                self.marker.hide()
            return

        map_point = self.toMapCoordinates(event.pos())  # Canvas CRS

        canvas_crs = self.canvas().mapSettings().destinationCrs()
        layer_crs = layer.crs()
        same_crs = canvas_crs == layer_crs

        # Build CRS transforms only when needed
        transform = None        # Layer CRS  →  Canvas CRS
        transform_to_layer = None  # Canvas CRS →  Layer CRS
        if not same_crs:
            try:
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                transform_to_layer = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            except Exception:  # nosec B110
                pass  # keep as None → fall back to no-transform path

        search_radius = self.canvas().mapUnitsPerPixel() * 15  # Canvas CRS units

        # ---- Build feature-query rect in Layer CRS ----
        rect_canvas = QgsRectangle(
            map_point.x() - search_radius, map_point.y() - search_radius,
            map_point.x() + search_radius, map_point.y() + search_radius
        )
        if transform_to_layer:
            try:
                rect_layer = transform_to_layer.transformBoundingBox(rect_canvas)
            except Exception:
                rect_layer = rect_canvas
        else:
            rect_layer = rect_canvas

        request = QgsFeatureRequest().setFilterRect(rect_layer)
        features = list(layer.getFeatures(request))

        # ---- Transform cursor to Layer CRS for distance/snap calculations ----
        # (We NEVER modify feature geometries – they stay in Layer CRS at all times.)
        if transform_to_layer:
            try:
                cursor_layer = transform_to_layer.transform(map_point)
            except Exception:
                cursor_layer = map_point
        else:
            cursor_layer = map_point

        if not features:
            self._last_detected_feat = None
            self._last_detected_snap_point = None
            self._last_detected_snap_pixel = None
            self._last_detected_interpolation_ratio = 0.0
            if not self.is_pinned:
                self.hover_widget.hide()
                self._last_snap_pixel = None
                if self.marker:
                    self.marker.hide()
            return

        min_dist = float('inf')
        closest_feat = None

        # All distance work in Layer CRS (cursor_layer is already in Layer CRS)
        geom_point_layer = QgsGeometry.fromPointXY(cursor_layer)
        for feat in features:
            geom = feat.geometry()  # Layer CRS – read only, never modified
            if geom.isNull():
                continue
            dist = geom.distance(geom_point_layer)
            if dist < min_dist:
                min_dist = dist
                closest_feat = feat

        # Accept the closest feature if it was inside the query rect;
        # the rect already acts as our proximity gate (no raw min_dist threshold
        # needed since units could differ between Layer CRS and Canvas CRS).
        if closest_feat:
            geom = closest_feat.geometry()  # Layer CRS, read-only
            wkb_type = geom.wkbType()

            interpolation_ratio = 0.0
            if QgsWkbTypes.geometryType(wkb_type) == QgsWkbTypes.GeometryType.PointGeometry:
                # 点图层：直接用点坐标（Layer CRS）
                snap_layer_point = geom.asPoint()
            else:
                # 线/面图层：在 Layer CRS 中找最近投影点
                (_, snap_layer_point, _, _) = geom.closestSegmentWithContext(cursor_layer)

                # 计算沿线段的插值比率 t（无量纲，与 CRS 无关）
                polyline = geom.asPolyline()
                if len(polyline) >= 2:
                    v1 = polyline[0]
                    v2 = polyline[-1]
                    dx = v2.x() - v1.x()
                    dy = v2.y() - v1.y()
                    seg_len_sq = dx * dx + dy * dy
                    if seg_len_sq > 0:
                        t = ((snap_layer_point.x() - v1.x()) * dx + (snap_layer_point.y() - v1.y()) * dy) / seg_len_sq
                        interpolation_ratio = max(0.0, min(1.0, t))

            # ---- 把 Layer CRS 吸附点正投到 Canvas CRS 供 marker 使用 ----
            if transform:
                try:
                    snap_map_point = transform.transform(snap_layer_point)
                except Exception:
                    snap_map_point = snap_layer_point  # fallback: same CRS or transform failed
            else:
                snap_map_point = snap_layer_point  # 同 CRS，无需转换

            # ---- 吸附像素坐标（Canvas 局部坐标）----
            snap_canvas_pt = self.toCanvasCoordinates(
                QgsPointXY(snap_map_point.x(), snap_map_point.y())
            )
            snap_pixel = QPoint(int(snap_canvas_pt.x()), int(snap_canvas_pt.y()))

            # 暂存当前探测到的数值
            self._last_detected_feat = closest_feat
            self._last_detected_snap_point = snap_map_point  # Canvas CRS
            self._last_detected_snap_pixel = snap_pixel
            self._last_detected_interpolation_ratio = interpolation_ratio

            # 如果没有固定，正常进行悬浮窗及定位标的渲染更新
            if not self.is_pinned:
                # ---- 更新或创建吸附定位图标 ----
                if not self.marker:
                    self.marker = QgsVertexMarker(self.canvas())
                    icon_type = QgsVertexMarker.IconType.ICON_CROSS if hasattr(QgsVertexMarker, 'IconType') else QgsVertexMarker.ICON_CROSS
                    self.marker.setIconType(icon_type)  # 十字准星定位标
                    self.marker.setIconSize(12)
                    self.marker.setPenWidth(2)

                self.marker.setColor(QColor(235, 79, 79))  # 滑动状态：亮红色
                self.marker.setCenter(QgsPointXY(snap_map_point.x(), snap_map_point.y()))
                self.marker.show()

                # 防抖：与上次吸附位置差 > 3px 才移动鼠标
                if self._last_snap_pixel is None or (
                    abs(snap_pixel.x() - self._last_snap_pixel.x()) > 3 or
                    abs(snap_pixel.y() - self._last_snap_pixel.y()) > 3
                ):
                    global_snap = self.canvas().mapToGlobal(snap_pixel)
                    QCursor.setPos(global_snap)
                    self._last_snap_pixel = snap_pixel

                # ---- 悬浮窗位置（基于吸附点，不跟鼠标原始位置）----
                self.hover_widget.update_info(layer, closest_feat, interpolation_ratio)

                local_pos = snap_pixel + QPoint(8, 8)

                # 使用 sizeHint() 动态获取渲染后的真实尺寸
                self.hover_widget.adjustSize()
                size_hint = self.hover_widget.sizeHint()
                w_w = size_hint.width()
                w_h = size_hint.height()

                # 边界检查：防止悬浮窗超出 canvas 区域（全部使用 Canvas 局部坐标）
                canvas_size = self.canvas().size()

                if local_pos.x() + w_w > canvas_size.width():
                    local_pos.setX(snap_pixel.x() - w_w - 8)
                if local_pos.y() + w_h > canvas_size.height():
                    local_pos.setY(snap_pixel.y() - w_h - 8)
                if local_pos.x() < 0:
                    local_pos.setX(0)
                if local_pos.y() < 0:
                    local_pos.setY(0)

                self.hover_widget.move(local_pos)
                self.hover_widget.show()
                self.hover_widget.raise_()
        else:
            self._last_detected_feat = None
            self._last_detected_snap_point = None
            self._last_detected_snap_pixel = None
            self._last_detected_interpolation_ratio = 0.0
            if not self.is_pinned:
                self.hover_widget.hide()
                self._last_snap_pixel = None
                if self.marker:
                    self.marker.hide()

    def canvasPressEvent(self, event):
        layer = self.tracked_layer
        if not layer or not layer.isValid():
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # 鼠标左键点击
            if self._last_detected_feat and self._last_detected_snap_point:
                # 1. 处于吸附范围内，且点击了轨迹点：锁定固定此点
                self.is_pinned = True
                self.pinned_feat = self._last_detected_feat
                self.pinned_snap_point = self._last_detected_snap_point
                self.pinned_snap_pixel = self._last_detected_snap_pixel
                self.pinned_interpolation_ratio = self._last_detected_interpolation_ratio

                # 定位图标外观更新：转为绿色表示“锁定”
                if not self.marker:
                    self.marker = QgsVertexMarker(self.canvas())
                    icon_type = QgsVertexMarker.IconType.ICON_CROSS if hasattr(QgsVertexMarker, 'IconType') else QgsVertexMarker.ICON_CROSS
                    self.marker.setIconType(icon_type)  # 十字准星定位标
                    self.marker.setIconSize(12)
                    self.marker.setPenWidth(2)
                self.marker.setColor(QColor(76, 175, 80))  # 绿色
                self.marker.setCenter(QgsPointXY(self.pinned_snap_point.x(), self.pinned_snap_point.y()))
                self.marker.show()

                # 固定悬浮窗内容与位置
                self.hover_widget.update_info(layer, self.pinned_feat, self.pinned_interpolation_ratio)

                local_pos = self.pinned_snap_pixel + QPoint(8, 8)

                self.hover_widget.adjustSize()
                size_hint = self.hover_widget.sizeHint()
                w_w = size_hint.width()
                w_h = size_hint.height()

                # 边界检查：防止悬浮窗超出 canvas 区域（全部使用 Canvas 局部坐标）
                canvas_size = self.canvas().size()

                if local_pos.x() + w_w > canvas_size.width():
                    local_pos.setX(self.pinned_snap_pixel.x() - w_w - 8)
                if local_pos.y() + w_h > canvas_size.height():
                    local_pos.setY(self.pinned_snap_pixel.y() - w_h - 8)
                if local_pos.x() < 0:
                    local_pos.setX(0)
                if local_pos.y() < 0:
                    local_pos.setY(0)

                self.hover_widget.move(local_pos)
                self.hover_widget.show()
                self.hover_widget.raise_()
            else:
                # 2. 点击空白区域（距离轨迹较远）：解除固定
                self.release_pin()
                self.update_hover_for_event(event)
        elif event.button() == Qt.MouseButton.RightButton:
            # 鼠标右键点击：解除固定
            self.release_pin()
            self.update_hover_for_event(event)

    def release_pin(self):
        self.is_pinned = False
        self.pinned_feat = None
        self.pinned_snap_point = None
        self.pinned_snap_pixel = None
        self.pinned_interpolation_ratio = 0.0
        if self.marker:
            self.marker.setColor(QColor(235, 79, 79))  # 恢复成滑动的亮红色

    def update_hover_for_event(self, event):
        # 触发正常的移动检查，使悬浮窗和图标瞬间定位到最新鼠标位置
        self.canvasMoveEvent(event)

    def activate(self):
        super().activate()
        try:
            self.canvas().extentsChanged.connect(self.update_pinned_position)
        except Exception:  # nosec B110
            pass

    def deactivate(self):
        try:
            self.canvas().extentsChanged.disconnect(self.update_pinned_position)
        except Exception:  # nosec B110
            pass
        self.hover_widget.hide()
        self._last_snap_pixel = None
        self.is_pinned = False
        self.pinned_feat = None
        self.pinned_snap_point = None
        self.pinned_snap_pixel = None
        self.pinned_interpolation_ratio = 0.0
        self._last_detected_feat = None
        self._last_detected_snap_point = None
        self._last_detected_snap_pixel = None
        self._last_detected_interpolation_ratio = 0.0
        # 清理地图上的定位标识
        if self.marker:
            self.canvas().scene().removeItem(self.marker)
            self.marker = None
        super().deactivate()

    def update_pinned_position(self):
        """当画布平移或缩放导致 extents 变化时，重新计算固定点的像素位置并移动悬浮窗"""
        if self.is_pinned and self.pinned_snap_point:
            # 根据当前的地图缩放与平移，将固定的地图坐标重新映射为 canvas 局部像素坐标
            snap_canvas_pt = self.toCanvasCoordinates(
                QgsPointXY(self.pinned_snap_point.x(), self.pinned_snap_point.y())
            )
            self.pinned_snap_pixel = QPoint(int(snap_canvas_pt.x()), int(snap_canvas_pt.y()))

            local_pos = self.pinned_snap_pixel + QPoint(8, 8)

            self.hover_widget.adjustSize()
            size_hint = self.hover_widget.sizeHint()
            w_w = size_hint.width()
            w_h = size_hint.height()

            # 边界检查
            canvas_size = self.canvas().size()

            if local_pos.x() + w_w > canvas_size.width():
                local_pos.setX(self.pinned_snap_pixel.x() - w_w - 8)
            if local_pos.y() + w_h > canvas_size.height():
                local_pos.setY(self.pinned_snap_pixel.y() - w_h - 8)
            if local_pos.x() < 0:
                local_pos.setX(0)
            if local_pos.y() < 0:
                local_pos.setY(0)

            self.hover_widget.move(local_pos)
            self.hover_widget.raise_()


class ColorGPX:

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None
        self.hover_widget = None
        self.hover_action = None
        self.hover_settings_action = None
        self.hover_map_tool = None

        # Fetch locale and sanitize to prevent path traversal
        locale_name = QgsSettings().value("locale/userLocale", QLocale.system().name())
        if locale_name is not None:
            locale_name = str(locale_name)
        else:
            locale_name = "en"
        if not re.match(r"^[a-zA-Z0-9_\-]+$", locale_name):
            locale_name = "en"

        # Normalize QGIS locale format (e.g. zh-Hans → zh_CN, zh-Hant → zh_TW)
        _locale_map = {
            "zh-hans": "zh_CN",
            "zh-hant": "zh_TW",
            "zh-cn":   "zh_CN",
            "zh-tw":   "zh_TW",
        }
        locale_candidates = []
        _key = locale_name.lower()
        if _key in _locale_map:
            locale_candidates.append(_locale_map[_key])
        # Also try replacing hyphens with underscores (e.g. zh-CN → zh_CN)
        locale_candidates.append(locale_name.replace("-", "_"))
        # Also try just the language prefix (e.g. zh_CN → zh)
        locale_candidates.append(locale_name.split("_")[0].split("-")[0])

        self.translator = QTranslator()
        i18n_dir = os.path.join(os.path.dirname(__file__), "i18n")
        for candidate in locale_candidates:
            if self.translator.load(f"ColorGPX_{candidate}", i18n_dir):
                QCoreApplication.installTranslator(self.translator)
                break

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icons_Component", "Generate_ColorGPX.svg")
        self.action = QAction(QIcon(icon_path), tr("GPX → ColorGPX"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        hover_icon_path = os.path.join(os.path.dirname(__file__), "icons_Component", "ColorGPX_Mouse_Prompt.svg")
        self.hover_action = QAction(QIcon(hover_icon_path), tr("Hover Track Info"), self.iface.mainWindow())
        self.hover_action.setCheckable(True)
        self.hover_action.triggered.connect(self.toggle_hover_tool)

        settings_icon_path = os.path.join(os.path.dirname(__file__), "icons_Component", "Mouse_Prompt_Settings.svg")
        self.hover_settings_action = QAction(QIcon(settings_icon_path), tr("Hover Settings"), self.iface.mainWindow())
        self.hover_settings_action.triggered.connect(self.show_hover_settings)

        self.iface.addPluginToVectorMenu("ColorGPX", self.action)

        # 创建独立的可移动工具栏
        self.toolbar = self.iface.addToolBar(tr("ColorGPX"))
        self.toolbar.setObjectName("ColorGPX")
        self.toolbar.addAction(self.action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.hover_action)
        self.toolbar.addAction(self.hover_settings_action)

        self.iface.mapCanvas().mapToolSet.connect(self.on_map_tool_changed)

    def unload(self):
        try:
            self.iface.mapCanvas().mapToolSet.disconnect(self.on_map_tool_changed)
        except Exception:  # nosec B110
            pass

        if self.hover_map_tool and self.iface.mapCanvas().mapTool() == self.hover_map_tool:
            self.iface.mapCanvas().unsetMapTool(self.hover_map_tool)

        if self.hover_map_tool:
            del self.hover_map_tool
            self.hover_map_tool = None
        if self.hover_widget:
            self.hover_widget.setParent(None)
            self.hover_widget.deleteLater()
            self.hover_widget = None

        # Uninstall translator to clean up memory
        QCoreApplication.removeTranslator(self.translator)
        self.iface.removePluginVectorMenu("ColorGPX", self.action)
        if self.toolbar:
            self.toolbar.clear()
            del self.toolbar

    def toggle_hover_tool(self, checked):
        if checked:
            # 每次启用都弹出图层选择对话框
            dlg = ColorGPXHoverLayerDialog(self.iface.mainWindow())
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected_layer():
                # 用户取消 → 恢复按钮未选中状态
                if self.hover_action:
                    self.hover_action.setChecked(False)
                return

            tracked_layer = dlg.selected_layer()

            # 销毁旧的 map tool（可能追踪不同图层）
            if self.hover_map_tool:
                if self.iface.mapCanvas().mapTool() == self.hover_map_tool:
                    self.iface.mapCanvas().unsetMapTool(self.hover_map_tool)
                del self.hover_map_tool
                self.hover_map_tool = None

            if not self.hover_widget:
                self.hover_widget = ColorGPXHoverWidget(self.iface.mapCanvas())

            self.hover_map_tool = ColorGPXHoverMapTool(
                self.iface.mapCanvas(), self.hover_widget, tracked_layer
            )
            self.iface.mapCanvas().setMapTool(self.hover_map_tool)
        else:
            if self.hover_map_tool and self.iface.mapCanvas().mapTool() == self.hover_map_tool:
                self.iface.mapCanvas().unsetMapTool(self.hover_map_tool)
            if self.hover_widget:
                self.hover_widget.hide()

    def on_map_tool_changed(self, new_tool):
        is_hover_tool = (new_tool == self.hover_map_tool) if self.hover_map_tool else False
        if self.hover_action:
            self.hover_action.setChecked(is_hover_tool)
        if not is_hover_tool and self.hover_widget:
            self.hover_widget.hide()

    def show_hover_settings(self):
        dialog = ColorGPXHoverSettingsDialog(self.iface.mainWindow())
        dialog.exec()

    def run(self):
        dialog = ColorGPXDialog(self.iface.mainWindow())

        def on_ok():
            layer = dialog.get_selected_layer()
            if not layer:
                QMessageBox.warning(None, tr("Error"), tr("Please select a GPX track_points layer"))
                return

            elev_name = dialog.elev_field.text().strip() or "ELEV"
            speed_name = dialog.speed_field.text().strip() or "speed"
            slope_name = dialog.slope_field.text().strip() or "Slope"
            output_name = dialog.output_name.text().strip() or "ColorGPX"
            if dialog.rb_speed.isChecked():
                render_type = "speed"
            elif dialog.rb_elevation.isChecked():
                render_type = "elevation"
            else:
                render_type = "slope"
            if dialog.rb_point.isChecked():
                render_mode = "point"
            elif dialog.rb_gradient.isChecked():
                render_mode = "gradient_line"
            else:
                render_mode = "line"
            color_ramp_name = dialog.ramp_display.text()
            output_path = dialog.output_path.text().strip()
            reverse_ramp = dialog.reverse_cb.isChecked()
            has_speed = dialog.has_speed

            # Fetch selected units
            elev_unit = dialog.elev_unit_combo.currentText()
            slope_unit = dialog.slope_unit_combo.currentText()
            speed_unit = dialog.speed_unit_combo.currentText()

            self.create_colored_gpx(layer, output_name, elev_name, speed_name, slope_name,
                                    render_type, render_mode, color_ramp_name, output_path,
                                    dialog.progress_bar, reverse_ramp, simulate_speed=not has_speed,
                                    elev_unit=elev_unit, speed_unit=speed_unit, slope_unit=slope_unit)
            QTimer.singleShot(500, dialog.accept)

        dialog.processing_callback = on_ok
        dialog.exec()

    def create_colored_gpx(self, layer, output_name, elev_name, speed_name, slope_name,
                           render_type, render_mode="point", color_ramp_name="", output_path="",
                           progress_bar=None, reverse_ramp=False, simulate_speed=False,
                           elev_unit="m", speed_unit="m/s", slope_unit="°"):
        source = layer.source()
        gpx_file = source.split("|")[0]

        if not os.path.exists(gpx_file):
            self.iface.messageBar().pushCritical("ColorGPX", tr("Please select a track_points layer from GPX data!"))
            return

        # Format units and field names as requested, e.g. slope-% or speed-km/h
        elev_field_name = f"{elev_name}-{elev_unit}"
        speed_field_name = f"{speed_name}-{speed_unit}"
        slope_field_name = f"{slope_name}-{slope_unit}"

        # ---- process ---- #
        def _update_progress(current, total):
            if progress_bar:
                progress_bar.setMaximum(total)
                progress_bar.setValue(current)
                progress_bar.repaint()

        if render_mode == "point":
            out = process_points(gpx_file, elev_field_name, speed_field_name, slope_field_name,
                                 _update_progress, simulate_speed, elev_unit, speed_unit, slope_unit)
            apply_renderer = apply_point_renderer
        elif render_mode == "gradient_line":
            out = process_lines(gpx_file, elev_field_name, speed_field_name, slope_field_name,
                                _update_progress, simulate_speed, elev_unit, speed_unit, slope_unit)
            apply_renderer = apply_gradient_renderer
        else:
            out = process_lines(gpx_file, elev_field_name, speed_field_name, slope_field_name,
                                _update_progress, simulate_speed, elev_unit, speed_unit, slope_unit)
            apply_renderer = apply_line_renderer
        out.setName(output_name)
        QgsProject.instance().addMapLayer(out)

        if render_type == "speed":
            field_to_render = speed_field_name
        elif render_type == "elevation":
            field_to_render = elev_field_name
        else:
            field_to_render = slope_field_name
        if render_mode == "gradient_line":
            apply_renderer(out, field_to_render, color_ramp_name, reverse_ramp, render_type)
        else:
            apply_renderer(out, field_to_render, color_ramp_name, reverse_ramp)

        # ---- save to file ---- #
        if output_path:
            ext = os.path.splitext(output_path)[1].lower()
            driver_map = {".geojson": "GeoJSON", ".shp": "ESRI Shapefile", ".gpkg": "GPKG"}
            driver_name = driver_map.get(ext, "GPKG")

            try:
                result = QgsVectorFileWriter.writeAsVectorFormat(
                    out, output_path, "UTF-8", out.crs(), driver_name
                )
                if isinstance(result, (list, tuple)):
                    error_code, error_msg = result[0], (result[1] if len(result) > 1 else "")
                else:
                    error_code, error_msg = result, ""

                if error_code == QgsVectorFileWriter.WriterError.NoError:
                    self.iface.messageBar().pushSuccess(
                        tr("Saved"), f"{output_path}"
                    )
                else:
                    self.iface.messageBar().pushCritical(
                        tr("Save failed"), error_msg or str(error_code)
                    )
            except Exception as e:
                self.iface.messageBar().pushCritical(tr("Save failed"), str(e))

        # Localize render mode label dynamically
        mode_label_tr = tr("point") if render_mode == "point" else (tr("gradient_line") if render_mode == "gradient_line" else tr("line"))
        msg = tr("{} created ({} mode)").format(output_name, mode_label_tr)
        self.iface.messageBar().pushSuccess(tr("Success"), msg)
