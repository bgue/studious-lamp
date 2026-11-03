"""The Throughline web client: server-rendered pages under ``/web``, mounted into the API app.

``tl_web.app.mount(app)`` is the one entry point (``tl_api.app.create_app`` calls it when the web
is switched on). Importing this package must not import ``textual``.
"""
