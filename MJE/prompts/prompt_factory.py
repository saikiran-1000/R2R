import os
from utility.logger import logger
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class PromptFactory:
    """
    Centralizes per-file-type prompt metadata.
    - INFO_DESC: human-readable description for the file-type
    - DATA_PLACEHOLDER: the variable name used in the prompt template (e.g., EMAIL_TEXT or EXCEL_JSON)
    """

    # Read environment (with safe defaults)
    TEXT_INFO_DESC: str = os.getenv("TEXT_FILE_INFO_DESC", "plain text")
    EXCEL_INFO_DESC: str = os.getenv(
        "EXCEL_FILE_INFO_DESC", "an Excel workbook as JSON"
    )

    TEXT_DATA_PLACEHOLDER: str = os.getenv("TEXT_DATA_PLACEHOLDER", "EMAIL_TEXT")
    EXCEL_DATA_PLACEHOLDER: str = os.getenv("EXCEL_DATA_PLACEHOLDER", "EXCEL_JSON")

    # Map by normalized extension (no dot, lowercased)
    _INFO_DESC_BY_EXT: Dict[str, str] = {
        "xlsx": EXCEL_INFO_DESC,
        "xls": EXCEL_INFO_DESC,
        "xlsm": EXCEL_INFO_DESC,
        "txt": TEXT_INFO_DESC,
        "text": TEXT_INFO_DESC,
        "eml": TEXT_INFO_DESC,
    }

    _DATA_PLACEHOLDER_BY_EXT: Dict[str, str] = {
        "xlsx": EXCEL_DATA_PLACEHOLDER,
        "xls": EXCEL_DATA_PLACEHOLDER,
        "xlsm": EXCEL_DATA_PLACEHOLDER,
        "txt": TEXT_DATA_PLACEHOLDER,
        "text": TEXT_DATA_PLACEHOLDER,
        "eml": TEXT_DATA_PLACEHOLDER,
    }

    @staticmethod
    def _normalize_ext(file_type: str) -> str:
        """
        Accepts 'xlsx' or '.xlsx' and returns 'xlsx' (lowercased).
        """
        if not file_type:
            return ""
        ft = file_type.lower().strip()
        return ft[1:] if ft.startswith(".") else ft

    @classmethod
    def get_file_info_desc(cls, file_type: str) -> Optional[str]:
        """
        Returns the human-readable description for the file type.
        """
        ext = cls._normalize_ext(file_type)
        try:
            return cls._INFO_DESC_BY_EXT[ext]
        except KeyError:
            logger.warning("Unknown file type for info desc: %r", file_type)
            return None

    @classmethod
    def get_data_placeholder(cls, file_type: str) -> Optional[str]:
        """
        Returns the prompt placeholder token for the data blob (e.g., 'EMAIL_TEXT' or 'EXCEL_JSON').
        """
        ext = cls._normalize_ext(file_type)
        try:
            return cls._DATA_PLACEHOLDER_BY_EXT[ext]
        except KeyError:
            logger.warning("Unknown file type for data placeholder: %r", file_type)
            return None
