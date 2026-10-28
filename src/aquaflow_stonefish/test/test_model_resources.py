"""Resolve the asset paths used by real scenes and RViz against the moved model tree."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

PACKAGE = Path(__file__).resolve().parents[1]


class ModelResourcesTest(unittest.TestCase):
    def assert_resource(self, value, scene):
        prefix = "$(find aquaflow_stonefish)/"
        if value.startswith(prefix):
            path = PACKAGE / value[len(prefix):]
        elif "$(" in value:
            return
        else:
            path = PACKAGE / "model" / value
        self.assertTrue(path.is_file(), "{} references missing {}".format(scene, path))

    def test_scene_meshes_textures_and_includes_resolve(self):
        for scene in (PACKAGE / "scenarios").glob("*.scn"):
            for element in ET.parse(scene).getroot().iter():
                for attribute in ("filename", "texture", "file"):
                    value = element.get(attribute)
                    if value:
                        self.assert_resource(value, scene.name)

    def test_urdf_meshes_resolve(self):
        prefix = "package://aquaflow_stonefish/"
        for urdf in (PACKAGE / "model/robot").rglob("*.urdf"):
            for mesh in ET.parse(urdf).getroot().iter("mesh"):
                value = mesh.get("filename")
                self.assertTrue(value.startswith(prefix), value)
                self.assertTrue((PACKAGE / value[len(prefix):]).is_file(), value)

    def test_rviz_selects_existing_urdfs(self):
        text = (PACKAGE / "launch/visualization.launch").read_text(encoding="utf-8")
        paths = re.findall(r"'([^']+\.urdf)'", text)
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue((PACKAGE / path).is_file(), path)

    def test_install_directories_exist(self):
        text = (PACKAGE / "CMakeLists.txt").read_text(encoding="utf-8")
        groups = re.findall(r"(?ms)^install\(DIRECTORY\s+(.*?)\s+DESTINATION", text)
        self.assertTrue(groups)
        for group in groups:
            for path in group.split():
                self.assertTrue((PACKAGE / path).is_dir(), path)


if __name__ == "__main__":
    unittest.main()
