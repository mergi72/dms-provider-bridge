"""Driver package compatibility layer.

Driver implementations currently live in ``dms_provider_bridge.providers`` for
backward compatibility. This package exposes the same module path for new
runtime code without moving files yet.
"""

from __future__ import annotations

import dms_provider_bridge.providers as _providers_package

__path__ = _providers_package.__path__

