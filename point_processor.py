from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsPoint, QgsGeometry, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject
from qgis.PyQt.QtCore import QVariant, QDateTime, Qt
try:
    from qgis.PyQt.QtCore import QMetaType
    _Int = QMetaType.Type.Int
    _Double = QMetaType.Type.Double
    _String = QMetaType.Type.QString
    _DateTime = QMetaType.Type.QDateTime
except (ImportError, AttributeError):
    _Int = QVariant.Int
    _Double = QVariant.Double
    _String = QVariant.String
    _DateTime = QVariant.DateTime
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405
import math
from datetime import datetime, timezone
def parse_iso_time_to_qdatetime(time_str):
    if not time_str:
        return QDateTime()
    time_str = time_str.strip()
    if " " in time_str:
        time_str = time_str.replace(" ", "T")
    dt = QDateTime.fromString(time_str, Qt.DateFormat.ISODate)
    if dt.isValid():
        return dt
    return QDateTime()



def parse_iso_time_to_seconds(time_str):
    if not time_str:
        return None
    time_str = time_str.strip()
    if time_str.endswith('Z'):
        time_str = time_str[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(time_str)
    except Exception:
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return (dt - datetime(1970, 1, 1)).total_seconds()



def haversine_distance(lon1, lat1, lon2, lat2):
    """Return horizontal distance in meters between two WGS84 points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def process_points(gpx_file, elev_name="ELEV", speed_name="speed", slope_name="Slope", progress_callback=None, simulate_speed=False, elev_unit="m", speed_unit="m/s", slope_unit="°"):
    """Parse GPX and return a PointZM memory layer with speed, elevation, slope, time, track_seg_point_id."""
    elev_scale = 3.28084 if elev_unit == "ft" else 1.0
    speed_scale = 3.6 if speed_unit == "km/h" else (2.23694 if speed_unit == "mph" else 1.0)

    tree = ET.parse(gpx_file)  # nosec B314
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
                ct_lower = ct.lower()
                if ct_lower in ("ele", "elevation", "altitude", "alt", "height"):
                    try:
                        ele = float(child.text)
                    except (ValueError, TypeError):
                        pass
                elif ct_lower == "speed":
                    try:
                        speed = float(child.text)
                    except (ValueError, TypeError):
                        pass
                elif ct_lower == "time":
                    time_val = child.text or ""
                elif ct_lower == "extensions":
                    for ext_child in child:
                        ect = ext_child.tag.split("}")[-1] if "}" in ext_child.tag else ext_child.tag
                        ect_lower = ect.lower()
                        if ect_lower == "speed":
                            try:
                                speed = float(ext_child.text)
                            except (ValueError, TypeError):
                                pass
                        elif ect_lower in ("ele", "elevation", "altitude", "alt", "height"):
                            try:
                                ele = float(ext_child.text)
                            except (ValueError, TypeError):
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

    # Determine local UTM zone based on track coordinates center
    lons = [p["lon"] for p in points]
    lats = [p["lat"] for p in points]
    center_lon = sum(lons) / len(lons) if lons else 0.0
    center_lat = sum(lats) / len(lats) if lats else 0.0
    center_lon = max(-180.0, min(180.0, center_lon))
    zone = int((center_lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))
    epsg = 32600 + zone if center_lat >= 0 else 32700 + zone
    utm_crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
    
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), utm_crs, QgsProject.instance())
    out = QgsVectorLayer(f"PointZ?crs={utm_crs.authid()}", "colorGPX_points", "memory")
    provider = out.dataProvider()
    provider.addAttributes([
        QgsField(speed_name, _Double, "double"),
        QgsField(elev_name, _Double, "double"),
        QgsField(slope_name, _Double, "double"),
        QgsField("time", _DateTime, "datetime"),
        QgsField("track_seg_point_id", _Int, "integer"),
    ])
    out.updateFields()

    # group by seg_idx, assign per-segment point index
    seg_groups = {}
    for d in points:
        seg_groups.setdefault(d["seg_idx"], []).append(d)

    if simulate_speed:
        for seg_id, pts in seg_groups.items():
            n = len(pts)
            if n < 2:
                for p in pts:
                    p["speed"] = 0.0
                continue

            times = []
            for p in pts:
                times.append(parse_iso_time_to_seconds(p["time"]))

            seg_speeds = []
            for i in range(n - 1):
                t1 = times[i]
                t2 = times[i + 1]
                if t1 is None or t2 is None:
                    seg_speeds.append(0.0)
                    continue
                dt = t2 - t1
                if dt <= 0:
                    seg_speeds.append(0.0)
                    continue
                dist = haversine_distance(pts[i]["lon"], pts[i]["lat"], pts[i+1]["lon"], pts[i+1]["lat"])
                seg_speeds.append(dist / dt)

            pts[0]["speed"] = seg_speeds[0]
            for j in range(1, n - 1):
                pts[j]["speed"] = (seg_speeds[j - 1] + seg_speeds[j]) / 2.0
            pts[n - 1]["speed"] = seg_speeds[-1]


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
                if abs(d_ele) >= MIN_ELE_DIFF and dist > 0:
                    if slope_unit == "%":
                        slope = round((d_ele / dist) * 100, 3)
                    else:
                        slope = round(math.degrees(math.atan(d_ele / dist)), 3)
                else:
                    slope = 0.0
            else:
                slope = 0.0

            ele_conv = round(d["ele"] * elev_scale, 3)
            speed_conv = round(d["speed"] * speed_scale, 3)

            f = QgsFeature(out.fields())
            pt_proj = transform.transform(QgsPointXY(d["lon"], d["lat"]))
            pt = QgsPoint(pt_proj.x(), pt_proj.y(), ele_conv)
            f.setGeometry(QgsGeometry(pt))
            f.setAttributes([speed_conv, ele_conv, slope, parse_iso_time_to_qdatetime(d["time"]), pt_idx])
            feats.append(f)
            if progress_callback:
                progress_callback(len(feats), total)

    provider.addFeatures(feats)
    out.updateExtents()
    return out
