"""Service modules for PDF processing and extraction."""

# Explicitly expose service modules to the package namespace to resolve import issues
from . import pdf_service
from . import character_service
from . import image_generation_service
from . import prompt_service # Add prompt_service back