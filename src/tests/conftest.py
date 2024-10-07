import base64
import logging
import os
import tempfile

import pytest

_LOG = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def manage_gsa_key():
    encoded_json = os.getenv("GSA_JSON")
    if not encoded_json:
        yield
    else:
        _LOG.info("Setting up GSA json file")
        decoded_json = base64.standard_b64decode(encoded_json)
        with tempfile.NamedTemporaryFile(mode="wb+") as temp:
            temp.write(decoded_json)
            os.putenv("GOOGLE_APPLICATION_CREDENTIALS", temp.name)
            yield
