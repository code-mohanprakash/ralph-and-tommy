from importlib.metadata import version

import fleek_agents


def test_version_matches_the_installed_package() -> None:
    assert fleek_agents.__version__ == version("ralph-and-tommy")
