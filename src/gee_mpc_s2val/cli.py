"""Console entry points (see [project.scripts] in pyproject.toml)."""


def reconcile() -> None:
    from .reconcile import main
    main()


def e2() -> None:
    from .e2 import main
    main()


def impact() -> None:
    from .impact import main
    main()


def verify_demo() -> None:
    from .verify import main
    main()
