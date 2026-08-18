import os
from typing import Tuple, Optional


def get_storage_credentials(storage_choice: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (connection_string, account_url) for the chosen storage account.

    storage_choice must be either 'sensitive' or 'nonsensitive'. Returns a tuple
    of environment variable values (may be None if not set).
    """
    if storage_choice not in ("sensitive", "nonsensitive"):
        raise ValueError("storage_account must be 'sensitive' or 'nonsensitive'.")

    if storage_choice == "sensitive":
        return os.getenv("SENSITIVE_CONNECTION_STRING"), os.getenv("SENSITIVE_ACCOUNT_URL")

    return os.getenv("NOSENSITIVE_CONNECTION_STRING"), os.getenv("NOSENSITIVE_ACCOUNT_URL")
