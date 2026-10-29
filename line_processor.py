from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsPoint, QgsGeometry, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject
from qgis.PyQt.QtCore import QVariant, QDateTime, Qt
try:
    from qgis.PyQt.QtCore import QMetaType
    _Int = QMetaType.Type.Int
    _Double = QMetaType.Type.Double
    _String = QMetaType.Type.QString
    _DateTime = QMetaType.Type.QDateTime
except (ImportError, AttributeError):
    try:
        _Int = QVariant.Int
        _Double = QVariant.Double
        _String = QVariant.String
        _DateTime = QVariant.DateTime
    except (ImportError, AttributeError):
        _Int = 2
        _Double = 6
        _String = 10
        _DateTime = 16
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


def process_lines(gpx_file, elev_name="ELEV", speed_name="speed", slope_name="Slope", progress_callback=None, simulate_speed=False, elev_unit="m", speed_unit="m/s", slope_unit="°"):
    """Parse GPX and return a LineStringZ memory layer.

    Points are grouped by track segment and exploded into individual
    2-point line segments.  Each segment carries the average speed
    and elevation of its endpoints.
    """
    elev_scale = 3.28084 if elev_unit == "ft" else 1.0
    speed_scale = 3.6 if speed_unit == "km/h" else (2.23694 if speed_unit == "mph" else 1.0)

    tree = ET.parse(gpx_file)  # nosec B314
    root = tree.getroot()

    # ---- iterate trk → trkseg → trkpt ---- #
    points = []
    seg_idx = 0
    for trk in root:
        if not trk.tag.endswith("trk"):
            continue
        for trkseg in trk:
            if not trkseg.tag.endswith("trkseg"):
                continue
            # ---- process each <trkpt> inside this <trkseg> ---- #
            for trkpt in trkseg:
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
                        except (ValueError, TypeError):  # nosec B110
                            pass
                    elif ct_lower == "speed":
                        try:
                            speed = float(child.text)
                        except (ValueError, TypeError):  # nosec B110
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
                                except (ValueError, TypeError):  # nosec B110
                                    pass
                            elif ect_lower in ("ele", "elevation", "altitude", "alt", "height"):
                                try:
                                    ele = float(ext_child.text)
                                except (ValueError, TypeError):  # nosec B110
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

    # ---- build the LineStringZ memory layer ---- #
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
    out = QgsVectorLayer(f"LineStringZ?crs={utm_crs.authid()}", "colorGPX_lines", "memory")
    provider = out.dataProvider()
    provider.addAttributes([
        QgsField("ID", _Int, "integer"),
        QgsField("time", _DateTime, "datetime"),
        QgsField("time_E", _DateTime, "datetime"),
        QgsField(speed_name, _Double, "double"),
        QgsField(elev_name, _Double, "double"),
        QgsField(speed_name + "_S", _Double, "double"),
        QgsField(speed_name + "_E", _Double, "double"),
        QgsField(elev_name + "_S", _Double, "double"),
        QgsField(elev_name + "_E", _Double, "double"),
        QgsField(slope_name, _Double, "double"),
        QgsField(slope_name + "_S", _Double, "double"),
        QgsField(slope_name + "_E", _Double, "double"),
    ])
    out.updateFields()

    # ---- group by seg_idx and explode into 2-point segments ---- #
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


    # ---- compute segment slope and smooth with bidirectional EMA ---- #
    # Minimum elevation difference threshold to avoid GPS noise (meters)
    MIN_ELE_DIFF = 0.5
    ALPHA = 0.5  # EMA decay factor
    seg_slopes = {}
    smoothed_point_slopes = {}
    for seg_id, pts in seg_groups.items():
        n = len(pts)
        # Step 1: calculate raw segment slopes
        slopes = []
        for i in range(n - 1):
            dist = haversine_distance(pts[i]["lon"], pts[i]["lat"], pts[i+1]["lon"], pts[i+1]["lat"])
            d_ele = pts[i+1]["ele"] - pts[i]["ele"]
            if abs(d_ele) >= MIN_ELE_DIFF and dist > 0:
                if slope_unit == "%":
                    val = (d_ele / dist) * 100
                else:
                    val = math.degrees(math.atan(d_ele / dist))
            else:
                val = 0.0
            slopes.append(val)

        if n < 2:
            smoothed_point_slopes[seg_id] = [0.0] * n
            seg_slopes[seg_id] = slopes
            continue

        # Step 2: bidirectional EMA on segment slopes
        # forward pass
        forward = [slopes[0]]
        for i in range(1, len(slopes)):
            forward.append(ALPHA * slopes[i] + (1 - ALPHA) * forward[-1])
        # backward pass
        backward = [0.0] * len(slopes)
        backward[-1] = slopes[-1]
        for i in range(len(slopes) - 2, -1, -1):
            backward[i] = ALPHA * slopes[i] + (1 - ALPHA) * backward[i + 1]
        # smoothed segment slopes
        smoothed_segs = [(forward[i] + backward[i]) / 2.0 for i in range(len(slopes))]

        # Step 3: derive per-point slopes from smoothed segment slopes
        # first point = first segment slope, last point = last segment slope
        # middle points = average of adjacent segment slopes
        point_slopes = [smoothed_segs[0]]
        for i in range(1, n - 1):
            point_slopes.append((smoothed_segs[i - 1] + smoothed_segs[i]) / 2.0)
        point_slopes.append(smoothed_segs[-1])

        seg_slopes[seg_id] = smoothed_segs
        smoothed_point_slopes[seg_id] = point_slopes

    feats = []
    total_pairs = sum(max(0, len(pts) - 1) for pts in seg_groups.values())
    total_lines = total_pairs
    done = 0
    for seg_id, pts in seg_groups.items():
        point_slopes = smoothed_point_slopes[seg_id]
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            slope_s = round(point_slopes[i], 3)
            slope_e = round(point_slopes[i + 1], 3)
            slope_avg = round((slope_s + slope_e) / 2.0, 3)

            # Converted and rounded values
            ele1_conv = round(p1["ele"] * elev_scale, 3)
            ele2_conv = round(p2["ele"] * elev_scale, 3)
            ele_avg_conv = round(((p1["ele"] + p2["ele"]) / 2.0) * elev_scale, 3)

            speed1_conv = round(p1["speed"] * speed_scale, 3)
            speed2_conv = round(p2["speed"] * speed_scale, 3)
            speed_avg_conv = round(((p1["speed"] + p2["speed"]) / 2.0) * speed_scale, 3)

            # Generate sub-segments (original or densified)
            segments = [(p1, p2)]
            # Create features for each sub-segment
            for d1, d2 in segments:
                pt1_proj = transform.transform(QgsPointXY(d1["lon"], d1["lat"]))
                pt2_proj = transform.transform(QgsPointXY(d2["lon"], d2["lat"]))
                g1 = QgsPoint(pt1_proj.x(), pt1_proj.y(), ele1_conv)
                g2 = QgsPoint(pt2_proj.x(), pt2_proj.y(), ele2_conv)
                line = QgsGeometry.fromPolyline([g1, g2])
                f = QgsFeature(out.fields())
                f.setGeometry(line)
                f.setAttributes([i, parse_iso_time_to_qdatetime(d1["time"]),
                                 parse_iso_time_to_qdatetime(d2["time"]),
                                 speed_avg_conv,
                                 ele_avg_conv,
                                 speed1_conv, speed2_conv,
                                 ele1_conv, ele2_conv,
                                 slope_avg, slope_s, slope_e])
                feats.append(f)
                done += 1
                if progress_callback:
                    progress_callback(done, total_lines)

    provider.addFeatures(feats)
    out.updateExtents()
    return out
