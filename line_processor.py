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
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405
import math


def haversine_distance(lon1, lat1, lon2, lat2):
    """Return horizontal distance in meters between two WGS84 points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def process_lines(gpx_file, elev_name="ELEV", speed_name="speed", slope_name="Slope", progress_callback=None):
    """Parse GPX and return a LineStringZ memory layer.

    Points are grouped by track segment and exploded into individual
    2-point line segments.  Each segment carries the average speed
    and elevation of its endpoints.
    """

    tree = ET.parse(gpx_file)  # nosec B314
    root = tree.getroot()

    # ---- collect raw trkpt values, tracking segment boundaries ---- #
    points = []
    seg_idx = 0
    prev_tag = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        # a new <trkseg> means the next <trkpt> starts a new segment
        if tag == "trkseg":
            prev_tag = tag
            continue

        if tag != "trkpt":
            prev_tag = tag
            continue

        # first trkpt after a trkseg starts a new segment counter
        if prev_tag == "trkseg":
            seg_idx += 1
            # (seg_idx starts at 0 for the first trkseg; here it becomes 1.
            #  so we shift: the first trkseg gets seg_idx = 0)
            # Actually simpler: increment seg_idx before processing the group.
            pass

        # Actually, let me rethink: track segments explicitly.
        # Reset: iterate by finding <trkseg> and processing its children.
        prev_tag = tag

    # ---- simpler approach: iterate trk elements ---- #
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
                    if ct == "ele":
                        try:
                            ele = float(child.text)
                        except (ValueError, TypeError):
                            pass
                    elif ct == "speed":
                        try:
                            speed = float(child.text)
                        except (ValueError, TypeError):
                            pass
                    elif ct == "time":
                        time_val = child.text or ""
                    elif ct == "extensions":
                        for ext_child in child:
                            ect = ext_child.tag.split("}")[-1] if "}" in ext_child.tag else ext_child.tag
                            if ect == "speed":
                                try:
                                    speed = float(ext_child.text)
                                except (ValueError, TypeError):
                                    pass
                            elif ect == "ele":
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

    # ---- build the LineStringZ memory layer ---- #
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    out = QgsVectorLayer(f"LineStringZM?crs={crs.authid()}", "colorGPX_lines", "memory")
    provider = out.dataProvider()
    provider.addAttributes([
        QgsField("ID", _Int, "integer"),
        QgsField("time", _String, "string"),
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
            slopes.append(math.degrees(math.atan(d_ele / dist)) if abs(d_ele) >= MIN_ELE_DIFF and dist > 0 else 0.0)

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
            # Generate sub-segments (original or densified)
            segments = [(p1, p2)]
            # Create features for each sub-segment
            for d1, d2 in segments:
                g1 = QgsPoint(d1["lon"], d1["lat"], d1["ele"], d1["speed"])
                g2 = QgsPoint(d2["lon"], d2["lat"], d2["ele"], d2["speed"])
                line = QgsGeometry.fromPolyline([g1, g2])
                f = QgsFeature(out.fields())
                f.setGeometry(line)
                f.setAttributes([i, d1["time"],
                                 (d1["speed"] + d2["speed"]) / 2.0,
                                 (d1["ele"] + d2["ele"]) / 2.0,
                                 d1["speed"], d2["speed"],
                                 d1["ele"], d2["ele"],
                                 slope_avg, slope_s, slope_e])
                feats.append(f)
                done += 1
                if progress_callback:
                    progress_callback(done, total_lines)

    provider.addFeatures(feats)
    return out
