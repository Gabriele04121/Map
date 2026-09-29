"""Importing this package registers every built-in provider."""
from . import base  # noqa: F401
from . import content, geographic, safety  # noqa: F401
from .events import nager  # noqa: F401
from .flights import mock as _fm, travelpayouts  # noqa: F401
from .fx import frankfurter  # noqa: F401
from .geocoding import open_meteo as _gm  # noqa: F401
from .hotels import cost_profile  # noqa: F401
from .trains import mock as _tm, transitous  # noqa: F401
from .weather import open_meteo  # noqa: F401
