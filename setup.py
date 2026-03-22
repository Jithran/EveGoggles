from setuptools import setup, find_packages

setup(
    name="eve-goggles",
    version="0.1.0",
    packages=find_packages(),
    package_data={"": ["../presets/*.json"]},
    install_requires=[
        "PyQt6>=6.4.0",
        "python-xlib>=0.33",
        "ewmh>=0.1.6",
        "pynput>=1.7.6",
        "Pillow>=10.0.0",
        "python-mss>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "eve-goggles=eve_goggles.main:main",
        ],
    },
    python_requires=">=3.10",
)
