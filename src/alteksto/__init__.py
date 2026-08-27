"""The paper bundle format: what a bundle is, and whether one is valid.

This package is the contract and nothing else. It imports the standard
library only, so a consumer that reads and checks bundles installs what
the contract weighs. The code that produces bundles lives in `engines/`,
outside this package, and depends on it rather than the other way round.
"""

__version__ = "0.4.0"
