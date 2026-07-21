from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout,
                                QLabel, QComboBox, QLineEdit, QPushButton,
                                 QMessageBox, QFileDialog, QTextEdit, QProgressBar, QMenu,
                                 QListWidget, QListWidgetItem, QCheckBox, QSizePolicy, QApplication,
                                 QSlider, QWidget)
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor
from qgis.PyQt.QtCore import Qt, QSize, QTimer
from qgis.core import *
from qgis.PyQt.QtWidgets import QRadioButton, QButtonGroup
import os


def tr(zh, en):
    """Return Chinese or English text based on QGIS locale."""
    locale = QgsSettings().value("locale/userLocale", "")
    return zh if locale.startswith("zh") else en


from .point_processor import process_points
from .point_renderer import apply_renderer as apply_point_renderer
from .line_processor import process_lines
from .line_renderer import apply_renderer as apply_line_renderer
from .gradient_line_renderer import apply_gradient_renderer


class ColorGPXDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ColorGPX - 参数设置", "ColorGPX - Settings"))
        self.setMinimumWidth(500)

        main_layout = QVBoxLayout(self)

        # ---- left panel ---- #
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel(tr("输入图层 (GPX track_points):", "Input layer (GPX track_points):")))
        self.layer_combo = QComboBox()
        self.refresh_layers()
        left_layout.addWidget(self.layer_combo)

        left_layout.addWidget(QLabel(tr("渲染方式:", "Render mode:")))
        self.render_mode_group = QButtonGroup()
        self.rb_point = QRadioButton(tr("点风格", "Point"))
        self.rb_line = QRadioButton(tr("线风格", "Line"))
        self.rb_gradient = QRadioButton(tr("渐变线", "Gradient Line"))
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

        left_layout.addWidget(QLabel(tr("渲染字段类型:", "Render field:")))
        self.render_type_group = QButtonGroup()
        self.rb_speed = QRadioButton(tr("速度", "Speed"))
        self.rb_elevation = QRadioButton(tr("高程", "Elevation"))
        self.rb_slope = QRadioButton(tr("坡度", "Slope"))
        self.render_type_group.addButton(self.rb_speed)
        self.render_type_group.addButton(self.rb_elevation)
        self.render_type_group.addButton(self.rb_slope)
        self.rb_speed.setChecked(True)
        type_row = QHBoxLayout()
        type_row.addWidget(self.rb_speed)
        type_row.addWidget(self.rb_elevation)
        type_row.addWidget(self.rb_slope)
        type_row.addStretch()
        left_layout.addLayout(type_row)

        left_layout.addWidget(QLabel(tr("色带:", "Color ramp:")))
        ramp_row = QHBoxLayout()
        self.ramp_preview = QLabel()
        self.ramp_preview.setFixedSize(74, 22)
        ramp_row.addWidget(self.ramp_preview)
        self.ramp_display = QLineEdit()
        self.ramp_display.setReadOnly(True)
        ramp_row.addWidget(self.ramp_display, stretch=1)
        self.ramp_btn = QPushButton(tr("选择...", "Select..."))
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
        self.reverse_cb = QCheckBox(tr("反转色带", "Reverse ramp"))
        self.processing_callback = None
        self.reverse_cb.toggled.connect(self._update_ramp_preview)
        ramp_rev_row.addWidget(self.reverse_cb)
        ramp_rev_row.addStretch()
        left_layout.addLayout(ramp_rev_row)

        left_layout.addWidget(QLabel(tr("输出高度字段名:", "Elevation field name:")))
        self.elev_field = QLineEdit("ELEV")
        left_layout.addWidget(self.elev_field)

        left_layout.addWidget(QLabel(tr("输出速度字段名:", "Speed field name:")))
        self.speed_field = QLineEdit("speed")
        left_layout.addWidget(self.speed_field)

        left_layout.addWidget(QLabel(tr("输出坡度字段名:", "Slope field name:")))
        self.slope_field = QLineEdit("Slope")
        left_layout.addWidget(self.slope_field)

        # ---- output destination ---- #
        left_layout.addWidget(QLabel(tr("输出图层:", "Output layer:")))
        dest_layout = QHBoxLayout()
        self.output_name = QLineEdit("ColorGPX")
        dest_layout.addWidget(self.output_name, stretch=1)

        self.output_dest_btn = QPushButton("…")
        self.output_dest_btn.setFixedWidth(35)
        self.output_dest_menu = QMenu(self)
        self.output_dest_menu.addAction(
            tr("创建临时图层", "Temporary layer")
        ).triggered.connect(self._on_dest_temp)
        self.output_dest_menu.addAction(
            tr("保存到文件...", "Save to file...")
        ).triggered.connect(self._on_dest_file)
        self.output_dest_btn.setMenu(self.output_dest_menu)
        dest_layout.addWidget(self.output_dest_btn)
        left_layout.addLayout(dest_layout)

        self.output_path = QLineEdit()
        self.output_path.setVisible(False)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(tr("确定运行", "Run"))
        cancel_btn = QPushButton(tr("取消", "Cancel"))
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
        if QgsSettings().value("locale/userLocale", "").startswith("zh"):
            info_html = (
                '<html><body style="font-family:Microsoft YaHei,sans-serif;font-size:11px;color:#333;">'
                '<h3 style="margin:0 0 8px;color:#2c6b32;">ColorGPX</h3>'
                '<p style="margin:0 0 10px;line-height:1.5;">将GPX轨迹点按速度、高度或坡度（°）渲染为渐变色。</p>'
                '<hr>'
                '<h4 style="margin:8px 0 4px;">使用步骤</h4>'
                '<ol style="margin:2px 0;padding-left:18px;line-height:1.6;">'
                '<li>选择 GPX track_points 图层</li>'
                '<li>选择渲染方式（点 / 线 / 渐变线）</li>'
                '<li>选择渲染字段（速度 / 高度 / 坡度°）</li>'
                '<li>选择色带</li>'
                '<li>点击「确定运行」</li>'
                '</ol>'
                '<h4 style="margin:8px 0 4px;">保存文件</h4>'
                '<p style="margin:2px 0;line-height:1.5;">可选保存路径，支持 GeoJSON / GPKG / Shapefile 格式。</p>'
                '<p style="margin:8px 0 0;color:#888;font-size:10px;">作者：OpenQGIS</p>'
                '</body></html>'
            )
        else:
            info_html = (
                '<html><body style="font-family:Segoe UI,sans-serif;font-size:11px;color:#333;">'
                '<h3 style="margin:0 0 8px;color:#2c6b32;">ColorGPX</h3>'
                '<p style="margin:0 0 10px;line-height:1.5;">Render GPX track points as graduated colors by speed, elevation or slope (°).</p>'
                '<hr>'
                '<h4 style="margin:8px 0 4px;">How to use</h4>'
                '<ol style="margin:2px 0;padding-left:18px;line-height:1.6;">'
                '<li>Select a GPX track_points layer</li>'
                '<li>Choose render mode (Point / Line / Gradient)</li>'
                '<li>Choose render field (Speed / Elevation / Slope°)</li>'
                '<li>Choose a color ramp</li>'
                '<li>Click \u201cRun\u201d</li>'
                '</ol>'
                '<h4 style="margin:8px 0 4px;">Save</h4>'
                '<p style="margin:2px 0;line-height:1.5;">Optionally save to GeoJSON, GPKG or Shapefile.</p>'
                '<p style="margin:8px 0 0;color:#888;font-size:10px;">Author: OpenQGIS</p>'
                '</body></html>'
            )
        self.info_edit.setHtml(info_html)
        top_layout = QHBoxLayout()
        top_layout.addLayout(left_layout, stretch=1)
        top_layout.addWidget(self.info_edit, stretch=0)

        self.progress_bar = QProgressBar()

        main_layout.addLayout(top_layout, stretch=1)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(btn_layout)

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
            tr("保存图层", "Save layer"),
            "",
            tr("GeoJSON (*.geojson);;GPKG (*.gpkg);;Shapefile (*.shp);;所有文件 (*)", "GeoJSON (*.geojson);;GPKG (*.gpkg);;Shapefile (*.shp);;All files (*)")
        )
        if file_path:
            self.output_path.setText(file_path)

    def _pick_color_ramp(self):
        """Open a fixed-height dialog to pick a color ramp."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("选择色带", "Select Color Ramp"))
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
        ok_btn = QPushButton(tr("确定", "OK"))
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton(tr("取消", "Cancel"))
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


class ColorGPX:

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "icon.svg")
        self.action = QAction(QIcon(icon_path), tr("GPX → ColorGPX", "GPX → ColorGPX"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToVectorMenu("ColorGPX", self.action)

        # 创建独立的可移动工具栏
        self.toolbar = self.iface.addToolBar(tr("ColorGPX", "ColorGPX"))
        self.toolbar.setObjectName("ColorGPX")
        self.toolbar.addAction(self.action)

    def unload(self):
        self.iface.removePluginVectorMenu("ColorGPX", self.action)
        if self.toolbar:
            del self.toolbar

    def run(self):
        dialog = ColorGPXDialog(self.iface.mainWindow())

        def on_ok():
            layer = dialog.get_selected_layer()
            if not layer:
                QMessageBox.warning(None, tr("错误", "Error"), tr("请选择GPX的track_points图层", "Please select a GPX track_points layer"))
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
            self.create_colored_gpx(layer, output_name, elev_name, speed_name, slope_name,
                                    render_type, render_mode, color_ramp_name, output_path,
                    dialog.progress_bar, reverse_ramp)
            QTimer.singleShot(500, dialog.accept)

        dialog.processing_callback = on_ok
        dialog.exec()

    def create_colored_gpx(self, layer, output_name, elev_name, speed_name, slope_name,
                           render_type, render_mode="point", color_ramp_name="", output_path="",
                           progress_bar=None, reverse_ramp=False):
        source = layer.source()
        gpx_file = source.split("|")[0]

        if not os.path.exists(gpx_file):
            self.iface.messageBar().pushCritical("ColorGPX", tr("请选择GPX数据的 track_points 图层！", "Please select a track_points layer from GPX data!"))
            return

        # ---- process ---- #
        def _update_progress(current, total):
            if progress_bar:
                progress_bar.setMaximum(total)
                progress_bar.setValue(current)
                progress_bar.repaint()

        if render_mode == "point":
            out = process_points(gpx_file, elev_name, speed_name, slope_name, _update_progress)
            apply_renderer = apply_point_renderer
        elif render_mode == "gradient_line":
            out = process_lines(gpx_file, elev_name, speed_name, slope_name, _update_progress)
            apply_renderer = apply_gradient_renderer
        else:
            out = process_lines(gpx_file, elev_name, speed_name, slope_name, _update_progress)
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
                        tr("保存成功", "Saved"), f"{output_path}"
                    )
                else:
                    self.iface.messageBar().pushCritical(
                        tr("保存失败", "Save failed"), error_msg or str(error_code)
                    )
            except Exception as e:
                self.iface.messageBar().pushCritical(tr("保存失败", "Save failed"), str(e))

        mode_label = {"point": "点", "gradient_line": "渐变线", "line": "线"}.get(render_mode, render_mode)
        msg = tr(f"{output_name} 创建完成（{mode_label}模式）", f"{output_name} created ({render_mode} mode)")
        self.iface.messageBar().pushSuccess(tr("成功", "Success"), msg)
