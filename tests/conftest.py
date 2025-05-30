"""pytest-homeassistant-custom-component-specifika fixtures."""
import sys
import pytest
from pathlib import Path

# Lägg till 'config' mappen i Pythons sökväg
# Detta gör så att testerna kan importera från custom_components
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Denna "magiska" fixture aktiverar laddning av custom integrations i testmiljön
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations."""
    yield