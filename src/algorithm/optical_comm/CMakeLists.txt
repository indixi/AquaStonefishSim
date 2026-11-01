cmake_minimum_required(VERSION 3.0.2)
project(optical_comm)
find_package(catkin REQUIRED COMPONENTS
  rospy sensor_msgs std_msgs cv_bridge stonefish_ros message_generation
)
catkin_python_setup()
add_message_files(FILES CommRequest.msg CommEvent.msg)
generate_messages(DEPENDENCIES std_msgs)
catkin_package(CATKIN_DEPENDS rospy sensor_msgs std_msgs cv_bridge stonefish_ros message_runtime)
catkin_install_python(PROGRAMS scripts/optical_comm_node.py scripts/communication_demo.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY launch config DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
if(CATKIN_ENABLE_TESTING)
  catkin_add_nosetests(test)
endif()
