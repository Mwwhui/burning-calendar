import pytest

from burncal.io import make_demo_data


@pytest.fixture(scope="session")
def demo_raw():
    # smaller than the default demo so the suite stays fast
    return make_demo_data(seed=7, scale=0.4)
