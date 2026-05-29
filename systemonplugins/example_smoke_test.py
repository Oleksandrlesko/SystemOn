# Мінімальний тестовий плагін SystemOn.
# Має бути функція register_plugin(app_context).


def register_plugin(app_context):
    """Викликається один раз під час старту додатку."""
    main_window = app_context.get("main_window")
    print(
        f"[SystemOn plugin: example_smoke_test] OK — "
        f"main_window={type(main_window).__name__ if main_window else None!r}"
    )
