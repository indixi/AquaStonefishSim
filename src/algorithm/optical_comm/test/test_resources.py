import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
REPO=PACKAGE.parents[2]
SIM=REPO/"src/aquaflow_stonefish"

class ResourceTest(unittest.TestCase):
    def test_three_static_robots_have_unique_names_looks_and_optical_topics(self):
        world=ET.parse(SIM/"scenarios/three_robot_optical_comm.scn").getroot()
        robots=[];looks=[]
        for include in world.findall("include"):
            args={arg.get("name"):arg.get("value") for arg in include.findall("arg")}
            path=include.get("file").replace("$(find aquaflow_stonefish)",str(SIM))
            text=Path(path).read_text(encoding="utf-8")
            for key,value in args.items():text=text.replace("$(arg "+key+")",value)
            expanded=ET.fromstring(text)
            robots.extend(expanded.findall("robot"))
            looks.extend(look.get("name") for look in expanded.findall("looks/look"))
            for node in expanded.iter():
                for attr in ("filename","texture"):
                    value=node.get(attr)
                    if value:self.assertTrue((SIM/"model"/value).is_file(),value)
        self.assertEqual([r.get("name") for r in robots],["leader","follower_1","follower_2"])
        self.assertEqual(len(looks),len(set(looks)))
        self.assertTrue(all(r.get("fixed")=="true" for r in robots))
        self.assertEqual(sum(len(r.findall("light")) for r in robots),24)
        for robot in robots:
            name=robot.get("name")
            camera=robot.find("sensor")
            self.assertEqual(camera.get("type"),"camera")
            self.assertEqual(camera.find("ros_publisher").get("topic"),"/"+name+"/rgb")
            for light in robot.findall("light"):
                self.assertIn(light.find("ros_subscriber").get("command"),
                              ["/"+name+"/lights/left/cmd","/"+name+"/lights/right/cmd"])

    def test_launch_uses_nested_ros_package_and_real_scene(self):
        launch=ET.parse(PACKAGE/"launch/three_robot_comm.launch").getroot()
        instances=[item for item in launch.findall("include") if "robot_comm.launch" in item.get("file")]
        roles=[{arg.get("name"):arg.get("value") for arg in item.findall("arg")} for item in instances]
        self.assertEqual([(r["node_id"],r["role"]) for r in roles],[("1","leader"),("2","follower"),("3","follower")])
        self.assertEqual(ET.parse(PACKAGE/"package.xml").getroot().findtext("name"),"optical_comm")

if __name__=="__main__":unittest.main()
