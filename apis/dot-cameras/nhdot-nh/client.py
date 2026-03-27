#!/usr/bin/env python3
"""
NewEngland511 / NHDOT Traffic Camera & Incident API Client
===========================================================
A production-quality Python client for the New England 511 traffic information
system (https://newengland511.org), which covers New Hampshire, Vermont, and
Maine DOT data including the NHDOT traffic camera network.

This module was reverse-engineered from the NewEngland511 web application by
inspecting its JavaScript bundles, map layer configuration, and XHR requests.
No API key or authentication is required for read-only access to public data.

Discovered endpoints
---------------------
  GET /map/mapIcons/{layer}?lang=en
      Returns all map markers for a given layer (cameras, incidents, signs, etc.)
      as a JSON object with:
        - item1: icon SVG configuration
        - item2: array of { itemId, location:[lat,lon], icon, title }

  GET /tooltip/{layer}/{id}?lang=en
      Returns an HTML snippet with full detail for a single marker (camera name,
      image URLs, roadway, last-updated time, sign messages, etc.)

  GET /map/Cctv/{imageId}
      Returns the live JPEG snapshot for a specific camera view.
      Camera image IDs are discovered via the tooltip endpoint.

  GET /Camera/GetVideoUrl?imageId={id}
      Returns a JSON object with streaming video URL info (when available).

  GET /list/GetData/{typeId}?draw=1&start=0&length=N&...
      DataTables server-side endpoint.  Returns JSON with draw/recordsTotal/
      recordsFiltered/data.  The data array is populated only with a well-formed
      column spec query string.  Returns 408 cameras, 295+ traffic events, etc.

  GET /List/UniqueColumnValuesForEvents/{typeId}
      Returns unique filter values (states, roadways, severities, etc.) for a
      given event type.  Useful for building dynamic filter UIs.

Available map layer IDs
-----------------------
  Cameras, Incidents, IncidentClosures, Construction, ConstructionClosures,
  FutureRoadwork, FutureConstructionClosure, TruckRestrictions, SpecialEvents,
  SpecialEventClosures, Waze, WazeIncidents, WazeClosures, MessageSigns,
  WeatherStations, WeatherEvents, WeatherForecast, DisplayedParking, Bridge,
  InformationCenter, FerryTerminals, MileMarkers

New Hampshire geography bounds
--------------------------------
  Latitude:  42.69 – 45.31 N
  Longitude: 71.09 – 72.55 W

Usage (CLI)
-----------
    python nhdot_client.py cameras
    python nhdot_client.py cameras --nh
    python nhdot_client.py camera 628
    python nhdot_client.py image 950 --save waterbury.jpg
    python nhdot_client.py incidents
    python nhdot_client.py incidents --nh
    python nhdot_client.py signs
    python nhdot_client.py layers
    python nhdot_client.py tooltip Cameras 628

Author: reverse-engineered from newengland511.org  (2026-03-27)
Stdlib only: urllib, json, html.parser, dataclasses, argparse
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://newengland511.org"

# New Hampshire approximate bounding box
NH_LAT_MIN = 42.69
NH_LAT_MAX = 45.31
NH_LON_MIN = -72.55
NH_LON_MAX = -71.09

# Known map layer IDs (extracted from the map page HTML data-layerid attributes)
LAYER_IDS: Dict[str, str] = {
    "Cameras":                   "Traffic cameras (CCTV)",
    "Incidents":                 "Traffic incidents",
    "IncidentClosures":          "Incident-related road closures",
    "Construction":              "Active construction zones",
    "ConstructionClosures":      "Construction-related closures",
    "FutureRoadwork":            "Future / scheduled roadwork",
    "FutureConstructionClosure": "Future construction closures",
    "TruckRestrictions":         "Truck weight/height restrictions",
    "SpecialEvents":             "Special events",
    "SpecialEventClosures":      "Special event closures",
    "Waze":                      "Waze crowd-sourced reports",
    "WazeIncidents":             "Waze incidents",
    "WazeClosures":              "Waze closures",
    "MessageSigns":              "Dynamic message signs (DMS/VMS)",
    "WeatherStations":           "Roadside weather stations",
    "WeatherEvents":             "Weather event alerts",
    "WeatherForecast":           "Weather forecast points",
    "DisplayedParking":          "Parking availability",
    "Bridge":                    "Bridge restrictions",
    "InformationCenter":         "Travel information centers",
    "FerryTerminals":            "Ferry terminals",
    "MileMarkers":               "Mile markers",
    "TrafficSpeeds":             "Traffic speed / congestion (raster tile)",
    "WinterRoads":               "Winter road conditions (raster tile)",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Referer": BASE_URL + "/",
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MapMarker:
    """A single marker returned by the /map/mapIcons/{layer} endpoint."""
    item_id: str
    lat: float
    lon: float
    title: str = ""
    layer: str = ""


@dataclass
class CameraView:
    """
    A single camera view (there may be multiple views per physical site).
    image_id corresponds to the integer used in /map/Cctv/{image_id}.
    """
    image_id: str
    image_url: str
    title: str = ""
    description: str = ""
    refresh_rate_ms: int = 10_000


@dataclass
class Camera:
    """A physical camera site with one or more views."""
    site_id: str
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    views: List[CameraView] = field(default_factory=list)
    state: str = ""
    roadway: str = ""

    @property
    def primary_image_url(self) -> str:
        """Return the live JPEG URL for the first (primary) camera view."""
        if self.views:
            return BASE_URL + self.views[0].image_url
        return ""

    @property
    def all_image_urls(self) -> List[str]:
        return [BASE_URL + v.image_url for v in self.views]


@dataclass
class Incident:
    """A traffic incident / event."""
    item_id: str
    lat: float
    lon: float
    title: str = ""
    description: str = ""
    location: str = ""
    start_time: str = ""
    end_time: str = ""
    layer: str = "Incidents"


@dataclass
class MessageSign:
    """A dynamic message sign (DMS/VMS)."""
    item_id: str
    lat: float
    lon: float
    location: str = ""
    message: str = ""
    last_updated: str = ""


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

class CameraTooltipParser(HTMLParser):
    """Parse the HTML returned by /tooltip/Cameras/{id}.

    The HTML structure for each camera view is:
        <a href="/map/Cctv/{imageId}">
          <img class="carouselCctvImage cctvImage"
               data-lazy="/map/Cctv/{imageId}"
               data-fs-title="..."
               data-fs-desc="..."
               data-refresh-rate="10000"
               id="{imageId}img" />
        </a>

    The anchor tag appears first, so we collect anchors as placeholders and then
    upgrade them with the full metadata when the img tag is encountered.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name: str = ""
        # keyed by image_id str -> CameraView
        self._views_by_id: Dict[str, CameraView] = {}
        self._in_strong = False
        self._strong_text = ""

    @property
    def views(self) -> List[CameraView]:
        return list(self._views_by_id.values())

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = dict(attrs)
        if tag == "strong":
            self._in_strong = True
        elif tag == "img":
            css = attr_dict.get("class", "") or ""
            if "cctvImage" in css:
                lazy = attr_dict.get("data-lazy") or ""
                img_id = attr_dict.get("id") or ""
                fs_title = attr_dict.get("data-fs-title") or ""
                fs_desc = attr_dict.get("data-fs-desc") or ""
                try:
                    refresh = int(attr_dict.get("data-refresh-rate") or 10000)
                except (ValueError, TypeError):
                    refresh = 10_000
                # image_id extracted from data-lazy URL like /map/Cctv/950
                m = re.search(r"/map/Cctv/(\d+)", lazy)
                img_numeric = m.group(1) if m else img_id.replace("img", "")
                # Overwrite any placeholder created by the anchor handler
                self._views_by_id[img_numeric] = CameraView(
                    image_id=img_numeric,
                    image_url=lazy or f"/map/Cctv/{img_numeric}",
                    title=html.unescape(fs_title),
                    description=html.unescape(fs_desc),
                    refresh_rate_ms=refresh,
                )
        elif tag == "a":
            href = attr_dict.get("href") or ""
            m = re.search(r"/map/Cctv/(\d+)", href)
            if m:
                img_id = m.group(1)
                # Only add as placeholder if we haven't seen this image yet
                if img_id not in self._views_by_id:
                    self._views_by_id[img_id] = CameraView(
                        image_id=img_id,
                        image_url=href,
                    )

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong":
            self._in_strong = False
            if self._strong_text and not self.name:
                self.name = html.unescape(self._strong_text.strip())
            self._strong_text = ""

    def handle_data(self, data: str) -> None:
        if self._in_strong:
            self._strong_text += data


class TooltipTextParser(HTMLParser):
    """Generic tooltip parser that extracts visible text and key field values."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_tags = {"script", "style"}
        self._current_skip = 0
        self._texts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in self._skip_tags:
            self._current_skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags and self._current_skip > 0:
            self._current_skip -= 1

    def handle_data(self, data: str) -> None:
        if self._current_skip == 0:
            stripped = data.strip()
            if stripped:
                self._texts.append(stripped)

    @property
    def text(self) -> str:
        return " ".join(self._texts)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def _get(path: str, params: Optional[Dict[str, str]] = None,
         timeout: int = 15) -> bytes:
    """
    Perform a GET request against BASE_URL + path and return raw bytes.
    Raises urllib.error.URLError / urllib.error.HTTPError on failure.
    """
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    ctx = _make_ssl_ctx()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def _get_json(path: str, params: Optional[Dict[str, str]] = None,
              timeout: int = 15) -> Any:
    """GET + JSON parse."""
    raw = _get(path, params=params, timeout=timeout)
    return json.loads(raw.decode("utf-8", errors="replace"))


def _get_html(path: str, params: Optional[Dict[str, str]] = None,
              timeout: int = 15) -> str:
    """GET + decode as UTF-8 string."""
    raw = _get(path, params=params, timeout=timeout)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------

def get_layer_markers(layer: str, lang: str = "en") -> List[MapMarker]:
    """
    Fetch all map markers for the given layer (e.g., "Cameras", "Incidents").

    Returns a list of MapMarker objects with itemId, lat, lon, title.
    The endpoint is /map/mapIcons/{layer}?lang={lang}.

    Note: Without the ?lang=en parameter the endpoint returns a PNG image
    (a bug / fallback in the server).  Always pass lang=en.
    """
    data = _get_json(f"/map/mapIcons/{layer}", params={"lang": lang})
    markers: List[MapMarker] = []
    for item in data.get("item2", []):
        loc = item.get("location", [0.0, 0.0])
        markers.append(MapMarker(
            item_id=str(item.get("itemId", "")),
            lat=float(loc[0]) if len(loc) > 0 else 0.0,
            lon=float(loc[1]) if len(loc) > 1 else 0.0,
            title=item.get("title", ""),
            layer=layer,
        ))
    return markers


def get_layer_markers_nh(layer: str, lang: str = "en") -> List[MapMarker]:
    """
    Fetch markers for the given layer, filtered to New Hampshire geography.

    Uses the NH bounding box (lat 42.69–45.31, lon -72.55– -71.09).
    """
    all_markers = get_layer_markers(layer, lang=lang)
    return [
        m for m in all_markers
        if NH_LAT_MIN <= m.lat <= NH_LAT_MAX and NH_LON_MIN <= m.lon <= NH_LON_MAX
    ]


def get_camera_tooltip(site_id: str, lang: str = "en") -> Camera:
    """
    Fetch the tooltip HTML for a camera site and parse it into a Camera object.

    The tooltip reveals the camera's human-readable name and the list of camera
    view image IDs (used to fetch live JPEG snapshots via /map/Cctv/{imageId}).

    Each site_id corresponds to the itemId returned by get_layer_markers("Cameras").
    """
    html_src = _get_html(f"/tooltip/Cameras/{site_id}", params={"lang": lang})
    parser = CameraTooltipParser()
    parser.feed(html_src)
    return Camera(
        site_id=site_id,
        name=parser.name,
        views=parser.views,
    )


def get_tooltip_html(layer: str, item_id: str, lang: str = "en") -> str:
    """
    Fetch raw HTML tooltip for any layer+id combination.
    Useful for incident details, message sign content, etc.
    """
    return _get_html(f"/tooltip/{layer}/{item_id}", params={"lang": lang})


def get_tooltip_text(layer: str, item_id: str, lang: str = "en") -> str:
    """
    Fetch tooltip for any layer+id and return human-readable plain text.
    """
    src = get_tooltip_html(layer, item_id, lang=lang)
    p = TooltipTextParser()
    p.feed(src)
    return p.text


def get_camera_image(image_id: str, timeout: int = 15) -> bytes:
    """
    Download the live JPEG snapshot for a specific camera view.

    image_id is the integer portion from the image URL /map/Cctv/{image_id}.
    Returns raw JPEG bytes.  To display or save:
        data = get_camera_image("950")
        with open("cam.jpg", "wb") as f:
            f.write(data)
    """
    return _get(f"/map/Cctv/{image_id}", timeout=timeout)


def get_camera_image_url(image_id: str) -> str:
    """Return the absolute URL of a camera image (does not download it)."""
    return f"{BASE_URL}/map/Cctv/{image_id}"


def list_cameras(nh_only: bool = False) -> List[MapMarker]:
    """
    List all camera markers.  Each marker has site_id, lat, lon.

    Call get_camera_tooltip(marker.item_id) to get the full Camera object with
    name, image URLs, and view list.

    Parameters
    ----------
    nh_only : bool
        If True, filter to cameras within the New Hampshire bounding box.
    """
    if nh_only:
        return get_layer_markers_nh("Cameras")
    return get_layer_markers("Cameras")


def list_cameras_full(nh_only: bool = False,
                      max_cameras: Optional[int] = None) -> List[Camera]:
    """
    Fetch full Camera objects including names and image URLs.

    This calls the tooltip endpoint for each camera, so it is slower (one HTTP
    request per camera).  Use max_cameras to limit the result set during testing.

    Parameters
    ----------
    nh_only    : If True, restrict to NH geography.
    max_cameras: Limit to the first N cameras.
    """
    markers = list_cameras(nh_only=nh_only)
    if max_cameras is not None:
        markers = markers[:max_cameras]
    cameras: List[Camera] = []
    for m in markers:
        cam = get_camera_tooltip(m.item_id)
        cam.lat = m.lat
        cam.lon = m.lon
        cameras.append(cam)
    return cameras


def list_incidents(nh_only: bool = False) -> List[MapMarker]:
    """List all traffic incident markers."""
    if nh_only:
        return get_layer_markers_nh("Incidents")
    return get_layer_markers("Incidents")


def list_construction(nh_only: bool = False) -> List[MapMarker]:
    """List all active construction zone markers."""
    if nh_only:
        return get_layer_markers_nh("Construction")
    return get_layer_markers("Construction")


def list_message_signs(nh_only: bool = False) -> List[MapMarker]:
    """List all dynamic message sign (DMS/VMS) markers."""
    if nh_only:
        return get_layer_markers_nh("MessageSigns")
    return get_layer_markers("MessageSigns")


def list_weather_stations(nh_only: bool = False) -> List[MapMarker]:
    """List all roadside weather station markers."""
    if nh_only:
        return get_layer_markers_nh("WeatherStations")
    return get_layer_markers("WeatherStations")


def list_closures(nh_only: bool = False) -> List[MapMarker]:
    """List all road closure markers (incident + construction closures combined)."""
    incident_closures = get_layer_markers_nh("IncidentClosures") if nh_only \
        else get_layer_markers("IncidentClosures")
    const_closures = get_layer_markers_nh("ConstructionClosures") if nh_only \
        else get_layer_markers("ConstructionClosures")
    return incident_closures + const_closures


def get_unique_filter_values(type_id: str) -> Dict[str, Any]:
    """
    Fetch unique column filter values for list pages.
    Used to populate state/roadway/severity/subtype dropdowns.

    type_id examples: 'traffic', 'Cameras'

    Returns a dict like:
      { "state": ["Maine","New Hampshire","Vermont",...],
        "roadway": ["I-89","I-93",...],
        "severity": ["High","Low","Medium",...],
        ... }
    """
    return _get_json(f"/List/UniqueColumnValuesForEvents/{type_id}")


# ---------------------------------------------------------------------------
# Convenience: NH camera list with full detail
# ---------------------------------------------------------------------------

def get_nh_cameras() -> List[Camera]:
    """
    Convenience function: return all NH traffic cameras with full details.

    Fetches the camera marker list filtered to NH geography, then fetches the
    tooltip for each camera to get names and image URLs.

    This makes N+1 HTTP requests (1 for the marker list, 1 per camera).
    Total NH cameras is typically 100–150.
    """
    markers = list_cameras(nh_only=True)
    cameras: List[Camera] = []
    for m in markers:
        cam = get_camera_tooltip(m.item_id)
        cam.lat = m.lat
        cam.lon = m.lon
        cameras.append(cam)
    return cameras


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_cameras(args: argparse.Namespace) -> None:
    """List camera markers (quick view — no names or image URLs)."""
    markers = list_cameras(nh_only=args.nh)
    print(f"{'SiteID':<10} {'Lat':>10} {'Lon':>11}  Title")
    print("-" * 55)
    for m in markers:
        print(f"{m.item_id:<10} {m.lat:>10.6f} {m.lon:>11.6f}  {m.title}")
    print(f"\nTotal: {len(markers)}")


def _cmd_camera(args: argparse.Namespace) -> None:
    """Fetch full details for one camera site."""
    cam = get_camera_tooltip(args.site_id)
    print(f"Site ID  : {cam.site_id}")
    print(f"Name     : {cam.name}")
    print(f"Views    : {len(cam.views)}")
    for i, v in enumerate(cam.views, 1):
        print(f"  View {i}: imageId={v.image_id}  url={BASE_URL + v.image_url}")
        if v.title:
            print(f"           title={v.title}")
        print(f"           refresh={v.refresh_rate_ms} ms")


def _cmd_image(args: argparse.Namespace) -> None:
    """Download a camera snapshot."""
    img_data = get_camera_image(args.image_id)
    if args.save:
        with open(args.save, "wb") as f:
            f.write(img_data)
        print(f"Saved {len(img_data):,} bytes to {args.save}")
    else:
        print(f"Image size: {len(img_data):,} bytes (JPEG)")
        print(f"URL: {get_camera_image_url(args.image_id)}")
        print("(use --save FILE to write to disk)")


def _cmd_incidents(args: argparse.Namespace) -> None:
    """List all incident markers."""
    markers = list_incidents(nh_only=args.nh)
    print(f"{'ID':<10} {'Lat':>10} {'Lon':>11}")
    print("-" * 38)
    for m in markers:
        print(f"{m.item_id:<10} {m.lat:>10.6f} {m.lon:>11.6f}  {m.title}")
    print(f"\nTotal incidents: {len(markers)}")


def _cmd_signs(args: argparse.Namespace) -> None:
    """List all dynamic message sign markers."""
    markers = list_message_signs(nh_only=args.nh)
    print(f"{'SignID':<10} {'Lat':>10} {'Lon':>11}")
    print("-" * 38)
    for m in markers:
        print(f"{m.item_id:<10} {m.lat:>10.6f} {m.lon:>11.6f}  {m.title}")
    print(f"\nTotal signs: {len(markers)}")


def _cmd_layers(args: argparse.Namespace) -> None:
    """List all known map layer IDs with descriptions."""
    print(f"{'Layer ID':<35}  Description")
    print("-" * 75)
    for lid, desc in LAYER_IDS.items():
        print(f"{lid:<35}  {desc}")


def _cmd_tooltip(args: argparse.Namespace) -> None:
    """Fetch and print plain-text tooltip for any layer+id."""
    text = get_tooltip_text(args.layer, args.id)
    print(text)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="NewEngland511 / NHDOT traffic camera & incident client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # cameras
    p_cams = sub.add_parser("cameras", help="List all camera markers")
    p_cams.add_argument("--nh", action="store_true",
                        help="Filter to New Hampshire only")
    p_cams.set_defaults(func=_cmd_cameras)

    # camera
    p_cam = sub.add_parser("camera", help="Full detail for one camera site")
    p_cam.add_argument("site_id", help="Camera site ID (from cameras list)")
    p_cam.set_defaults(func=_cmd_camera)

    # image
    p_img = sub.add_parser("image", help="Download live camera snapshot")
    p_img.add_argument("image_id", help="Image ID (from camera detail)")
    p_img.add_argument("--save", metavar="FILE",
                       help="Save JPEG to this path instead of printing info")
    p_img.set_defaults(func=_cmd_image)

    # incidents
    p_inc = sub.add_parser("incidents", help="List traffic incident markers")
    p_inc.add_argument("--nh", action="store_true",
                       help="Filter to New Hampshire only")
    p_inc.set_defaults(func=_cmd_incidents)

    # signs
    p_signs = sub.add_parser("signs", help="List dynamic message signs")
    p_signs.add_argument("--nh", action="store_true",
                         help="Filter to New Hampshire only")
    p_signs.set_defaults(func=_cmd_signs)

    # layers
    p_layers = sub.add_parser("layers", help="List all available layer IDs")
    p_layers.set_defaults(func=_cmd_layers)

    # tooltip
    p_tip = sub.add_parser("tooltip",
                            help="Fetch plain-text tooltip for any layer+id")
    p_tip.add_argument("layer", help="Layer ID (e.g. Cameras, Incidents)")
    p_tip.add_argument("id", help="Item ID")
    p_tip.set_defaults(func=_cmd_tooltip)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
