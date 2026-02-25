from setuptools import setup, find_packages

ver = "1.2.1"

setup(
    name="geniusweb",
    version=ver,
    description="GeniusWeb glue code to connect python3 parties",
    url="https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWeb",
    author="W.Pasman",
    # packages={'src':'*'},
    packages=find_packages(exclude=["test", "test.*", "test.*.*"]),
    package_data={"geniusweb": ["py.typed"], "tudelft": ["py.typed"]},
    install_requires=[
        "pyson@https://tracinsy.ewi.tudelft.nl/pubtrac/Utilities/export/312/pyson/dist/pyson-1.1.3.tar.gz",
        "utilities@https://tracinsy.ewi.tudelft.nl/pubtrac/Utilities/export/314/utilitiespy/dist/utilities-1.0.5.tar.gz",
        "logging@https://tracinsy.ewi.tudelft.nl/pubtrac/Utilities/export/226/loggingpy/dist/logging-1.0.0.tar.gz",
        "websocket-client==1.0.1",
        # "PyQt5==5.15.6"
        "PyQt5",
    ],
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
