from setuptools import setup
from pip.req import parse_requirements

# parse_requirements() returns generator of pip.req.InstallRequirement objects
install_reqs = parse_requirements("requirements.txt", session=False)
requirements = [str(ir.req) for ir in install_reqs]

setup(
    name="slack_consul",
    version=0.1,
    py_modules=['slack_consul.slack_consul'],
    install_requires=requirements,
    test_suite="nose.collector",
    entry_points={
        "console_scripts": [
            "slack_consul=slack_consul.slack_consul:loop"
        ]
    }
)