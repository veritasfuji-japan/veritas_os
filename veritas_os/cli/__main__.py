"""Allow running verifier as ``python -m veritas_os.cli.verify_trustlog``."""

from veritas_os.cli.verify_trustlog import main
raise SystemExit(main())
