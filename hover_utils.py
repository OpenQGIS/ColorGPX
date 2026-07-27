import math
import re
try:
    from qgis.PyQt.QtCore import QVariant
except ImportError:
    class QVariant:
        DateTime = 16
        Date = 14

def detect_field_and_unit(layer, field_type):
    """
    Detect the field name and its unit from a QgsVectorLayer.
    field_type: 'time', 'elevation', 'speed', 'slope'
    Returns (field_name, unit_str or None)
    """
    if not layer:
        return None, None
    fields = layer.fields()
    
    if field_type == 'time':
        for f in fields:
            if f.name().lower() == 'time':
                return f.name(), None
        for f in fields:
            if f.type() in (QVariant.DateTime, QVariant.Date):
                return f.name(), None
        return None, None

    keywords = {
        'elevation': ['ele', 'elev', 'elevation', 'altitude', 'alt', 'height'],
        'speed': ['speed', 'velocity', 'vel'],
        'slope': ['slope', 'grade']
    }
    
    target_kws = keywords.get(field_type, [])
    
    for f in fields:
        fname = f.name()
        fname_lower = fname.lower()
        
        # Tokenize by common delimiters: -, _, or space
        tokens = re.split(r'[-_\s]+', fname_lower)
        
        # Check if any token matches the keywords exactly
        match = False
        for tok in tokens:
            if tok in target_kws:
                match = True
                break
                
        if match:
            # Extract unit from the last part of the field name
            # e.g., speed-km/h, track-1_speed_km/h, speed_KM/H
            last_underscore = fname.rfind('_')
            last_hyphen = fname.rfind('-')
            split_idx = max(last_underscore, last_hyphen)
            
            unit = None
            if split_idx != -1:
                unit = fname[split_idx + 1:].strip().lower()
            
            # Normalize / Validate unit
            if field_type == 'elevation':
                if unit not in ('m', 'ft'):
                    unit = 'm'
            elif field_type == 'speed':
                if unit not in ('m/s', 'km/h', 'mph'):
                    unit = 'm/s'
            elif field_type == 'slope':
                if unit not in ('°', '%'):
                    unit = '°'
            return fname, unit
                
    return None, None

def convert_value(val, from_unit, to_unit, field_type):
    """
    Convert a numeric value between units.
    """
    if val is None:
        return None
    try:
        val = float(val)
    except (ValueError, TypeError):
        return None
        
    if from_unit == to_unit or not from_unit or not to_unit:
        return val

    if field_type == 'elevation':
        if from_unit == 'm' and to_unit == 'ft':
            return val * 3.28084
        elif from_unit == 'ft' and to_unit == 'm':
            return val / 3.28084

    elif field_type == 'speed':
        # Normalize to m/s
        val_ms = val
        if from_unit == 'km/h':
            val_ms = val / 3.6
        elif from_unit == 'mph':
            val_ms = val / 2.23694
            
        # Convert to target
        if to_unit == 'm/s':
            return val_ms
        elif to_unit == 'km/h':
            return val_ms * 3.6
        elif to_unit == 'mph':
            return val_ms * 2.23694

    elif field_type == 'slope':
        if from_unit == '°' and to_unit == '%':
            return math.tan(math.radians(val)) * 100
        elif from_unit == '%' and to_unit == '°':
            return math.degrees(math.atan(val / 100))

    return val
