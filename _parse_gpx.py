import xml.etree.ElementTree as ET
import sys

gpx_file = r"E:\QGIS文章\OpenQGIS_Lab\OpenQGIS_QGISPlugins_LAB\ColorGPX\GPX\厄尔娜沟（甲尔猛措） .gpx"
tree = ET.parse(gpx_file)
root = tree.getroot()

count = 0
for elem in root.iter():
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    if tag == "trkpt":
        count += 1
        if 82 <= count <= 90:
            lat = elem.attrib.get("lat", "")
            lon = elem.attrib.get("lon", "")
            speed = ele = ""
            for child in elem:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "speed":
                    speed = child.text
                if ct == "ele":
                    ele = child.text
            print(f"#{count} lat={lat} lon={lon} speed={speed} ele={ele}")

print(f"\nTotal track points: {count}")
