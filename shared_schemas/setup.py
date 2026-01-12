"""
Setup file for shared_schemas package.
Allows installation as a local package using pip install -e.
"""

from setuptools import setup, find_packages

setup(
    name="shared_schemas",
    version="1.0.0",
    description="Shared Pydantic schemas for chat-agent microservices",
    author="Chat Agent Team",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "pydantic>=2.0.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.12",
    ],
)
