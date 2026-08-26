"""Drone-show Recipe tools plus the sibling Business Pack Recipe package."""

import os
from pathlib import Path
from pkgutil import extend_path


__path__ = extend_path(__path__, __name__)
show_root = Path(__file__).resolve().parents[2]
business_pack_root = Path(
    os.environ.get(
        "HAKONIWA_BUSINESS_PACK_ROOT",
        str(show_root.parent / "hakoniwa-business-pack"),
    )
).expanduser().resolve()
business_pack_recipe = business_pack_root / "tools" / "recipe"
if business_pack_recipe.is_dir() and str(business_pack_recipe) not in __path__:
    __path__.append(str(business_pack_recipe))
