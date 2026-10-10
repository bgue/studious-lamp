"""Scaffolders behind ``tl new`` (brief 25.2): plan the files, then write them without overwriting.

A scaffolder is a pure function from validated names to a :class:`Plan` (relative paths and
text). :func:`write_plan` is the only code that touches the disk. Templates are plain text files
under ``templates/`` filled with :class:`string.Template`, so a template change is a text change.
"""
