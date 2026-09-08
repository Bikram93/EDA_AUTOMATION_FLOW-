from setuptools import setup, find_packages

setup(
    name="eda_flow_project",
    version="0.1.0",
    description="Electronic Design Automation (EDA) Flow Automation Platform",
    author="EDA Automation Team",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "Flask>=3.0.0",
        "Jinja2>=3.1.0",
        "networkx>=3.0",
        "pandas>=2.0.0",
        "python-dotenv>=1.0.0",
        "psutil>=5.9.0",
    ],
    entry_points={
        "console_scripts": [
            "eda-server=src.server:main",
            "eda-web=web.app:main",
        ],
    },
)
