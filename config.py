import os
from dotenv import load_dotenv

# Load .env variables (make sure you have a .env file in project root)
load_dotenv()

class Config:
    """Base configuration shared across environments."""
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # turn True only when debugging SQL

class DevConfig(Config):
    """Local development configuration"""
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///clinic.db")
    DEBUG = True

class ProdConfig(Config):
    """Production configuration"""
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://user:password@host/db_name"
    )
    DEBUG = False