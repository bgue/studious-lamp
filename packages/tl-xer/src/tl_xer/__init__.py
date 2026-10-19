"""Reader for Primavera P6 XER files: tokenise, validate, type (brief section 9, M11; P1-I4).

``tl_xer.run.read_xer_file`` is the entry for callers; it runs ``tl_xer.process.process`` in the
resource envelope. Everything else is pure and bounded (``tl_xer.limits``).
"""
