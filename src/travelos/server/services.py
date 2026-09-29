"""Service wiring (composition root for domain services)."""
from __future__ import annotations


def build_services(ctx) -> None:
    from ..intelligence.destination import DestinationService
    from ..monitor.watches import Refresher, WatchService
    from ..packages.generator import PackageGenerator
    from ..pricing.fx import FxService
    from ..pricing.history import PriceHistory
    from ..recommend.discovery import DiscoveryService
    from ..recommend.engine import RecommendationEngine
    from ..search.endpoints import EndpointResolver
    from ..search.flexible import CheapestTrip, FlexibleSearch
    from ..search.globalsearch import GlobalSearch
    from ..search.transport import TransportService
    from ..search.travel import FlightSearchService, TrainSearchService
    from ..stats.analytics import Analytics
    from ..trips.service import PreferencesService, TripService

    s = ctx.svc
    s["fx"] = FxService(ctx)
    s["history"] = PriceHistory(ctx)
    s["prefs"] = PreferencesService(ctx)
    s["trips"] = TripService(ctx)
    s["endpoints"] = EndpointResolver(ctx)
    s["flights"] = FlightSearchService(ctx)
    s["trains"] = TrainSearchService(ctx)
    s["transport"] = TransportService(ctx)
    s["flexible"] = FlexibleSearch(ctx)
    s["cheapest"] = CheapestTrip(ctx)
    s["destination"] = DestinationService(ctx)
    s["recommend"] = RecommendationEngine(ctx)
    s["packages"] = PackageGenerator(ctx)
    s["discovery"] = DiscoveryService(ctx)
    s["watches"] = WatchService(ctx)
    s["refresher"] = Refresher(ctx)
    s["analytics"] = Analytics(ctx)
    s["search"] = GlobalSearch(ctx)
