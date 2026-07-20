from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsPoint, QgsGeometry, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import QVariant
try:
    from qgis.PyQt.QtCore import QMetaType
    _Int = QMetaType.Type.Int
    _Double = QMetaType.Type.Double
    _String = QMetaType.Type.QString
except (ImportError, AttributeError):
    _Int = QVariant.Int
    _Double = QVariant.Double
    _String = QVariant.String
import xml.etree.ElementTree as ET
import math


def haversine_distance(lon1, lat1, lon2, lat2):
    """Return horizontal distance in meters between two WGS84 points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def process_points(gpx_file, elev_name="ELEV", speed_name="speed", slope_name="Slope", progress_callback=None):
    """Parse GPX and return a PointZM memory layer with speed, elevation, slope, time, track_seg_point_id."""

    tree = ET.parse(gpx_file)
    root = tree.getroot()

    points = []
    seg_idx = 0
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag != "trkseg":
            continue
        for trkpt in elem:
            if not trkpt.tag.endswith("trkpt"):
                continue
            ele = 0.0
            speed = 0.0
            time_val = ""
            for child in trkpt:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "ele":
                    try:
                        ele = float(child.text)
                    except:
                        pass
                elif ct == "speed":
                    try:
                        speed = float(child.text)
                    except:
                        pass
                elif ct == "time":
                    time_val = child.text or ""
                elif ct == "extensions":
                    for ext_child in child:
                        ect = ext_child.tag.split("}")[-1] if "}" in ext_child.tag else ext_child.tag
                        if ect == "speed":
                            try:
                                speed = float(ext_child.text)
                            except Exception:
                                pass
                        elif ect == "ele":
                            try:
                                ele = float(ext_child.text)
                            except Exception:
                                pass
            points.append(dict(
                lon=float(trkpt.attrib.get("lon", 0)),
                lat=float(trkpt.attrib.get("lat", 0)),
                ele=ele,
                speed=speed,
                time=time_val,
                seg_idx=seg_idx,
            ))
        seg_idx += 1

    # memory layer: PointZM (ele -> Z, speed -> M)
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    out = QgsVectorLayer(f"PointZM?crs={crs.authid()}", "colorGPX_points", "memory")
    provider = out.dataProvider()
    provider.addAttributes([
        QgsField(speed_name, _Double, "double"),
        QgsField(elev_name, _Double, "double"),
        QgsField(slope_name, _Double, "double"),
        QgsField("time", _String, "string"),
        QgsField("track_seg_point_id", _Int, "integer"),
    ])
    out.updateFields()

    # group by seg_idx, assign per-segment point index
    seg_groups = {}
    for d in points:
        seg_groups.setdefault(d["seg_idx"], []).append(d)

    feats = []
    total = len(points)
    # Minimum elevation difference threshold to avoid GPS noise (meters)
    MIN_ELE_DIFF = 0.5
    for sid, pts in seg_groups.items():
        for pt_idx, d in enumerate(pts):
            # slope to next point in segment (last point = 0)
            if pt_idx < len(pts) - 1:
                p2 = pts[pt_idx + 1]
                dist = haversine_distance(d["lon"], d["lat"], p2["lon"], p2["lat"])
                d_ele = p2["ele"] - d["ele"]
                slope = round(math.degrees(math.atan(d_ele / dist)), 3) if abs(d_ele) >= MIN_ELE_DIFF and dist > 0 else 0.0
            else:
                slope = 0.0
            f = QgsFeature(out.fields())
            pt = QgsPoint(d["lon"], d["lat"], d["ele"], d["speed"])
            f.setGeometry(QgsGeometry(pt))
            f.setAttributes([d["speed"], d["ele"], slope, d["time"], pt_idx])
            feats.append(f)
            if progress_callback:
                progress_callback(len(feats), total)

    provider.addFeatures(feats)
    return out
