from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout,
                                QLabel, QComboBox, QLineEdit, QPushButton,
                                 QMessageBox, QFileDialog, QTextEdit, QProgressBar, QMenu,
                                 QListWidget, QListWidgetItem, QCheckBox, QSizePolicy, QApplication,
                                 QSlider, QWidget)
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor
from qgis.PyQt.QtCore import Qt, QSize, QTimer, QTranslator, QLocale, QCoreApplication
from qgis.core import *
from qgis.PyQt.QtWidgets import QRadioButton, QButtonGroup
import os
import re

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405



def tr(text, disambiguation=None):
    """Translate text using QCoreApplication with fallback context."""
    res = QCoreApplication.translate("ColorGPX", text, disambiguation)
    if res == text:
        res = QCoreApplication.translate("ColorGPXDialog", text, disambiguation)
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
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.rb_point)
        mode_row.addWidget(self.rb_line)
        mode_row.addWidget(self.rb_gradient)
        mode_row.addStretch()
        left_layout.addLayout(mode_row)

        left_layout.addWidget(QLabel(tr("Render field:")))
        self.render_type_group = QButtonGroup()
        self.rb_speed = QRadioButton(tr("Speed"))
        self.rb_elevation = QRadioButton(tr("Elevation"))
        self.rb_slope = QRadioButton(tr("Slope"))
        self.render_type_group.addButton(self.rb_speed)
        self.render_type_group.addButton(self.rb_elevation)
        self.render_type_group.addButton(self.rb_slope)
        self.rb_speed.setChecked(True)
        type_row = QHBoxLayout()
        
        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)
        speed_layout.addWidget(self.rb_speed)

        self.speed_warn_btn = QPushButton()
        self._icon_warn_yellow = QIcon(os.path.join(os.path.dirname(__file__), "icons", "warning_yellow.svg"))
        self._icon_warn_red = QIcon(os.path.join(os.path.dirname(__file__), "icons", "warning_red.svg"))
        self.speed_warn_btn.setIcon(self._icon_warn_yellow)
        self.speed_warn_btn.setIconSize(QSize(16, 16))
        self.speed_warn_btn.setStyleSheet("border: none; background: transparent;")
        self.speed_warn_btn.setToolTip(tr("Current speed is simulated speed. Click for more details."))
        self.speed_warn_btn.setVisible(False)
        self.speed_warn_btn.clicked.connect(self._show_speed_warning)
        speed_layout.addWidget(self.speed_warn_btn)
        
        type_row.addWidget(self.rb_elevation)
        type_row.addWidget(self.rb_slope)
        type_row.addLayout(speed_layout)
        type_row.addStretch()
        left_layout.addLayout(type_row)

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

    def _on_layer_changed(self):
        layer = self.get_selected_layer()
        if not layer:
            self.has_speed = False
            self.speed_warn_btn.setVisible(False)
            self._set_render_fields_enabled(True)
            return

        has_ele, has_time, has_speed = self._check_gpx_has_data(layer)
        self.has_speed = has_speed

        # No elevation/time means this layer cannot be rendered by any field
        if not has_ele and not has_time:
            self._set_render_fields_enabled(False)
            self.speed_warn_btn.setIcon(self._icon_warn_red)
            self.speed_warn_btn.setToolTip(
                tr("This layer has no elevation or time data. All render fields are unavailable.")
            )
            self.speed_warn_btn.clicked.disconnect()
            self.speed_warn_btn.clicked.connect(self._show_no_data_warning)
            self.speed_warn_btn.setVisible(True)
        else:
            self._set_render_fields_enabled(True)
            if has_speed:
                self.speed_warn_btn.setVisible(False)
            else:
                self.speed_warn_btn.setIcon(self._icon_warn_yellow)
                self.speed_warn_btn.setToolTip(tr("Current speed is simulated speed. Click for more details."))
                self.speed_warn_btn.clicked.disconnect()
                self.speed_warn_btn.clicked.connect(self._show_speed_warning)
                self.speed_warn_btn.setVisible(True)

    def _set_render_fields_enabled(self, enabled: bool):
        """Enable or disable all render-field radio buttons."""
        self.rb_speed.setEnabled(enabled)
        self.rb_elevation.setEnabled(enabled)
        self.rb_slope.setEnabled(enabled)

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
                    if tag == "ele":
                        has_ele = True
                    elif tag == "time":
                        has_time = True
                    elif tag == "speed":
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


class ColorGPX:

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None

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
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "icon.svg")
        self.action = QAction(QIcon(icon_path), tr("GPX → ColorGPX"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToVectorMenu("ColorGPX", self.action)

        # 创建独立的可移动工具栏
        self.toolbar = self.iface.addToolBar(tr("ColorGPX"))
        self.toolbar.setObjectName("ColorGPX")
        self.toolbar.addAction(self.action)

    def unload(self):
        # Uninstall translator to clean up memory
        QCoreApplication.removeTranslator(self.translator)
        self.iface.removePluginVectorMenu("ColorGPX", self.action)
        if self.toolbar:
            del self.toolbar

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
            self.create_colored_gpx(layer, output_name, elev_name, speed_name, slope_name,
                                    render_type, render_mode, color_ramp_name, output_path,
                                    dialog.progress_bar, reverse_ramp, simulate_speed=not has_speed)
            QTimer.singleShot(500, dialog.accept)

        dialog.processing_callback = on_ok
        dialog.exec()

    def create_colored_gpx(self, layer, output_name, elev_name, speed_name, slope_name,
                           render_type, render_mode="point", color_ramp_name="", output_path="",
                           progress_bar=None, reverse_ramp=False, simulate_speed=False):
        source = layer.source()
        gpx_file = source.split("|")[0]

        if not os.path.exists(gpx_file):
            self.iface.messageBar().pushCritical("ColorGPX", tr("Please select a track_points layer from GPX data!"))
            return

        # ---- process ---- #
        def _update_progress(current, total):
            if progress_bar:
                progress_bar.setMaximum(total)
                progress_bar.setValue(current)
                progress_bar.repaint()

        if render_mode == "point":
            out = process_points(gpx_file, elev_name, speed_name, slope_name, _update_progress, simulate_speed)
            apply_renderer = apply_point_renderer
        elif render_mode == "gradient_line":
            out = process_lines(gpx_file, elev_name, speed_name, slope_name, _update_progress, simulate_speed)
            apply_renderer = apply_gradient_renderer
        else:
            out = process_lines(gpx_file, elev_name, speed_name, slope_name, _update_progress, simulate_speed)
            apply_renderer = apply_line_renderer
        out.setName(output_name)
        QgsProject.instance().addMapLayer(out)

        if render_type == "speed":
            field_to_render = speed_name
        elif render_type == "elevation":
            field_to_render = elev_name
        else:
            field_to_render = slope_name
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
