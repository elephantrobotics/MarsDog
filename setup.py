from setuptools import find_packages, setup

package_name = "marsdog_sim2d"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    package_data={
        package_name: [
            "assets/dog/*.png",
            "assets/human/*.png",
            "assets/backgrounds/*.png",
            "assets/config/*.yaml",
        ]
    },
    include_package_data=True,
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools", "arcade>=3.3.3"],
    zip_safe=True,
    maintainer="MarsDog",
    maintainer_email="marsdog@example.com",
    description="Lightweight Arcade 2D ROS2 visualization for MarsDog events and state.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "arcade_viewer_node = marsdog_sim2d.arcade_viewer_node:main",
        ],
    },
)
